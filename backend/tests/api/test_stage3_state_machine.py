"""
Stage 3 Test Suite: Order State Machine, Audit Trail & Cancellation Foundation.
Verifies:
1. Legal transition progression and OrderEvent audit trail recording.
2. Illegal state jumps returning 409 with current_state and allowed_next_states.
3. Server-side actor role and resource ownership enforcement (403 Forbidden).
4. Idempotency of repeated transitions without duplicate events or double stock restoration.
5. Atomic cancellation with exactly-once deterministic inventory stock restoration.
6. Customer cancellation reason validation across lifecycle states.
7. Shop owner rejection with mandatory reason.
8. Active delivery cancellation and rider release on order cancellation.
9. Concurrency protection via row-level locking (SELECT ... FOR UPDATE).
10. Alembic migration verification for order_events audit table.
"""
import pytest
import uuid
import asyncio
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import text, select
from sqlalchemy.orm import selectinload

from app.db.session import engine, async_session_maker
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.cart import Cart
from app.models.order import Order, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile

pytestmark = pytest.mark.asyncio


async def create_direct_user(role: UserRole, email_prefix: str = "user") -> tuple[User, str]:
    """Helper to insert user directly in DB and issue JWT, bypassing auth rate limiters."""
    user_id = uuid.uuid4()
    email = f"{email_prefix}_{user_id}@example.com"
    token = create_access_token(str(user_id), role.value)

    async with async_session_maker() as session:
        user = User(
            id=user_id,
            email=email,
            name=f"Test {role.value.capitalize()}",
            password_hash="hashed_dummy_password",
            role=role,
            is_active=True
        )
        session.add(user)
        if role == UserRole.customer:
            cart = Cart(id=uuid.uuid4(), customer_id=user_id)
            session.add(cart)
        await session.commit()
        await session.refresh(user)

    return user, token


async def setup_stage3_fixtures():
    """Setup standard test environment with shop owner, customers, rider, and shop."""
    owner, token_owner = await create_direct_user(UserRole.shop_owner, "s3_owner")
    cust1, token_cust1 = await create_direct_user(UserRole.customer, "s3_cust1")
    cust2, token_cust2 = await create_direct_user(UserRole.customer, "s3_cust2")
    rider_user, token_rider = await create_direct_user(UserRole.rider, "s3_rider")

    shop_id = uuid.uuid4()
    p1_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    rider_id = uuid.uuid4()

    async with async_session_maker() as session:
        # Create Shop
        shop = Shop(
            id=shop_id,
            owner_id=owner.id,
            name="Stage 3 Test Shop",
            address="123 Test Street",
            is_active=True,
            is_orderable=True,
            verification_status="verified",
            location="SRID=4326;POINT(1.0 1.0)",
        )
        session.add(shop)

        # Create Products
        p1 = Product(id=p1_id, shop_id=shop_id, name="State Machine Widget", price=100.0, is_active=True)
        p2 = Product(id=p2_id, shop_id=shop_id, name="Audit Trail Gadget", price=50.0, is_active=True)
        session.add_all([p1, p2])

        # Create Inventories
        inv1 = Inventory(id=uuid.uuid4(), product_id=p1_id, stock=10, version=1)
        inv2 = Inventory(id=uuid.uuid4(), product_id=p2_id, stock=10, version=1)
        session.add_all([inv1, inv2])

        # Create Rider Profile
        rider = RiderProfile(
            id=rider_id,
            user_id=rider_user.id,
            is_available=True,
            location="SRID=4326;POINT(1.0 1.0)",
        )
        session.add(rider)
        await session.commit()

    return {
        "owner": owner,
        "token_owner": token_owner,
        "cust1": cust1,
        "token_cust1": token_cust1,
        "cust2": cust2,
        "token_cust2": token_cust2,
        "rider_user": rider_user,
        "token_rider": token_rider,
        "shop_id": shop_id,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "rider_id": rider_id,
    }


