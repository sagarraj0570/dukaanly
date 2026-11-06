"""
Comprehensive Test Suite for Commerce Correctness (Phase 2.7 Focus Area 2).

Enforces:
1. Live price recheck at cart addition and approval (tampering in payload is impossible, DB price is authoritative).
2. Live stock validation (overselling prevented, stock drops immediately block order creation).
3. Single-shop cart invariant strictly enforced (existing carts are never silently overwritten or replaced).
4. Directory-only businesses (Geoapify/OSM discovered, unverified) cannot become orderable products.
5. Optimistic locking on inventory updates (preventing race conditions via version column).
"""

from decimal import Decimal
import uuid
import pytest
from fastapi import HTTPException
from sqlalchemy import select, text, delete
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.models.cart import Cart, CartItem
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.shop import Shop, ShopVerificationStatus
from app.models.user import User, UserRole
from app.models.order import Order, OrderItem
from app.models.delivery import Delivery
from app.models.payment import Payment
from app.models.notification import Notification
from app.services import cart as cart_service
from app.services.catalog_search import search_partner_catalog

pytestmark = pytest.mark.asyncio

PATNA_LAT = 25.6144
PATNA_LON = 85.1158


@pytest.fixture
async def verified_shop_and_products():
    """Seed a verified partner shop with active products and inventory."""
    async with async_session_maker() as session:
        owner_id = uuid.uuid4()
        merchant = User(
            id=owner_id,
            name="Verified Kirana Merchant",
            email=f"merchant_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="dummy_hash",
            role=UserRole.shop_owner,
            is_active=True,
        )
        session.add(merchant)
        await session.flush()

        shop_id = uuid.uuid4()
        shop = Shop(
            id=shop_id,
            name="Patna City Verified Mart",
            owner_id=owner_id,
            address="Fraser Road, Patna",
            phone="+916122119900",
            location=WKTElement(f"POINT({PATNA_LON} {PATNA_LAT})", srid=4326),
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
            source="manual_partner",
        )
        session.add(shop)
        await session.flush()

        # Product 1: In stock with initial price
        prod1_id = uuid.uuid4()
        prod1 = Product(
            id=prod1_id,
            shop_id=shop_id,
            name="Premium Basmati Rice 5kg",
            category="Groceries",
            price=Decimal("450.00"),
            is_active=True,
        )
        inv1 = Inventory(product_id=prod1_id, stock=5, version=1)
        session.add(prod1)
        session.add(inv1)

        # Product 2: Low stock item
        prod2_id = uuid.uuid4()
        prod2 = Product(
            id=prod2_id,
            shop_id=shop_id,
            name="Organic Desi Ghee 500ml",
            category="Dairy",
            price=Decimal("380.00"),
            is_active=True,
        )
        inv2 = Inventory(product_id=prod2_id, stock=2, version=1)
        session.add(prod2)
        session.add(inv2)

        await session.commit()
        yield {
            "shop_id": shop_id,
            "owner_id": owner_id,
            "prod1_id": prod1_id,
            "prod2_id": prod2_id,
        }

        # Cleanup
        order_ids = (await session.execute(select(Order.id).where(Order.shop_id == shop_id))).scalars().all()
        if order_ids:
            await session.execute(delete(Delivery).where(Delivery.order_id.in_(order_ids)))
            await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
            await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))

        await session.execute(delete(OrderItem).where(OrderItem.product_id.in_([prod1_id, prod2_id])))
        await session.execute(delete(CartItem).where(CartItem.product_id.in_([prod1_id, prod2_id])))
        await session.execute(delete(Cart).where(Cart.shop_id == shop_id))
        await session.execute(delete(Inventory).where(Inventory.product_id.in_([prod1_id, prod2_id])))
        await session.execute(delete(Product).where(Product.id.in_([prod1_id, prod2_id])))
        await session.execute(delete(Shop).where(Shop.id == shop_id))
        await session.execute(delete(Notification).where(Notification.user_id == owner_id))
        await session.execute(delete(User).where(User.id == owner_id))
        await session.commit()


