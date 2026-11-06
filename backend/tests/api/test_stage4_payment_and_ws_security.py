"""
Stage 4 Test Suite: Payment Verification & WebSocket Security Hardening.

Covers:
1. Deterministic HMAC-SHA256 payment signature verification using server secret.
2. Rejection of invalid, tampered, or malformed payment signatures.
3. Server-side validation of order ownership, payable state, amount, and currency.
4. Idempotent payment confirmation with no duplicate transitions or events.
5. Unique provider payment ID collision handling returning 409 Conflict (not raw 500).
6. Production-mode blocking of mock payment operations.
7. Webhook HMAC-SHA256 signature verification and malformed payload handling.
8. WebSocket authentication rejection on missing or invalid JWT tokens (WS 1008).
9. WebSocket authorization rejection on non-participant users (WS 1008).
10. WebSocket frame-size limiting (>64KB rejected with WS 1009).
11. WebSocket inbound schema validation rejecting malformed JSON, unknown types, extra fields, and invalid coordinates.
12. WebSocket actor permission enforcement: only assigned rider can update location.
"""
import pytest
import uuid
import json
import subprocess
import sys
import time
import socket
import httpx
import websockets
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import engine, async_session_maker
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.product import Product
from app.models.order import Order, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.payment import Payment, PaymentStatus
from app.models.rider import RiderProfile
from app.services.payment_provider import (
    compute_mock_razorpay_signature,
    compute_mock_webhook_signature,
    get_payment_provider,
)

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
def live_ws_server():
    """Starts an ephemeral Uvicorn instance for real WebSocket protocol testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = False
    for _ in range(30):
        try:
            res = httpx.get(f"http://127.0.0.1:{port}/api/v1/health/live")
            if res.status_code == 200:
                started = True
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not started:
        proc.kill()
        pytest.fail("Failed to start live server for WebSocket tests")

    yield f"ws://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()

async def create_user_direct(role: UserRole = UserRole.customer) -> tuple[User, str]:
    """Helper to create a user directly in the database avoiding registration rate limits."""
    email = f"st4_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
    user_id = uuid.uuid4()
    async with async_session_maker() as session:
        user = User(
            id=user_id,
            email=email,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehashfortesting1234567890",
            name=f"Stage4 {role.value.capitalize()}",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
    token = create_access_token(str(user_id), role.value)
    return user, token

async def setup_stage4_order(price: float = 250.0) -> tuple[User, str, User, str, Shop, Product, Order]:
    """Creates a verified shop, product, customer, and a pending order for testing payments."""
    owner, owner_token = await create_user_direct(UserRole.shop_owner)
    customer, customer_token = await create_user_direct(UserRole.customer)

    async with async_session_maker() as session:
        shop = Shop(
            name=f"Stage4 Shop {uuid.uuid4().hex[:6]}",
            address="123 Market St",
            location="SRID=4326;POINT(77.5946 12.9716)",
            owner_id=owner.id,
            is_active=True,
            is_orderable=True,
            verification_status="verified",
        )
        session.add(shop)
        await session.flush()

        product = Product(
            name=f"Stage4 Item {uuid.uuid4().hex[:6]}",
            price=Decimal(str(price)),
            shop_id=shop.id,
            is_active=True,
        )
        session.add(product)
        await session.flush()

        order = Order(
            customer_id=customer.id,
            shop_id=shop.id,
            status=OrderStatus.pending,
            total_amount=Decimal(str(price)),
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        await session.refresh(shop)
        await session.refresh(product)

    return owner, owner_token, customer, customer_token, shop, product, order


# =====================================================================
# PAYMENT INTEGRITY & VERIFICATION TESTS
# =====================================================================

async def test_payment_verification_deterministic_hmac_sha256(async_client: AsyncClient):
    """Test valid payment confirmation with deterministic HMAC-SHA256 signature and order state synchronization."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(350.0)
    headers = {"Authorization": f"Bearer {customer_token}"}

    # 1. Initiate payment
    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers=headers)
    assert init_res.status_code == 200
    init_data = init_res.json()
    provider_order_id = init_data["provider_order_id"]

    # 2. Compute deterministic HMAC-SHA256 signature using server secret
    payment_id = f"pay_mock_{uuid.uuid4().hex[:8]}"
    valid_signature = compute_mock_razorpay_signature(provider_order_id, payment_id)

    verify_req = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_signature,
    }

    # 3. Verify payment
    verify_res = await async_client.post("/api/v1/payments/verify", json=verify_req, headers=headers)
    assert verify_res.status_code == 200
    res_data = verify_res.json()
    assert res_data["status"] == "captured"
    assert res_data["provider_payment_id"] == payment_id

    # 4. Assert order transitioned to confirmed
    async with async_session_maker() as session:
        refreshed_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert refreshed_order.status == OrderStatus.confirmed

        # Assert audit trail (OrderEvent) recorded the transition
        events = (await session.execute(
            select(OrderEvent).where(OrderEvent.order_id == order.id).order_by(OrderEvent.created_at)
        )).scalars().all()
        assert len(events) >= 1
        confirm_event = [e for e in events if e.to_state == OrderStatus.confirmed.value]
        assert len(confirm_event) == 1
        assert confirm_event[0].actor_role == "system"


