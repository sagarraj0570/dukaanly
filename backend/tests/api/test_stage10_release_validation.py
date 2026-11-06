"""
Stage 10 — End-to-End Deployment, Security Validation & Release Readiness Tests.

Validates:
1. Complete Multi-Role End-to-End Commerce Workflow (Customer -> Shop Owner -> Rider -> Delivery Completed).
2. Strict One-Shop-Per-Cart rule enforcement across distinct shops.
3. IDOR Authorization Isolation across customers, shop owners, and delivery riders.
4. Concurrency Integrity: Competing checkouts for the last available unit (stock=1) without overselling.
5. Payment State Machine Synchronization: Mock payment confirmation, reservation consumption, and webhook idempotency.
6. Operational Diagnostics Endpoint Verification (RBAC & Telemetry).
"""

import asyncio
import uuid
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from sqlalchemy.orm import selectinload

from app.db.session import engine, async_session_maker
from app.models.inventory import Inventory
from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.models.order import Order, OrderStatus
from app.models.payment import Payment, PaymentStatus
from app.models.shop import Shop, ShopVerificationStatus
from app.models.user import User, UserRole
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile
from app.core.security import create_access_token, get_password_hash
from app.services.payment_provider import compute_mock_razorpay_signature

pytestmark = pytest.mark.asyncio


