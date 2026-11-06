"""
Idempotent Merchant Import Pipeline.
Coordinates candidate ingestion, category allowlisting, spatial coordinate checks,
conservative deduplication, batch tracking, and transactional persistence.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, cast
from geoalchemy2 import Geography

from app.models.shop import Shop, ShopVerificationStatus
from app.models.import_batch import ImportBatch
from app.models.cart import Cart
from app.models.order import Order
from app.services.importer.base import (
    BaseListingProvider,
    AreaConfig,
    NormalizedListing,
    ImportSummary,
)

logger = logging.getLogger(__name__)

DEFAULT_ALLOWED_CATEGORIES = [
    "grocery",
    "supermarket",
    "convenience",
    "chemist",
    "bakery",
    "dairy",
]

class MerchantImportService:
    """
    Orchestrates candidate listing ingestion into Dukaanly.
    Guarantees that public records remain non-orderable discovered listings
    linked to an identifiable import batch.
    """

    def __init__(
        self,
        db: AsyncSession,
        provider: BaseListingProvider,
        area: Optional[AreaConfig] = None,
        allowed_categories: Optional[List[str]] = None,
        dedup_distance_meters: float = 25.0,
    ):
        self.db = db
        self.provider = provider
        self.area = area or AreaConfig()
        self.allowed_categories = allowed_categories or DEFAULT_ALLOWED_CATEGORIES
        self.dedup_distance_meters = dedup_distance_meters

    async def run_import(
        self,
        dry_run: bool = False,
        max_records: int = 100
    ) -> ImportSummary:
        batch_id = uuid.uuid4()
        summary = ImportSummary(
            provider=self.provider.provider_name,
            area=self.area.name,
            dry_run=dry_run,
            batch_id=str(batch_id),
        )

        batch_record: Optional[ImportBatch] = None
        if not dry_run:
            batch_record = ImportBatch(
                id=batch_id,
                provider=self.provider.provider_name,
                source_dataset=f"{self.provider.provider_name} [{self.area.city}]",
                status="running",
                started_at=datetime.now(timezone.utc),
            )
            self.db.add(batch_record)
            await self.db.flush()

        try:
            candidates = await self.provider.fetch_candidate_listings(
                area=self.area,
                categories=self.allowed_categories,
                max_records=max_records,
            )
        except Exception as e:
            logger.error(f"Provider {self.provider.provider_name} failed during fetch: {e}")
            summary.errors.append(f"Fetch failure: {str(e)}")
            if batch_record:
                batch_record.status = "failed"
                batch_record.notes = f"Fetch failure: {str(e)}"
                await self.db.commit()
            return summary

        summary.total_fetched = len(candidates)
        seen_source_ids = set()
        normalized_allowed_cats = {c.lower() for c in self.allowed_categories}

        for listing in candidates:
            # 1. Geographic envelope and coordinate validation
            if not self.area.contains(listing.latitude, listing.longitude):
                summary.rejected_bounds += 1
                continue

            # 2. Category allowlist validation
            if normalized_allowed_cats and listing.category.lower() not in normalized_allowed_cats:
                summary.rejected_category += 1
                continue

            # 3. Stable provider ID uniqueness check
            if listing.source_id:
                if listing.source_id in seen_source_ids:
                    summary.duplicates_source += 1
                    continue

                existing_res = await self.db.execute(
                    select(Shop).where(
                        Shop.source == listing.source,
                        Shop.source_id == listing.source_id,
                        Shop.verification_status != ShopVerificationStatus.archived,
                    )
                )
                existing_shop = existing_res.scalar_one_or_none()
                if existing_shop:
                    summary.duplicates_source += 1
                    seen_source_ids.add(listing.source_id)
                    if not dry_run:
                        existing_shop.last_seen_at = datetime.now(timezone.utc)
                    continue

                seen_source_ids.add(listing.source_id)

            # 4. Spatial deduplication check using PostGIS geography ST_DWithin
            candidate_point = func.ST_SetSRID(
                func.ST_MakePoint(listing.longitude, listing.latitude),
                4326
            )
            candidate_geog = cast(candidate_point, Geography())
            shop_geog = cast(Shop.location, Geography())

            spatial_check = await self.db.execute(
                select(Shop).where(
                    Shop.verification_status != ShopVerificationStatus.archived,
                    Shop.is_active == True,
                    func.ST_DWithin(shop_geog, candidate_geog, self.dedup_distance_meters)
                )
            )
            near_shop = spatial_check.scalars().first()
            if near_shop and near_shop.name.lower().strip() == listing.name.lower().strip():
                summary.duplicates_spatial += 1
                continue

            # 5. Process valid candidate
            if dry_run:
                summary.accepted += 1
                summary.records.append({
                    "name": listing.name,
                    "category": listing.category,
                    "address": listing.address,
                    "latitude": listing.latitude,
                    "longitude": listing.longitude,
                    "source_id": listing.source_id,
                    "status": "dry_run_validated",
                })
            else:
                point_wkt = f"SRID=4326;POINT({listing.longitude} {listing.latitude})"
                new_shop = Shop(
                    id=uuid.uuid4(),
                    owner_id=None,
                    import_batch_id=batch_id,
                    name=listing.name,
                    description=f"Local {listing.category} store in {self.area.city}.",
                    address=listing.address,
                    phone=listing.phone,
                    opening_hours=listing.opening_hours,
                    location=point_wkt,
                    is_active=True,
                    is_orderable=False,
                    verification_status=ShopVerificationStatus.discovered,
                    source=listing.source,
                    source_id=listing.source_id,
                    source_attribution=listing.source_attribution,
                    original_url=listing.original_url,
                    imported_at=listing.imported_at,
                    last_seen_at=listing.last_seen_at,
                )
                self.db.add(new_shop)
                summary.accepted += 1
                summary.records.append({
                    "id": str(new_shop.id),
                    "name": listing.name,
                    "category": listing.category,
                    "source_id": listing.source_id,
                    "status": "persisted",
                })

        if not dry_run:
            if batch_record:
                batch_record.status = "completed"
                batch_record.completed_at = datetime.now(timezone.utc)
                batch_record.total_fetched = summary.total_fetched
                batch_record.accepted_count = summary.accepted
                batch_record.duplicate_count = summary.duplicates_source + summary.duplicates_spatial
                batch_record.rejected_count = summary.rejected_bounds + summary.rejected_category
            await self.db.commit()

        logger.info(
            f"Import complete ({'DRY-RUN' if dry_run else 'LIVE'}): Batch={summary.batch_id}, "
            f"Fetched={summary.total_fetched}, Accepted={summary.accepted}, "
            f"DupSource={summary.duplicates_source}, DupSpatial={summary.duplicates_spatial}, "
            f"RejBounds={summary.rejected_bounds}, RejCat={summary.rejected_category}"
        )

        return summary


async def rollback_import_batch(
    db: AsyncSession,
    batch_id: uuid.UUID,
    mode: str = "archive"  # "archive" (safe for production) or "delete" (clean test runs)
) -> Dict[str, Any]:
    """
    Concurrency-safe, audited rollback for a specific merchant import batch.
    
    1. Locks the ImportBatch and its associated Shop records using row-level locking.
    2. Validates that no shops have been claimed, verified, or referenced in commerce transactions.
    3. Either archives (sets verification_status='archived', is_active=False) or deletes candidate records.
    4. Updates the batch status to 'archived' or 'rolled_back' inside a single transaction.
    """
    if mode not in ("archive", "delete"):
        raise ValueError(f"Invalid rollback mode '{mode}'. Choose 'archive' or 'delete'.")

    # 1. Acquire batch record with row-level lock
    batch_stmt = select(ImportBatch).where(ImportBatch.id == batch_id).with_for_update()
    batch_res = await db.execute(batch_stmt)
    batch = batch_res.scalar_one_or_none()

    if not batch:
        raise ValueError(f"Import batch {batch_id} not found.")

    if batch.status in ("rolled_back", "archived"):
        raise ValueError(f"Batch {batch_id} has already been {batch.status}.")

    # 2. Acquire all shops in the batch with row-level lock
    shops_stmt = select(Shop).where(Shop.import_batch_id == batch_id).with_for_update()
    shops_res = await db.execute(shops_stmt)
    shops = shops_res.scalars().all()

    # 3. Concurrency check: Ensure no shops in this batch have been claimed or verified
    claimed_shops = [
        s for s in shops
        if s.owner_id is not None or s.verification_status == ShopVerificationStatus.verified
    ]
    if claimed_shops:
        raise ValueError(
            f"Concurrency conflict: {len(claimed_shops)} shop(s) in this batch have been claimed "
            f"or verified by a merchant (e.g. '{claimed_shops[0].name}'). Aborting batch rollback."
        )

    # 4. Check foreign-key dependencies (carts, orders)
    shop_ids = [s.id for s in shops]
    if shop_ids:
        cart_count = (await db.execute(
            select(func.count(Cart.id)).where(Cart.shop_id.in_(shop_ids))
        )).scalar_one()

        order_count = (await db.execute(
            select(func.count(Order.id)).where(Order.shop_id.in_(shop_ids))
        )).scalar_one()

        if cart_count > 0 or order_count > 0:
            if mode == "delete":
                raise ValueError(
                    f"Foreign key conflict: {cart_count} cart(s) and {order_count} order(s) reference "
                    f"shops in this batch. Cannot delete rows. Use mode='archive' instead."
                )

    # 5. Execute rollback action inside the transaction
    affected_count = len(shops)
    now_ts = datetime.now(timezone.utc)

    if mode == "archive":
        for s in shops:
            s.verification_status = ShopVerificationStatus.archived
            s.is_active = False
            s.is_orderable = False
        batch.status = "archived"
        batch.notes = f"Archived {affected_count} shops at {now_ts.isoformat()}"
    elif mode == "delete":
        for s in shops:
            await db.delete(s)
        batch.status = "rolled_back"
        batch.notes = f"Deleted {affected_count} shops at {now_ts.isoformat()}"

    await db.commit()

    return {
        "batch_id": str(batch_id),
        "provider": batch.provider,
        "mode": mode,
        "status": batch.status,
        "affected_shops": affected_count,
        "timestamp": now_ts.isoformat(),
    }