async def test_payment_verification_invalid_signature_rejected(async_client: AsyncClient):
    """Test that mismatched or tampered HMAC-SHA256 signatures are rejected and marked failed."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(150.0)
    headers = {"Authorization": f"Bearer {customer_token}"}

    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers=headers)
    assert init_res.status_code == 200
    provider_order_id = init_res.json()["provider_order_id"]

    payment_id = f"pay_mock_{uuid.uuid4().hex[:8]}"
    # 64 hex characters but calculated with wrong secret
    tampered_sig = compute_mock_razorpay_signature(provider_order_id, payment_id, secret="wrong_secret_key")

    verify_req = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": tampered_sig,
    }

    verify_res = await async_client.post("/api/v1/payments/verify", json=verify_req, headers=headers)
    assert verify_res.status_code == 400
    assert "verification failed" in verify_res.json()["detail"].lower()

    # Verify payment status is failed and order remains pending
    async with async_session_maker() as session:
        payment = (await session.execute(select(Payment).where(Payment.provider_order_id == provider_order_id))).scalar_one()
        assert payment.status == PaymentStatus.failed
        assert payment.failure_reason == "Signature verification failed"

        refreshed_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert refreshed_order.status == OrderStatus.pending


async def test_payment_verification_malformed_signature_format(async_client: AsyncClient):
    """Test that malformed signature strings (non-hex, wrong length) are rejected with 400."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(100.0)
    headers = {"Authorization": f"Bearer {customer_token}"}

    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    # Test 1: Short string
    res1 = await async_client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": "pay_mock_123",
        "razorpay_signature": "short_sig",
    }, headers=headers)
    assert res1.status_code == 400

    # Test 2: 64 chars but non-hex
    res2 = await async_client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": "pay_mock_123",
        "razorpay_signature": "z" * 64,
    }, headers=headers)
    assert res2.status_code == 400


async def test_payment_verification_order_ownership_and_state(async_client: AsyncClient):
    """Test that unauthorized customer cannot verify another customer's payment."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(200.0)
    other_customer, other_token = await create_user_direct(UserRole.customer)

    # Initiate as customer
    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers={"Authorization": f"Bearer {customer_token}"})
    provider_order_id = init_res.json()["provider_order_id"]

    payment_id = f"pay_mock_{uuid.uuid4().hex[:8]}"
    valid_sig = compute_mock_razorpay_signature(provider_order_id, payment_id)

    # Attempt to verify using other_customer's token
    verify_res = await async_client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig,
    }, headers={"Authorization": f"Bearer {other_token}"})
    assert verify_res.status_code == 403
    assert "Not authorized" in verify_res.json()["detail"]


async def test_payment_verification_idempotency(async_client: AsyncClient):
    """Test that repeating an identical verification request returns 200 idempotently without duplicate side effects."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(500.0)
    headers = {"Authorization": f"Bearer {customer_token}"}

    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]
    payment_id = f"pay_mock_{uuid.uuid4().hex[:8]}"
    valid_sig = compute_mock_razorpay_signature(provider_order_id, payment_id)

    verify_payload = {
        "razorpay_order_id": provider_order_id,
        "razorpay_payment_id": payment_id,
        "razorpay_signature": valid_sig,
    }

    # First call -> 200 captured
    res1 = await async_client.post("/api/v1/payments/verify", json=verify_payload, headers=headers)
    assert res1.status_code == 200
    assert res1.json()["status"] == "captured"

    # Second call (idempotent repeat) -> 200 captured
    res2 = await async_client.post("/api/v1/payments/verify", json=verify_payload, headers=headers)
    assert res2.status_code == 200
    assert res2.json()["status"] == "captured"

    # Assert no duplicate OrderEvents were recorded
    async with async_session_maker() as session:
        events = (await session.execute(
            select(OrderEvent).where(OrderEvent.order_id == order.id, OrderEvent.to_state == OrderStatus.confirmed.value)
        )).scalars().all()
        assert len(events) == 1


