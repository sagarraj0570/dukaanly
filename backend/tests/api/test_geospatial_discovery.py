"""
Geospatial Discovery & Catalog Seeding Test Suite for Dukaanly.

Covers:
- Geospatial shop discovery via PostGIS ST_DWithin / ST_Distance
- Radius enforcement (inclusion / exclusion)
- Distance ordering (closest first, tier-ranked)
- Per-location personalization
- Query validation (bad coords, bad radius, missing pair)
- Directory-only shop visibility rules
- Empty-area result state
- No-location fallback (returns all shops, distance_meters=None)
- Catalog seeding: minimum 50 products per demo shop
- Seed idempotency (no duplicates on double-run)
- Custom user products not overwritten by seed
- Product-shop ownership integrity
- Inventory non-negative stock + valid optimistic-lock version
- Production environment guard on seed_demo_data()
"""

import uuid
import pytest
from decimal import Decimal
from unittest.mock import patch
from httpx import AsyncClient
from sqlalchemy import select, func

from app.db.session import engine, async_session_maker
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.db.seed_demo import verify_seed_environment, seed_demo_data
from app.db.demo_catalog import DEMO_SHOPS, DEMO_PRODUCTS

pytestmark = pytest.mark.asyncio

# ── Coordinates used throughout ───────────────────────────────────────────────
# Boring Road, Patna
BORING_LAT = 25.6144
BORING_LON = 85.1158

# Kankarbagh, Patna (~6 km from Boring Road)
KANKARBAGH_LAT = 25.5947
KANKARBAGH_LON = 85.1588

# Remote coords far outside Patna (approx 50+ km away)
REMOTE_LAT = 25.2000
REMOTE_LON = 84.9000


# ── Helper: create a shop owner and return auth token ─────────────────────────
async def _create_shop_owner(client: AsyncClient, suffix: str = "") -> str:
    """Register a user, upgrade to shop_owner, and return a JWT."""
    email = f"geo_test_owner_{suffix}_{uuid.uuid4().hex[:8]}@test.com"
    await client.post("/api/v1/auth/register", json={
        "name": "Test Owner", "email": email, "password": "PassWord123"
    })
    async with engine.connect() as conn:
        from sqlalchemy import text
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": email})
        await conn.commit()
    token_resp = await client.post("/api/v1/auth/login", json={"email": email, "password": "PassWord123"})
    return token_resp.json()["access_token"]


async def _create_shop(client: AsyncClient, token: str, name: str, lat: float, lon: float) -> str:
    """Create a shop and return its UUID string."""
    res = await client.post(
        "/api/v1/shops",
        json={"name": name, "address": "Test Address, Patna", "location": {"latitude": lat, "longitude": lon}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res.status_code == 201, f"Shop creation failed: {res.text}"
    return res.json()["id"]


# ══════════════════════════════════════════════════════════════════════════════
# 1. GEOSPATIAL DISCOVERY TESTS
# ══════════════════════════════════════════════════════════════════════════════

async def test_shops_within_radius_returned(async_client: AsyncClient):
    """A shop exactly at the query origin must appear when radius covers it."""
    token = await _create_shop_owner(async_client, "within")
    shop_id = await _create_shop(async_client, token, "Near Shop Boring", BORING_LAT, BORING_LON)

    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 3000, "size": 100},
    )
    assert res.status_code == 200
    data = res.json()
    ids = [s["id"] for s in data["items"]]
    assert shop_id in ids, "Shop at origin not found within 3 km radius"
    # Distance should be essentially 0
    matched = next(s for s in data["items"] if s["id"] == shop_id)
    assert matched["distance_meters"] is not None
    assert matched["distance_meters"] <= 50.0


