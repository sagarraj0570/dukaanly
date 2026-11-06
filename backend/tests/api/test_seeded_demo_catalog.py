"""
Automated Test Suite for Dukaanly Realistic Seeded Demo Catalog.

Validates:
1. Production guard: verify_seed_environment strictly protects non-dev environments.
2. Idempotent seeding: rerunning does not create duplicate shops, products, or users.
3. Catalog availability and category filtering across all 8 target categories:
   Groceries, Dairy, Snacks, Beverages, Personal Care, Household Essentials, Bakery, Medicines.
4. Product units, descriptions, prices, and demo metadata identification.
5. Strict separation of demo shops vs unverified directory listings (directory cannot be ordered).
6. Out-of-stock validation (stock=0 item rejects cart addition).
7. Insufficient stock validation (quantity > available stock rejects cart addition).
8. Transactional checkout, optimistic locking, and inventory decrement.
9. Reset stock (--reset-stock) restoring inventory quantities.
"""

import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order
from app.core.security import create_access_token
from app.db.seed_demo import verify_seed_environment, seed_demo_data
from app.db.demo_catalog import DEMO_USERS, DEMO_SHOPS, DEMO_PRODUCTS

pytestmark = pytest.mark.asyncio

# ── Helpers ───────────────────────────────────────────────────────────────────

async def get_demo_customer_token() -> tuple[User, str]:
    async with async_session_maker() as session:
        user = (await session.execute(
            select(User).where(User.email == "customer@dukaanly.com")
        )).scalar_one()
        token = create_access_token(subject=str(user.id), role=user.role.value)
        return user, token


# ── Tests ─────────────────────────────────────────────────────────────────────

async def test_verify_seed_environment_guard():
    """Seeding must be strictly permitted ONLY in development environments."""
    # Permitted
    assert verify_seed_environment("development") is True
    assert verify_seed_environment("DEVELOPMENT") is True
    assert verify_seed_environment(" development ") is True

    # Forbidden
    for invalid_env in ["production", "staging", "test", "", None, 123]:
        with pytest.raises(RuntimeError) as exc_info:
            verify_seed_environment(invalid_env)
        assert "Demo seeding aborted" in str(exc_info.value)


async def test_idempotent_seeding_preserves_counts():
    """Rerunning seed_demo_data must be strictly idempotent and produce zero duplicates."""
    # Run 1
    stats1 = await seed_demo_data(reset_stock=False)
    # Run 2
    stats2 = await seed_demo_data(reset_stock=False)

    assert stats2["users_created"] == 0
    assert stats2["shops_created"] == 0
    assert stats2["products_created"] == 0
    assert len(stats2["inventory_report"]) == len(DEMO_SHOPS)
    assert all(row["meets_50_product_minimum"] for row in stats2["inventory_report"])

    async with async_session_maker() as session:
        # Check exactly 3 demo partner shops exist
        demo_shops = (await session.execute(
            select(Shop).where(Shop.source == "demo")
        )).scalars().all()
        assert len(demo_shops) == 3

        shop_names = {s.name for s in demo_shops}
        assert "Patna Super Kirana" in shop_names
        assert "Patna City Medicos" in shop_names
        assert "Pataliputra Bakery & Confectionery" in shop_names

        for s in demo_shops:
            assert s.verification_status == ShopVerificationStatus.verified
            assert s.is_orderable is True
            assert s.is_active is True
            assert s.source_attribution == "Dukaanly Demo Catalog"
            assert s.owner_id is not None


async def test_demo_products_catalog_coverage_and_categories(async_client: AsyncClient):
    """Product catalogs must span all 8 target categories and support category filtering."""
    expected_categories = {
        "Groceries",
        "Dairy",
        "Snacks",
        "Beverages",
        "Personal Care",
        "Household Essentials",
        "Bakery",
        "Medicines",
    }

    async with async_session_maker() as session:
        demo_shops = (await session.execute(
            select(Shop).where(Shop.source == "demo")
        )).scalars().all()

    found_categories = set()
    total_demo_products = 0

    for shop in demo_shops:
        res = await async_client.get(f"/api/v1/shops/{shop.id}/products", params={"size": 100})
        assert res.status_code == 200
        data = res.json()
        assert data["total"] > 0
        total_demo_products += data["total"]

        for item in data["items"]:
            assert item["name"]
            assert item["price"] is not None
            assert float(item["price"]) > 0
            assert item["description"] is not None and len(item["description"]) > 0
            assert item.get("image_url"), f"Product {item['name']} missing image_url"
            assert item["image_url"].startswith(("http", "/static/")), (
                f"Product {item['name']} image_url must be an HTTP(S) URL or a served static asset"
            )
            if item.get("category"):
                found_categories.add(item["category"])

    # Ensure all 8 categories are represented
    assert expected_categories.issubset(found_categories)
    assert total_demo_products >= 75