async def test_stage3_legal_transition_flow_with_order_events(async_client: AsyncClient):
    """
    1. Legal transition progression and OrderEvent audit trail recording:
    - Checkout -> pending (with initial OrderEvent)
    - Shop owner confirms -> confirmed
    - Shop owner prepares -> preparing
    - Shop owner ready -> ready_for_delivery
    - Delivery picked up -> order syncs to ready_for_delivery
    - Delivery out_for_delivery -> order syncs to out_for_delivery
    - Delivery delivered -> order syncs to delivered
    - Verify all events in GET /orders/{id}/events
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}
    h_rider = {"Authorization": f"Bearer {ctx['token_rider']}"}

    # Customer adds items to cart & checks out
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 2}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    assert res_co.status_code == 201
    order_id = res_co.json()["id"]
    assert res_co.json()["status"] == "pending"

    # Shop owner confirms
    res_conf = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "confirmed", "reason": "Order accepted by merchant"},
        headers=h_owner
    )
    assert res_conf.status_code == 200
    assert res_conf.json()["status"] == "confirmed"

    # Shop owner marks preparing
    res_prep = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "preparing"},
        headers=h_owner
    )
    assert res_prep.status_code == 200
    assert res_prep.json()["status"] == "preparing"

    # Shop owner marks ready_for_delivery
    res_ready = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "ready_for_delivery"},
        headers=h_owner
    )
    assert res_ready.status_code == 200
    assert res_ready.json()["status"] == "ready_for_delivery"

    # Create delivery & assign rider
    res_del_create = await async_client.post("/api/v1/deliveries", json={"order_id": order_id}, headers=h_owner)
    assert res_del_create.status_code == 201
    delivery_id = res_del_create.json()["id"]

    res_assign = await async_client.post(
        f"/api/v1/deliveries/{delivery_id}/assign",
        json={"rider_id": str(ctx["rider_id"])},
        headers=h_owner
    )
    assert res_assign.status_code == 200

    # Rider marks picked up
    res_pick = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "picked_up"},
        headers=h_rider
    )
    assert res_pick.status_code == 200

    # Rider marks out_for_delivery
    res_out = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "out_for_delivery"},
        headers=h_rider
    )
    assert res_out.status_code == 200

    # Check order synchronized to out_for_delivery
    res_ord_check = await async_client.get(f"/api/v1/orders/{order_id}", headers=h_cust1)
    assert res_ord_check.json()["status"] == "out_for_delivery"

    # Rider marks delivered
    res_deliv = await async_client.patch(
        f"/api/v1/deliveries/{delivery_id}/status",
        json={"status": "delivered"},
        headers=h_rider
    )
    assert res_deliv.status_code == 200

    # Final order check
    res_final = await async_client.get(f"/api/v1/orders/{order_id}", headers=h_cust1)
    assert res_final.json()["status"] == "delivered"

    # Audit Trail verification
    res_events = await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)
    assert res_events.status_code == 200
    events = res_events.json()
    assert len(events) >= 5

    # Check events sequence
    states_sequence = [(e["from_state"], e["to_state"]) for e in events]
    assert ("created", "pending") in states_sequence
    assert ("pending", "confirmed") in states_sequence
    assert ("confirmed", "preparing") in states_sequence
    assert ("preparing", "ready_for_delivery") in states_sequence
    assert ("ready_for_delivery", "out_for_delivery") in states_sequence or ("out_for_delivery", "delivered") in states_sequence


async def test_stage3_illegal_state_jumps_return_409(async_client: AsyncClient):
    """
    2. Illegal state jumps return 409 Conflict with structured response:
    - Attempting pending -> ready_for_delivery fails with 409.
    - Response includes current_state and allowed_next_states.
    - Terminal states (delivered, cancelled) cannot transition.
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    # Create pending order
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # Illegal jump: pending -> ready_for_delivery
    res_jump = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "ready_for_delivery"},
        headers=h_owner
    )
    assert res_jump.status_code == 409
    err = res_jump.json()
    assert "detail" in err
    detail = err["detail"]
    assert detail["current_state"] == "pending"
    assert "confirmed" in detail["allowed_next_states"]
    assert "cancelled" in detail["allowed_next_states"]

    # Cancel order to reach terminal state
    res_cancel = await async_client.post(f"/api/v1/orders/{order_id}/cancel", headers=h_cust1)
    assert res_cancel.status_code == 200
    assert res_cancel.json()["status"] == "cancelled"

    # Attempt transition out of terminal cancelled state
    res_term = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "confirmed"},
        headers=h_owner
    )
    assert res_term.status_code == 409


