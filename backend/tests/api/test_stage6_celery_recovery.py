"""
Dukaanly Stage 6: Celery Timeout Jobs & Order/Delivery Recovery Test Suite.

Verifies:
1. Celery task discovery and Celery Beat schedule configuration.
2. Eligible vs ineligible timeout candidates (pending orders, confirmed orders, assigned deliveries).
3. Exact timeout boundary enforcement.
4. Idempotency: repeated task execution yields zero duplicate side effects.
5. Concurrency: multiple workers racing on the same records with row-level locks (SELECT ... FOR UPDATE).
6. Strict protection of in-progress deliveries (picked_up, out_for_delivery, delivered).
7. Safe delivery reassignment: previous rider release, partial unique index compliance,
   replacement delivery creation, and atomic PostGIS reassignment.
8. Stock restoration exactly-once semantics and OrderEvent audit trail recording.
"""
import asyncio
import uuid
from datetime import datetime, timezone, timedelta
from decimal import Decimal
import pytest
from httpx import AsyncClient
from sqlalchemy import select, text
from geoalchemy2.shape import from_shape
from shapely.geometry import Point

from app.core import security
from app.core.celery_app import celery_app
from app.core.config import settings
from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.payment import Payment, PaymentStatus
from app.models.rider import RiderProfile
from app.tasks.order_recovery import (
    _reconcile_stale_pending_orders_async,
    _reconcile_stale_unaccepted_orders_async,
    _reconcile_stale_deliveries_async,
    reconcile_stale_pending_orders,
    reconcile_stale_unaccepted_orders,
    reconcile_stale_deliveries,
)
from app.services.state_machine import transition_order

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixture Helpers
# ---------------------------------------------------------------------------

async def create_stage6_user(role: UserRole = UserRole.customer, prefix: str = "s6") -> User:
    async with async_session_maker() as session:
        uid = uuid.uuid4()
        user = User(
            id=uid,
            name=f"User {uid.hex[:6]}",
            email=f"{prefix}_{uid.hex[:8]}@example.com",
            phone_number=f"+91{uid.int % 10000000000:010d}",
            password_hash=security.get_password_hash("ValidPass123!"),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


async def setup_stage6_fixtures():
    """Creates a verified shop, active products, inventory, customer, and riders."""
    owner = await create_stage6_user(UserRole.shop_owner, "s6_owner")
    customer = await create_stage6_user(UserRole.customer, "s6_cust")
    rider_user1 = await create_stage6_user(UserRole.rider, "s6_rider1")
    rider_user2 = await create_stage6_user(UserRole.rider, "s6_rider2")

    shop_id = uuid.uuid4()
    p1_id = uuid.uuid4()
    p2_id = uuid.uuid4()
    rider1_id = uuid.uuid4()
    rider2_id = uuid.uuid4()

    # Patna coordinates (consistent with project geospatial fixtures)
    patna_lat, patna_lon = 25.5941, 85.1376

    async with async_session_maker() as session:
        shop = Shop(
            id=shop_id,
            owner_id=owner.id,
            name="Stage 6 Express Mart",
            address="Station Road, Patna",
            is_active=True,
            is_orderable=True,
            verification_status=ShopVerificationStatus.verified,
            location=f"SRID=4326;POINT({patna_lon} {patna_lat})",
        )
        session.add(shop)

        p1 = Product(id=p1_id, shop_id=shop_id, name="Recovery Bread", price=40.0, is_active=True)
        p2 = Product(id=p2_id, shop_id=shop_id, name="Recovery Milk", price=30.0, is_active=True)
        session.add_all([p1, p2])

        inv1 = Inventory(id=uuid.uuid4(), product_id=p1_id, stock=50, version=1)
        inv2 = Inventory(id=uuid.uuid4(), product_id=p2_id, stock=50, version=1)
        session.add_all([inv1, inv2])

        # Rider 1 (unresponsive rider who will time out)
        r1 = RiderProfile(
            id=rider1_id,
            user_id=rider_user1.id,
            is_available=False,  # currently busy with assignment
            location=f"SRID=4326;POINT({patna_lon + 0.001} {patna_lat + 0.001})",
            location_updated_at=datetime.now(timezone.utc),
        )
        # Rider 2 (available nearby replacement candidate)
        r2 = RiderProfile(
            id=rider2_id,
            user_id=rider_user2.id,
            is_available=True,
            location=f"SRID=4326;POINT({patna_lon + 0.002} {patna_lat + 0.002})",
            location_updated_at=datetime.now(timezone.utc),
        )
        session.add_all([r1, r2])
        await session.commit()

    return {
        "owner": owner,
        "customer": customer,
        "shop_id": shop_id,
        "p1_id": p1_id,
        "p2_id": p2_id,
        "rider1_id": rider1_id,
        "rider2_id": rider2_id,
        "patna_lat": patna_lat,
        "patna_lon": patna_lon,
    }


async def create_test_order(
    customer_id: uuid.UUID,
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    status: OrderStatus = OrderStatus.pending,
    age_seconds: int = 1200,
    quantity: int = 2,
    price: float = 40.0,
) -> Order:
    """Helper to insert an order with historical created_at and items."""
    async with async_session_maker() as session:
        created_time = datetime.now(timezone.utc) - timedelta(seconds=age_seconds)
        order_id = uuid.uuid4()
        total = Decimal(str(price * quantity))

        order = Order(
            id=order_id,
            customer_id=customer_id,
            shop_id=shop_id,
            status=status,
            total_amount=total,
            created_at=created_time,
            updated_at=created_time,
        )
        session.add(order)

        item = OrderItem(
            id=uuid.uuid4(),
            order_id=order_id,
            product_id=product_id,
            product_name="Test Product",
            unit_price=Decimal(str(price)),
            quantity=quantity,
            line_total=total,
        )
        session.add(item)

        initial_event = OrderEvent(
            id=uuid.uuid4(),
            order_id=order_id,
            from_state="created",
            to_state=status.value,
            actor_role="system",
            reason="Test order initial creation",
            created_at=created_time,
        )
        session.add(initial_event)

        # Invariant: Pending order has reserved inventory stock
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == product_id))).scalar_one()
        inv.stock -= quantity
        session.add(inv)

        await session.commit()
        await session.refresh(order)
        return order


