import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from geoalchemy2.elements import WKTElement
from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.user import User, UserRole
from app.core.security import create_access_token
from app.services.importer.curated_provider import CuratedDatasetProvider
from app.services.importer.pipeline import MerchantImportService
from app.services.importer.base import AreaConfig
from app.services.importer.osm import import_osm_listings

pytestmark = pytest.mark.asyncio

async def test_patna_candidate_listing_discovery(async_client: AsyncClient):
    """Candidate listings are discoverable via PostGIS coordinates but marked as non-orderable."""
    shop_id = uuid.uuid4()
    unique_source = f"osm:node:{uuid.uuid4().hex[:8]}"

    async with async_session_maker() as session:
        candidate_shop = Shop(
            id=shop_id,
            owner_id=None,
            name="Patna Test Candidate Kirana",
            description="A neighbourhood candidate listing from OSM.",
            address="Boring Canal Road, Patna, Bihar 800001",
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
            source="osm",
            source_id=unique_source,
            source_attribution="© OpenStreetMap contributors, ODbL",
        )
        session.add(candidate_shop)
        await session.commit()

    # Query nearby shops using Patna coordinates
    response = await async_client.get(
        "/api/v1/shops",
        params={
            "latitude": 25.6144,
            "longitude": 85.1158,
            "radius_meters": 3000,
            "size": 100,
        }
    )
    assert response.status_code == 200
    data = response.json()
    items = data["items"]
    
    found = next((s for s in items if s["id"] == str(shop_id)), None)
    assert found is not None
    assert found["name"] == "Patna Test Candidate Kirana"
    assert found["owner_id"] is None
    assert found["is_orderable"] is False
    assert found["verification_status"] == "discovered"
    assert found["is_delivery_eligible"] is False
    assert found["source"] == "osm"
    assert found["source_attribution"] == "© OpenStreetMap contributors, ODbL"

