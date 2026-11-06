"""
Safe Cleanup Script for Legacy Synthetic Directory Listings in Dukaanly.

Audits and cleans legacy synthetic shops generated with mock IDs (osm:node:94820xxxxx).
Safety guarantees:
1. Dry-run by default.
2. Checks that shop has no owner (owner_id IS NULL).
3. Checks that shop has no associated orders.
4. Requires explicit confirmation before any destructive changes.
"""

import argparse
import asyncio
import logging
import sys
from sqlalchemy import select, delete, func
from app.core.config import settings
from app.db.session import async_session_maker
from app.models.shop import Shop, ShopVerificationStatus
from app.models.order import Order
from app.models.cart import CartItem
from app.models.product import Product
from app.services.importer.curated_provider import (
    CuratedDatasetProvider,
    FABRICATED_SOURCE_ID_PATTERN,
)
from app.services.importer.pipeline import MerchantImportService
from app.services.importer.base import AreaConfig

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("cleanup")


async def perform_cleanup(action: str, confirm: bool, import_verified: bool):
    logger.info("=== DUKAANLY TARGET ENVIRONMENT AUDIT ===")
    logger.info("Environment: APP_ENV=%s", settings.APP_ENV)
    logger.info("Database: %s@%s:%s/%s", settings.POSTGRES_USER, settings.POSTGRES_HOST, settings.POSTGRES_PORT, settings.POSTGRES_DB)

    if settings.APP_ENV not in ("development", "test"):
        logger.error("DANGER: Current APP_ENV is '%s'! Automated cleanup is strictly prohibited in staging/production without manual intervention.", settings.APP_ENV)
        return

    async with async_session_maker() as session:
        # Audit all shops in DB
        total_shops = (await session.execute(select(func.count(Shop.id)))).scalar_one()
        partner_shops = (await session.execute(
            select(Shop).where(Shop.verification_status == ShopVerificationStatus.verified)
        )).scalars().all()

        logger.info("Total shops in database: %d", total_shops)
        logger.info("Verified partner shops protected: %d", len(partner_shops))
        for p in partner_shops:
            logger.info("  [PROTECTED PARTNER] %s (ID: %s, is_orderable=%s)", p.name, p.id, p.is_orderable)

        # Select synthetic listings matching pattern
        stmt = select(Shop).where(Shop.source_id.like("osm:node:94820%"))
        shops = (await session.execute(stmt)).scalars().all()

        logger.info("Found %d legacy synthetic candidate shops targeted for cleanup.", len(shops))
        if not shops:
            logger.info("No synthetic shops found. Database is clean.")
            return

        # Pre-flight safety check
        shops_to_archive = []
        shops_to_delete = []

        for s in shops:
            # Check owner
            if s.owner_id is not None:
                logger.error("Shop '%s' (ID: %s) has an owner assigned! Aborting cleanup.", s.name, s.id)
                return

            # Check orders
            order_count = (
                await session.execute(select(func.count(Order.id)).where(Order.shop_id == s.id))
            ).scalar_one()

            if order_count > 0:
                logger.info(
                    "Shop '%s' (ID: %s) has %d existing order(s). Will be ARCHIVED to preserve referential integrity.",
                    s.name,
                    s.id,
                    order_count,
                )
                shops_to_archive.append(s)
            else:
                shops_to_delete.append(s)

        logger.info(
            "Audit complete: %d shops to archive (have orders), %d shops eligible for deletion/archival.",
            len(shops_to_archive),
            len(shops_to_delete),
        )

        if action == "dry-run":
            logger.info("--- DRY RUN REPORT ---")
            for s in shops_to_archive:
                logger.info("Would ARCHIVE (preserves FK/order integrity): '%s' (source_id: %s)", s.name, s.source_id)
            for s in shops_to_delete:
                logger.info("Would CLEAN: '%s' (source_id: %s)", s.name, s.source_id)
            logger.info("Run with --archive or --delete with --confirm to execute.")
            return

        if not confirm:
            logger.error("Action '%s' requires --confirm flag to execute. Aborting.", action)
            return

        if action == "archive":
            all_to_archive = shops_to_archive + shops_to_delete
            for s in all_to_archive:
                s.verification_status = ShopVerificationStatus.archived
                s.is_active = False
            await session.commit()
            logger.info("Successfully archived all %d synthetic shops.", len(all_to_archive))

        elif action == "delete":
            # Archive the ones with orders to protect referential integrity
            for s in shops_to_archive:
                s.verification_status = ShopVerificationStatus.archived
                s.is_active = False

            # Delete the ones with no orders
            if shops_to_delete:
                delete_ids = [s.id for s in shops_to_delete]
                prod_ids_stmt = select(Product.id).where(Product.shop_id.in_(delete_ids))
                prod_ids = (await session.execute(prod_ids_stmt)).scalars().all()
                if prod_ids:
                    await session.execute(delete(CartItem).where(CartItem.product_id.in_(prod_ids)))
                    await session.execute(delete(Product).where(Product.id.in_(prod_ids)))

                await session.execute(delete(Shop).where(Shop.id.in_(delete_ids)))

            await session.commit()
            logger.info(
                "Cleanup complete: %d shops deleted, %d shops archived (preserved for order history).",
                len(shops_to_delete),
                len(shops_to_archive),
            )

        if import_verified:
            logger.info("Importing verified Patna regional extract...")
            provider = CuratedDatasetProvider()
            pipeline = MerchantImportService(
                db=session,
                provider=provider,
                area=AreaConfig(),
                allowed_categories=["grocery", "supermarket", "chemist", "bakery", "dairy", "department_store"],
            )
            summary = await pipeline.run_import(dry_run=False)
            logger.info("Verified import complete: %d listings imported.", summary.accepted)


def main():
    parser = argparse.ArgumentParser(description="Cleanup legacy synthetic directory listings.")
    parser.add_argument(
        "--action",
        choices=["dry-run", "archive", "delete"],
        default="dry-run",
        help="Action to perform (default: dry-run)",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Explicit confirmation required for archive or delete",
    )
    parser.add_argument(
        "--import-verified",
        action="store_true",
        help="Immediately import authentic Patna listings after cleanup",
    )

    args = parser.parse_args()
    asyncio.run(perform_cleanup(action=args.action, confirm=args.confirm, import_verified=args.import_verified))


if __name__ == "__main__":
    main()