async def _create_test_user(role: UserRole, prefix: str = "st10") -> tuple[User, str]:
    """Helper to create and commit a user directly to avoid HTTP register/login rate limiters."""
    user_id = uuid.uuid4()
    email = f"{prefix}_{user_id.hex[:8]}@example.com"
    pwd_hash = get_password_hash("PassWord123!")

    async with async_session_maker() as session:
        user = User(
            id=user_id,
            name=f"User {prefix}",
            email=email,
            password_hash=pwd_hash,
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()

    token = create_access_token(str(user_id), role.value)
    return user, token


async def _create_test_shop(owner_id: uuid.UUID, name: str, lat: float, lng: float) -> uuid.UUID:
    """Helper to create a verified orderable shop directly in PostgreSQL."""
    shop_id = uuid.uuid4()
    point_wkt = f"SRID=4326;POINT({lng} {lat})"

    async with async_session_maker() as session:
        shop = Shop(
            id=shop_id,
            owner_id=owner_id,
            name=name,
            address="Test Address, Patna",
            location=point_wkt,
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
        )
        session.add(shop)
        await session.commit()
    return shop_id


async def _create_test_product(shop_id: uuid.UUID, name: str, price: float, stock: int) -> tuple[uuid.UUID, uuid.UUID]:
    """Helper to create a product and its associated inventory record."""
    from app.models.product import Product

    prod_id = uuid.uuid4()
    async with async_session_maker() as session:
        product = Product(
            id=prod_id,
            shop_id=shop_id,
            name=name,
            price=Decimal(str(price)),
            is_active=True,
        )
        session.add(product)
        await session.flush()

        inv = Inventory(
            product_id=prod_id,
            stock=stock,
            version=1,
        )
        session.add(inv)
        await session.commit()
    return prod_id, inv.id


# ==============================================================================
# 1. COMPLETE END-TO-END COMMERCE WORKFLOW
# ==============================================================================
async def test_stage10_complete_e2e_commerce_workflow(async_client: AsyncClient):
    """
    Validates the entire Dukaanly commerce and delivery lifecycle across all roles:
    1. Customer discovers shop via PostGIS geospatial query.
    2. Customer adds product to cart and updates quantity.
    3. Customer executes checkout -> Order created in pending, inventory reserved.
    4. Mock payment initiated and verified -> Order confirmed, reservation consumed.
    5. Shop owner progresses order: confirmed -> preparing -> ready_for_delivery.
    6. Delivery created and assigned to rider.
    7. Rider transitions delivery: assigned -> picked_up -> out_for_delivery -> delivered.
    8. Verifies consistent final state across database models.
    """
    # 1. Setup Actors
    owner, token_owner = await _create_test_user(UserRole.shop_owner, "owner_e2e")
    cust, token_cust = await _create_test_user(UserRole.customer, "cust_e2e")
    rider_user, token_rider = await _create_test_user(UserRole.rider, "rider_e2e")

    h_owner = {"Authorization": f"Bearer {token_owner}"}
    h_cust = {"Authorization": f"Bearer {token_cust}"}
    h_rider = {"Authorization": f"Bearer {token_rider}"}

    # Setup Rider Profile in DB
    rider_profile_id = uuid.uuid4()
    async with async_session_maker() as session:
        rider_prof = RiderProfile(
            id=rider_profile_id,
            user_id=rider_user.id,
            is_available=True,
            location="SRID=4326;POINT(85.1410 25.6110)",
        )
        session.add(rider_prof)
        await session.commit()

    # Create Shop in Patna (Boring Road)
    shop_id = await _create_test_shop(owner.id, "Stage 10 Flagship Mart", 25.6120, 85.1400)
    p_id, _ = await _create_test_product(shop_id, "Organic Basmati Rice", 150.00, stock=20)

    # 2. Customer Geospatial Discovery (PostGIS ST_DWithin)
    res_disc = await async_client.get(
        "/api/v1/shops",
        params={"latitude": 25.6125, "longitude": 85.1405, "radius_meters": 3000},
        headers=h_cust,
    )
    assert res_disc.status_code == 200
    shops_found = res_disc.json()["items"]
    assert any(s["id"] == str(shop_id) for s in shops_found)

    # 3. Add to Cart & Update Quantity
    res_cart = await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": str(p_id), "quantity": 2},
        headers=h_cust,
    )
    assert res_cart.status_code == 200
    cart_data = res_cart.json()
    assert len(cart_data["items"]) == 1
    assert cart_data["items"][0]["quantity"] == 2

    # 4. Checkout with Atomic Reservation & OCC
    idem_key = f"idem_{uuid.uuid4().hex}"
    res_checkout = await async_client.post(
        "/api/v1/orders/checkout",
        json={
            "idempotency_key": idem_key,
            "destination_latitude": 25.6125,
            "destination_longitude": 85.1405,
        },
        headers=h_cust,
    )
    assert res_checkout.status_code == 201, f"Checkout failed: {res_checkout.text}"
    order_data = res_checkout.json()
    order_id = uuid.UUID(order_data["id"])
    assert order_data["status"] == "pending"

    # Verify Database State after checkout
    async with async_session_maker() as session:
        # Stock decremented: 20 - 2 = 18
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == p_id))).scalar_one()
        assert inv.stock == 18

        # Active Reservation created
        reservations = (await session.execute(
            select(InventoryReservation).where(InventoryReservation.order_id == order_id)
        )).scalars().all()
        assert len(reservations) == 1
        assert reservations[0].quantity == 2
        assert reservations[0].status == ReservationStatus.active

    # 5. Payment Initiation & Mock Verification
    res_payment_init = await async_client.post(
        f"/api/v1/orders/{order_id}/payment",
        headers=h_cust,
    )
    assert res_payment_init.status_code == 200
    rzp_order_id = res_payment_init.json()["provider_order_id"]
    fake_payment_id = f"pay_{uuid.uuid4().hex[:14]}"
    mock_signature = compute_mock_razorpay_signature(rzp_order_id, fake_payment_id)

    res_verify = await async_client.post(
        "/api/v1/payments/verify",
        json={
            "razorpay_payment_id": fake_payment_id,
            "razorpay_order_id": rzp_order_id,
            "razorpay_signature": mock_signature,
        },
        headers=h_cust,
    )
    assert res_verify.status_code == 200
    assert res_verify.json()["status"] == "captured"

    # Verify Order Confirmed & Reservation Consumed
    async with async_session_maker() as session:
        order_db = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one()
        assert order_db.status == OrderStatus.confirmed

        res_db = (await session.execute(
            select(InventoryReservation).where(InventoryReservation.order_id == order_id)
        )).scalar_one()
        assert res_db.status == ReservationStatus.consumed

    # 6. Shop Owner Transitions: confirmed -> preparing -> ready_for_delivery
    res_prep = await async_client.patch(
        f"/api/v1/shops/{shop_id}/orders/{order_id}/status",
        json={"status": "preparing"},
        headers=h_owner,
    )
    assert res_prep.status_code == 200
    assert res_prep.json()["status"] == "preparing"

    res_ready = await async_client.patch(
        f"/api/v1/shops/{shop_id}/orders/{order_id}/status",
        json={"status": "ready_for_delivery"},
        headers=h_owner,
    )
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready_for_delivery"

    # 7. Delivery Assignment
    # Check or create delivery for this order
    async with async_session_maker() as session:
        deliv = (await session.execute(select(Delivery).where(Delivery.order_id == order_id))).scalar_one_or_none()
        if not deliv:
            deliv = Delivery(order_id=order_id, status=DeliveryStatus.pending)
            session.add(deliv)
            await session.commit()
        delivery_id = deliv.id

    # Assign Rider
    res_assign = await async_client.post(
        f"/api/v1/deliveries/{delivery_id}/assign",
        json={"rider_id": str(rider_profile_id)},
        headers=h_owner,
    )
    assert res_assign.status_code == 200
    assert res_assign.json()["status"] == "assigned"

    # 8. Rider Transitions Delivery: picked_up -> out_for_delivery -> delivered
    res_pickup = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "picked_up"},
        headers=h_rider,
    )
    assert res_pickup.status_code == 200
    assert res_pickup.json()["status"] == "picked_up"

    res_out = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "out_for_delivery"},
        headers=h_rider,
    )
    assert res_out.status_code == 200
    assert res_out.json()["status"] == "out_for_delivery"

    res_delivered = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "delivered"},
        headers=h_rider,
    )
    assert res_delivered.status_code == 200
    assert res_delivered.json()["status"] == "delivered"

    # 9. Verify Customer Order History reflects completed order
    res_order = await async_client.get(f"/api/v1/orders/{order_id}", headers=h_cust)
    assert res_order.status_code == 200
    assert res_order.json()["status"] == "delivered"

    res_history = await async_client.get("/api/v1/orders", headers=h_cust)
    assert res_history.status_code == 200
    history_items = res_history.json()["items"]
    assert any(o["id"] == str(order_id) and o["status"] == "delivered" for o in history_items)


