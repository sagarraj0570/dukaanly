"""
Automated Proximity Dispatch Atomic Claim Test Suite (Stage A4).

Verifies the atomic claim protocol (POST /api/v1/riders/me/offers/{offer_id}/accept) in ONE transaction:
1. Two riders accept the same delivery simultaneously (concurrency race):
   - Exactly one 200 OK, exactly one 409 Conflict.
   - Exactly one assigned rider.
   - Winning offer accepted, losing offer cancelled.
   - Winner is_available=False, loser is_available=True.
2. One rider accepting offers on two deliveries simultaneously:
   - Exactly one succeeds, second gets 409 Conflict.
   - Rider's is_available=False.
   - First delivery assigned, second delivery remains pending with rider_id IS NULL.
3. Accept racing with order cancellation:
   - Exactly one consistent outcome.
   - No assigned delivery on a cancelled order, no leaked is_available=False.
4. Accept after expiry rejected even if cleanup task never ran:
   - Returns 409 Conflict ("Offer has expired").
   - Delivery remains pending and unassigned; rider remains available.
5. Accept by a rider with no offer / another rider's offer returns 403 Forbidden.
6. Accept by an off-duty rider returns 409 Conflict.
7. IntegrityError path rolls back fully:
   - Rider is_available and offer status do not persist; returns 409 Conflict.
8. Event publishing failure does not roll back or fail the claim:
   - WebSocket exception is logged, claim transaction remains committed with 200 OK.
9. Manual shop-owner assignment cancels open offers:
   - Existing assign_rider endpoint sets open dispatch offers to 'cancelled'.
10. Privacy boundary:
   - Rider cannot access customer drop details before accept (403 Forbidden).
   - Only after successful accept can rider access delivery detail (200 OK).
"""

import uuid
import asyncio
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import text, select, update
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.order import Order, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus
from app.models.rider import RiderProfile
from app.services.state_machine import transition_order
from app.core.security import create_access_token


SHOP_LAT = 25.6144
SHOP_LON = 85.1158


def _auth_headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


async def _create_test_entities(session, rider_offsets=None):
    """Creates a merchant shop and optional candidate riders."""
    suffix = uuid.uuid4().hex[:8]

    owner = User(
        id=uuid.uuid4(),
        name=f"Merchant A4 {suffix}",
        email=f"owner_{suffix}@dukaanly.com",
        password_hash="hash",
        role=UserRole.shop_owner,
        is_active=True,
    )
    cust = User(
        id=uuid.uuid4(),
        name=f"Customer A4 {suffix}",
        email=f"cust_{suffix}@dukaanly.com",
        password_hash="hash",
        role=UserRole.customer,
        is_active=True,
    )
    session.add(owner)
    session.add(cust)
    await session.flush()

    shop = Shop(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name=f"Shop A4 {suffix}",
        address="Boring Road, Patna",
        location=WKTElement(f"SRID=4326;POINT({SHOP_LON} {SHOP_LAT})"),
        is_active=True,
    )
    session.add(shop)
    await session.flush()

    riders = []
    if rider_offsets:
        for offset_lat, offset_lon in rider_offsets:
            r_user = User(
                id=uuid.uuid4(),
                name=f"Rider {uuid.uuid4().hex[:6]}",
                email=f"rider_{uuid.uuid4().hex[:8]}@dukaanly.com",
                password_hash="hash",
                role=UserRole.rider,
                is_active=True,
            )
            session.add(r_user)
            await session.flush()

            rp = RiderProfile(
                id=uuid.uuid4(),
                user_id=r_user.id,
                is_available=True,
                location=WKTElement(f"SRID=4326;POINT({SHOP_LON + offset_lon} {SHOP_LAT + offset_lat})"),
                location_updated_at=datetime.now(timezone.utc),
            )
            session.add(rp)
            riders.append((r_user, rp))

    await session.commit()
    return owner, cust, shop, riders


