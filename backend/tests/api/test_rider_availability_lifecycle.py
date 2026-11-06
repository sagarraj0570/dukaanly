import uuid
import pytest
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.order import Order, OrderStatus
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus
from app.services.state_machine import transition_order, transition_delivery
from app.services.delivery import assign_rider
from app.tasks.order_recovery import _reconcile_stale_deliveries_async


async def _create_test_hierarchy(session, rider_available=True, delivery_status=DeliveryStatus.pending, assigned_minutes_ago=None):
    """Helper to create a valid hierarchy satisfying all foreign keys."""
    suffix = uuid.uuid4().hex[:8]
    cust = User(
        id=uuid.uuid4(),
        name=f"Customer {suffix}",
        email=f"cust_{suffix}@example.com",
        password_hash="hash",
        role=UserRole.customer,
        is_active=True,
    )
    owner = User(
        id=uuid.uuid4(),
        name=f"Owner {suffix}",
        email=f"owner_{suffix}@example.com",
        password_hash="hash",
        role=UserRole.shop_owner,
        is_active=True,
    )
    rider_user = User(
        id=uuid.uuid4(),
        name=f"Rider {suffix}",
        email=f"rider_{suffix}@example.com",
        password_hash="hash",
        role=UserRole.rider,
        is_active=True,
    )
    session.add_all([cust, owner, rider_user])
    await session.flush()

    shop = Shop(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name=f"Shop {suffix}",
        address="Boring Road, Patna",
        location=WKTElement("SRID=4326;POINT(85.1376 25.5941)"),
        is_active=True,
    )
    session.add(shop)
    await session.flush()

    rider = RiderProfile(
        id=uuid.uuid4(),
        user_id=rider_user.id,
        is_available=rider_available,
        location=WKTElement("SRID=4326;POINT(85.1370 25.5940)"),
        location_updated_at=datetime.now(timezone.utc),
    )
    session.add(rider)

    order = Order(
        id=uuid.uuid4(),
        customer_id=cust.id,
        shop_id=shop.id,
        status=OrderStatus.confirmed,
        total_amount=150.0,
    )
    session.add(order)
    await session.flush()

    assigned_at = None
    if assigned_minutes_ago is not None:
        assigned_at = datetime.now(timezone.utc) - timedelta(minutes=assigned_minutes_ago)
    elif delivery_status in [DeliveryStatus.assigned, DeliveryStatus.out_for_delivery, DeliveryStatus.picked_up]:
        assigned_at = datetime.now(timezone.utc)

    delivery = Delivery(
        id=uuid.uuid4(),
        order_id=order.id,
        rider_id=rider.id if delivery_status != DeliveryStatus.pending else None,
        status=delivery_status,
        destination_location=WKTElement("SRID=4326;POINT(85.1380 25.5950)"),
        assigned_at=assigned_at,
    )
    session.add(delivery)
    await session.commit()

    return cust, owner, rider_user, shop, rider, order, delivery


@pytest.mark.asyncio
async def test_delivered_frees_rider():
    """Verify that transitioning a delivery to 'delivered' sets rider.is_available = True."""
    async with async_session_maker() as session:
        cust, owner, rider_u, shop, rider, order, delivery = await _create_test_hierarchy(
            session, rider_available=False, delivery_status=DeliveryStatus.out_for_delivery
        )

        admin = User(
            id=uuid.uuid4(),
            role=UserRole.admin,
            email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
            password_hash="h",
            name="Admin",
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        await transition_delivery(
            db=session,
            delivery_id=delivery.id,
            to_status=DeliveryStatus.delivered,
            actor=admin,
        )

        r_refreshed = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider.id))).scalar_one()
        assert r_refreshed.is_available is True, "Rider should be available after delivery completion"


@pytest.mark.asyncio
async def test_delivery_cancelled_frees_rider():
    """Verify that transitioning an assigned delivery to 'cancelled' sets rider.is_available = True."""
    async with async_session_maker() as session:
        cust, owner, rider_u, shop, rider, order, delivery = await _create_test_hierarchy(
            session, rider_available=False, delivery_status=DeliveryStatus.assigned
        )

        admin = User(
            id=uuid.uuid4(),
            role=UserRole.admin,
            email=f"admin_{uuid.uuid4().hex[:6]}@test.com",
            password_hash="h",
            name="Admin",
            is_active=True,
        )
        session.add(admin)
        await session.flush()
        await transition_delivery(
            db=session,
            delivery_id=delivery.id,
            to_status=DeliveryStatus.cancelled,
            actor=admin,
            reason="Customer cancelled",
        )

        r_refreshed = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider.id))).scalar_one()
        assert r_refreshed.is_available is True, "Rider should be available after delivery cancellation"


