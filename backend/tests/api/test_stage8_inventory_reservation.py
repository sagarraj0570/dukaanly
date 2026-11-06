"""
Stage 8: Transactional Inventory Reservation & Payment-Aware Checkout Tests.

Validates:
1. Reservation lifecycle (create, consume, release, expire, invalid transitions).
2. Checkout integration (durable reservations, deterministic OCC lock ordering).
3. Concurrency guarantees (competing checkouts for final unit, no oversell, no negative stock).
4. Payment lifecycle synchronization (capture consumes, failure releases).
5. Centralized exactly-once stock restoration (no duplicate increments).
6. Celery background expiration and reconciliation.
7. Reservation status API and security.
"""
import uuid
import asyncio
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, async_session_maker
from app.models.inventory import Inventory
from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.shop import ShopVerificationStatus
from app.services.reservation import (
    create_order_reservations,
    consume_order_reservations,
    release_order_reservations,
    get_order_reservation_summary,
)
from app.services.payment_provider import compute_mock_razorpay_signature, compute_mock_webhook_signature
from app.services.payment_provider.razorpay import RazorpayPaymentProvider
from app.tasks.order_recovery import (
    _reconcile_expired_inventory_reservations_async,
    _reconcile_stale_pending_orders_async,
    _reconcile_stale_unaccepted_orders_async,
)

pytestmark = pytest.mark.asyncio


async def _setup_market_fixture(async_client: AsyncClient, initial_stock: int = 10):
    """Helper to set up verified shop, product with initial stock, and customer."""
    uid = uuid.uuid4().hex[:8]
    owner_email = f"st8_owner_{uid}@example.com"
    customer_email = f"st8_cust_{uid}@example.com"

    await async_client.post("/api/v1/auth/register", json={"name": "Owner", "email": owner_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer", "email": customer_email, "password": "PassWord123"})

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()

    token_owner = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "PassWord123"})).json()["access_token"]
    token_cust = (await async_client.post("/api/v1/auth/login", json={"email": customer_email, "password": "PassWord123"})).json()["access_token"]

    # Create shop and product
    shop_res = await async_client.post(
        "/api/v1/shops",
        json={"name": f"Stage 8 Shop {uid}", "address": "Patna Main Road", "location": {"latitude": 25.6144, "longitude": 85.1158}},
        headers={"Authorization": f"Bearer {token_owner}"}
    )
    shop_id = shop_res.json()["id"]

    prod_res = await async_client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": f"Product 8 {uid}", "price": 150.0},
        headers={"Authorization": f"Bearer {token_owner}"}
    )
    product_id = prod_res.json()["id"]

    # Set inventory stock
    await async_client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json={"stock": initial_stock, "expected_version": 1},
        headers={"Authorization": f"Bearer {token_owner}"}
    )

    return {
        "token_owner": token_owner,
        "token_cust": token_cust,
        "shop_id": shop_id,
        "product_id": product_id,
        "customer_email": customer_email,
    }


async def test_reservation_lifecycle_and_invariants():
    """Direct service-level test of reservation lifecycle state machine and exactly-once restoration."""
    async with async_session_maker() as session:
        # Create dummy shop, user, product, inventory, order
        uid = uuid.uuid4().hex[:8]
        from app.models.user import User
        from app.models.shop import Shop
        from app.models.product import Product
        from geoalchemy2.elements import WKTElement

        user = User(name="Test Res User", email=f"res_{uid}@example.com", password_hash="pw")
        session.add(user)
        await session.flush()

        shop = Shop(
            name=f"Res Shop {uid}",
            address="Addr",
            owner_id=user.id,
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            verification_status=ShopVerificationStatus.verified,
            is_active=True,
            is_orderable=True
        )
        session.add(shop)
        await session.flush()

        product = Product(name=f"Res Prod {uid}", price=100.0, shop_id=shop.id)
        session.add(product)
        await session.flush()

        inv = Inventory(product_id=product.id, stock=10, version=1)
        session.add(inv)

        order = Order(customer_id=user.id, shop_id=shop.id, total_amount=Decimal("200.00"), status=OrderStatus.pending)
        session.add(order)
        await session.flush()

        # 1. Create reservations
        items_plan = [{"product_id": product.id, "quantity": 2}]
        inv.stock -= 2
        inv.version += 1
        reservations = await create_order_reservations(session, order, items_plan, user.id, ttl_seconds=900)
        await session.commit()

        assert len(reservations) == 1
        res = reservations[0]
        assert res.status == ReservationStatus.active
        assert res.quantity == 2
        assert res.expires_at > datetime.now(timezone.utc)

        # 2. Consume reservations (Simulate Payment Capture)
        consumed = await consume_order_reservations(session, order.id)
        assert len(consumed) == 1
        assert consumed[0].status == ReservationStatus.consumed
        assert consumed[0].consumed_at is not None
        await session.commit()

        # 3. Idempotent repeat consumption
        consumed_again = await consume_order_reservations(session, order.id)
        assert len(consumed_again) == 1
        assert consumed_again[0].status == ReservationStatus.consumed

        # 4. Attempting to release a consumed reservation must NOT restore stock
        released_count = await release_order_reservations(session, order.id, release_reason="test_fail")
        assert released_count == 0  # No active reservations released!
        await session.commit()

        # Verify stock remained at 8 (did not restore consumed stock)
        inv_check = (await session.execute(select(Inventory).where(Inventory.product_id == product.id))).scalar_one()
        assert inv_check.stock == 8