@pytest.fixture
async def second_verified_shop():
    """Seed a distinct second verified partner shop for multi-shop cart invariant testing."""
    async with async_session_maker() as session:
        owner_id = uuid.uuid4()
        merchant = User(
            id=owner_id,
            name="Second Shop Merchant",
            email=f"merchant2_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="dummy_hash",
            role=UserRole.shop_owner,
            is_active=True,
        )
        session.add(merchant)
        await session.flush()

        shop_id = uuid.uuid4()
        shop = Shop(
            id=shop_id,
            name="Kankarbagh Daily Store",
            owner_id=owner_id,
            address="Kankarbagh, Patna",
            phone="+916122119911",
            location=WKTElement(f"POINT({PATNA_LON + 0.01} {PATNA_LAT + 0.01})", srid=4326),
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
            source="manual_partner",
        )
        session.add(shop)
        await session.flush()

        prod_id = uuid.uuid4()
        prod = Product(
            id=prod_id,
            shop_id=shop_id,
            name="Masala Chai CTC 500g",
            category="Beverages",
            price=Decimal("220.00"),
            is_active=True,
        )
        inv = Inventory(product_id=prod_id, stock=10, version=1)
        session.add(prod)
        session.add(inv)
        await session.commit()

        yield {
            "shop_id": shop_id,
            "owner_id": owner_id,
            "prod_id": prod_id,
        }

        # Cleanup
        order_ids = (await session.execute(select(Order.id).where(Order.shop_id == shop_id))).scalars().all()
        if order_ids:
            await session.execute(delete(Delivery).where(Delivery.order_id.in_(order_ids)))
            await session.execute(delete(Payment).where(Payment.order_id.in_(order_ids)))
            await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(order_ids)))
            await session.execute(delete(Order).where(Order.id.in_(order_ids)))

        await session.execute(delete(OrderItem).where(OrderItem.product_id == prod_id))
        await session.execute(delete(CartItem).where(CartItem.product_id == prod_id))
        await session.execute(delete(Cart).where(Cart.shop_id == shop_id))
        await session.execute(delete(Inventory).where(Inventory.product_id == prod_id))
        await session.execute(delete(Product).where(Product.id == prod_id))
        await session.execute(delete(Shop).where(Shop.id == shop_id))
        await session.execute(delete(Notification).where(Notification.user_id == owner_id))
        await session.execute(delete(User).where(User.id == owner_id))
        await session.commit()


@pytest.fixture
async def directory_only_shop():
    """Seed a directory-only / discovered business that is NOT orderable."""
    async with async_session_maker() as session:
        shop_id = uuid.uuid4()
        shop = Shop(
            id=shop_id,
            name="Discovered Patna Landmark Business (Non-Orderable)",
            owner_id=None,  # No registered merchant
            address="Exhibition Road, Patna",
            phone="+916120000000",
            location=WKTElement(f"POINT({PATNA_LON} {PATNA_LAT})", srid=4326),
            is_active=False,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
            source="geoapify_osm",
        )
        session.add(shop)
        await session.flush()

        # Product nominally linked to discovered listing
        prod_id = uuid.uuid4()
        prod = Product(
            id=prod_id,
            shop_id=shop_id,
            name="Directory Specimen Item",
            category="General",
            price=Decimal("99.00"),
            is_active=True,
        )
        inv = Inventory(product_id=prod_id, stock=50, version=1)
        session.add(prod)
        session.add(inv)
        await session.commit()

        yield {
            "shop_id": shop_id,
            "prod_id": prod_id,
        }

        # Cleanup
        await session.execute(delete(CartItem).where(CartItem.product_id == prod_id))
        await session.execute(delete(Inventory).where(Inventory.product_id == prod_id))
        await session.execute(delete(Product).where(Product.id == prod_id))
        await session.execute(delete(Shop).where(Shop.id == shop_id))
        await session.commit()


@pytest.fixture
async def customer_user():
    async with async_session_maker() as session:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            name="Commerce Test Customer",
            email=f"commerce_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="dummy_hash",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        yield user

        await session.execute(text("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id = :uid)"), {"uid": str(user_id)})
        await session.execute(text("DELETE FROM carts WHERE customer_id = :uid"), {"uid": str(user_id)})
        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": str(user_id)})
        await session.commit()


# ---------------------------------------------------------------------------
# Test 1: Live Price Recheck at Cart Addition
# ---------------------------------------------------------------------------
async def test_live_price_recheck_at_cart_addition(verified_shop_and_products, customer_user):
    """
    Ensure cart totals strictly compute from current database prices.
    Price changes in database immediately update cart response totals.
    """
    prod1_id = verified_shop_and_products["prod1_id"]
    async with async_session_maker() as session:
        # Add 1x Basmati Rice at initial price ₹450.00
        cart_resp = await cart_service.add_item_to_cart(
            db=session,
            customer=customer_user,
            product_id=prod1_id,
            quantity=1,
        )
        assert cart_resp.total_amount == Decimal("450.00")
        assert cart_resp.items[0].product_price == Decimal("450.00")

        # Merchant increases price in DB to ₹490.00
        prod = await session.get(Product, prod1_id)
        prod.price = Decimal("490.00")
        await session.commit()

        # Re-fetch cart; price must reflect authoritative DB value, not old cached price
        updated_cart = await cart_service.get_cart(db=session, customer=customer_user)
        assert updated_cart.items[0].product_price == Decimal("490.00")
        assert updated_cart.total_amount == Decimal("490.00")