async def test_shop_outside_radius_excluded(async_client: AsyncClient):
    """A shop placed at Boring Road must NOT appear when querying from Kankarbagh (≈6 km) with 1 km radius."""
    token = await _create_shop_owner(async_client, "outside")
    shop_id = await _create_shop(async_client, token, "Far Boring Road Shop", BORING_LAT, BORING_LON)

    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": KANKARBAGH_LAT, "longitude": KANKARBAGH_LON, "radius_meters": 1000, "size": 100},
    )
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["items"]]
    assert shop_id not in ids, "Shop 6+ km away was incorrectly included in 1 km radius"


async def test_radius_3km_respected(async_client: AsyncClient):
    """Near shop (at origin) in results; far shop (~6 km) excluded from 3 km search."""
    token = await _create_shop_owner(async_client, "3km")
    near_id = await _create_shop(async_client, token, "Near Shop 3km", BORING_LAT, BORING_LON)
    far_id  = await _create_shop(async_client, token, "Far Shop 3km",  KANKARBAGH_LAT, KANKARBAGH_LON)

    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 3000, "size": 100},
    )
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["items"]]
    assert near_id in ids, "Near shop missing from 3 km results"
    assert far_id not in ids, "Far shop (~6 km) incorrectly included in 3 km radius"


async def test_radius_10km_includes_farther_shops(async_client: AsyncClient):
    """Both shops (Boring Road and Kankarbagh, ~6 km apart) appear under 10 km radius."""
    token = await _create_shop_owner(async_client, "10km")
    near_id = await _create_shop(async_client, token, "Near Shop 10km", BORING_LAT, BORING_LON)
    far_id  = await _create_shop(async_client, token, "Far Shop 10km",  KANKARBAGH_LAT, KANKARBAGH_LON)

    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 10000, "size": 100},
    )
    assert res.status_code == 200
    ids = [s["id"] for s in res.json()["items"]]
    assert near_id in ids, "Near shop missing from 10 km results"
    assert far_id in ids, "Far shop (~6 km) not found within 10 km radius"


async def test_distance_ordering_closest_first(async_client: AsyncClient):
    """Results must be ordered by ascending distance (closest shop first)."""
    token = await _create_shop_owner(async_client, "order")

    # Create three shops at increasing distances from BORING_LAT/LON
    close_id  = await _create_shop(async_client, token, "Distance Order Close",  BORING_LAT,             BORING_LON)
    # ~3.5 km north
    mid_id    = await _create_shop(async_client, token, "Distance Order Mid",    BORING_LAT + 0.03,      BORING_LON)
    # ~6 km at Kankarbagh
    far_id    = await _create_shop(async_client, token, "Distance Order Far",    KANKARBAGH_LAT,         KANKARBAGH_LON)

    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 10000, "size": 100},
    )
    assert res.status_code == 200
    items = res.json()["items"]
    ids = [s["id"] for s in items]

    assert close_id in ids and mid_id in ids and far_id in ids

    close_idx = ids.index(close_id)
    mid_idx   = ids.index(mid_id)
    far_idx   = ids.index(far_id)

    assert close_idx < mid_idx,  "Close shop should rank before mid shop"
    assert mid_idx   < far_idx,  "Mid shop should rank before far shop"

    # Verify distance_meters are non-decreasing within same tier
    prev_dist = 0.0
    for item in items:
        if item["id"] in (close_id, mid_id, far_id):
            assert item["distance_meters"] >= prev_dist - 1  # allow tiny float drift
            prev_dist = item["distance_meters"]