# ---------------------------------------------------------------------------
# 1. Celery Task Discovery and Beat Schedules
# ---------------------------------------------------------------------------

async def test_celery_task_discovery_and_beat_schedules():
    """Verify Celery app discovers recovery tasks and registers beat schedules."""
    celery_app.loader.import_default_modules()
    registered = celery_app.tasks.keys()

    assert "reconcile_stale_pending_orders" in registered
    assert "reconcile_stale_unaccepted_orders" in registered
    assert "reconcile_stale_deliveries" in registered

    schedules = celery_app.conf.beat_schedule
    assert "reconcile-stale-pending-orders-every-minute" in schedules
    assert "reconcile-stale-unaccepted-orders-every-two-minutes" in schedules
    assert "reconcile-stale-deliveries-every-minute" in schedules

    assert schedules["reconcile-stale-pending-orders-every-minute"]["task"] == "reconcile_stale_pending_orders"
    assert schedules["reconcile-stale-unaccepted-orders-every-two-minutes"]["task"] == "reconcile_stale_unaccepted_orders"
    assert schedules["reconcile-stale-deliveries-every-minute"]["task"] == "reconcile_stale_deliveries"


# ---------------------------------------------------------------------------
# 2. Stale Pending Order Timeout & Deterministic Stock Restoration
# ---------------------------------------------------------------------------