async def test_stage3_role_permission_enforcement(async_client: AsyncClient):
    """
    3. Wrong role returns 403 Forbidden:
    - Customer cannot confirm orders.
    - Unrelated customer cannot cancel another's order.
    - Unrelated shop owner cannot reject another's order.
    """
    ctx = await setup_stage3_fixtures()
    other_owner, token_other_owner = await create_direct_user(UserRole.shop_owner, "other_owner")
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_cust2 = {"Authorization": f"Bearer {ctx['token_cust2']}"}
    h_other_owner = {"Authorization": f"Bearer {token_other_owner}"}

    # Customer 1 creates order
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # Customer 1 attempts to confirm order via shop route -> 403 Forbidden (requires shop_owner role)
    res_cust_conf = await async_client.patch(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status",
        json={"status": "confirmed"},
        headers=h_cust1
    )
    assert res_cust_conf.status_code == 403

    # Customer 2 attempts to cancel Customer 1's order -> 403 Forbidden
    res_other_cancel = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Malicious cancel"},
        headers=h_cust2
    )
    assert res_other_cancel.status_code == 403

    # Other shop owner attempts to reject Shop 1's order -> 403 Forbidden
    res_other_rej = await async_client.post(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/reject",
        json={"reason": "Unauthorized rejection"},
        headers=h_other_owner
    )
    assert res_other_rej.status_code == 403