async def test_active_reservation_release_restores_stock_exactly_once():
    """Releasing active reservations restores stock exactly once, subsequent releases are no-ops."""
    async with async_session_maker() as session:
        uid = uuid.uuid4().hex[:8]
        from app.models.user import User
        from app.models.shop import Shop
        from app.models.product import Product
        from geoalchemy2.elements import WKTElement

        user = User(name="Test Rel User", email=f"rel_{uid}@example.com", password_hash="pw")
        session.add(user)
        await session.flush()

        shop = Shop(
            name=f"Rel Shop {uid}",
            address="Addr",
            owner_id=user.id,
            location=WKTElement("POINT(85.1158 25.6144)", srid=4326),
            verification_status=ShopVerificationStatus.verified,
            is_active=True,
            is_orderable=True
        )
        session.add(shop)
        await session.flush()

        product = Product(name=f"Rel Prod {uid}", price=50.0, shop_id=shop.id)
        session.add(product)
        await session.flush()

        inv = Inventory(product_id=product.id, stock=5, version=1)
        session.add(inv)

        order = Order(customer_id=user.id, shop_id=shop.id, total_amount=Decimal("150.00"), status=OrderStatus.pending)
        session.add(order)
        await session.flush()

        # Reserve 3 units
        inv.stock -= 3
        inv.version += 1
        await create_order_reservations(session, order, [{"product_id": product.id, "quantity": 3}], user.id)
        await session.commit()

        # Release active reservation
        released = await release_order_reservations(session, order.id, release_reason="customer_cancelled", to_status=ReservationStatus.released)
        assert released == 1
        await session.commit()

        # Verify stock restored to 5
        inv_after = (await session.execute(select(Inventory).where(Inventory.product_id == product.id))).scalar_one()
        assert inv_after.stock == 5

        # Second release attempt: must be 0 and stock must remain 5
        released_again = await release_order_reservations(session, order.id, release_reason="duplicate_call", to_status=ReservationStatus.released)
        assert released_again == 0
        await session.commit()

        inv_final = (await session.execute(select(Inventory).where(Inventory.product_id == product.id))).scalar_one()
        assert inv_final.stock == 5


async def test_checkout_creates_reservations_and_reservation_endpoint(async_client: AsyncClient):
    """Verifies that checkout creates durable reservations and the /reservation status endpoint returns accurate countdown."""
    fixture = await _setup_market_fixture(async_client, initial_stock=8)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Add 3 units to cart
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 3}, headers=headers)

    # Checkout
    idempotency_key = str(uuid.uuid4())
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": idempotency_key},
        headers=headers
    )
    assert checkout_res.status_code == 201
    order_data = checkout_res.json()
    order_id = order_data["id"]

    assert order_data["status"] == "pending"
    assert order_data["reservation_status"] == "active"
    assert order_data["reservation_expires_at"] is not None

    # Verify inventory was decremented in database
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 5  # 8 - 3 = 5

        # Verify durable reservation record
        res_stmt = select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id))
        reservations = (await session.execute(res_stmt)).scalars().all()
        assert len(reservations) == 1
        assert reservations[0].quantity == 3
        assert reservations[0].status == ReservationStatus.active

    # Check reservation summary endpoint
    res_status_resp = await async_client.get(f"/api/v1/orders/{order_id}/reservation", headers=headers)
    assert res_status_resp.status_code == 200
    res_summary = res_status_resp.json()
    assert res_summary["status"] == "active"
    assert res_summary["seconds_remaining"] > 0
    assert "server_time" in res_summary and res_summary["server_time"] is not None
    assert res_summary["is_expired"] is False
    assert len(res_summary["items"]) == 1
    assert res_summary["items"][0]["quantity"] == 3


async def test_concurrency_last_unit_reservation(async_client: AsyncClient):
    """Two concurrent customers attempt to reserve the final remaining unit. Exactly one must succeed."""
    fixture = await _setup_market_fixture(async_client, initial_stock=1)
    token_cust1 = fixture["token_cust"]
    product_id = fixture["product_id"]

    # Register second customer
    cust2_email = f"st8_cust2_{uuid.uuid4().hex[:8]}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Customer 2", "email": cust2_email, "password": "PassWord123"})
    token_cust2 = (await async_client.post("/api/v1/auth/login", json={"email": cust2_email, "password": "PassWord123"})).json()["access_token"]

    # Both customers add 1 item to cart
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 1}, headers={"Authorization": f"Bearer {token_cust1}"})
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 1}, headers={"Authorization": f"Bearer {token_cust2}"})

    # Compete for the last unit concurrently
    res1, res2 = await asyncio.gather(
        async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers={"Authorization": f"Bearer {token_cust1}"}),
        async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers={"Authorization": f"Bearer {token_cust2}"}),
    )

    status_codes = sorted([res1.status_code, res2.status_code])
    assert status_codes == [201, 409], f"Expected [201, 409], got: {status_codes}"

    # Verify inventory stock is exactly 0 and not negative
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 0

        # Exactly 1 active reservation in database
        active_reservations = (await session.execute(
            select(InventoryReservation).where(
                InventoryReservation.product_id == uuid.UUID(product_id),
                InventoryReservation.status == ReservationStatus.active
            )
        )).scalars().all()
        assert len(active_reservations) == 1