async def test_stale_pending_order_auto_cancellation_and_stock_restoration():
    """Pending orders older than the timeout are auto-cancelled with exact stock restoration."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=1200, quantity=3  # 20 mins old
    )

    # Initial stock before recovery (50 - 3 = 47)
    async with async_session_maker() as session:
        inv_before = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        assert inv_before.stock == 47
        version_before = inv_before.version

        # Add uncaptured pending payment record
        pay = Payment(
            order_id=order.id,
            provider="razorpay",
            provider_order_id=f"order_{uuid.uuid4().hex[:8]}",
            amount=120.0,
            currency="INR",
            status=PaymentStatus.created,
        )
        session.add(pay)
        await session.commit()

    # Run pending recovery
    cancelled_count = await _reconcile_stale_pending_orders_async(cutoff_seconds=900)
    assert cancelled_count >= 1

    # Invariant: Order is cancelled, stock is restored to 50, version incremented
    async with async_session_maker() as session:
        refreshed_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert refreshed_order.status == OrderStatus.cancelled

        inv_after = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        assert inv_after.stock == 50
        assert inv_after.version == version_before + 1

        # Verify payment status was cancelled
        pay_after = (await session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
        assert pay_after.status == PaymentStatus.cancelled

        # Verify OrderEvent audit entry
        events = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == order.id))).scalars().all()
        cancel_event = [e for e in events if e.to_state == "cancelled"]
        assert len(cancel_event) == 1
        assert cancel_event[0].actor_role == "system"
        assert "timeout exceeded" in cancel_event[0].reason


# ---------------------------------------------------------------------------
# 3. Ineligible Pending Orders Not Cancelled (Recent & Captured Payment)
# ---------------------------------------------------------------------------

async def test_ineligible_pending_order_protected():
    """Recent pending orders (< timeout) are never cancelled."""
    f = await setup_stage6_fixtures()
    recent_order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=120, quantity=2  # 2 mins old
    )

    cancelled_count = await _reconcile_stale_pending_orders_async(cutoff_seconds=900)

    async with async_session_maker() as session:
        refreshed = (await session.execute(select(Order).where(Order.id == recent_order.id))).scalar_one()
        assert refreshed.status == OrderStatus.pending


async def test_captured_payment_pending_order_protected():
    """An order with a captured payment is never cancelled by the pending recovery job."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=1200, quantity=2
    )

    async with async_session_maker() as session:
        pay = Payment(
            order_id=order.id,
            provider="razorpay",
            provider_order_id=f"order_{uuid.uuid4().hex[:8]}",
            provider_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
            amount=80.0,
            currency="INR",
            status=PaymentStatus.captured,
            paid_at=datetime.now(timezone.utc),
        )
        session.add(pay)
        await session.commit()

    await _reconcile_stale_pending_orders_async(cutoff_seconds=900)

    async with async_session_maker() as session:
        refreshed = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert refreshed.status == OrderStatus.pending, "Order with captured payment must not be auto-cancelled"


# ---------------------------------------------------------------------------
# 4. Exact Timeout Boundary Behavior
# ---------------------------------------------------------------------------

async def test_timeout_exact_boundary_enforcement():
    """Verify boundary condition: orders inside cutoff are preserved; orders past cutoff are cancelled."""
    f = await setup_stage6_fixtures()
    # Order A: 890 seconds old (inside 900s timeout)
    order_inside = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=890, quantity=1
    )
    # Order B: 910 seconds old (past 900s timeout)
    order_past = await create_test_order(
        f["customer"].id, f["shop_id"], f["p2_id"],
        status=OrderStatus.pending, age_seconds=910, quantity=1
    )

    await _reconcile_stale_pending_orders_async(cutoff_seconds=900)

    async with async_session_maker() as session:
        ord_inside = (await session.execute(select(Order).where(Order.id == order_inside.id))).scalar_one()
        ord_past = (await session.execute(select(Order).where(Order.id == order_past.id))).scalar_one()

        assert ord_inside.status == OrderStatus.pending
        assert ord_past.status == OrderStatus.cancelled


# ---------------------------------------------------------------------------
# 5. Stale Unaccepted Confirmed Order Cancellation & Refund
# ---------------------------------------------------------------------------

async def test_stale_unaccepted_confirmed_order_cancellation_and_refund():
    """Confirmed order unaccepted by shop owner beyond timeout is cancelled, stock restored, payment marked refunded."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.confirmed, age_seconds=2400, quantity=4  # 40 mins old
    )

    async with async_session_maker() as session:
        pay = Payment(
            order_id=order.id,
            provider="razorpay",
            provider_order_id=f"order_{uuid.uuid4().hex[:8]}",
            provider_payment_id=f"pay_{uuid.uuid4().hex[:8]}",
            amount=160.0,
            currency="INR",
            status=PaymentStatus.captured,
            paid_at=datetime.now(timezone.utc),
        )
        session.add(pay)
        # Pending delivery created when order was confirmed
        deliv = Delivery(order_id=order.id, status=DeliveryStatus.pending)
        session.add(deliv)
        await session.commit()

    cancelled = await _reconcile_stale_unaccepted_orders_async(cutoff_seconds=1800)
    assert cancelled >= 1

    async with async_session_maker() as session:
        ord_ref = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert ord_ref.status == OrderStatus.cancelled

        # Payment refunded (explicit simulated mock refund indication)
        pay_ref = (await session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
        assert pay_ref.status == PaymentStatus.refunded
        assert "Simulated mock refund" in (pay_ref.failure_reason or "")

        # Delivery cancelled
        del_ref = (await session.execute(select(Delivery).where(Delivery.order_id == order.id))).scalar_one()
        assert del_ref.status == DeliveryStatus.cancelled


# ---------------------------------------------------------------------------
# 6. Progressed Deliveries Strictly Protected (Never Cancelled)
# ---------------------------------------------------------------------------

async def test_progressed_deliveries_strictly_protected():
    """Confirmed orders whose delivery is picked_up or out_for_delivery are strictly protected from auto-cancellation."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.confirmed, age_seconds=3600, quantity=1
    )

    async with async_session_maker() as session:
        deliv = Delivery(
            order_id=order.id,
            rider_id=f["rider1_id"],
            status=DeliveryStatus.picked_up,
            picked_up_at=datetime.now(timezone.utc) - timedelta(minutes=10),
        )
        session.add(deliv)
        await session.commit()

    await _reconcile_stale_unaccepted_orders_async(cutoff_seconds=1800)

    async with async_session_maker() as session:
        ord_ref = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert ord_ref.status == OrderStatus.confirmed, "Order with picked up delivery must NOT be cancelled"