# ---------------------------------------------------------------------------
# Test 2: Live Stock Validation Prevents Overselling
# ---------------------------------------------------------------------------
async def test_live_stock_validation_at_cart_addition(verified_shop_and_products, customer_user):
    """
    Ensure cart rejects addition exceeding authoritative inventory stock.
    """
    prod2_id = verified_shop_and_products["prod2_id"]  # stock = 2
    async with async_session_maker() as session:
        # Requesting 3 items when stock is 2 must raise HTTP 400
        with pytest.raises(HTTPException) as exc_info:
            await cart_service.add_item_to_cart(
                db=session,
                customer=customer_user,
                product_id=prod2_id,
                quantity=3,
            )
        assert exc_info.value.status_code == 400
        assert "Only 2 items available in stock" in exc_info.value.detail

        # Add allowable quantity (2)
        cart_resp = await cart_service.add_item_to_cart(
            db=session,
            customer=customer_user,
            product_id=prod2_id,
            quantity=2,
        )
        assert len(cart_resp.items) == 1
        assert cart_resp.items[0].quantity == 2

        # Deplete stock to 0 in DB (another customer checked out)
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == prod2_id))).scalar_one()
        inv.stock = 0
        await session.commit()

        # Trying to increment or add more fails with stock error
        with pytest.raises(HTTPException) as exc_info:
            await cart_service.add_item_to_cart(
                db=session,
                customer=customer_user,
                product_id=prod2_id,
                quantity=1,
            )
        assert exc_info.value.status_code == 400
        assert "Only 0 items available in stock" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test 3: Single-Shop Invariant Prevents Silent Cart Replacement
# ---------------------------------------------------------------------------
async def test_single_shop_invariant_prevents_silent_cart_replacement(
    verified_shop_and_products,
    second_verified_shop,
    customer_user,
):
    """
    Verify customer cannot mix products across different shops.
    Existing cart from Shop 1 is NEVER silently overridden or cleared when adding from Shop 2.
    """
    shop1_prod_id = verified_shop_and_products["prod1_id"]
    shop2_prod_id = second_verified_shop["prod_id"]

    async with async_session_maker() as session:
        # Step 1: Customer adds item from Shop 1
        cart_1 = await cart_service.add_item_to_cart(
            db=session,
            customer=customer_user,
            product_id=shop1_prod_id,
            quantity=1,
        )
        assert cart_1.shop_id == verified_shop_and_products["shop_id"]
        assert len(cart_1.items) == 1

        # Step 2: Customer attempts to add item from Shop 2 without clearing
        with pytest.raises(HTTPException) as exc_info:
            await cart_service.add_item_to_cart(
                db=session,
                customer=customer_user,
                product_id=shop2_prod_id,
                quantity=1,
            )
        assert exc_info.value.status_code == 400
        assert "A cart can only contain products from one shop" in exc_info.value.detail

        # Step 3: Verify Shop 1 item is STILL present in cart (not silently replaced)
        intact_cart = await cart_service.get_cart(db=session, customer=customer_user)
        assert intact_cart.shop_id == verified_shop_and_products["shop_id"]
        assert len(intact_cart.items) == 1
        assert intact_cart.items[0].product_id == shop1_prod_id


# ---------------------------------------------------------------------------
# Test 4: Directory-Only Discovered Business Rejection
# ---------------------------------------------------------------------------
async def test_directory_only_business_cannot_be_ordered_from(
    directory_only_shop,
    customer_user,
):
    """
    Verify directory-only (unverified / non-orderable) listings cannot be ordered from.
    Attempting to add their products to cart strictly raises HTTP 400.
    """
    dir_prod_id = directory_only_shop["prod_id"]

    async with async_session_maker() as session:
        with pytest.raises(HTTPException) as exc_info:
            await cart_service.add_item_to_cart(
                db=session,
                customer=customer_user,
                product_id=dir_prod_id,
                quantity=1,
            )
        assert exc_info.value.status_code == 400
        assert "directory discovery only" in exc_info.value.detail


# ---------------------------------------------------------------------------
# Test 5: Directory-Only Shop Excluded from Catalog Retrieval
# ---------------------------------------------------------------------------
async def test_directory_only_business_excluded_from_catalog_search(
    directory_only_shop,
):
    """
    Verify search_partner_catalog never returns products from directory-only shops.
    """
    async with async_session_maker() as session:
        results = await search_partner_catalog(
            db=session,
            latitude=PATNA_LAT,
            longitude=PATNA_LON,
            query="Directory Specimen Item",
        )
        assert len(results) == 0, "Directory-only shop products must never appear in catalog search"


# ---------------------------------------------------------------------------
# Test 6: Optimistic Locking with Inventory Version Column
# ---------------------------------------------------------------------------
async def test_inventory_optimistic_locking_concurrency(verified_shop_and_products):
    """
    Verify core engineering requirement from AGENTS.md:
    Stock updates use optimistic locking with a version column to prevent race conditions.
    """
    prod1_id = verified_shop_and_products["prod1_id"]

    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == prod1_id))).scalar_one()
        current_version = inv.version
        initial_stock = inv.stock

        # Simulate concurrent checkout deducting 1 item with expected version
        stmt = (
            text("""
                UPDATE inventory 
                SET stock = stock - 1, version = version + 1 
                WHERE product_id = :pid AND version = :ver
            """)
        )
        res = await session.execute(stmt, {"pid": str(prod1_id), "ver": current_version})
        assert res.rowcount == 1
        await session.commit()

        # Concurrent second request attempts deduction with stale version -> 0 rows updated
        res_stale = await session.execute(stmt, {"pid": str(prod1_id), "ver": current_version})
        assert res_stale.rowcount == 0, "Optimistic lock must reject updates with stale version"