async def test_payment_verification_duplicate_provider_payment_id_conflict(async_client: AsyncClient):
    """Test that attempting to reuse an already captured provider_payment_id returns 409 Conflict (not raw 500)."""
    owner1, owner1_token, customer1, customer1_token, shop1, product1, order1 = await setup_stage4_order(200.0)
    owner2, owner2_token, customer2, customer2_token, shop2, product2, order2 = await setup_stage4_order(200.0)
    headers1 = {"Authorization": f"Bearer {customer1_token}"}
    headers2 = {"Authorization": f"Bearer {customer2_token}"}

    # Initiate order 1
    init1 = (await async_client.post(f"/api/v1/orders/{order1.id}/payment", headers=headers1)).json()
    # Initiate order 2
    init2 = (await async_client.post(f"/api/v1/orders/{order2.id}/payment", headers=headers2)).json()

    shared_payment_id = f"pay_mock_shared_{uuid.uuid4().hex[:8]}"

    # Verify order 1 with shared_payment_id
    sig1 = compute_mock_razorpay_signature(init1["provider_order_id"], shared_payment_id)
    res1 = await async_client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": init1["provider_order_id"],
        "razorpay_payment_id": shared_payment_id,
        "razorpay_signature": sig1,
    }, headers=headers1)
    assert res1.status_code == 200

    # Attempt to verify order 2 with the SAME shared_payment_id -> must return 409 Conflict
    sig2 = compute_mock_razorpay_signature(init2["provider_order_id"], shared_payment_id)
    res2 = await async_client.post("/api/v1/payments/verify", json={
        "razorpay_order_id": init2["provider_order_id"],
        "razorpay_payment_id": shared_payment_id,
        "razorpay_signature": sig2,
    }, headers=headers2)
    assert res2.status_code == 409
    assert "already been used" in res2.json()["detail"] or "conflict" in res2.json()["detail"].lower()


async def test_payment_webhook_hmac_sha256_verification(async_client: AsyncClient):
    """Test webhook verification with valid and invalid HMAC-SHA256 signatures."""
    owner, owner_token, customer, customer_token, shop, product, order = await setup_stage4_order(300.0)
    headers = {"Authorization": f"Bearer {customer_token}"}

    # Initiate payment so a Payment record exists
    init_res = await async_client.post(f"/api/v1/orders/{order.id}/payment", headers=headers)
    provider_order_id = init_res.json()["provider_order_id"]

    payment_id = f"pay_mock_wh_{uuid.uuid4().hex[:8]}"
    webhook_payload = {
        "event": "payment.captured",
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": provider_order_id
                }
            }
        }
    }
    payload_bytes = json.dumps(webhook_payload).encode("utf-8")

    # 1. Invalid webhook signature -> 400
    bad_wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        content=payload_bytes,
        headers={"x-razorpay-signature": "0" * 64}
    )
    assert bad_wh_res.status_code == 400

    # 2. Valid webhook signature -> 200
    valid_wh_sig = compute_mock_webhook_signature(payload_bytes)
    good_wh_res = await async_client.post(
        "/api/v1/payments/webhook",
        content=payload_bytes,
        headers={"x-razorpay-signature": valid_wh_sig}
    )
    assert good_wh_res.status_code == 200

    # Assert order status confirmed via webhook
    async with async_session_maker() as session:
        refreshed_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert refreshed_order.status == OrderStatus.confirmed