# ---------------------------------------------------------------------------
# 7. Stale Delivery Assignment Reconciliation & Safe Reassignment
# ---------------------------------------------------------------------------

async def test_stale_delivery_assignment_releases_rider_and_reassigns():
    """Stale assigned delivery frees unresponsive rider, preserves indexes, and reassigns nearby available candidate."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.ready_for_delivery, age_seconds=1800, quantity=1
    )

    stale_assigned_time = datetime.now(timezone.utc) - timedelta(minutes=25)
    dest_geom = f"SRID=4326;POINT({f['patna_lon']} {f['patna_lat']})"

    async with async_session_maker() as session:
        stale_deliv = Delivery(
            order_id=order.id,
            rider_id=f["rider1_id"],
            status=DeliveryStatus.assigned,
            assigned_at=stale_assigned_time,
            picked_up_at=None,
            destination_location=dest_geom,
        )
        session.add(stale_deliv)
        await session.commit()
        stale_deliv_id = stale_deliv.id

    # Verify Rider 1 is currently unavailable and Rider 2 is available
    async with async_session_maker() as session:
        r1 = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider1_id"]))).scalar_one()
        r2 = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider2_id"]))).scalar_one()
        assert r1.is_available is False
        assert r2.is_available is True

    # Run delivery recovery
    reassigned_count = await _reconcile_stale_deliveries_async(cutoff_seconds=900)
    assert reassigned_count >= 1

    async with async_session_maker() as session:
        # 1. Stale delivery is cancelled
        old_del = (await session.execute(select(Delivery).where(Delivery.id == stale_deliv_id))).scalar_one()
        assert old_del.status == DeliveryStatus.cancelled

        # 2. Previous Rider 1 is released and is now available
        r1_ref = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider1_id"]))).scalar_one()
        assert r1_ref.is_available is True

        # 3. New replacement delivery exists for the same order
        new_del = (
            await session.execute(
                select(Delivery).where(
                    Delivery.order_id == order.id,
                    Delivery.id != stale_deliv_id,
                )
            )
        ).scalar_one()

        # 4. Replacement delivery was atomically assigned to Rider 2 via PostGIS discovery
        assert new_del.status == DeliveryStatus.assigned
        assert new_del.rider_id == f["rider2_id"]

        # 5. Rider 2 is now marked unavailable
        r2_ref = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider2_id"]))).scalar_one()
        assert r2_ref.is_available is False

        # 6. Database partial unique indexes verified intact: exactly one active delivery per order & per rider
        active_order_dels = (
            await session.execute(
                select(Delivery).where(
                    Delivery.order_id == order.id,
                    Delivery.status.in_([DeliveryStatus.pending, DeliveryStatus.assigned, DeliveryStatus.picked_up]),
                )
            )
        ).scalars().all()
        assert len(active_order_dels) == 1

        active_r2_dels = (
            await session.execute(
                select(Delivery).where(
                    Delivery.rider_id == f["rider2_id"],
                    Delivery.status.in_([DeliveryStatus.assigned, DeliveryStatus.picked_up]),
                )
            )
        ).scalars().all()
        assert len(active_r2_dels) == 1


# ---------------------------------------------------------------------------
# 8. Idempotency: Repeated Execution Yields Zero Duplicate Side Effects
# ---------------------------------------------------------------------------

async def test_repeated_task_execution_idempotency():
    """Running recovery tasks multiple times on the same data produces zero duplicate cancellations or restorations."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=1500, quantity=5
    )

    # First run: cancels 1 order and restores stock once
    c1 = await _reconcile_stale_pending_orders_async(cutoff_seconds=900)
    assert c1 >= 1

    async with async_session_maker() as session:
        inv1 = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        stock_after_c1 = inv1.stock
        version_after_c1 = inv1.version

    # Second run immediately on same database state
    c2 = await _reconcile_stale_pending_orders_async(cutoff_seconds=900)
    assert c2 == 0, "Second run must find zero eligible orders"

    async with async_session_maker() as session:
        inv2 = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        assert inv2.stock == stock_after_c1, "Stock must not be double-restored"
        assert inv2.version == version_after_c1, "Inventory version must not change on idempotent replay"