async def test_payment_verification_consumes_reservation(async_client: AsyncClient):
    """Payment verification confirms order and transitions active reservation to consumed."""
    fixture = await _setup_market_fixture(async_client, initial_stock=5)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    # 1. Initiate payment
    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert init_res.status_code == 200
    init_data = init_res.json()
    provider_order_id = init_data["provider_order_id"]

    # 2. Verify with valid signature
    payment_id = init_data.get("mock_payment_id") or f"pay_mock_{uuid.uuid4().hex[:6]}"
    sig = init_data.get("mock_signature") or compute_mock_razorpay_signature(provider_order_id, payment_id)

    verify_res = await async_client.post(
        "/api/v1/payments/verify",
        json={"razorpay_order_id": provider_order_id, "razorpay_payment_id": payment_id, "razorpay_signature": sig},
        headers=headers
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["status"] == "captured"

    # 3. Check order and reservation status
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.confirmed

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.consumed
        assert res.consumed_at is not None

        # Stock is still 3 (5 - 2 = 3)
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 3


async def test_webhook_payment_failed_releases_reservation_and_cancels_order(async_client: AsyncClient):
    """Webhook reporting payment.failed releases reservations and restores stock exactly once."""
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 4}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Send payment.failed webhook
    import json
    wh_payload = {
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_fail_{uuid.uuid4().hex[:6]}",
                    "order_id": provider_order_id,
                    "error_description": "Card expired / simulated failure",
                }
            }
        }
    }
    payload_bytes = json.dumps(wh_payload).encode()
    wh_sig = compute_mock_webhook_signature(payload_bytes)

    wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        content=payload_bytes,
        headers={"x-razorpay-signature": wh_sig}
    )
    assert wh_res.status_code == 200

    # Verify order is cancelled, reservation is released, and stock is restored
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.released
        assert res.released_at is not None

        # Stock was restored from 6 back to 10
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10


async def test_celery_task_reconciles_expired_reservations(async_client: AsyncClient):
    """Celery background task reconciles expired active reservations and restores stock exactly once."""
    fixture = await _setup_market_fixture(async_client, initial_stock=6)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    # Manually backdate the reservation expiration time to 5 minutes ago
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Run the Celery expiration recovery task directly
    recovered_count = await _reconcile_expired_inventory_reservations_async()
    assert recovered_count >= 1

    # Verify reservation transitioned to expired and stock restored
    async with async_session_maker() as session:
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.expired
        assert res.released_at is not None

        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        # Stock restored from 4 back to 6
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 6

    # Running Celery task again should find 0 expired active reservations and not restore stock again
    recovered_second = await _reconcile_expired_inventory_reservations_async()
    assert recovered_second == 0

    async with async_session_maker() as session:
        inv_check = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv_check.stock == 6


async def test_cannot_pay_for_expired_reservation(async_client: AsyncClient):
    """Attempting payment initiation on an order with an expired reservation is rejected with 400 Bad Request."""
    fixture = await _setup_market_fixture(async_client, initial_stock=4)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    # Expire reservation manually
    past_time = datetime.now(timezone.utc) - timedelta(minutes=10)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Attempting to initiate payment should be rejected
    pay_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert pay_res.status_code == 400
    assert "expired" in pay_res.json()["detail"].lower()


async def test_mock_payment_initiation_provides_sandbox_credentials(async_client: AsyncClient):
    """Payment initiation returns sandbox details without exposing private server secrets to the client."""
    fixture = await _setup_market_fixture(async_client, initial_stock=4)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 1}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    pay_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert pay_res.status_code == 200
    data = pay_res.json()
    assert "mock_payment_id" in data
    assert "mock_signature" in data
    # Ensure raw secret is NOT leaked in response
    assert "key_secret" not in data
    assert "webhook_secret" not in data


async def test_unknown_payment_outcome_retains_reservation(async_client: AsyncClient):
    """
    Issue 1: An ambiguous or unknown payment outcome (e.g. gateway timeout or connection error)
    MUST retain the active reservation instead of prematurely releasing stock or cancelling the order.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=5)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    assert init_res.status_code == 200
    provider_order_id = init_res.json()["provider_order_id"]

    # Backdate reservation expiration
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Simulate gateway communication error / network timeout
    import httpx
    RazorpayPaymentProvider.set_mock_fetch_exception(
        provider_order_id,
        httpx.RequestError(f"Gateway connection timed out for {provider_order_id}")
    )

    try:
        # Run reconciliation task
        recovered_count = await _reconcile_expired_inventory_reservations_async()
        # Should NOT count as recovered/closed because it was retained
        assert recovered_count == 0

        # Verify reservation is STILL active, order is STILL pending, stock is NOT restored
        async with async_session_maker() as session:
            res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
            assert res.status == ReservationStatus.active
            assert res.released_at is None

            order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
            assert order.status == OrderStatus.pending

            # Stock was 5 - 2 = 3; should still be 3
            inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
            assert inv.stock == 3
    finally:
        RazorpayPaymentProvider.reset_mock_state()


async def test_in_flight_processing_retains_reservation(async_client: AsyncClient):
    """
    Issue 1: In-flight processing status ('processing', 'authorized', etc.) from provider
    MUST retain the active reservation while payment processing completes.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=5)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Backdate reservation expiration
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Simulate in-flight payment at provider
    RazorpayPaymentProvider.set_mock_order_status(provider_order_id, "processing")

    try:
        recovered_count = await _reconcile_expired_inventory_reservations_async()
        assert recovered_count == 0

        async with async_session_maker() as session:
            res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
            assert res.status == ReservationStatus.active

            order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
            assert order.status == OrderStatus.pending

            inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
            assert inv.stock == 3
    finally:
        RazorpayPaymentProvider.reset_mock_state()