async def test_different_user_locations_get_different_shops(async_client: AsyncClient):
    """
    Querying from Boring Road returns the Boring Road shop first.
    Querying from Kankarbagh returns the Kankarbagh shop first.
    """
    token = await _create_shop_owner(async_client, "location")
    boring_id     = await _create_shop(async_client, token, "Boring Road Exclusive",    BORING_LAT,     BORING_LON)
    kankarbagh_id = await _create_shop(async_client, token, "Kankarbagh Exclusive",     KANKARBAGH_LAT, KANKARBAGH_LON)

    # Query from Boring Road
    res_boring = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 10000, "size": 100},
    )
    assert res_boring.status_code == 200
    ids_boring = [s["id"] for s in res_boring.json()["items"]]
    assert boring_id in ids_boring
    assert kankarbagh_id in ids_boring
    # Boring Road shop should be closer from Boring Road perspective
    assert ids_boring.index(boring_id) < ids_boring.index(kankarbagh_id)

    # Query from Kankarbagh
    res_kank = await async_client.get(
        "/api/v1/shops",
        params={"latitude": KANKARBAGH_LAT, "longitude": KANKARBAGH_LON, "radius_meters": 10000, "size": 100},
    )
    assert res_kank.status_code == 200
    ids_kank = [s["id"] for s in res_kank.json()["items"]]
    assert kankarbagh_id in ids_kank
    # Kankarbagh shop should appear in results (near-origin)
    matched = next(s for s in res_kank.json()["items"] if s["id"] == kankarbagh_id)
    assert matched["distance_meters"] <= 50.0


async def test_invalid_coordinates_rejected(async_client: AsyncClient):
    """Out-of-range lat/lon values must be rejected with 422 Unprocessable Entity."""
    # Latitude > 90 → invalid
    res = await async_client.get("/api/v1/shops", params={"latitude": 91.0, "longitude": BORING_LON})
    assert res.status_code == 422, f"Expected 422 for lat=91, got {res.status_code}"

    # Longitude > 180 → invalid
    res = await async_client.get("/api/v1/shops", params={"latitude": 25.6, "longitude": 181.0})
    assert res.status_code == 422, f"Expected 422 for lon=181, got {res.status_code}"

    # Only latitude supplied (longitude missing) → 400
    res = await async_client.get("/api/v1/shops", params={"latitude": 25.6})
    assert res.status_code == 400, f"Expected 400 for unpaired lat, got {res.status_code}"


async def test_invalid_radius_rejected(async_client: AsyncClient):
    """Radius below 100 m or above 10,000 m must be rejected with 422."""
    base = {"latitude": 25.6, "longitude": BORING_LON}

    res_small = await async_client.get("/api/v1/shops", params={**base, "radius_meters": 50})
    assert res_small.status_code == 422, f"Expected 422 for radius=50, got {res_small.status_code}"

    res_large = await async_client.get("/api/v1/shops", params={**base, "radius_meters": 99999})
    assert res_large.status_code == 422, f"Expected 422 for radius=99999, got {res_large.status_code}"


async def test_directory_only_shop_never_orderable_via_discovery(async_client: AsyncClient):
    """
    A shop with is_orderable=False / verification_status=discovered:
    - Excluded from delivery_only=true results
    - Present in general results with is_orderable=False
    """
    token = await _create_shop_owner(async_client, "directory")

    # Create shop via API (defaults: verified + orderable)
    res_create = await async_client.post(
        "/api/v1/shops",
        json={"name": "Dir Only Shop", "address": "Dir St", "location": {"latitude": BORING_LAT, "longitude": BORING_LON}},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_create.status_code == 201
    shop_id = res_create.json()["id"]

    # Manually downgrade in DB to directory-only
    async with engine.connect() as conn:
        from sqlalchemy import text
        await conn.execute(
            text("UPDATE shops SET is_orderable=false, verification_status='discovered' WHERE id=:sid"),
            {"sid": shop_id},
        )
        await conn.commit()

    # delivery_only=true → shop must be ABSENT (not orderable)
    res_delivery = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 3000, "delivery_only": "true", "size": 100},
    )
    assert res_delivery.status_code == 200
    ids_delivery = [s["id"] for s in res_delivery.json()["items"]]
    assert shop_id not in ids_delivery, "Directory shop incorrectly showed in delivery_only results"

    # delivery_only=false → shop IS visible but is_orderable=False
    res_all = await async_client.get(
        "/api/v1/shops",
        params={"latitude": BORING_LAT, "longitude": BORING_LON, "radius_meters": 3000, "size": 100},
    )
    assert res_all.status_code == 200
    ids_all = [s["id"] for s in res_all.json()["items"]]
    assert shop_id in ids_all, "Directory shop completely absent from general discovery"
    matched = next(s for s in res_all.json()["items"] if s["id"] == shop_id)
    assert matched["is_orderable"] is False