# ---------------------------------------------------------------------------
# 9. Concurrency: Two Workers Racing on the Same Pending Order
# ---------------------------------------------------------------------------

async def test_concurrent_workers_race_on_same_pending_order():
    """Simultaneous workers racing on the same pending order execute exactly one cancellation with row locks."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.pending, age_seconds=1500, quantity=2
    )

    # Launch two simultaneous recovery tasks
    results = await asyncio.gather(
        _reconcile_stale_pending_orders_async(cutoff_seconds=900),
        _reconcile_stale_pending_orders_async(cutoff_seconds=900),
    )

    # Combined cancellations across both workers must equal exactly 1
    total_cancelled = sum(results)
    assert total_cancelled == 1, f"Expected exactly 1 cancellation between concurrent workers, got {results}"

    async with async_session_maker() as session:
        events = (await session.execute(select(OrderEvent).where(OrderEvent.order_id == order.id))).scalars().all()
        cancel_events = [e for e in events if e.to_state == "cancelled"]
        assert len(cancel_events) == 1, "Exactly one cancellation event must be recorded"


# ---------------------------------------------------------------------------
# 10. Concurrency Race: Timeout Cancellation vs Shop Acceptance
# ---------------------------------------------------------------------------

async def test_timeout_cancellation_race_with_shop_acceptance():
    """Race between shop acceptance and timeout cancellation resolves cleanly via SELECT ... FOR UPDATE."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.confirmed, age_seconds=2000, quantity=2
    )

    async def shop_accept():
        async with async_session_maker() as session:
            try:
                await transition_order(
                    db=session,
                    order_id=order.id,
                    to_status=OrderStatus.preparing,
                    actor=f["owner"],
                    actor_role="shop_owner",
                    shop_id=f["shop_id"],
                )
                return "accepted"
            except Exception as e:
                return f"rejected_{type(e).__name__}"

    async def timeout_cancel():
        return await _reconcile_stale_unaccepted_orders_async(cutoff_seconds=1800)

    res_shop, res_timeout = await asyncio.gather(shop_accept(), timeout_cancel())

    async with async_session_maker() as session:
        final_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        # The final state must be either preparing (shop won) or cancelled (timeout won), never corrupted
        assert final_order.status in (OrderStatus.preparing, OrderStatus.cancelled)


# ---------------------------------------------------------------------------
# 11. Stale Delivery with No Nearby Available Rider Leaves Delivery Pending
# ---------------------------------------------------------------------------