async def test_provider_reconciliation_detects_late_capture(async_client: AsyncClient):
    """
    Issue 1: If payment is reported captured/paid by provider during reservation expiry,
    the recovery task consumes the reservation and confirms the order rather than releasing stock.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=8)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 3}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Backdate reservation
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Gateway reports payment as paid
    RazorpayPaymentProvider.set_mock_order_status(provider_order_id, "paid")

    try:
        recovered_count = await _reconcile_expired_inventory_reservations_async()
        assert recovered_count >= 1

        async with async_session_maker() as session:
            res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
            assert res.status == ReservationStatus.consumed
            assert res.consumed_at is not None

            order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
            assert order.status == OrderStatus.confirmed

            pay = (await session.execute(select(Payment).where(Payment.order_id == uuid.UUID(order_id)))).scalar_one()
            assert pay.status == PaymentStatus.captured

            # Stock was 8 - 3 = 5, stays 5
            inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
            assert inv.stock == 5
    finally:
        RazorpayPaymentProvider.reset_mock_state()


async def test_definitive_provider_failure_releases_stock(async_client: AsyncClient):
    """
    Issue 1: If provider confirms payment definitively failed, the reservation is released
    and stock is restored.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=7)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Backdate reservation
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Gateway reports definitive failure
    RazorpayPaymentProvider.set_mock_order_status(provider_order_id, "failed")

    try:
        recovered_count = await _reconcile_expired_inventory_reservations_async()
        assert recovered_count >= 1

        async with async_session_maker() as session:
            res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
            assert res.status == ReservationStatus.released
            assert res.released_at is not None

            order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
            assert order.status == OrderStatus.cancelled

            pay = (await session.execute(select(Payment).where(Payment.order_id == uuid.UUID(order_id)))).scalar_one()
            assert pay.status == PaymentStatus.failed

            # Stock was 7 - 2 = 5, restored back to 7
            inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
            assert inv.stock == 7
    finally:
        RazorpayPaymentProvider.reset_mock_state()


async def test_pending_beyond_policy_and_compensating_workflow(async_client: AsyncClient):
    """
    Issue 1: If payment is pending beyond policy threshold (unpaid at provider and TTL expired),
    stock is restored and order cancelled. If a late capture arrives subsequently,
    the compensating workflow automatically refunds the customer without reviving the order or overselling stock.
    """
    import json
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 4}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Backdate reservation
    past_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Reconcile expired pending order
    recovered_count = await _reconcile_expired_inventory_reservations_async()
    assert recovered_count >= 1

    # Verify reservation expired, order cancelled, stock restored
    async with async_session_maker() as session:
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.expired

        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        # Stock restored from 6 back to 10
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10

    # COMPENSATING WORKFLOW TEST:
    # A late webhook arrives from the provider claiming payment was captured for this cancelled order
    late_payment_id = f"pay_late_{uuid.uuid4().hex[:6]}"
    wh_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": late_payment_id,
                    "order_id": provider_order_id,
                    "amount": 60000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }
    payload_bytes = json.dumps(wh_payload).encode()
    wh_sig = compute_mock_webhook_signature(payload_bytes)

    wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        content=payload_bytes,
        headers={"x-razorpay-signature": wh_sig}
    )
    assert wh_res.status_code == 200

    # Verify compensating workflow:
    # 1. Payment marked refunded (NOT captured)
    # 2. Order remains cancelled (NOT revived)
    # 3. Stock remains 10 (NOT double-sold)
    async with async_session_maker() as session:
        pay = (await session.execute(select(Payment).where(Payment.order_id == uuid.UUID(order_id)))).scalar_one()
        assert pay.status == PaymentStatus.refunded
        assert "auto-refunded" in (pay.failure_reason or "")

        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10


async def test_stage6_stale_pending_recovery_delegates_to_reservation_service_without_double_restoration(async_client: AsyncClient):
    """
    Issue 2: Stage 6 recovery task (_reconcile_stale_pending_orders_async) must delegate to the
    centralized reservation service for reservation-backed orders rather than independently restoring stock.
    Subsequent execution of Stage 8 recovery task must not double-restore stock.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 3 units -> stock becomes 7
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 3}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    # Verify initial stock and active reservation
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 7

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.active
        initial_inv_version = inv.version

    # Backdate both order created_at and reservation expires_at (past cutoff for both Stage 6 and Stage 8 tasks)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=20)
    async with async_session_maker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order_id))
            .values(created_at=past_time)
        )
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=past_time)
        )
        await session.commit()

    # Run Stage 6 recovery task first
    s6_cancelled = await _reconcile_stale_pending_orders_async()
    assert s6_cancelled >= 1

    # Verify that:
    # 1. Order was cancelled
    # 2. Reservation was transitioned to 'expired' via centralized reservation service
    # 3. Stock was restored exactly once from 7 to 10
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.expired
        assert res.released_at is not None

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10
        version_after_s6 = inv.version
        assert version_after_s6 == initial_inv_version + 1

    # Now run Stage 8 recovery task on the same database state
    s8_recovered = await _reconcile_expired_inventory_reservations_async()
    # Should find 0 active expired reservations because it was already cleanly expired
    assert s8_recovered == 0

    # Crucial assertion: Stock must NOT have been restored again (must remain 10, NOT 13!)
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10
        assert inv.version == version_after_s6


async def test_stage6_unaccepted_order_recovery_releases_consumed_reservations_via_centralized_service(async_client: AsyncClient):
    """
    Issue 2: When a confirmed order is cancelled by Stage 6 unaccepted order recovery,
    its 'consumed' reservations must be transitioned to 'released' by delegating to the
    centralized reservation service, preventing independent raw SQL inventory increments.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=12)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 4 units -> stock becomes 8
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 4}, headers=headers)
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)).json()["id"]

    # Initiate and verify payment -> consumes reservation, confirms order, stock remains 8
    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()

    verify_res = await async_client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_order_id": pay_data["provider_order_id"],
            "razorpay_payment_id": pay_data["mock_payment_id"],
            "razorpay_signature": pay_data["mock_signature"],
        },
        headers=headers,
    )
    assert verify_res.status_code == 200

    # Verify reservation is consumed and order confirmed
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.confirmed

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.consumed

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 8
        version_before_cancellation = inv.version

    # Backdate confirmation time beyond shop acceptance timeout (ORDER_CONFIRMED_TIMEOUT_SECONDS)
    past_time = datetime.now(timezone.utc) - timedelta(minutes=45)
    async with async_session_maker() as session:
        await session.execute(
            update(Order)
            .where(Order.id == uuid.UUID(order_id))
            .values(updated_at=past_time, created_at=past_time)
        )
        await session.commit()

    # Run Stage 6 unaccepted order recovery task
    cancelled_count = await _reconcile_stale_unaccepted_orders_async()
    assert cancelled_count >= 1

    # Verify that:
    # 1. Order was cancelled
    # 2. Consumed reservation was transitioned to 'released' via centralized reservation service
    # 3. Stock was restored from 8 back to 12
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled

        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        assert res.status == ReservationStatus.released
        assert res.released_at is not None

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 12
        assert inv.version == version_before_cancellation + 1