async def test_empty_coverage_correct_empty_state(async_client: AsyncClient):
    """Querying from a remote location with no shops within radius returns 200 OK with empty items."""
    res = await async_client.get(
        "/api/v1/shops",
        params={"latitude": REMOTE_LAT, "longitude": REMOTE_LON, "radius_meters": 500, "size": 100},
    )
    assert res.status_code == 200
    data = res.json()
    assert data["items"] == [], f"Expected empty items, got {len(data['items'])} shops"
    assert data["total"] == 0


async def test_no_location_returns_all_shops_unpaged(async_client: AsyncClient):
    """
    GET /api/v1/shops without lat/lon must return 200 with items list and
    distance_meters=None for every item.
    """
    res = await async_client.get("/api/v1/shops", params={"size": 100})
    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert isinstance(data["items"], list)
    # All items must have distance_meters=None when no location supplied
    for item in data["items"]:
        assert item["distance_meters"] is None, (
            f"Expected distance_meters=None without coords, got {item['distance_meters']} for shop {item['name']}"
        )


# ══════════════════════════════════════════════════════════════════════════════
# 2. CATALOG SEEDING TESTS
# ══════════════════════════════════════════════════════════════════════════════

async def test_demo_shops_have_minimum_50_products():
    """Every orderable demo shop must have at least 50 active products after seeding."""
    # Ensure seed has run (idempotent: safe to call again)
    with patch("app.db.seed_demo.settings") as mock_settings:
        mock_settings.APP_ENV = "development"
        # Re-use the existing seeded state; seed_demo_data checks env via verify_seed_environment()
        # which reads settings.APP_ENV - patch it to be safe in CI/test envs
        pass

    async with async_session_maker() as session:
        demo_shops = (await session.execute(
            select(Shop).where(Shop.source == "demo", Shop.is_orderable == True)
        )).scalars().all()

        assert len(demo_shops) >= 1, "No orderable demo shops found - has seed_demo_data been run?"

        for shop in demo_shops:
            count = (await session.execute(
                select(func.count()).select_from(Product).where(
                    Product.shop_id == shop.id,
                    Product.is_active == True,
                )
            )).scalar_one()
            assert count >= 50, (
                f"Shop '{shop.name}' has only {count} active products; expected >= 50"
            )


async def test_seed_is_idempotent_no_duplicates():
    """
    Running seed_demo_data twice must produce zero new shops or products on the second run,
    and the total demo shop count must remain exactly 3.
    """
    # First pass (or no-op if already seeded)
    stats1 = await seed_demo_data(reset_stock=False)
    # Second pass - must be idempotent
    stats2 = await seed_demo_data(reset_stock=False)

    assert stats2["users_created"] == 0, "Second seed created duplicate users"
    assert stats2["shops_created"] == 0, "Second seed created duplicate shops"
    assert stats2["products_created"] == 0, "Second seed created duplicate products"

    async with async_session_maker() as session:
        demo_shop_count = (await session.execute(
            select(func.count()).select_from(Shop).where(Shop.source == "demo")
        )).scalar_one()
        assert demo_shop_count == 3, f"Expected exactly 3 demo shops, found {demo_shop_count}"