async def test_mock_payment_blocked_in_production_without_flag():
    """Test that mock payment verification and webhook processing raise 500 when APP_ENV is production and ALLOW_MOCK_PAYMENTS is False."""
    orig_env = settings.APP_ENV
    orig_allow = settings.ALLOW_MOCK_PAYMENTS
    try:
        settings.APP_ENV = "production"
        settings.ALLOW_MOCK_PAYMENTS = False

        from app.services.payment_provider.razorpay import RazorpayPaymentProvider
        from fastapi import HTTPException

        # 1. Provider constructor guard
        with pytest.raises(HTTPException) as exc_init:
            RazorpayPaymentProvider()
        assert exc_init.value.status_code == 500
        assert "disabled in production" in str(exc_init.value.detail).lower()

        # 2. Method-level guards
        provider = object.__new__(RazorpayPaymentProvider)
        provider.key_id = "mock_key_id"
        provider.key_secret = "mock_secret"
        provider.webhook_secret = "mock_webhook"
        provider.is_mock = True

        with pytest.raises(HTTPException) as exc1:
            await provider.create_payment_order(100.0, "INR", "receipt-1")
        assert exc1.value.status_code == 500
        assert "disabled in production" in str(exc1.value.detail).lower()

        with pytest.raises(HTTPException) as exc2:
            await provider.verify_payment({
                "razorpay_order_id": "order_123",
                "razorpay_payment_id": "pay_123",
                "razorpay_signature": "0" * 64,
            })
        assert exc2.value.status_code == 500
        assert "disabled in production" in str(exc2.value.detail).lower()

        with pytest.raises(HTTPException) as exc3:
            await provider.verify_webhook(b'{"test": 1}', "0" * 64)
        assert exc3.value.status_code == 500
        assert "disabled in production" in str(exc3.value.detail).lower()
    finally:
        settings.APP_ENV = orig_env
        settings.ALLOW_MOCK_PAYMENTS = orig_allow


# =====================================================================
# WEBSOCKET SECURITY & FRAME HARDENING TESTS
# =====================================================================

async def setup_stage4_delivery():
    """Sets up a delivery, rider, shop, and order for WebSocket testing."""
    owner, owner_token = await create_user_direct(UserRole.shop_owner)
    customer, customer_token = await create_user_direct(UserRole.customer)
    rider_user, rider_token = await create_user_direct(UserRole.rider)

    async with async_session_maker() as session:
        shop = Shop(
            name=f"WS Shop {uuid.uuid4().hex[:6]}",
            address="456 Delivery Rd",
            location="SRID=4326;POINT(77.5946 12.9716)",
            owner_id=owner.id,
            is_active=True,
            is_orderable=True,
            verification_status="verified",
        )
        session.add(shop)
        await session.flush()

        order = Order(
            customer_id=customer.id,
            shop_id=shop.id,
            status=OrderStatus.confirmed,
            total_amount=Decimal("150.00"),
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(order)
        await session.flush()

        rider_profile = RiderProfile(
            user_id=rider_user.id,
            is_available=True,
            location="SRID=4326;POINT(77.5900 12.9700)",
        )
        session.add(rider_profile)
        await session.flush()

        delivery = Delivery(
            order_id=order.id,
            rider_id=rider_profile.id,
            status=DeliveryStatus.assigned,
            destination_location="SRID=4326;POINT(77.5980 12.9750)",
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)

    return customer, customer_token, rider_user, rider_token, delivery


async def test_websocket_authentication_missing_token(live_ws_server):
    """Test connecting without a token is rejected with WS 1008."""
    delivery_id = uuid.uuid4()
    try:
        async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery_id}"):
            pytest.fail("Should have been rejected")
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatus) as exc:
        if isinstance(exc, websockets.exceptions.ConnectionClosedError):
            assert exc.code == 1008


async def test_websocket_authentication_invalid_token(live_ws_server):
    """Test connecting with an invalid/forged JWT is rejected with WS 1008."""
    delivery_id = uuid.uuid4()
    try:
        async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery_id}?token=invalid.jwt.token"):
            pytest.fail("Should have been rejected")
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatus) as exc:
        if isinstance(exc, websockets.exceptions.ConnectionClosedError):
            assert exc.code == 1008


async def test_websocket_authorization_unauthorized_user(live_ws_server):
    """Test that a customer not associated with the delivery's order is rejected with WS 1008."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()
    other_customer, other_token = await create_user_direct(UserRole.customer)

    try:
        async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={other_token}"):
            pytest.fail("Should have been rejected")
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatus) as exc:
        if isinstance(exc, websockets.exceptions.ConnectionClosedError):
            assert exc.code == 1008


async def test_websocket_frame_size_limit_exceeded(live_ws_server):
    """Test that frames exceeding 64KB trigger immediate connection termination with WS 1009."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        ready = json.loads(await ws.recv())
        assert ready["event"] == "connection.ready"

        # Send frame > 64KB (65,536 bytes)
        huge_payload = json.dumps({"type": "ping", "data": "A" * 70000})
        await ws.send(huge_payload)

        with pytest.raises(websockets.exceptions.ConnectionClosedError) as exc_info:
            await ws.recv()
        assert exc_info.value.code == 1009