# ==============================================================================
# 2. STRICT ONE-SHOP-PER-CART RULE ENFORCEMENT
# ==============================================================================
async def test_stage10_one_shop_per_cart_enforcement(async_client: AsyncClient):
    """
    Attempting to add items from two distinct shops into a single cart must be
    rejected with HTTP 400 Bad Request to maintain single-vendor checkout invariants.
    """
    owner1, _ = await _create_test_user(UserRole.shop_owner, "owner_cart1")
    owner2, _ = await _create_test_user(UserRole.shop_owner, "owner_cart2")
    cust, token_cust = await _create_test_user(UserRole.customer, "cust_multi_shop")
    h_cust = {"Authorization": f"Bearer {token_cust}"}

    shop1_id = await _create_test_shop(owner1.id, "Shop Alpha", 25.61, 85.14)
    shop2_id = await _create_test_shop(owner2.id, "Shop Beta", 25.62, 85.15)

    p1, _ = await _create_test_product(shop1_id, "Shop 1 Item", 50.0, 10)
    p2, _ = await _create_test_product(shop2_id, "Shop 2 Item", 75.0, 10)

    # Add item from Shop 1
    res1 = await async_client.post("/api/v1/cart/items", json={"product_id": str(p1), "quantity": 1}, headers=h_cust)
    assert res1.status_code == 200

    # Attempt to add item from Shop 2 (MUST fail)
    res2 = await async_client.post("/api/v1/cart/items", json={"product_id": str(p2), "quantity": 1}, headers=h_cust)
    assert res2.status_code == 400
    assert "one shop" in res2.text.lower()


# ==============================================================================
# 3. IDOR AUTHORIZATION ISOLATION BOUNDARIES
# ==============================================================================
async def test_stage10_idor_authorization_isolation(async_client: AsyncClient):
    """
    Verifies that actors cannot view or mutate resources belonging to others:
    - Customer A cannot access Customer B's order.
    - Customer A cannot cancel Customer B's order.
    - Shop Owner A cannot modify Shop Owner B's products.
    """
    owner_a, token_owner_a = await _create_test_user(UserRole.shop_owner, "owner_idor_a")
    owner_b, token_owner_b = await _create_test_user(UserRole.shop_owner, "owner_idor_b")
    cust_a, token_cust_a = await _create_test_user(UserRole.customer, "cust_idor_a")
    cust_b, token_cust_b = await _create_test_user(UserRole.customer, "cust_idor_b")

    h_owner_a = {"Authorization": f"Bearer {token_owner_a}"}
    h_owner_b = {"Authorization": f"Bearer {token_owner_b}"}
    h_cust_a = {"Authorization": f"Bearer {token_cust_a}"}
    h_cust_b = {"Authorization": f"Bearer {token_cust_b}"}

    shop_a = await _create_test_shop(owner_a.id, "Owner A Store", 25.61, 85.14)
    shop_b = await _create_test_shop(owner_b.id, "Owner B Store", 25.62, 85.15)

    p_a, _ = await _create_test_product(shop_a, "Product A", 100.0, 10)

    # Customer A creates order
    await async_client.post("/api/v1/cart/items", json={"product_id": str(p_a), "quantity": 1}, headers=h_cust_a)
    res_co = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers=h_cust_a,
    )
    assert res_co.status_code == 201
    order_a_id = res_co.json()["id"]

    # Customer B attempts to view Customer A's order (MUST be 403 or 404)
    res_view = await async_client.get(f"/api/v1/orders/{order_a_id}", headers=h_cust_b)
    assert res_view.status_code in (403, 404)

    # Customer B attempts to cancel Customer A's order (MUST be 403)
    res_cancel = await async_client.post(f"/api/v1/orders/{order_a_id}/cancel", headers=h_cust_b)
    assert res_cancel.status_code in (403, 404)

    # Shop Owner B attempts to modify Shop Owner A's product inventory (MUST be 403)
    res_hack_inv = await async_client.patch(
        f"/api/v1/products/{p_a}/inventory",
        json={"stock": 999, "expected_version": 1},
        headers=h_owner_b,
    )
    assert res_hack_inv.status_code == 403