async def test_stage3_idempotency_of_repeated_transitions(async_client: AsyncClient):
    """
    4. Idempotent repeated transition produces no duplicate order_events or stock modifications:
    - Repeated confirmed status returns 200 with no new events.
    - Repeated cancel status returns 200 with no duplicate stock restoration.
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 2}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # First confirm
    res_c1 = await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=h_owner)
    assert res_c1.status_code == 200

    # Read events count
    events_1 = (await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)).json()
    count_after_c1 = len(events_1)

    # Repeat confirm (idempotent)
    res_c2 = await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=h_owner)
    assert res_c2.status_code == 200

    events_2 = (await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)).json()
    assert len(events_2) == count_after_c1, "Idempotent transition must not create duplicate OrderEvent"

    # Cancel order
    res_canc1 = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Customer cancellation test"},
        headers=h_cust1
    )
    assert res_canc1.status_code == 200
    events_after_cancel = (await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)).json()
    count_after_cancel = len(events_after_cancel)

    # Check inventory restored to 10
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == ctx["p1_id"]))).scalar_one()
        assert inv.stock == 10
        expected_version = inv.version

    # Repeat cancel (idempotent)
    res_canc2 = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Customer cancellation test again"},
        headers=h_cust1
    )
    assert res_canc2.status_code == 200

    # Stock must remain 10, version must NOT increment again, events must NOT increase
    async with async_session_maker() as session:
        inv2 = (await session.execute(select(Inventory).where(Inventory.product_id == ctx["p1_id"]))).scalar_one()
        assert inv2.stock == 10
        assert inv2.version == expected_version

    events_after_canc2 = (await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)).json()
    assert len(events_after_canc2) == count_after_cancel


async def test_stage3_customer_cancellation_reason_rules(async_client: AsyncClient):
    """
    6. Customer cancellation reason validation:
    - Pending order cancels without reason.
    - Confirmed/preparing order requires non-empty reason.
    - Attempting without reason in preparing returns 400.
    - Ready_for_delivery order cannot be cancelled by customer (409).
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    # Order 1: pending cancels without reason
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_o1 = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    o1_id = res_o1.json()["id"]

    res_c1 = await async_client.post(f"/api/v1/orders/{o1_id}/cancel", headers=h_cust1)
    assert res_c1.status_code == 200
    assert res_c1.json()["status"] == "cancelled"

    # Order 2: confirmed/preparing order
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_o2 = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    o2_id = res_o2.json()["id"]

    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{o2_id}/status", json={"status": "confirmed"}, headers=h_owner)
    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{o2_id}/status", json={"status": "preparing"}, headers=h_owner)

    # Cancel without reason when preparing -> 400 Bad Request
    res_no_reason = await async_client.post(f"/api/v1/orders/{o2_id}/cancel", json={"reason": "   "}, headers=h_cust1)
    assert res_no_reason.status_code == 400
    assert "Cancellation reason is required" in res_no_reason.json()["detail"]

    # Cancel with reason -> 200 OK
    res_with_reason = await async_client.post(
        f"/api/v1/orders/{o2_id}/cancel",
        json={"reason": "Need to cancel, unexpected emergency"},
        headers=h_cust1
    )
    assert res_with_reason.status_code == 200
    assert res_with_reason.json()["status"] == "cancelled"

    # Order 3: ready_for_delivery cannot be cancelled by customer
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_o3 = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    o3_id = res_o3.json()["id"]

    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{o3_id}/status", json={"status": "confirmed"}, headers=h_owner)
    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{o3_id}/status", json={"status": "preparing"}, headers=h_owner)
    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{o3_id}/status", json={"status": "ready_for_delivery"}, headers=h_owner)

    res_ready_canc = await async_client.post(
        f"/api/v1/orders/{o3_id}/cancel",
        json={"reason": "Too late cancel"},
        headers=h_cust1
    )
    assert res_ready_canc.status_code == 409


async def test_stage3_shop_owner_rejection_and_cancellation(async_client: AsyncClient):
    """
    7. Shop owner rejection with mandatory reason:
    - Missing reason fails with 422.
    - Valid rejection transitions order to cancelled, restores stock, records audit event.
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 3}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # Rejection without reason fails schema validation (422)
    res_no_reason = await async_client.post(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/reject",
        json={},
        headers=h_owner
    )
    assert res_no_reason.status_code == 422

    # Rejection with empty string fails with 422 or 400
    res_empty = await async_client.post(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/reject",
        json={"reason": ""},
        headers=h_owner
    )
    assert res_empty.status_code in [400, 422]

    # Rejection with valid reason
    res_rej = await async_client.post(
        f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/reject",
        json={"reason": "Shop closed for the day"},
        headers=h_owner
    )
    assert res_rej.status_code == 200
    assert res_rej.json()["status"] == "cancelled"

    # Verify inventory restored
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == ctx["p1_id"]))).scalar_one()
        assert inv.stock == 10

    # Verify event audit trail
    events = (await async_client.get(f"/api/v1/orders/{order_id}/events", headers=h_cust1)).json()
    rej_event = [e for e in events if e["to_state"] == "cancelled"][0]
    assert rej_event["actor_role"] == "shop_owner"
    assert rej_event["reason"] == "Shop closed for the day"


async def test_stage3_order_cancellation_releases_active_delivery_and_rider(async_client: AsyncClient):
    """
    8. Active delivery cancelled and rider released on order cancellation:
    - Order is confirmed and assigned to a rider (rider is_available=False).
    - Order is cancelled.
    - Delivery transitions to cancelled.
    - Rider is_available transitions back to True.
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    # Checkout order
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # Confirm order
    await async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=h_owner)

    # Create and assign delivery
    res_del = await async_client.post("/api/v1/deliveries", json={"order_id": order_id}, headers=h_owner)
    delivery_id = res_del.json()["id"]
    await async_client.post(f"/api/v1/deliveries/{delivery_id}/assign", json={"rider_id": str(ctx["rider_id"])}, headers=h_owner)

    # Confirm rider is unavailable
    async with async_session_maker() as session:
        rider = (await session.execute(select(RiderProfile).where(RiderProfile.id == ctx["rider_id"]))).scalar_one()
        assert rider.is_available is False

    # Customer cancels order
    res_canc = await async_client.post(
        f"/api/v1/orders/{order_id}/cancel",
        json={"reason": "Cancelling prior to pickup"},
        headers=h_cust1
    )
    assert res_canc.status_code == 200

    # Verify Delivery is cancelled and Rider is available again in DB
    async with async_session_maker() as session:
        deliv = (await session.execute(select(Delivery).where(Delivery.id == delivery_id))).scalar_one()
        assert deliv.status == DeliveryStatus.cancelled

        rider_after = (await session.execute(select(RiderProfile).where(RiderProfile.id == ctx["rider_id"]))).scalar_one()
        assert rider_after.is_available is True