async def test_websocket_malformed_json_handling(live_ws_server):
    """Test that malformed JSON payloads return a structured error event without crashing the session."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        ready = json.loads(await ws.recv())
        assert ready["event"] == "connection.ready"

        # Send invalid JSON
        await ws.send("{not valid json}")
        err = json.loads(await ws.recv())
        assert err["event"] == "error"
        assert "invalid json" in err["message"].lower()

        # Connection remains alive for subsequent valid ping
        await ws.send(json.dumps({"type": "ping"}))
        pong = json.loads(await ws.recv())
        assert pong["event"] == "pong"


async def test_websocket_unknown_message_type_rejected(live_ws_server):
    """Test that messages with unknown 'type' return a structured error event."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        await ws.recv() # connection.ready

        await ws.send(json.dumps({"type": "unsupported_action"}))
        err = json.loads(await ws.recv())
        assert err["event"] == "error"
        assert "unknown message type" in err["message"].lower()


async def test_websocket_unsupported_protocol_version_rejected(live_ws_server):
    """Test that client specifying unsupported protocol version receives an error."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        await ws.recv() # connection.ready

        await ws.send(json.dumps({"type": "ping", "version": 99}))
        err = json.loads(await ws.recv())
        assert err["event"] == "error"
        assert "unsupported protocol version" in err["message"].lower()


async def test_websocket_strict_schema_forbids_extra_fields(live_ws_server):
    """Test that inbound messages with unexpected extra fields are rejected by Pydantic extra='forbid'."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        await ws.recv() # connection.ready

        # Send ping with extra forbidden field
        await ws.send(json.dumps({"type": "ping", "forged_admin_field": True}))
        err = json.loads(await ws.recv())
        assert err["event"] == "error"
        assert "invalid ping payload" in err["message"].lower()


async def test_websocket_location_update_coordinate_bounds(live_ws_server):
    """Test that coordinates outside valid latitude [-90, 90] and longitude [-180, 180] are rejected."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={rider_token}") as ws:
        await ws.recv() # connection.ready

        # Invalid latitude: 120.0
        await ws.send(json.dumps({"type": "location_update", "latitude": 120.0, "longitude": 77.59}))
        err1 = json.loads(await ws.recv())
        assert err1["event"] == "error"
        assert "invalid location update payload" in err1["message"].lower()

        # Invalid longitude: -210.0
        await ws.send(json.dumps({"type": "location_update", "latitude": 12.97, "longitude": -210.0}))
        err2 = json.loads(await ws.recv())
        assert err2["event"] == "error"
        assert "invalid location update payload" in err2["message"].lower()


async def test_websocket_location_update_unauthorized_actor(live_ws_server):
    """Test that non-rider participants (e.g. customer) cannot push location updates."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as ws:
        await ws.recv() # connection.ready

        # Customer attempts to send location update
        await ws.send(json.dumps({"type": "location_update", "latitude": 12.97, "longitude": 77.59}))
        err = json.loads(await ws.recv())
        assert err["event"] == "error"
        assert "only the assigned rider" in err["message"].lower()


async def test_websocket_location_update_assigned_rider_accepted(live_ws_server):
    """Test that the assigned rider can submit valid location updates and persist to database."""
    customer, customer_token, rider_user, rider_token, delivery = await setup_stage4_delivery()

    async with websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={customer_token}") as c_ws, \
               websockets.connect(f"{live_ws_server}/api/v1/ws/deliveries/{delivery.id}?token={rider_token}") as r_ws:
        await c_ws.recv()  # customer connection.ready
        await r_ws.recv()  # rider connection.ready

        # Send valid location update
        new_lat = 12.9725
        new_lng = 77.5950
        await r_ws.send(json.dumps({
            "type": "location_update",
            "version": 1,
            "latitude": new_lat,
            "longitude": new_lng,
        }))

        # Await real-time broadcast to ensure persistence and Redis pubsub completed
        broadcast_raw = await c_ws.recv()
        broadcast_msg = json.loads(broadcast_raw)
        assert broadcast_msg["event"] == "delivery.location_updated"
        assert broadcast_msg["data"]["latitude"] == new_lat
        assert broadcast_msg["data"]["longitude"] == new_lng

    # Verify that the rider's location was updated in the database
    async with async_session_maker() as session:
        from geoalchemy2.shape import to_shape
        rider_profile = (await session.execute(
            select(RiderProfile).where(RiderProfile.user_id == rider_user.id)
        )).scalar_one()
        assert rider_profile.location is not None
        pt = to_shape(rider_profile.location)
        assert pytest.approx(pt.y, abs=1e-4) == new_lat
        assert pytest.approx(pt.x, abs=1e-4) == new_lng