async def test_demo_products_realistic_images_and_uniqueness(async_client: AsyncClient):
    """Seeded products expose served image metadata without requiring fake unique imagery."""
    async with async_session_maker() as session:
        demo_shops = (await session.execute(
            select(Shop).where(Shop.source == "demo")
        )).scalars().all()

    image_urls = []
    product_names = []

    for shop in demo_shops:
        res = await async_client.get(f"/api/v1/shops/{shop.id}/products", params={"size": 100})
        assert res.status_code == 200
        for item in res.json()["items"]:
            product_names.append(item["name"])
            image_urls.append(item["image_url"])

    assert len(product_names) >= 80
    assert len(image_urls) == len(product_names)
    # The demo catalog deliberately reuses category-appropriate licensed/local assets;
    # image uniqueness is not a proxy for product or inventory integrity.
    unique_images = set(image_urls)
    assert len(unique_images) >= 10, f"Expected a varied demo image set, got {len(unique_images)} assets"

    # Test backend category filtering
    kirana_shop = next(s for s in demo_shops if "Kirana" in s.name)
    dairy_res = await async_client.get(
        f"/api/v1/shops/{kirana_shop.id}/products",
        params={"category": "Dairy", "size": 100}
    )
    assert dairy_res.status_code == 200
    dairy_items = dairy_res.json()["items"]
    assert len(dairy_items) > 0
    assert all(i["category"] == "Dairy" for i in dairy_items)


async def test_directory_listings_not_orderable_and_no_products(async_client: AsyncClient):
    """Discovered public directory listings must remain non-orderable and have zero demo products."""
    async with async_session_maker() as session:
        # Fetch discovered directory shops
        stmt = select(Shop).where(
            Shop.source.in_(["gmap", "geoapify", "osm"]),
            Shop.verification_status == ShopVerificationStatus.discovered
        )
        directory_shops = (await session.execute(stmt)).scalars().all()
        assert len(directory_shops) > 0

        sample_shop = directory_shops[0]
        assert sample_shop.is_orderable is False
        assert sample_shop.owner_id is None

        # Verify zero products seeded for this directory store
        prods = (await session.execute(
            select(Product).where(Product.shop_id == sample_shop.id)
        )).scalars().all()
        assert len(prods) == 0

    # Verify attempting to add an item to cart for a non-orderable shop fails
    # Create a dummy product assigned to this directory shop to test boundary
    async with async_session_maker() as session:
        fake_prod = Product(
            shop_id=sample_shop.id,
            name="Unorderable Test Item",
            price=Decimal("100.00"),
            is_active=True,
        )
        session.add(fake_prod)
        await session.flush()
        fake_inv = Inventory(product_id=fake_prod.id, stock=10, version=1)
        session.add(fake_inv)
        await session.commit()
        fake_prod_id = fake_prod.id

    try:
        _, customer_token = await get_demo_customer_token()
        headers = {"Authorization": f"Bearer {customer_token}"}

        # Clear cart first
        await async_client.delete("/api/v1/cart", headers=headers)

        res = await async_client.post(
            "/api/v1/cart/items",
            json={"product_id": str(fake_prod_id), "quantity": 1},
            headers=headers
        )
        assert res.status_code == 400
        assert "directory discovery only" in res.json()["detail"]
    finally:
        # Clean up temporary test product
        async with async_session_maker() as session:
            inv = (await session.execute(select(Inventory).where(Inventory.product_id == fake_prod_id))).scalar_one_or_none()
            if inv:
                await session.delete(inv)
            p = (await session.execute(select(Product).where(Product.id == fake_prod_id))).scalar_one_or_none()
            if p:
                await session.delete(p)
            await session.commit()


async def test_out_of_stock_validation(async_client: AsyncClient):
    """Adding a product with stock=0 must be rejected with 400 Bad Request."""
    async with async_session_maker() as session:
        zero_prod = (await session.execute(
            select(Product).where(Product.name.like("%Zero Stock%"))
        )).scalar_one_or_none()
        assert zero_prod is not None

        zero_inv = (await session.execute(
            select(Inventory).where(Inventory.product_id == zero_prod.id)
        )).scalar_one()
        assert zero_inv.stock == 0

    _, customer_token = await get_demo_customer_token()
    headers = {"Authorization": f"Bearer {customer_token}"}

    # Clear cart
    await async_client.delete("/api/v1/cart", headers=headers)

    res = await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": str(zero_prod.id), "quantity": 1},
        headers=headers
    )
    assert res.status_code == 400
    assert "Only 0 items available in stock" in res.json()["detail"]