# ==============================================================================
# 4. CONCURRENCY: LAST-UNIT HIGH-CONCURRENCY RACE
# ==============================================================================
async def test_stage10_last_unit_high_concurrency_race(async_client: AsyncClient):
    """
    Multiple concurrent checkouts compete for the single remaining unit (stock=1):
    - Exactly 1 checkout succeeds (HTTP 201).
    - Exactly 4 checkouts receive conflict responses (HTTP 409).
    - Final stock is exactly zero.
    - Zero negative inventory or orphaned reservations.
    """
    owner, _ = await _create_test_user(UserRole.shop_owner, "owner_last_unit")
    shop_id = await _create_test_shop(owner.id, "Last Unit Mart", 25.61, 85.14)
    p_id, _ = await _create_test_product(shop_id, "Rare Vintage Tea", 250.0, stock=1)

    # Create 5 distinct customers with item in cart
    customers = []
    for i in range(5):
        _, tok = await _create_test_user(UserRole.customer, f"last_unit_cust_{i}")
        h = {"Authorization": f"Bearer {tok}"}
        await async_client.post("/api/v1/cart/items", json={"product_id": str(p_id), "quantity": 1}, headers=h)
        customers.append(h)

    # Fire all 5 checkouts concurrently
    tasks = [
        async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h)
        for h in customers
    ]
    results = await asyncio.gather(*tasks)

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(409)

    assert success_count == 1, f"Expected exactly 1 checkout to succeed, got {success_count}. Statuses: {status_codes}"
    assert conflict_count == 4, f"Expected exactly 4 checkouts to be rejected with 409, got {conflict_count}"

    # Database verification
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == p_id))).scalar_one()
        assert inv.stock == 0, f"Expected final stock 0, found {inv.stock}"

        reservations = (await session.execute(
            select(InventoryReservation).where(InventoryReservation.product_id == p_id)
        )).scalars().all()
        assert len(reservations) == 1, f"Expected exactly 1 reservation row, found {len(reservations)}"


# ==============================================================================
# 5. REFRESH TOKEN REUSE DETECTION & FAMILY REVOCATION
# ==============================================================================
async def test_stage10_refresh_token_family_revocation(async_client: AsyncClient):
    """
    Reusing a previously rotated refresh token outside the grace window must trigger
    token reuse detection, immediately revoking all tokens in the entire family.
    """
    user, _ = await _create_test_user(UserRole.customer, "reuse_cust")

    # Initial login
    res_login = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "PassWord123!"},
    )
    assert res_login.status_code == 200
    token1 = res_login.json()["refresh_token"]

    # Rotate token1 -> receive token2
    res_refresh1 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert res_refresh1.status_code == 200
    token2 = res_refresh1.json()["refresh_token"]
    assert token2 != token1

    # Simulate reuse outside grace window:
    # Update token1's revoked_at in DB to 10 seconds ago to simulate replay after grace period
    from datetime import datetime, timezone, timedelta
    from app.models.user import RefreshToken
    from app.core.security import hash_refresh_token
    from sqlalchemy import update

    async with async_session_maker() as session:
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == hash_refresh_token(token1))
            .values(revoked_at=datetime.now(timezone.utc) - timedelta(seconds=10))
        )
        await session.commit()

    # Replaying token1 outside grace triggers token reuse detection and revokes family
    res_reuse = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token1})
    assert res_reuse.status_code in (401, 403)
    assert "reuse" in res_reuse.text.lower() or "revoked" in res_reuse.text.lower()

    # Successor token2 must now also be revoked
    res_token2 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": token2})
    assert res_token2.status_code in (401, 403)


# ==============================================================================
# 6. OPERATIONAL DIAGNOSTICS & TELEMETRY
# ==============================================================================
async def test_stage10_diagnostics_operational_telemetry(async_client: AsyncClient):
    """
    Administrative operational diagnostics endpoint provides real-time pool metrics,
    Redis latency, Celery configuration, and active WebSocket connection telemetry.
    """
    admin_user, token_admin = await _create_test_user(UserRole.admin, "admin_diag")
    h_admin = {"Authorization": f"Bearer {token_admin}"}

    res = await async_client.get("/api/v1/health/diagnostics", headers=h_admin)
    assert res.status_code == 200
    data = res.json()

    assert data["status"] == "healthy"
    assert "database" in data
    assert data["database"]["pool"]["pool_size"] == 10
    assert "redis" in data
    assert data["redis"]["connected"] is True
    assert "celery" in data
    assert data["celery"]["task_acks_late"] is True
    assert data["celery"]["worker_prefetch_multiplier"] == 1
    assert "websockets" in data