@pytest.mark.asyncio
async def test_order_cancelled_while_assigned_frees_rider():
    """Verify that cancelling an order with an assigned delivery frees the rider and cancels delivery."""
    async with async_session_maker() as session:
        cust, owner, rider_u, shop, rider, order, delivery = await _create_test_hierarchy(
            session, rider_available=False, delivery_status=DeliveryStatus.assigned
        )

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.cancelled,
            actor=owner,
            reason="Out of stock",
        )

        r_refreshed = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider.id))).scalar_one()
        assert r_refreshed.is_available is True, "Rider should be freed when assigned order is cancelled"

        d_refreshed = (await session.execute(select(Delivery).where(Delivery.id == delivery.id))).scalar_one()
        assert d_refreshed.status == DeliveryStatus.cancelled


@pytest.mark.asyncio
async def test_order_cancelled_mid_offer_cancels_open_offers():
    """Verify that cancelling an order while dispatch offers are pending cancels all open offers."""
    async with async_session_maker() as session:
        cust, owner, rider_u, shop, rider, order, delivery = await _create_test_hierarchy(
            session, rider_available=True, delivery_status=DeliveryStatus.pending
        )

        offer = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            rider_id=rider.id,
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        session.add(offer)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.cancelled,
            actor=owner,
            reason="Customer request",
        )

        o_refreshed = (await session.execute(select(DeliveryOffer).where(DeliveryOffer.id == offer.id))).scalar_one()
        assert o_refreshed.status == "cancelled", "Open offers must be cancelled on order cancellation"


@pytest.mark.asyncio
async def test_manual_assign_cancels_open_offers_and_sets_rider_unavailable():
    """Verify that manual shop owner assignment sets rider unavailable, clears awaiting_rider, and cancels open offers."""
    async with async_session_maker() as session:
        cust, owner, rider_u1, shop, r1, order, delivery = await _create_test_hierarchy(
            session, rider_available=True, delivery_status=DeliveryStatus.pending
        )

        # Create second rider
        r2_user = User(
            id=uuid.uuid4(),
            name="Rider 2",
            email=f"r2_{uuid.uuid4().hex[:6]}@example.com",
            password_hash="h",
            role=UserRole.rider,
            is_active=True,
        )
        session.add(r2_user)
        await session.flush()
        r2 = RiderProfile(id=uuid.uuid4(), user_id=r2_user.id, is_available=True)
        session.add(r2)

        # Open offer for r2
        offer = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            rider_id=r2.id,
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        session.add(offer)
        delivery.awaiting_rider = True
        session.add(delivery)
        await session.commit()

        # Shop owner manually assigns r1
        updated = await assign_rider(db=session, delivery_id=delivery.id, rider_id=r1.id, owner=owner)
        assert updated.rider_id == r1.id
        assert updated.status == DeliveryStatus.assigned
        assert updated.awaiting_rider is False

        # r1 is now unavailable
        r1_refreshed = (await session.execute(select(RiderProfile).where(RiderProfile.id == r1.id))).scalar_one()
        assert r1_refreshed.is_available is False

        # Open offer for r2 is cancelled
        offer_refreshed = (await session.execute(select(DeliveryOffer).where(DeliveryOffer.id == offer.id))).scalar_one()
        assert offer_refreshed.status == "cancelled"


@pytest.mark.asyncio
async def test_stale_delivery_recovery_frees_rider():
    """Verify that Celery stale delivery reconciliation releases the unresponsive rider."""
    async with async_session_maker() as session:
        cust, owner, rider_u, shop, rider, order, delivery = await _create_test_hierarchy(
            session, rider_available=False, delivery_status=DeliveryStatus.assigned, assigned_minutes_ago=30
        )

        recovered = await _reconcile_stale_deliveries_async(cutoff_seconds=10, db_session=session)
        assert recovered >= 1

        r_refreshed = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider.id))).scalar_one()
        assert r_refreshed.is_available is True, "Stale rider must be marked available upon redispatch"