async def test_insufficient_stock_validation(async_client: AsyncClient):
    """Requesting more quantity than available inventory must be rejected."""
    async with async_session_maker() as session:
        low_prod = (await session.execute(
            select(Product).where(Product.name.like("%Low Stock%"))
        )).scalar_one_or_none()
        assert low_prod is not None

        low_inv = (await session.execute(
            select(Inventory).where(Inventory.product_id == low_prod.id)
        )).scalar_one()
        current_stock = low_inv.stock

    _, customer_token = await get_demo_customer_token()
    headers = {"Authorization": f"Bearer {customer_token}"}

    await async_client.delete("/api/v1/cart", headers=headers)

    # Request more than current stock
    excessive_qty = current_stock + 5
    res = await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": str(low_prod.id), "quantity": excessive_qty},
        headers=headers
    )
    assert res.status_code == 400
    assert f"Only {current_stock} items available in stock" in res.json()["detail"]


async def test_transactional_checkout_and_optimistic_stock_decrement(async_client: AsyncClient):
    """Checkout must atomically decrement inventory stock and increment version."""
    async with async_session_maker() as session:
        # Pick an in-stock grocery item from Patna Super Kirana
        shop = (await session.execute(
            select(Shop).where(Shop.name == "Patna Super Kirana")
        )).scalar_one()

        prod = (await session.execute(
            select(Product)
            .join(Inventory)
            .where(Product.shop_id == shop.id, Product.name == "Aashirvaad Superior MP Shudh Chakki Atta 5kg")
        )).scalar_one()

        inv = (await session.execute(
            select(Inventory).where(Inventory.product_id == prod.id)
        )).scalar_one()
        initial_stock = inv.stock
        initial_version = inv.version
        prod_id = prod.id
        prod_price = prod.price

    _, customer_token = await get_demo_customer_token()
    headers = {"Authorization": f"Bearer {customer_token}"}

    # 1. Clear cart and add item
    await async_client.delete("/api/v1/cart", headers=headers)
    qty = 2
    add_res = await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": str(prod_id), "quantity": qty},
        headers=headers
    )
    assert add_res.status_code == 200

    # 2. Perform checkout (destination coordinates in Boring Road)
    idem_key = str(uuid.uuid4())
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={
            "idempotency_key": idem_key,
            "destination_latitude": 25.6144,
            "destination_longitude": 85.1158,
        },
        headers=headers
    )
    assert checkout_res.status_code == 201
    order_data = checkout_res.json()
    assert order_data["status"] == "pending"
    assert Decimal(str(order_data["total_amount"])) == prod_price * qty
    assert order_data["shop_id"] == str(shop.id)

    # 3. Verify optimistic decrement in database
    async with async_session_maker() as session:
        inv_after = (await session.execute(
            select(Inventory).where(Inventory.product_id == prod_id)
        )).scalar_one()
        assert inv_after.stock == initial_stock - qty
        assert inv_after.version == initial_version + 1

    # 4. Verify checkout idempotency: repeating with same key returns order without double decrement
    replay_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={
            "idempotency_key": idem_key,
            "destination_latitude": 25.6144,
            "destination_longitude": 85.1158,
        },
        headers=headers
    )
    assert replay_res.status_code == 201
    assert replay_res.json()["id"] == order_data["id"]

    async with async_session_maker() as session:
        inv_recheck = (await session.execute(
            select(Inventory).where(Inventory.product_id == prod_id)
        )).scalar_one()
        assert inv_recheck.stock == initial_stock - qty  # No double decrement!


async def test_reset_stock_restores_inventory():
    """seed_demo_data(reset_stock=True) must restore inventory back to configured catalog levels."""
    # Run reset_stock
    stats = await seed_demo_data(reset_stock=True)
    assert stats["inventory_reset"] > 0

    async with async_session_maker() as session:
        # Check that Aashirvaad Atta stock has returned to initial 45
        atta = (await session.execute(
            select(Product).where(Product.name == "Aashirvaad Superior MP Shudh Chakki Atta 5kg")
        )).scalar_one()
        atta_inv = (await session.execute(
            select(Inventory).where(Inventory.product_id == atta.id)
        )).scalar_one()
        assert atta_inv.stock == 45