async def test_candidate_listing_delivery_eligibility(async_client: AsyncClient):
    """Candidate directory listing explicitly rejects delivery eligibility."""
    shop_id = uuid.uuid4()
    async with async_session_maker() as session:
        candidate_shop = Shop(
            id=shop_id,
            owner_id=None,
            name="Boring Road Pharmacy (Listing)",
            address="Boring Road, Patna",
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
        )
        session.add(candidate_shop)
        await session.commit()

    response = await async_client.get(
        f"/api/v1/shops/{shop_id}/delivery-eligibility",
        params={
            "latitude": 25.6144,
            "longitude": 85.1158,
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert data["is_delivery_eligible"] is False
    assert "directory listing" in data["message"].lower()

async def test_cart_item_guardrail_blocks_unverified_shop(async_client: AsyncClient):
    """Attempting to add a product from a non-orderable discovered shop must fail with HTTP 400."""
    shop_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    customer_id = uuid.uuid4()

    async with async_session_maker() as session:
        candidate_shop = Shop(
            id=shop_id,
            owner_id=None,
            name="Candidate Kirana",
            address="Patna",
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
        )
        session.add(candidate_shop)
        await session.flush()

        product = Product(
            id=prod_id,
            shop_id=shop_id,
            name="Wheat Flour 10kg",
            category="Groceries",
            price=Decimal("350.00"),
            is_active=True,
        )
        session.add(product)
        await session.flush()

        inventory = Inventory(product_id=prod_id, stock=50, version=1)
        session.add(inventory)

        customer = User(
            id=customer_id,
            name="Patna Customer",
            email=f"customer_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(customer)
        await session.commit()

    token = create_access_token(str(customer_id), "customer")

    response = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": str(prod_id), "quantity": 1}
    )
    assert response.status_code == 400
    assert "directory discovery only" in response.json()["detail"]

async def test_osm_importer_deduplication():
    """OSM importer respects duplicate source IDs and coordinate bounds."""
    test_node = f"test_{uuid.uuid4().hex[:6]}"
    test_listings = [
        {
            "source_id": f"osm:node:{test_node}",
            "name": "Test Importer Shop A",
            "address": "Boring Road, Patna",
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{test_node}",  # duplicate ID
            "name": "Test Importer Shop A Duplicate",
            "address": "Boring Road, Patna",
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{test_node}_oob",
            "name": "Test Out of Bounds Shop",
            "address": "New Delhi",
            "latitude": 28.6139,  # outside Patna bounds
            "longitude": 77.2090,
        },
    ]

    try:
        async with async_session_maker() as session:
            stats = await import_osm_listings(session, listings=test_listings)
            assert stats["imported"] == 1
            assert stats["skipped_duplicate_source"] == 1
            assert stats["skipped_bounds"] == 1
    finally:
        async with async_session_maker() as session:
            from sqlalchemy import delete
            await session.execute(
                delete(Shop).where(Shop.source == "osm", Shop.source_id == f"osm:node:{test_node}")
            )
            await session.commit()

async def test_dry_run_zero_database_writes():
    """Dry-run mode must validate candidate listings without creating rows in the database."""
    from app.services.importer.base import AreaConfig
    from app.services.importer.curated_provider import CuratedDatasetProvider
    from app.services.importer.pipeline import MerchantImportService
    from sqlalchemy import select, func

    mock_node = f"dry_run_{uuid.uuid4().hex[:6]}"
    custom_dataset = [
        {
            "source_id": f"osm:node:{mock_node}_1",
            "name": "Dry Run Test Shop 1",
            "address": "Boring Road, Patna",
            "category": "grocery",
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{mock_node}_2",
            "name": "Dry Run Test Shop 2",
            "address": "Boring Road, Patna",
            "category": "chemist",
            "latitude": 25.6150,
            "longitude": 85.1160,
        },
    ]

    async with async_session_maker() as session:
        count_before = (await session.execute(select(func.count(Shop.id)))).scalar_one()

        provider = CuratedDatasetProvider(dataset=custom_dataset)
        service = MerchantImportService(
            db=session,
            provider=provider,
            area=AreaConfig(),
            allowed_categories=["grocery", "chemist"],
        )

        summary = await service.run_import(dry_run=True, max_records=10)
        assert summary.dry_run is True
        assert summary.total_fetched == 2
        assert summary.accepted == 2

        count_after = (await session.execute(select(func.count(Shop.id)))).scalar_one()
        assert count_after == count_before  # ZERO database writes in dry-run mode

async def test_category_filtering_and_bounds_rejection():
    """Unallowlisted categories and coordinates outside target envelope are rejected."""
    from app.services.importer.base import AreaConfig
    from app.services.importer.curated_provider import CuratedDatasetProvider
    from app.services.importer.pipeline import MerchantImportService

    node = f"cat_test_{uuid.uuid4().hex[:6]}"
    dataset = [
        {
            "source_id": f"osm:node:{node}_grocery",
            "name": "Valid Grocery",
            "category": "grocery",
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{node}_car",
            "name": "Invalid Auto Repair",
            "category": "car_repair",  # not in allowed categories
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{node}_oob",
            "name": "Out of Bounds Chemist",
            "category": "chemist",
            "latitude": 12.9716,  # Bengaluru (outside Patna)
            "longitude": 77.5946,
        },
    ]

    async with async_session_maker() as session:
        provider = CuratedDatasetProvider(dataset=dataset)
        service = MerchantImportService(
            db=session,
            provider=provider,
            area=AreaConfig(),
            allowed_categories=["grocery", "chemist"],
        )

        summary = await service.run_import(dry_run=True)
        assert summary.total_fetched == 2  # Provider filtered out-of-bounds at fetch
        assert summary.accepted == 1
        assert summary.rejected_category == 1

async def test_radius_validation_and_10km_maximum(async_client: AsyncClient):
    """Radius validation strictly enforces 100m minimum and 10,000m (10km) maximum."""
    # 1. Radius exceeding 10km (15,000m) rejected with 422
    res_large = await async_client.get(
        "/api/v1/shops",
        params={"latitude": 25.6144, "longitude": 85.1158, "radius_meters": 15000}
    )
    assert res_large.status_code == 422

    # 2. Radius below 100m (50m) rejected with 422
    res_small = await async_client.get(
        "/api/v1/shops",
        params={"latitude": 25.6144, "longitude": 85.1158, "radius_meters": 50}
    )
    assert res_small.status_code == 422

    # 3. Maximum supported radius (10,000m / 10km) accepted
    res_valid_max = await async_client.get(
        "/api/v1/shops",
        params={"latitude": 25.6144, "longitude": 85.1158, "radius_meters": 10000}
    )
    assert res_valid_max.status_code == 200

async def test_checkout_rejection_for_unverified_candidate_shop(async_client: AsyncClient):
    """Checkout must fail with HTTP 400 if cart references an unverified candidate listing."""
    from app.services.order import checkout
    from fastapi import HTTPException

    shop_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    async with async_session_maker() as session:
        candidate_shop = Shop(
            id=shop_id,
            owner_id=None,
            name="Unverified Shop for Checkout",
            address="Patna",
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
        )
        session.add(candidate_shop)

        customer = User(
            id=cust_id,
            name="Test Customer Checkout",
            email=f"cust_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(customer)

        from app.models.cart import Cart, CartItem
        cart = Cart(customer_id=cust_id, shop_id=shop_id)
        session.add(cart)
        await session.flush()

        prod_id = uuid.uuid4()
        product = Product(
            id=prod_id,
            shop_id=shop_id,
            name="Rice 5kg",
            category="Groceries",
            price=Decimal("200.00"),
            is_active=True,
        )
        session.add(product)
        await session.flush()

        inv = Inventory(product_id=prod_id, stock=20, version=1)
        session.add(inv)

        cart_item = CartItem(cart_id=cart.id, product_id=prod_id, quantity=1)
        session.add(cart_item)
        await session.commit()

        # Direct checkout attempt
        with pytest.raises(HTTPException) as exc_info:
            await checkout(
                db=session,
                customer=customer,
                idempotency_key=str(uuid.uuid4()),
                destination_latitude=25.6144,
                destination_longitude=85.1158,
            )
        assert exc_info.value.status_code == 400
        assert "not activated for online commerce" in exc_info.value.detail.lower()


async def test_import_batch_tracking_and_safe_archival():
    """Verify that import runs record an ImportBatch and can be safely archived."""
    from app.services.importer.pipeline import rollback_import_batch
    from app.models.import_batch import ImportBatch

    dataset = [
        {
            "source_id": f"osm:node:{uuid.uuid4().hex[:8]}",
            "name": f"Batch Test Store 1 {uuid.uuid4().hex[:4]}",
            "category": "grocery",
            "latitude": 25.6144,
            "longitude": 85.1158,
        },
        {
            "source_id": f"osm:node:{uuid.uuid4().hex[:8]}",
            "name": f"Batch Test Store 2 {uuid.uuid4().hex[:4]}",
            "category": "chemist",
            "latitude": 25.6145,
            "longitude": 85.1159,
        },
    ]

    async with async_session_maker() as session:
        provider = CuratedDatasetProvider(dataset=dataset)
        service = MerchantImportService(
            db=session,
            provider=provider,
            area=AreaConfig(),
        )

        summary = await service.run_import(dry_run=False, max_records=2)
        assert summary.batch_id is not None
        batch_uuid = uuid.UUID(summary.batch_id)

        # Verify ImportBatch in DB
        batch = await session.get(ImportBatch, batch_uuid)
        assert batch is not None
        assert batch.status == "completed"
        assert batch.accepted_count == 2
        assert batch.total_fetched == 2

        # Verify shops linked to batch
        stmt = select(Shop).where(Shop.import_batch_id == batch_uuid)
        shops = (await session.execute(stmt)).scalars().all()
        assert len(shops) == 2
        assert all(s.verification_status == ShopVerificationStatus.discovered for s in shops)

        # Rollback via archival
        rollback_res = await rollback_import_batch(db=session, batch_id=batch_uuid, mode="archive")
        assert rollback_res["status"] == "archived"
        assert rollback_res["affected_shops"] == 2

        # Verify shops are now archived and inactive
        await session.refresh(batch)
        assert batch.status == "archived"

        for s in shops:
            await session.refresh(s)
            assert s.verification_status == ShopVerificationStatus.archived
            assert s.is_active is False


async def test_rollback_rejection_for_claimed_shop():
    """Verify that rollback aborts if any shop in the batch has been claimed/verified."""
    from app.services.importer.pipeline import rollback_import_batch
    from app.models.import_batch import ImportBatch

    dataset = [
        {
            "source_id": f"osm:node:{uuid.uuid4().hex[:8]}",
            "name": f"Claimed Protection Store {uuid.uuid4().hex[:4]}",
            "category": "grocery",
            "latitude": 25.6144,
            "longitude": 85.1158,
        }
    ]

    async with async_session_maker() as session:
        provider = CuratedDatasetProvider(dataset=dataset)
        service = MerchantImportService(db=session, provider=provider, area=AreaConfig())
        summary = await service.run_import(dry_run=False, max_records=1)
        batch_uuid = uuid.UUID(summary.batch_id)

        # Simulate an approved merchant claiming this shop
        stmt = select(Shop).where(Shop.import_batch_id == batch_uuid)
        shop = (await session.execute(stmt)).scalar_one()
        user = User(
            id=uuid.uuid4(),
            name="Claimed Merchant Owner",
            email=f"claimed_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.shop_owner,
            is_active=True,
        )
        session.add(user)
        await session.flush()
        shop.owner_id = user.id
        shop.verification_status = ShopVerificationStatus.verified
        await session.commit()

        # Attempt to roll back this batch must fail
        with pytest.raises(ValueError) as exc_info:
            await rollback_import_batch(db=session, batch_id=batch_uuid, mode="delete")

        assert "Concurrency conflict" in str(exc_info.value)
        assert "claimed" in str(exc_info.value)


async def test_fabricated_source_ids_rejected_by_curated_provider():
    """Fabricated/synthetic source IDs are rejected by CuratedDatasetProvider and never imported."""
    synthetic_items = [
        {
            "source_id": "osm:node:948201001",
            "name": "Fabricated Boring Road Kirana",
            "category": "grocery",
            "latitude": 25.6144,
            "longitude": 85.1158,
            "address": "Boring Road, Patna",
        },
        {
            "source_id": "osm:node:948202001",
            "name": "Fabricated Kankarbagh Store",
            "category": "grocery",
            "latitude": 25.6020,
            "longitude": 85.1530,
            "address": "Kankarbagh, Patna",
        },
        {
            "source_id": "osm:node:948203001",
            "name": "Fabricated Rajendra Nagar Store",
            "category": "grocery",
            "latitude": 25.6010,
            "longitude": 85.1610,
            "address": "Rajendra Nagar, Patna",
        },
        {
            "source_id": "osm:node:948204001",
            "name": "Fabricated Bailey Road Store",
            "category": "grocery",
            "latitude": 25.6110,
            "longitude": 85.0880,
            "address": "Bailey Road, Patna",
        },
    ]

    area = AreaConfig()
    provider = CuratedDatasetProvider(dataset=synthetic_items)
    for item in synthetic_items:
        normalized = provider.validate_and_normalize(item, area=area)
        assert normalized is None, f"Expected fabricated item {item['source_id']} to be rejected"

    # Default curated provider must contain ONLY authentic listings with NO synthetic IDs
    default_provider = CuratedDatasetProvider()
    listings = await default_provider.fetch_candidate_listings(
        area=area, categories=["grocery", "supermarket", "chemist", "bakery", "dairy"]
    )
    assert len(listings) > 0
    for listing in listings:
        assert not listing.source_id.startswith("osm:node:948201"), (
            f"Found legacy synthetic source ID {listing.source_id} in curated provider"
        )
        assert listing.source in ("gmap", "geoapify", "osm")
        assert listing.name
        assert listing.latitude is not None
        assert listing.longitude is not None


async def test_unverified_shop_cannot_receive_orders(async_client: AsyncClient):
    """Discovered/unverified shops cannot receive orders via cart, checkout, or direct creation."""
    from app.services.order import checkout
    from fastapi import HTTPException
    from app.models.cart import Cart, CartItem

    shop_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    prod_id = uuid.uuid4()

    async with async_session_maker() as session:
        # Create unverified discovered shop
        discovered_shop = Shop(
            id=shop_id,
            owner_id=None,
            name="Unverified Directory Listing Store",
            address="Patliputra, Patna",
            location=WKTElement("POINT(85.1100 25.6242)", srid=4326),
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
            source="geoapify",
            source_id=f"geoapify:place:{uuid.uuid4().hex}",
        )
        session.add(discovered_shop)

        # Create product under discovered shop
        product = Product(
            id=prod_id,
            shop_id=shop_id,
            name="Unorderable Cold Drink",
            category="Beverages",
            price=Decimal("45.00"),
            is_active=True,
        )
        session.add(product)

        # Customer
        customer = User(
            id=cust_id,
            name="Test Customer Unverified",
            email=f"cust_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(customer)
        await session.commit()

    token = create_access_token(str(cust_id), "customer")

    # 1. Attempting to add product to cart must be rejected with 400
    res_cart = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": str(prod_id), "quantity": 1},
    )
    assert res_cart.status_code == 400
    assert "directory discovery only" in res_cart.json()["detail"].lower()

    # 2. Attempting direct checkout on an unverified shop must raise HTTPException 400
    async with async_session_maker() as session:
        # Load or create customer's cart and link to unverified shop
        stmt_cart = select(Cart).where(Cart.customer_id == cust_id)
        cart = (await session.execute(stmt_cart)).scalar_one_or_none()
        if not cart:
            cart = Cart(customer_id=cust_id, shop_id=shop_id)
            session.add(cart)
            await session.flush()
        else:
            cart.shop_id = shop_id

        forced_item = CartItem(cart_id=cart.id, product_id=prod_id, quantity=1)
        session.add(forced_item)
        await session.commit()

        loaded_cust = await session.get(User, cust_id)
        with pytest.raises(HTTPException) as exc_info:
            await checkout(
                db=session,
                customer=loaded_cust,
                idempotency_key=str(uuid.uuid4()),
                destination_latitude=25.6242,
                destination_longitude=85.1100,
            )
        assert exc_info.value.status_code == 400
        assert "not activated for online commerce" in exc_info.value.detail.lower()


async def test_verified_partner_inventory_unaffected(async_client: AsyncClient):
    """Verified partner shops remain orderable, stock tracks via optimistic locking, unaffected by directory listings."""
    from app.services.order import checkout

    partner_owner_id = uuid.uuid4()
    partner_shop_id = uuid.uuid4()
    prod_id = uuid.uuid4()
    cust_id = uuid.uuid4()

    async with async_session_maker() as session:
        # 1. Create verified partner shop with actual owner
        owner = User(
            id=partner_owner_id,
            name="Patna Verified Partner Owner",
            email=f"partner_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.shop_owner,
            is_active=True,
        )
        session.add(owner)
        await session.flush()

        shop = Shop(
            id=partner_shop_id,
            owner_id=partner_owner_id,
            name="Patna Verified Partner Store",
            description="Verified partner store with active inventory",
            address="Boring Road, Patna",
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
        )
        session.add(shop)
        await session.flush()

        # 2. Add product with initial stock 10, version 1
        product = Product(
            id=prod_id,
            shop_id=partner_shop_id,
            name="Sudha Special Milk 1L",
            category="Dairy",
            price=Decimal("60.00"),
            is_active=True,
        )
        session.add(product)
        await session.flush()

        inventory = Inventory(product_id=prod_id, stock=10, version=1)
        session.add(inventory)

        # 3. Customer
        customer = User(
            id=cust_id,
            name="Patna Regular Customer",
            email=f"customer_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="hash123",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(customer)
        await session.commit()

    token = create_access_token(str(cust_id), "customer")

    # 4. Add to cart succeeds
    res_cart = await async_client.post(
        "/api/v1/cart/items",
        headers={"Authorization": f"Bearer {token}"},
        json={"product_id": str(prod_id), "quantity": 2},
    )
    assert res_cart.status_code == 200

    # 5. Checkout succeeds and decrements inventory with optimistic lock update
    async with async_session_maker() as session:
        loaded_cust = await session.get(User, cust_id)
        order = await checkout(
            db=session,
            customer=loaded_cust,
            idempotency_key=str(uuid.uuid4()),
            destination_latitude=25.6150,
            destination_longitude=85.1160,
        )
        assert order is not None
        assert order.status == "pending"

        # Verify inventory stock was reduced from 10 to 8, version incremented from 1 to 2
        stmt_inv = select(Inventory).where(Inventory.product_id == prod_id)
        inv = (await session.execute(stmt_inv)).scalar_one()
        assert inv.stock == 8
        assert inv.version == 2