async def test_stale_delivery_no_nearby_rider_reverts_to_pending():
    """When no nearby rider is available, stale delivery is cancelled, old rider released, and replacement delivery is pending."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.ready_for_delivery, age_seconds=1800, quantity=1
    )

    # Make Rider 2 unavailable as well so no nearby candidates exist
    async with async_session_maker() as session:
        r2 = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider2_id"]))).scalar_one()
        r2.is_available = False
        session.add(r2)

        stale_assigned_time = datetime.now(timezone.utc) - timedelta(minutes=25)
        stale_deliv = Delivery(
            order_id=order.id,
            rider_id=f["rider1_id"],
            status=DeliveryStatus.assigned,
            assigned_at=stale_assigned_time,
            picked_up_at=None,
            destination_location=f"SRID=4326;POINT({f['patna_lon']} {f['patna_lat']})",
        )
        session.add(stale_deliv)
        await session.commit()
        stale_deliv_id = stale_deliv.id

    reassigned = await _reconcile_stale_deliveries_async(cutoff_seconds=900)
    assert reassigned >= 1

    async with async_session_maker() as session:
        # Old delivery cancelled
        old_d = (await session.execute(select(Delivery).where(Delivery.id == stale_deliv_id))).scalar_one()
        assert old_d.status == DeliveryStatus.cancelled

        # Rider 1 released
        r1_ref = (await session.execute(select(RiderProfile).where(RiderProfile.id == f["rider1_id"]))).scalar_one()
        assert r1_ref.is_available is True

        # Replacement delivery created in pending state with no rider assigned
        new_d = (
            await session.execute(
                select(Delivery).where(
                    Delivery.order_id == order.id,
                    Delivery.id != stale_deliv_id,
                )
            )
        ).scalar_one()
        assert new_d.status == DeliveryStatus.pending
        assert new_d.rider_id is None


# ---------------------------------------------------------------------------
# 12. Celery Synchronous Task Entrypoints & Retry Configuration
# ---------------------------------------------------------------------------

async def test_celery_synchronous_task_entrypoints_and_retry_config():
    """Verify Celery task functions execute cleanly synchronously and have bounded retry configurations."""
    # Verify retry and execution configurations
    for task_fn in [reconcile_stale_pending_orders, reconcile_stale_unaccepted_orders, reconcile_stale_deliveries]:
        assert task_fn.max_retries == 3
        assert task_fn.retry_backoff is True
        assert task_fn.retry_backoff_max == 60
        assert task_fn.autoretry_for is not None

    # Call task synchronously (as Celery worker does)
    res_pending = reconcile_stale_pending_orders(cutoff_seconds=900)
    assert isinstance(res_pending, int)

    res_unaccepted = reconcile_stale_unaccepted_orders(cutoff_seconds=1800)
    assert isinstance(res_unaccepted, int)

    res_deliveries = reconcile_stale_deliveries(cutoff_seconds=900)
    assert isinstance(res_deliveries, int)


# ---------------------------------------------------------------------------
# 13. Atomic Rollback on Cancellation Failure (All or Nothing)
# ---------------------------------------------------------------------------

async def test_atomic_rollback_on_cancellation_failure(monkeypatch):
    """If an error occurs mid-cancellation, rollback reverts status, stock, payment, and delivery atomically."""
    f = await setup_stage6_fixtures()
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.confirmed, age_seconds=2400, quantity=3
    )

    async with async_session_maker() as session:
        inv_before = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        stock_before = inv_before.stock
        version_before = inv_before.version

        pay = Payment(
            order_id=order.id,
            provider="razorpay",
            provider_order_id=f"order_{uuid.uuid4().hex[:8]}",
            amount=120.0,
            currency="INR",
            status=PaymentStatus.captured,
            paid_at=datetime.now(timezone.utc),
        )
        session.add(pay)
        deliv = Delivery(order_id=order.id, status=DeliveryStatus.pending)
        session.add(deliv)
        await session.commit()

    # Simulate an unexpected failure during transition_order
    from app.tasks import order_recovery
    original_transition = order_recovery.transition_order

    async def failing_transition(*args, **kwargs):
        raise RuntimeError("Simulated mid-transaction failure during state transition")

    monkeypatch.setattr(order_recovery, "transition_order", failing_transition)

    # Recovery task catches the exception and executes rollback
    cancelled_count = await _reconcile_stale_unaccepted_orders_async(cutoff_seconds=1800)
    assert cancelled_count == 0

    # Invariant: Entire state was rolled back atomically
    async with async_session_maker() as session:
        ord_ref = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert ord_ref.status == OrderStatus.confirmed, "Order status must remain confirmed after rollback"

        inv_ref = (await session.execute(select(Inventory).where(Inventory.product_id == f["p1_id"]))).scalar_one()
        assert inv_ref.stock == stock_before, "Stock must NOT be partially restored on failure"
        assert inv_ref.version == version_before, "Version must not change on failure"

        pay_ref = (await session.execute(select(Payment).where(Payment.order_id == order.id))).scalar_one()
        assert pay_ref.status == PaymentStatus.captured, "Payment status must remain captured after rollback"

        deliv_ref = (await session.execute(select(Delivery).where(Delivery.order_id == order.id))).scalar_one()
        assert deliv_ref.status == DeliveryStatus.pending, "Delivery must remain pending after rollback"


# ---------------------------------------------------------------------------
# 14. Rider Reassignment Race: No Double Assignment Under Concurrent Recovery
# ---------------------------------------------------------------------------

async def test_concurrent_rider_reassignment_race_no_double_assignment():
    """When multiple tasks race to reassign deliveries with only ONE candidate rider, at most one gets the rider."""
    f = await setup_stage6_fixtures()
    rider_user3 = await create_stage6_user(UserRole.rider, "s6_rider3")
    rider3_id = uuid.uuid4()

    async with async_session_maker() as session:
        r3 = RiderProfile(
            id=rider3_id,
            user_id=rider_user3.id,
            is_available=False,
            location=f"SRID=4326;POINT({f['patna_lon'] + 0.003} {f['patna_lat'] + 0.003})",
            location_updated_at=datetime.now(timezone.utc),
        )
        session.add(r3)
        await session.commit()

    # Order 1 and Order 2 both have stale assigned deliveries
    ord1 = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.ready_for_delivery, age_seconds=2000, quantity=1
    )
    ord2 = await create_test_order(
        f["customer"].id, f["shop_id"], f["p2_id"],
        status=OrderStatus.ready_for_delivery, age_seconds=2000, quantity=1
    )

    stale_assigned_time = datetime.now(timezone.utc) - timedelta(minutes=25)
    dest_geom = f"SRID=4326;POINT({f['patna_lon']} {f['patna_lat']})"

    async with async_session_maker() as session:
        # d1 is assigned to Rider 1, d2 is assigned to Rider 3
        # Both are stale; only Rider 2 is available as replacement candidate
        d1 = Delivery(
            order_id=ord1.id,
            rider_id=f["rider1_id"],
            status=DeliveryStatus.assigned,
            assigned_at=stale_assigned_time,
            destination_location=dest_geom,
        )
        d2 = Delivery(
            order_id=ord2.id,
            rider_id=rider3_id,
            status=DeliveryStatus.assigned,
            assigned_at=stale_assigned_time,
            destination_location=dest_geom,
        )
        session.add_all([d1, d2])
        await session.commit()

    # Launch two simultaneous recovery tasks
    res1, res2 = await asyncio.gather(
        _reconcile_stale_deliveries_async(cutoff_seconds=900),
        _reconcile_stale_deliveries_async(cutoff_seconds=900),
    )

    assert (res1 + res2) >= 1

    # Verify Rider 2 is assigned to AT MOST one active delivery across the entire database
    async with async_session_maker() as session:
        r2_active = (
            await session.execute(
                select(Delivery).where(
                    Delivery.rider_id == f["rider2_id"],
                    Delivery.status.in_([
                        DeliveryStatus.assigned,
                        DeliveryStatus.picked_up,
                        DeliveryStatus.out_for_delivery,
                    ]),
                )
            )
        ).scalars().all()

        assert len(r2_active) == 1, f"Rider 2 must be assigned to exactly 1 delivery, found {len(r2_active)}"


# ---------------------------------------------------------------------------
# 15. Confirmed-Order Timeout Uses Confirmation Timestamp (Full Preparation Window)
# ---------------------------------------------------------------------------

async def test_late_confirmation_receives_full_shop_acceptance_timeout():
    """An order created 25 mins ago but confirmed only 5 mins ago receives full 30 mins from confirmation time."""
    f = await setup_stage6_fixtures()
    # Order was placed 25 minutes ago
    order = await create_test_order(
        f["customer"].id, f["shop_id"], f["p1_id"],
        status=OrderStatus.confirmed, age_seconds=1500, quantity=1
    )

    # Customer completed payment only 5 minutes ago -> updated_at is 5 minutes ago
    recent_confirmed_time = datetime.now(timezone.utc) - timedelta(minutes=5)
    async with async_session_maker() as session:
        await session.execute(
            text("UPDATE orders SET updated_at = :upd WHERE id = :oid").bindparams(
                upd=recent_confirmed_time, oid=order.id
            )
        )
        await session.commit()

    # Run unaccepted order reconciliation with 30 minute timeout (1800s)
    # If it measured from created_at (25 min ago + 5 min margin), it would be close to expiring
    # But because it measures from updated_at (5 min ago), the shop has 25 minutes remaining!
    cancelled = await _reconcile_stale_unaccepted_orders_async(cutoff_seconds=1800)

    async with async_session_maker() as session:
        ord_ref = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        assert ord_ref.status == OrderStatus.confirmed, (
            "Order confirmed 5 minutes ago must NOT be cancelled under 30-minute timeout"
        )