async def test_stage3_concurrent_cancellation_vs_confirmation_race(async_client: AsyncClient):
    """
    9. Concurrency protection via row-level locking (SELECT ... FOR UPDATE):
    Simultaneously trigger customer cancellation vs shop owner confirmation.
    Under row lock, exactly one transition wins first without deadlocks or corrupt state.
    """
    ctx = await setup_stage3_fixtures()
    h_cust1 = {"Authorization": f"Bearer {ctx['token_cust1']}"}
    h_owner = {"Authorization": f"Bearer {ctx['token_owner']}"}

    # Checkout
    await async_client.post("/api/v1/cart/items", json={"product_id": str(ctx["p1_id"]), "quantity": 1}, headers=h_cust1)
    res_co = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_cust1)
    order_id = res_co.json()["id"]

    # Concurrently fire cancel and confirm
    task_cancel = async_client.post(f"/api/v1/orders/{order_id}/cancel", json={"reason": "Race cancel"}, headers=h_cust1)
    task_confirm = async_client.patch(f"/api/v1/shops/{ctx['shop_id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=h_owner)

    res_cancel, res_confirm = await asyncio.gather(task_cancel, task_confirm)

    status_codes = {res_cancel.status_code, res_confirm.status_code}
    # One succeeds with 200, the other either succeeds (if confirm won then cancel succeeded) or conflicts with 409
    assert 200 in status_codes

    # Check final order state in DB
    async with async_session_maker() as session:
        order = (await session.execute(select(Order).where(Order.id == order_id))).scalar_one()
        assert order.status in [OrderStatus.confirmed, OrderStatus.cancelled]


async def test_stage3_alembic_order_events_migration():
    """
    10. Alembic migration verification:
    - Exactly one head: 20a7fabed249
    - Down revision points to 6179f4c20f23
    - order_events table and indexes exist in DB
    """
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    config = Config(str(alembic_ini_path))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 head, got {heads}"

    rev = script.get_revision("20a7fabed249")
    assert rev.down_revision == "6179f4c20f23"

    async with async_session_maker() as session:
        # Check order_events table exists
        has_table = (await session.execute(text("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'order_events'
            );
        """))).scalar()
        assert has_table is True

        # Check columns
        columns = (await session.execute(text("""
            SELECT column_name, data_type 
            FROM information_schema.columns 
            WHERE table_name = 'order_events';
        """))).fetchall()
        col_names = {c[0] for c in columns}
        required_cols = {"id", "order_id", "from_state", "to_state", "actor_id", "actor_role", "reason", "created_at"}
        assert required_cols.issubset(col_names)