@pytest.mark.asyncio
async def test_two_riders_accept_same_delivery_simultaneously(async_client: AsyncClient, monkeypatch):
    """Concurrency verification: Two riders racing to claim the same delivery offer."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Create shop and two eligible candidate riders close to shop
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.006, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=250.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        # Confirm order to generate automated proximity dispatch offers
        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalars().all()
        assert len(offers) == 2

        offer1 = next(o for o in offers if o.rider_id == rider1_profile.id)
        offer2 = next(o for o in offers if o.rider_id == rider2_profile.id)

    # Concurrently execute accept requests from both riders
    t1 = async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/accept",
        headers=_auth_headers(rider1_user),
    )
    t2 = async_client.post(
        f"/api/v1/riders/me/offers/{offer2.id}/accept",
        headers=_auth_headers(rider2_user),
    )

    r1, r2 = await asyncio.gather(t1, t2)
    statuses = [r1.status_code, r2.status_code]
    assert 200 in statuses
    assert 409 in statuses

    # Verify winning and losing state in database
    winner_res = r1 if r1.status_code == 200 else r2
    loser_res = r2 if r1.status_code == 200 else r1
    winner_user = rider1_user if r1.status_code == 200 else rider2_user
    loser_user = rider2_user if r1.status_code == 200 else rider1_user
    winner_profile = rider1_profile if r1.status_code == 200 else rider2_profile
    loser_profile = rider2_profile if r1.status_code == 200 else rider1_profile
    winner_offer = offer1 if r1.status_code == 200 else offer2
    loser_offer = offer2 if r1.status_code == 200 else offer1

    assert loser_res.json()["detail"] in [
        "Delivery is no longer available (already assigned or cancelled)",
        "Delivery is no longer available",
        "Offer cannot be accepted: status is 'cancelled'",
    ]

    async with async_session_maker() as session:
        # 1. Delivery is assigned to winner only
        updated_delivery = (await session.execute(
            select(Delivery).where(Delivery.id == delivery.id)
        )).scalar_one()
        assert updated_delivery.status == DeliveryStatus.assigned
        assert updated_delivery.rider_id == winner_profile.id
        assert updated_delivery.assigned_at is not None

        # 2. Winning offer is accepted, losing offer is cancelled
        o_win = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.id == winner_offer.id)
        )).scalar_one()
        o_lose = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.id == loser_offer.id)
        )).scalar_one()
        assert o_win.status == DeliveryOfferStatus.accepted.value
        assert o_win.responded_at is not None
        assert o_lose.status == DeliveryOfferStatus.cancelled.value
        assert o_lose.responded_at is not None

        # 3. Winner availability is False; loser availability remains True
        wp = (await session.execute(select(RiderProfile).where(RiderProfile.id == winner_profile.id))).scalar_one()
        lp = (await session.execute(select(RiderProfile).where(RiderProfile.id == loser_profile.id))).scalar_one()
        assert wp.is_available is False
        assert lp.is_available is True

        # 4. OrderEvent audit trail recorded
        events = (await session.execute(
            select(OrderEvent).where(
                OrderEvent.order_id == order.id,
                OrderEvent.actor_role == "rider",
            )
        )).scalars().all()
        assert len(events) == 1
        assert events[0].actor_id == winner_user.id
        assert "Delivery accepted via automated proximity dispatch" in events[0].reason


@pytest.mark.asyncio
async def test_one_rider_accepts_two_deliveries_simultaneously(async_client: AsyncClient, monkeypatch):
    """Concurrency verification: One rider attempting to accept offers on two deliveries concurrently."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        # Order 1
        o1 = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=100.0, status=OrderStatus.pending)
        # Order 2
        o2 = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=200.0, status=OrderStatus.pending)
        session.add_all([o1, o2])
        await session.commit()

        # Confirm both orders
        await transition_order(db=session, order_id=o1.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")
        await transition_order(db=session, order_id=o2.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        # Fetch offers for this rider
        offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.rider_id == rider_profile.id)
        )).scalars().all()
        assert len(offers) == 2
        offer_a, offer_b = offers[0], offers[1]

    # Concurrently attempt to claim both offers
    h = _auth_headers(rider_user)
    t1 = async_client.post(f"/api/v1/riders/me/offers/{offer_a.id}/accept", headers=h)
    t2 = async_client.post(f"/api/v1/riders/me/offers/{offer_b.id}/accept", headers=h)

    r1, r2 = await asyncio.gather(t1, t2)
    statuses = [r1.status_code, r2.status_code]
    assert 200 in statuses
    assert 409 in statuses

    async with async_session_maker() as session:
        # Rider is now unavailable
        rp = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider_profile.id))).scalar_one()
        assert rp.is_available is False

        # One delivery is assigned, the other remains pending and unassigned
        deliv_a = (await session.execute(select(Delivery).where(Delivery.id == offer_a.delivery_id))).scalar_one()
        deliv_b = (await session.execute(select(Delivery).where(Delivery.id == offer_b.delivery_id))).scalar_one()

        assigned_deliveries = [d for d in [deliv_a, deliv_b] if d.status == DeliveryStatus.assigned]
        pending_deliveries = [d for d in [deliv_a, deliv_b] if d.status == DeliveryStatus.pending]

        assert len(assigned_deliveries) == 1
        assert assigned_deliveries[0].rider_id == rider_profile.id
        assert len(pending_deliveries) == 1
        assert pending_deliveries[0].rider_id is None