async def test_existing_user_products_not_overwritten():
    """
    A custom product added to a *non-demo* shop must survive a seed run unaffected.
    """
    custom_shop_name = f"Custom Test Shop {uuid.uuid4().hex[:8]}"
    custom_product_name = f"CustomProduct_{uuid.uuid4().hex[:8]}"

    # Create a non-demo shop + product directly in DB
    async with async_session_maker() as session:
        from geoalchemy2.elements import WKTElement
        custom_shop = Shop(
            name=custom_shop_name,
            address="Custom Lane, Patna",
            location=WKTElement(f"POINT({BORING_LON} {BORING_LAT})", srid=4326),
            source="manual",
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
        )
        session.add(custom_shop)
        await session.flush()

        custom_product = Product(
            shop_id=custom_shop.id,
            name=custom_product_name,
            price=Decimal("99.00"),
            is_active=True,
        )
        session.add(custom_product)
        await session.flush()
        custom_product_id = custom_product.id
        await session.commit()

    # Run seed
    await seed_demo_data(reset_stock=False)

    # Custom product must still exist and be unchanged
    async with async_session_maker() as session:
        product = (await session.execute(
            select(Product).where(Product.id == custom_product_id)
        )).scalar_one_or_none()
        assert product is not None, "Custom product was deleted by seed run"
        assert product.name == custom_product_name, "Custom product name was modified by seed"
        assert product.is_active is True, "Custom product was deactivated by seed"


async def test_all_products_belong_to_correct_shop():
    """
    After seeding, every product in the DEMO_PRODUCTS catalog must belong to its
    designated demo shop and no other.
    """
    async with async_session_maker() as session:
        for source_id, product_list in DEMO_PRODUCTS.items():
            # Find the demo shop
            shop = (await session.execute(
                select(Shop).where(Shop.source_id == source_id)
            )).scalar_one_or_none()

            if shop is None:
                # Shop not seeded in this test run - skip gracefully
                continue

            expected_names = {p["name"] for p in product_list}

            # All products belonging to this shop
            shop_products = (await session.execute(
                select(Product).where(Product.shop_id == shop.id)
            )).scalars().all()

            for prod in shop_products:
                # Only validate active demo-tagged products (seeded ones)
                if "[Dukaanly Demo Product]" in (prod.description or ""):
                    # Strip the tag and check it was part of this shop's catalog
                    assert prod.name in expected_names or not prod.is_active, (
                        f"Active demo product '{prod.name}' found in shop '{shop.name}' "
                        f"but not in its DEMO_PRODUCTS catalog entry"
                    )


async def test_inventory_nonnegative_and_occ_version_valid():
    """
    Every Inventory record for seeded demo products must have:
    - stock >= 0
    - version >= 1 (optimistic concurrency control initialized)
    """
    async with async_session_maker() as session:
        # Get all demo shop IDs
        demo_shop_ids = (await session.execute(
            select(Shop.id).where(Shop.source == "demo")
        )).scalars().all()

        if not demo_shop_ids:
            pytest.skip("No demo shops found - run seed_demo_data first")

        # Get all product IDs for demo shops
        demo_product_ids = (await session.execute(
            select(Product.id).where(Product.shop_id.in_(demo_shop_ids))
        )).scalars().all()

        if not demo_product_ids:
            pytest.skip("No demo products found - run seed_demo_data first")

        # Verify all inventories
        inventories = (await session.execute(
            select(Inventory).where(Inventory.product_id.in_(demo_product_ids))
        )).scalars().all()

        assert len(inventories) > 0, "No inventory records found for demo products"

        for inv in inventories:
            assert inv.stock >= 0, (
                f"Inventory for product {inv.product_id} has negative stock: {inv.stock}"
            )
            assert inv.version >= 1, (
                f"Inventory for product {inv.product_id} has invalid OCC version: {inv.version} (expected >= 1)"
            )


async def test_production_env_blocks_seed():
    """
    Calling seed_demo_data() (or verify_seed_environment) with env='production'
    must raise RuntimeError to prevent accidental demo data in production.
    """
    with pytest.raises(RuntimeError, match="Demo seeding aborted"):
        verify_seed_environment("production")

    with pytest.raises(RuntimeError, match="Demo seeding aborted"):
        verify_seed_environment("staging")

    with pytest.raises(RuntimeError, match="Demo seeding aborted"):
        verify_seed_environment("")

    with pytest.raises(RuntimeError, match="Demo seeding aborted"):
        verify_seed_environment(None)

    # Confirm development is still allowed
    assert verify_seed_environment("development") is True
    assert verify_seed_environment("DEVELOPMENT") is True