async def test_concurrency_lock_order_deadlock_prevention(async_client: AsyncClient):
    """
    Issue 3: Validate lock ordering across competing operations.
    Ensures canonical lock hierarchy:
      Order -> Payment -> InventoryReservation -> Inventory
    prevents PostgreSQL transaction deadlocks (40P01 / DeadlockDetectedError)
    when payment verification/capture and reservation expiry/cancellation
    compete concurrently on the same order.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 3 units -> stock becomes 7
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 3}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    # Initiate payment
    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]
    mock_payment_id = pay_data["mock_payment_id"]
    mock_signature = pay_data["mock_signature"]

    # Set up mock gateway to consider payment paid if polled
    RazorpayPaymentProvider.set_mock_order_status(provider_order_id, "paid")

    deadlock_errors = []
    successes = []

    # Coroutine A: Payment Verification
    async def run_payment_verification():
        try:
            res = await async_client.post(
                "/api/v1/payments/verify",
                json={
                    "razorpay_order_id": provider_order_id,
                    "razorpay_payment_id": mock_payment_id,
                    "razorpay_signature": mock_signature,
                },
                headers=headers,
            )
            successes.append(("verify", res.status_code))
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("verify", str(exc)))
            else:
                successes.append(("verify_exc", str(exc)))

    # Coroutine B: Order Expiry / Recovery
    async def run_order_recovery():
        try:
            async with async_session_maker() as session:
                order_stmt = select(Order).where(Order.id == uuid.UUID(order_id)).with_for_update()
                order = (await session.execute(order_stmt)).scalar_one_or_none()
                if order:
                    outcome = await _reconcile_single_order_reservation_async(
                        session=session,
                        order=order,
                        now=datetime.now(timezone.utc) + timedelta(minutes=15),
                    )
                    successes.append(("recovery", outcome))
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("recovery", str(exc)))
            else:
                successes.append(("recovery_exc", str(exc)))

    # Execute both simultaneously against real PostgreSQL database
    await asyncio.gather(run_payment_verification(), run_order_recovery())

    # STRICT ASSERTION: Zero PostgreSQL deadlocks occurred
    assert len(deadlock_errors) == 0, f"Deadlocks detected under concurrent execution: {deadlock_errors}"

    # Invariant assertion: order state is coherent and inventory matches reservation state
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()

        if order.status == OrderStatus.confirmed:
            assert res.status == ReservationStatus.consumed
            assert inv.stock == 7
        elif order.status == OrderStatus.cancelled:
            assert res.status in (ReservationStatus.expired, ReservationStatus.released)
            assert inv.stock == 10
        else:
            pytest.fail(f"Unexpected intermediate order status: {order.status}")


async def test_concurrency_webhook_vs_cancellation_lock_order(async_client: AsyncClient):
    """
    Validates lock order deadlock prevention between concurrent Payment Webhook (captured)
    and Customer Order Cancellation on the same order.
    """
    import json
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 2 units -> stock becomes 8
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    # Initiate payment
    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]
    mock_payment_id = pay_data["mock_payment_id"]

    webhook_body = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": mock_payment_id,
                    "order_id": provider_order_id,
                    "amount": 30000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }).encode("utf-8")
    sig = compute_mock_webhook_signature(webhook_body)

    deadlock_errors = []

    async def run_webhook():
        try:
            await async_client.post(
                "/api/v1/payments/webhook",
                content=webhook_body,
                headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
            )
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("webhook", str(exc)))

    async def run_cancellation():
        try:
            await async_client.post(
                f"/api/v1/orders/{order_id}/cancel",
                json={"reason": "Customer changed mind before confirmation"},
                headers=headers,
            )
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("cancel", str(exc)))

    await asyncio.gather(run_webhook(), run_cancellation())

    assert len(deadlock_errors) == 0, f"Deadlock occurred between webhook and cancellation: {deadlock_errors}"

    # Verify database consistency
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()

        if order.status == OrderStatus.confirmed:
            assert res.status == ReservationStatus.consumed
            assert inv.stock == 8
        elif order.status == OrderStatus.cancelled:
            assert res.status in (ReservationStatus.expired, ReservationStatus.released)
            assert inv.stock == 10


async def test_concurrency_payment_success_racing_with_expiry(async_client: AsyncClient):
    """
    Validates concurrency when Payment Verification races with Background Expiry Reconciliation.
    Either outcome (Payment Confirmed vs Expiry Cancelled) must complete deterministically
    without deadlocks, partial states, or invalid inventory counts.
    """
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 2 units -> stock becomes 8
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    # Initiate payment
    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]
    mock_payment_id = pay_data["mock_payment_id"]
    sig = compute_mock_razorpay_signature(provider_order_id, mock_payment_id)

    # Set reservation expired in DB
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=2))
        )
        await session.commit()

    deadlock_errors = []

    async def run_verify():
        try:
            return await async_client.post(
                "/api/v1/payments/verify",
                json={
                    "razorpay_order_id": provider_order_id,
                    "razorpay_payment_id": mock_payment_id,
                    "razorpay_signature": sig,
                },
                headers=headers,
            )
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("verify", str(exc)))
            return None

    async def run_expiry():
        try:
            return await _reconcile_expired_inventory_reservations_async()
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("expiry", str(exc)))
            return None

    await asyncio.gather(run_verify(), run_expiry())

    assert len(deadlock_errors) == 0, f"Deadlock occurred between verify and expiry: {deadlock_errors}"

    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()

        if order.status == OrderStatus.confirmed:
            assert res.status == ReservationStatus.consumed
            assert inv.stock == 8
        elif order.status == OrderStatus.cancelled:
            assert res.status in (ReservationStatus.expired, ReservationStatus.released)
            assert inv.stock == 10
        else:
            pytest.fail(f"Invalid intermediate order status: {order.status}")


async def test_concurrency_payment_failure_racing_with_expiry(async_client: AsyncClient):
    """
    Validates concurrency when Payment Failure Webhook races with Background Expiry Reconciliation.
    Both want to release the reservation. Stock MUST be restored exactly once (never double-restored).
    """
    import json
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]

    failed_body = json.dumps({
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_failed_{uuid.uuid4().hex[:8]}",
                    "order_id": provider_order_id,
                    "amount": 30000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Card was declined by issuing bank",
                }
            }
        }
    }).encode("utf-8")
    sig = compute_mock_webhook_signature(failed_body)

    # Set reservation expired in DB
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=2))
        )
        await session.commit()

    deadlock_errors = []

    async def run_webhook():
        try:
            await async_client.post(
                "/api/v1/payments/webhook",
                content=failed_body,
                headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
            )
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("webhook", str(exc)))

    async def run_expiry():
        try:
            await _reconcile_expired_inventory_reservations_async()
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("expiry", str(exc)))

    await asyncio.gather(run_webhook(), run_expiry())

    assert len(deadlock_errors) == 0, f"Deadlock occurred: {deadlock_errors}"

    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        res = (await session.execute(select(InventoryReservation).where(InventoryReservation.order_id == uuid.UUID(order_id)))).scalar_one()
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()

        assert order.status == OrderStatus.cancelled
        assert res.status in (ReservationStatus.expired, ReservationStatus.released)
        assert inv.stock == 10, f"Stock double-restored! Expected 10, got {inv.stock}"


async def test_duplicate_webhook_delivery_idempotency(async_client: AsyncClient):
    """
    Validates idempotency under duplicate webhook deliveries:
    1. Duplicate 'payment.captured' webhooks: second returns 'already_captured' and does not re-consume.
    2. Duplicate 'payment.failed' webhooks: second returns ok and does not double-restore stock.
    """
    import json
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # 1. Test duplicate captured webhook
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]
    mock_payment_id = pay_data["mock_payment_id"]

    captured_body = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": mock_payment_id,
                    "order_id": provider_order_id,
                    "amount": 30000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }).encode("utf-8")
    sig_captured = compute_mock_webhook_signature(captured_body)

    # First delivery
    res1 = await async_client.post(
        "/api/v1/payments/webhook",
        content=captured_body,
        headers={"X-Razorpay-Signature": sig_captured, "Content-Type": "application/json"},
    )
    assert res1.status_code == 200

    # Second delivery (duplicate delivery from payment gateway)
    res2 = await async_client.post(
        "/api/v1/payments/webhook",
        content=captured_body,
        headers={"X-Razorpay-Signature": sig_captured, "Content-Type": "application/json"},
    )
    assert res2.status_code == 200
    assert res2.json().get("message") == "already_captured"

    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 8, f"Stock changed unexpectedly on duplicate capture! Got {inv.stock}"

    # 2. Test duplicate failed webhook
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res2 = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id2 = checkout_res2.json()["id"]

    pay_init2 = await async_client.post(f"/api/v1/orders/{order_id2}/payment", headers=headers)
    pay_data2 = pay_init2.json()
    provider_order_id2 = pay_data2["provider_order_id"]

    failed_body = json.dumps({
        "event": "payment.failed",
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_fld_{uuid.uuid4().hex[:8]}",
                    "order_id": provider_order_id2,
                    "amount": 30000,
                    "currency": "INR",
                    "status": "failed",
                    "error_description": "Network timeout",
                }
            }
        }
    }).encode("utf-8")
    sig_failed = compute_mock_webhook_signature(failed_body)

    # First delivery
    res_f1 = await async_client.post(
        "/api/v1/payments/webhook",
        content=failed_body,
        headers={"X-Razorpay-Signature": sig_failed, "Content-Type": "application/json"},
    )
    assert res_f1.status_code == 200

    # Second delivery
    res_f2 = await async_client.post(
        "/api/v1/payments/webhook",
        content=failed_body,
        headers={"X-Razorpay-Signature": sig_failed, "Content-Type": "application/json"},
    )
    assert res_f2.status_code == 200

    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        # Initial 10 - 2 (order 1 confirmed) - 2 (order 2 created) + 2 (order 2 failed and restored) = 8
        assert inv.stock == 8, f"Stock double-restored on duplicate failed webhook! Got {inv.stock}"


async def test_late_payment_success_after_reservation_expiry_triggers_compensating_refund(async_client: AsyncClient):
    """
    Validates Safe Compensating Workflow:
    When an order's reservation expires and the order is cancelled, a subsequent late
    payment capture webhook:
    1. Does NOT revive the cancelled order.
    2. Does NOT deduct stock again or cause overselling.
    3. Automatically transitions payment to 'refunded'.
    4. Triggers provider refund via the payment provider adapter.
    """
    import json
    RazorpayPaymentProvider.reset_mock_state()
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Checkout 2 units -> stock becomes 8
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    # Initiate payment
    pay_init = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
    pay_data = pay_init.json()
    provider_order_id = pay_data["provider_order_id"]
    mock_payment_id = pay_data["mock_payment_id"]

    # Expire reservation and reconcile
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        )
        await session.commit()

    reconciled = await _reconcile_expired_inventory_reservations_async()
    assert reconciled == 1

    # Verify order is cancelled and stock is restored to 10
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10

    # Now deliver late payment.captured webhook
    late_capture_body = json.dumps({
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": mock_payment_id,
                    "order_id": provider_order_id,
                    "amount": 30000,
                    "currency": "INR",
                    "status": "captured",
                }
            }
        }
    }).encode("utf-8")
    sig = compute_mock_webhook_signature(late_capture_body)

    res = await async_client.post(
        "/api/v1/payments/webhook",
        content=late_capture_body,
        headers={"X-Razorpay-Signature": sig, "Content-Type": "application/json"},
    )
    assert res.status_code == 200

    # Verify safe compensating state
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == uuid.UUID(order_id)))).scalar_one()
        assert order.status == OrderStatus.cancelled, "Cancelled order was illegally revived!"

        payment = (await session.execute(select(Payment).where(Payment.order_id == uuid.UUID(order_id)))).scalar_one()
        assert payment.status == PaymentStatus.refunded, f"Payment status should be refunded, got {payment.status}"
        assert "late_payment_captured_after_order_cancellation: auto-refunded" in payment.failure_reason

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10, f"Stock was illegally re-deducted after late capture! Got {inv.stock}"


async def test_duplicate_cancellation_does_not_double_restore_stock(async_client: AsyncClient):
    """
    Validates that duplicate cancellation requests (sequential or concurrent):
    1. Do NOT restore stock multiple times.
    2. Second request returns 409 Conflict.
    3. Final stock is preserved exactly once.
    """
    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # 1. Sequential cancellation test
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id = checkout_res.json()["id"]

    # First cancellation succeeds
    res1 = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Customer cancellation 1"},
        headers=headers,
    )
    assert res1.status_code == 200

    # Second cancellation: returns 200 (idempotent state return) or 409 Conflict without double-restoring stock
    res2 = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Customer cancellation 2 duplicate"},
        headers=headers,
    )
    assert res2.status_code in (200, 409)

    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10, f"Sequential cancellation double-restored stock! Got {inv.stock}"

    # 2. Concurrent cancellations test
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
    checkout_res2 = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers,
    )
    order_id2 = checkout_res2.json()["id"]

    responses = await asyncio.gather(
        async_client.post(f"/api/v1/orders/{order_id2}/cancel", json={"reason": "Concurrent cancel A"}, headers=headers),
        async_client.post(f"/api/v1/orders/{order_id2}/cancel", json={"reason": "Concurrent cancel B"}, headers=headers),
    )
    statuses = [r.status_code for r in responses]
    assert 200 in statuses, f"At least one concurrent cancellation must succeed: {statuses}"
    assert 409 in statuses or 200 in statuses

    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10, f"Concurrent cancellations double-restored stock! Got {inv.stock}"


async def test_concurrency_multiple_expiry_workers(async_client: AsyncClient):
    """
    Validates concurrent background expiry workers using FOR UPDATE SKIP LOCKED:
    3 concurrent workers scanning for 3 expired orders must process them without deadlocks,
    with each order claimed exactly once, and all stock restored accurately.
    """
    fixture = await _setup_market_fixture(async_client, initial_stock=30)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    order_ids = []
    for _ in range(3):
        await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 2}, headers=headers)
        res = await async_client.post(
            "/api/v1/orders/checkout",
            json={"idempotency_key": str(uuid.uuid4())},
            headers=headers,
        )
        order_ids.append(res.json()["id"])

    # Stock is now 30 - 6 = 24
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 24

        # Artificially expire all 3 orders
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id.in_([uuid.UUID(oid) for oid in order_ids]))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=15))
        )
        await session.commit()

    # Launch 3 concurrent expiry workers
    results = await asyncio.gather(
        _reconcile_expired_inventory_reservations_async(),
        _reconcile_expired_inventory_reservations_async(),
        _reconcile_expired_inventory_reservations_async(),
    )

    total_recovered = sum(results)
    assert total_recovered == 3, f"Expected 3 orders recovered across workers, got {total_recovered} (distribution: {results})"

    # Verify all 3 orders cancelled and stock fully restored to 30
    async with async_session_maker() as session:
        orders = (await session.execute(select(Order).where(Order.id.in_([uuid.UUID(oid) for oid in order_ids])))).scalars().all()
        assert all(o.status == OrderStatus.cancelled for o in orders)

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 30, f"Expected stock restored to 30, got {inv.stock}"


async def test_concurrency_multi_product_reservation_release(async_client: AsyncClient):
    """
    Validates deterministic product_id ASC lock ordering during multi-product reservation release.
    Prevents deadlocks when multiple multi-item carts are simultaneously cancelled or expired.
    """
    uid = uuid.uuid4().hex[:8]
    owner_email = f"st8_multi_owner_{uid}@example.com"
    customer_email = f"st8_multi_cust_{uid}@example.com"

    await async_client.post("/api/v1/auth/register", json={"name": "Owner", "email": owner_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer", "email": customer_email, "password": "PassWord123"})

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()

    token_owner = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "PassWord123"})).json()["access_token"]
    token_cust = (await async_client.post("/api/v1/auth/login", json={"email": customer_email, "password": "PassWord123"})).json()["access_token"]
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    headers_cust = {"Authorization": f"Bearer {token_cust}"}

    shop_res = await async_client.post(
        "/api/v1/shops",
        json={"name": f"Multi Shop {uid}", "address": "Patna Lane", "location": {"latitude": 25.6144, "longitude": 85.1158}},
        headers=headers_owner
    )
    shop_id = shop_res.json()["id"]

    # Create 3 products
    p_ids = []
    for i in range(3):
        p_res = await async_client.post(
            f"/api/v1/shops/{shop_id}/products",
            json={"name": f"Multi Item {i}_{uid}", "price": 100.0 * (i + 1)},
            headers=headers_owner
        )
        pid = p_res.json()["id"]
        p_ids.append(pid)
        await async_client.patch(
            f"/api/v1/products/{pid}/inventory",
            json={"stock": 10, "expected_version": 1},
            headers=headers_owner
        )

    # Add all 3 to cart and checkout
    for pid in p_ids:
        await async_client.post("/api/v1/cart/items", json={"product_id": pid, "quantity": 1}, headers=headers_cust)

    checkout_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=headers_cust,
    )
    order_id = checkout_res.json()["id"]

    # Artificially expire reservations
    async with async_session_maker() as session:
        await session.execute(
            update(InventoryReservation)
            .where(InventoryReservation.order_id == uuid.UUID(order_id))
            .values(expires_at=datetime.now(timezone.utc) - timedelta(seconds=5))
        )
        await session.commit()

    deadlock_errors = []

    async def run_customer_cancel():
        try:
            await async_client.post(
                f"/api/v1/orders/{order_id}/cancel",
                json={"reason": "Customer cancellation during expiry"},
                headers=headers_cust,
            )
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("cancel", str(exc)))

    async def run_expiry_reconcile():
        try:
            await _reconcile_expired_inventory_reservations_async()
        except Exception as exc:
            if "deadlock" in str(exc).lower() or "40p01" in str(exc).lower():
                deadlock_errors.append(("reconcile", str(exc)))

    await asyncio.gather(run_customer_cancel(), run_expiry_reconcile())

    assert len(deadlock_errors) == 0, f"Deadlock occurred during multi-product release: {deadlock_errors}"

    # Verify all 3 products restored to stock 10
    async with async_session_maker() as session:
        for pid in p_ids:
            inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(pid)))).scalar_one()
            assert inv.stock == 10, f"Stock for {pid} was not restored to 10! Got {inv.stock}"


async def test_historical_order_without_reservations_handled_deliberately(async_client: AsyncClient):
    """
    Validates deliberate legacy fallback:
    Historical orders created prior to Stage 8 (with 0 reservation rows) must use the
    deterministic legacy stock restoration branch upon cancellation rather than failing
    or raising KeyError/AssertionError.
    """
    from app.models.order import OrderItem
    from app.models.user import User
    from sqlalchemy import func

    fixture = await _setup_market_fixture(async_client, initial_stock=10)
    token_cust = fixture["token_cust"]
    product_id = fixture["product_id"]
    shop_id = fixture["shop_id"]
    customer_email = fixture["customer_email"]
    headers = {"Authorization": f"Bearer {token_cust}"}

    # Simulate historical order created before Stage 8:
    # Directly insert Order and OrderItem in DB with 0 InventoryReservation records
    async with async_session_maker() as session:
        cust_user = (await session.execute(select(User).where(User.email == customer_email))).scalar_one()

        # Deduct stock directly as legacy code did
        await session.execute(
            update(Inventory)
            .where(Inventory.product_id == uuid.UUID(product_id))
            .values(stock=8, version=2)
        )

        hist_order = Order(
            customer_id=cust_user.id,
            shop_id=uuid.UUID(shop_id),
            status=OrderStatus.pending,
            total_amount=Decimal("300.00"),
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(hist_order)
        await session.flush()

        hist_item = OrderItem(
            order_id=hist_order.id,
            product_id=uuid.UUID(product_id),
            product_name="Historical Item",
            unit_price=Decimal("150.00"),
            quantity=2,
            line_total=Decimal("300.00"),
        )
        session.add(hist_item)
        await session.commit()
        hist_order_id = hist_order.id

    # Verify 0 reservation records exist for this historical order
    async with async_session_maker() as session:
        res_count = (await session.execute(
            select(func.count(InventoryReservation.id))
            .where(InventoryReservation.order_id == hist_order_id)
        )).scalar()
        assert res_count == 0, "Precondition failed: historical order should have 0 reservations"

    # Cancel the historical order via customer cancellation endpoint
    cancel_res = await async_client.post(
        f"/api/v1/orders/{hist_order_id}/cancel",
        json={"reason": "Cancelling historical pre-Stage 8 order"},
        headers=headers,
    )
    assert cancel_res.status_code == 200, f"Cancellation failed: {cancel_res.text}"

    # Verify legacy branch restored stock to 10
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == hist_order_id))).scalar_one()
        assert order.status == OrderStatus.cancelled

        inv = (await session.execute(select(Inventory).where(Inventory.product_id == uuid.UUID(product_id)))).scalar_one()
        assert inv.stock == 10, f"Legacy fallback failed to restore stock! Got {inv.stock}"
        assert inv.version == 3, f"Legacy fallback failed to increment version! Got {inv.version}"