@pytest.mark.asyncio
async def test_accept_racing_with_order_cancellation(async_client: AsyncClient, monkeypatch):
    """Concurrency verification: Rider accept racing against customer/shop order cancellation."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalar_one()

    # Race: rider claims offer while shop owner cancels order
    t_accept = async_client.post(
        f"/api/v1/riders/me/offers/{offer.id}/accept",
        headers=_auth_headers(rider_user),
    )
    t_cancel = async_client.post(
        f"/api/v1/orders/{order.id}/cancel",
        json={"reason": "Customer cancellation race condition test"},
        headers=_auth_headers(cust),
    )

    r_accept, r_cancel = await asyncio.gather(t_accept, t_cancel)

    # Cancellation must always succeed
    assert r_cancel.status_code == 200

    async with async_session_maker() as session:
        updated_order = (await session.execute(select(Order).where(Order.id == order.id))).scalar_one()
        updated_delivery = (await session.execute(select(Delivery).where(Delivery.id == delivery.id))).scalar_one()
        rp = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider_profile.id))).scalar_one()

        # Invariant 1: Order is cancelled
        assert updated_order.status == OrderStatus.cancelled

        # Invariant 2: Delivery is cancelled (never assigned on a cancelled order)
        assert updated_delivery.status == DeliveryStatus.cancelled

        # Invariant 3: Rider is NOT left with is_available=False
        assert rp.is_available is True


@pytest.mark.asyncio
async def test_accept_after_expiry_rejected_without_cleanup(async_client: AsyncClient, monkeypatch):
    """Verify offer accept after expiry is rejected by database clock even if background cleanup never ran."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalar_one()

        # Simulate expiry without background cleanup running (status remains 'offered')
        past_time = datetime.now(timezone.utc) - timedelta(seconds=15)
        await session.execute(
            update(DeliveryOffer)
            .where(DeliveryOffer.id == offer.id)
            .values(expires_at=past_time)
        )
        await session.commit()

    # Attempt accept
    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer.id}/accept",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "Offer has expired"

    async with async_session_maker() as session:
        rp = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider_profile.id))).scalar_one()
        deliv = (await session.execute(select(Delivery).where(Delivery.id == delivery.id))).scalar_one()
        assert rp.is_available is True
        assert deliv.status == DeliveryStatus.pending
        assert deliv.rider_id is None


@pytest.mark.asyncio
async def test_accept_by_unauthorized_rider_returns_403(async_client: AsyncClient, monkeypatch):
    """Verify rider cannot accept another rider's offer."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.006, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer1 = (await session.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.delivery_id == delivery.id,
                DeliveryOffer.rider_id == rider1_profile.id,
            )
        )).scalar_one()

    # Rider 2 attempts to accept Rider 1's offer
    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/accept",
        headers=_auth_headers(rider2_user),
    )
    assert res.status_code == 403
    assert "Forbidden" in res.json()["detail"]


@pytest.mark.asyncio
async def test_accept_by_off_duty_rider_returns_409(async_client: AsyncClient, monkeypatch):
    """Verify an off-duty rider (is_available=False) cannot claim an offer."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalar_one()

        # Rider goes off duty before claiming
        rider_profile.is_available = False
        session.add(rider_profile)
        await session.commit()

    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer.id}/accept",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "Rider is off duty or not available"


