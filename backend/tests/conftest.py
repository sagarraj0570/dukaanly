import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.db.session import engine

@pytest.fixture(autouse=True)
def disable_auto_dispatch_by_default(monkeypatch):
    """Keeps automated dispatch off by default so existing manual-flow tests are unaffected."""
    from app.core.config import settings
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", False)

@pytest.fixture(autouse=True)
async def cleanup_engine():
    yield
    await engine.dispose()

@pytest.fixture(autouse=True)
async def cleanup_test_shops():
    yield
    try:
        from app.db.session import async_session_maker
        from sqlalchemy import select, delete, update
        from app.models.shop import Shop
        from app.models.order import Order, OrderItem
        from app.models.delivery import Delivery
        from app.models.payment import Payment
        from app.models.cart import Cart, CartItem
        from app.models.product import Product
        from app.models.inventory import Inventory
        from app.models.inventory_reservation import InventoryReservation
        from app.models.user import User
        from app.models.notification import Notification
        from app.services.importer.curated_provider import PATNA_REGIONAL_EXTRACT

        DEMO_EMAILS = {
            "customer@dukaanly.com",
            "shop@dukaanly.com",
            "pharmacy@dukaanly.com",
            "bakery@dukaanly.com",
            "rider@dukaanly.com",
        }
        DEMO_SHOP_NAMES = {
            "Patna Super Kirana",
            "Patna City Medicos",
            "Pataliputra Bakery & Confectionery",
            "Patna Super Kirana (Verified Partner)",
            "Patna City Medicos (Verified Partner)",
            "Pataliputra Bakery & Confectionery (Verified Partner)",
        }
        PERMANENT_SOURCE_IDS = {item["source_id"] for item in PATNA_REGIONAL_EXTRACT if item.get("source_id")}
        HISTORICAL_ORDER_ID = uuid.UUID("1ffd9db1-68f6-436a-bd90-15df8f7edc85")

        async with async_session_maker() as session:
            # 1. Identify all non-permanent test shops
            all_shops = (await session.execute(select(Shop))).scalars().all()
            test_shops = [
                s for s in all_shops
                if s.name not in DEMO_SHOP_NAMES
                and s.source != "demo"
                and (s.source not in ("osm", "geoapify_osm", "gmap", "geoapify") or (s.source_id and s.source_id not in PERMANENT_SOURCE_IDS and not s.source_id.startswith("osm:node:94820")))
            ]
            shop_ids = [s.id for s in test_shops]

            if shop_ids:
                ord_ids = (await session.execute(
                    select(Order.id).where(Order.shop_id.in_(shop_ids), Order.id != HISTORICAL_ORDER_ID)
                )).scalars().all()
                if ord_ids:
                    await session.execute(delete(InventoryReservation).where(InventoryReservation.order_id.in_(ord_ids)))
                    await session.execute(delete(Delivery).where(Delivery.order_id.in_(ord_ids)))
                    await session.execute(delete(Payment).where(Payment.order_id.in_(ord_ids)))
                    await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(ord_ids)))
                    await session.execute(delete(Order).where(Order.id.in_(ord_ids)))
                prod_ids = (await session.execute(select(Product.id).where(Product.shop_id.in_(shop_ids)))).scalars().all()
                if prod_ids:
                    await session.execute(delete(OrderItem).where(OrderItem.product_id.in_(prod_ids)))
                    await session.execute(delete(CartItem).where(CartItem.product_id.in_(prod_ids)))
                    await session.execute(delete(Inventory).where(Inventory.product_id.in_(prod_ids)))
                    await session.execute(delete(Product).where(Product.id.in_(prod_ids)))
                await session.execute(delete(Cart).where(Cart.shop_id.in_(shop_ids)))
                await session.execute(delete(Shop).where(Shop.id.in_(shop_ids)))

            # 2. Identify all non-demo test users
            all_users = (await session.execute(select(User))).scalars().all()
            test_users = [u for u in all_users if u.email not in DEMO_EMAILS]
            user_ids = [u.id for u in test_users]
            if user_ids:
                await session.execute(delete(Notification).where(Notification.user_id.in_(user_ids)))
                user_ord_ids = (await session.execute(
                    select(Order.id).where(Order.customer_id.in_(user_ids), Order.id != HISTORICAL_ORDER_ID)
                )).scalars().all()
                if user_ord_ids:
                    await session.execute(delete(InventoryReservation).where(InventoryReservation.order_id.in_(user_ord_ids)))
                    await session.execute(delete(Delivery).where(Delivery.order_id.in_(user_ord_ids)))
                    await session.execute(delete(Payment).where(Payment.order_id.in_(user_ord_ids)))
                    await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(user_ord_ids)))
                    await session.execute(delete(Order).where(Order.id.in_(user_ord_ids)))
                user_cart_ids = (await session.execute(select(Cart.id).where(Cart.customer_id.in_(user_ids)))).scalars().all()
                if user_cart_ids:
                    await session.execute(delete(CartItem).where(CartItem.cart_id.in_(user_cart_ids)))
                    await session.execute(delete(Cart).where(Cart.id.in_(user_cart_ids)))
                await session.execute(delete(User).where(User.id.in_(user_ids)))

            # 3. Clean up any leftover test orders placed against demo shops during tests
            demo_shop_stmt = select(Shop.id).where(Shop.name.in_(DEMO_SHOP_NAMES))
            demo_shop_ids = (await session.execute(demo_shop_stmt)).scalars().all()
            if demo_shop_ids:
                demo_orders = (await session.execute(
                    select(Order.id).where(Order.shop_id.in_(demo_shop_ids), Order.id != HISTORICAL_ORDER_ID)
                )).scalars().all()
                if demo_orders:
                    await session.execute(delete(InventoryReservation).where(InventoryReservation.order_id.in_(demo_orders)))
                    await session.execute(delete(Delivery).where(Delivery.order_id.in_(demo_orders)))
                    await session.execute(delete(Payment).where(Payment.order_id.in_(demo_orders)))
                    await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(demo_orders)))
                    await session.execute(delete(Order).where(Order.id.in_(demo_orders)))

                # Clean up transient test products added dynamically during tests
                temp_prods = (await session.execute(
                    select(Product.id).where(Product.shop_id.in_(demo_shop_ids), Product.name.like("ZeroStock%"))
                )).scalars().all()
                if temp_prods:
                    await session.execute(delete(Inventory).where(Inventory.product_id.in_(temp_prods)))
                    await session.execute(delete(CartItem).where(CartItem.product_id.in_(temp_prods)))
                    await session.execute(delete(Product).where(Product.id.in_(temp_prods)))

            await session.commit()
        from app.core.rate_limit import reset_all_rate_limiters
        from app.core.redis import close_redis_client
        from app.core.ai import ai_service
        await reset_all_rate_limiters()
        await close_redis_client()
        # AI circuit-breaker state is process-global. Reset it between tests so
        # provider-failure scenarios cannot change unrelated retrieval tests.
        ai_service.reset_circuit_breaker()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error during test cleanup: {e}")

@pytest.fixture
async def async_client():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