@pytest.mark.asyncio
async def test_integrity_error_rolls_back_entire_claim(async_client: AsyncClient, monkeypatch):
    """Verify that IntegrityError (from active delivery uniqueness) rolls back all state changes completely."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        # 1. Give rider an active delivery already in database
        o_active = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=100.0, status=OrderStatus.confirmed)
        session.add(o_active)
        await session.flush()

        active_deliv = Delivery(
            id=uuid.uuid4(),
            order_id=o_active.id,
            rider_id=rider_profile.id,
            status=DeliveryStatus.assigned,
            destination_location=WKTElement(f"POINT({SHOP_LON} {SHOP_LAT})", srid=4326),
            assigned_at=datetime.now(timezone.utc),
        )
        session.add(active_deliv)

        # 2. Create another delivery and offer for this rider
        o_new = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=120.0, status=OrderStatus.confirmed)
        session.add(o_new)
        await session.flush()

        new_deliv = Delivery(
            id=uuid.uuid4(),
            order_id=o_new.id,
            status=DeliveryStatus.pending,
            destination_location=WKTElement(f"POINT({SHOP_LON} {SHOP_LAT})", srid=4326),
        )
        session.add(new_deliv)
        await session.flush()

        offer = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=new_deliv.id,
            rider_id=rider_profile.id,
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        session.add(offer)

        # Set rider_profile.is_available = True so it passes the initial availability check,
        # forcing the database index to catch the conflict at commit
        rider_profile.is_available = True
        session.add(rider_profile)
        await session.commit()

    # Attempt accept: DB partial unique index idx_active_delivery_per_rider will reject second active delivery
    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer.id}/accept",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 409
    assert res.json()["detail"] == "Rider already has an active delivery"

    # Assert clean rollback
    async with async_session_maker() as session:
        deliv = (await session.execute(select(Delivery).where(Delivery.id == new_deliv.id))).scalar_one()
        off = (await session.execute(select(DeliveryOffer).where(DeliveryOffer.id == offer.id))).scalar_one()
        assert deliv.status == DeliveryStatus.pending
        assert deliv.rider_id is None
        assert off.status == DeliveryOfferStatus.offered.value


@pytest.mark.asyncio
async def test_publishing_failure_does_not_undo_claim(async_client: AsyncClient, monkeypatch):
    """Verify that WebSocket/event publishing failure post-commit does not fail the claim."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalar_one()

    # Monkeypatch event publisher to raise an error
    async def _failing_publish(*args, **kwargs):
        raise ConnectionError("Simulated Redis WebSocket connection failure")

    monkeypatch.setattr("app.websockets.redis_pubsub.publish_delivery_event", _failing_publish)

    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer.id}/accept",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 200
    assert res.json()["status"] == "accepted"

    async with async_session_maker() as session:
        deliv = (await session.execute(select(Delivery).where(Delivery.id == delivery.id))).scalar_one()
        rp = (await session.execute(select(RiderProfile).where(RiderProfile.id == rider_profile.id))).scalar_one()
        assert deliv.status == DeliveryStatus.assigned
        assert deliv.rider_id == rider_profile.id
        assert rp.is_available is False


@pytest.mark.asyncio
async def test_manual_shop_owner_assignment_cancels_open_offers(async_client: AsyncClient, monkeypatch):
    """Verify manual shop-owner assignment cancels any open automated dispatch offers for the delivery."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.006, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalars().all()
        assert len(offers) == 2
        assert all(o.status == "offered" for o in offers)

    # Shop owner manually assigns rider 1 via manual endpoint
    res = await async_client.post(
        f"/api/v1/deliveries/{delivery.id}/assign",
        json={"rider_id": str(rider1_profile.id)},
        headers=_auth_headers(owner),
    )
    assert res.status_code == 200

    async with async_session_maker() as session:
        deliv = (await session.execute(select(Delivery).where(Delivery.id == delivery.id))).scalar_one()
        assert deliv.status == DeliveryStatus.assigned
        assert deliv.rider_id == rider1_profile.id

        # Open offers are cancelled
        updated_offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalars().all()
        assert len(updated_offers) == 2
        for off in updated_offers:
            assert off.status == "cancelled"
            assert off.responded_at is not None


@pytest.mark.asyncio
async def test_privacy_customer_details_revealed_only_after_accept(async_client: AsyncClient, monkeypatch):
    """Verify rider cannot view delivery details before accept, but gains access after successful claim."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(db=session, order_id=order.id, to_status=OrderStatus.confirmed, actor=owner, actor_role="shop_owner")

        delivery = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalar_one()

    h = _auth_headers(rider_user)

    # 1. Before accept: Rider cannot access GET /api/v1/deliveries/{delivery_id}
    res_before = await async_client.get(f"/api/v1/deliveries/{delivery.id}", headers=h)
    assert res_before.status_code == 403

    # 2. Accept offer
    res_accept = await async_client.post(f"/api/v1/riders/me/offers/{offer.id}/accept", headers=h)
    assert res_accept.status_code == 200

    # 3. After accept: Rider can access GET /api/v1/deliveries/{delivery_id}
    res_after = await async_client.get(f"/api/v1/deliveries/{delivery.id}", headers=h)
    assert res_after.status_code == 200
    deliv_data = res_after.json()
    assert deliv_data["id"] == str(delivery.id)
    assert deliv_data["rider_id"] == str(rider_profile.id)
    assert deliv_data["status"] == "assigned"
