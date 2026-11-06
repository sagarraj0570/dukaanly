"""
Automated Proximity Dispatch Offers Test Suite (Stage A3).

Verifies:
1. Batch creation on order confirmation with DISPATCH_AUTO_ENABLED=True.
2. No offers created on order confirmation when DISPATCH_AUTO_ENABLED=False.
3. Idempotency: Confirming an order twice creates only one batch.
4. Zero-candidate scenario: Attempt is recorded (dispatch_attempts=1, 0 offers) so escalation can advance immediately.
5. GET /api/v1/riders/me/offers shows only the authenticated rider's unexpired open offers.
6. GET /api/v1/riders/me/offers excludes expired, declined, and other riders' offers.
7. Security: GET /api/v1/riders/me/offers never exposes customer name, phone, email, or drop address.
8. Decline ownership: Rider B attempting to decline Rider A's offer receives HTTP 403 Forbidden.
9. Decline idempotency: Declining twice returns 200 with unchanged state.
10. Immediate escalation: When the last open offer in an attempt is declined, delivery immediately escalates to attempt 2.
11. Stale-assignment recovery in order_recovery.py: Unassigning a stale rider resets awaiting_rider to False and re-enters dispatch.
"""

import uuid
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient
from sqlalchemy import text, select, update
from geoalchemy2.elements import WKTElement

from app.db.session import async_session_maker
from app.core.config import settings
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.order import Order, OrderStatus
from app.models.delivery import Delivery, DeliveryStatus
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus
from app.models.rider import RiderProfile
from app.services.state_machine import transition_order
from app.tasks.order_recovery import _reconcile_stale_deliveries_async
from app.core.security import create_access_token


SHOP_LAT = 25.6144
SHOP_LON = 85.1158


async def _create_test_entities(session, rider_offsets=None):
    """Creates a merchant shop and optional candidate riders."""
    suffix = uuid.uuid4().hex[:8]

    owner = User(
        id=uuid.uuid4(),
        name="Merchant A3",
        email=f"owner_{suffix}@dukaanly.com",
        password_hash="hash",
        role=UserRole.shop_owner,
        is_active=True,
    )
    cust = User(
        id=uuid.uuid4(),
        name="Customer A3",
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
        name=f"Shop A3 {suffix}",
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


def _auth_headers(user: User) -> dict:
    token = create_access_token(subject=str(user.id), role=user.role.value)
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_batch_creation_on_order_confirmation(monkeypatch):
    """Verify batch creation on order confirmation when DISPATCH_AUTO_ENABLED is True."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Create shop and 2 riders within 3km (Attempt 1 radius)
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.010, 0.0)]  # ~550m and ~1.1km
        )

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=250.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        # Transition to confirmed
        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
            reason="Confirmed by merchant",
        )

        # Verify delivery created with dispatch metadata
        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        assert deliv.status == DeliveryStatus.pending
        assert deliv.rider_id is None
        assert deliv.dispatch_attempts == 1
        assert deliv.dispatch_started_at is not None
        assert deliv.awaiting_rider is False

        # Verify offers created for both riders
        offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == deliv.id)
        )).scalars().all()

        assert len(offers) == 2
        rider_profile_ids = {r[1].id for r in riders}
        offered_rider_ids = {o.rider_id for o in offers}
        assert offered_rider_ids == rider_profile_ids
        for o in offers:
            assert o.attempt_no == 1
            assert o.status == DeliveryOfferStatus.offered.value
            assert o.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_no_offers_when_dispatch_auto_disabled(monkeypatch):
    """Verify no delivery/offers created on order confirmation when DISPATCH_AUTO_ENABLED is False."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", False)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=250.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
            reason="Confirmed by merchant",
        )

        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one_or_none()

        assert deliv is None


@pytest.mark.asyncio
async def test_double_confirm_creates_single_batch(monkeypatch):
    """Verify confirming an order twice creates only one batch of offers."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=250.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        # Confirm first time
        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offers_first = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == deliv.id)
        )).scalars().all()
        assert len(offers_first) == 1

        # Confirm second time (idempotent)
        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        offers_second = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == deliv.id)
        )).scalars().all()
        assert len(offers_second) == 1
        assert deliv.dispatch_attempts == 1


@pytest.mark.asyncio
async def test_zero_candidate_attempt_recorded(monkeypatch):
    """Verify zero-candidate attempt is still recorded (attempts=1, 0 offers)."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Shop with NO riders anywhere nearby
        owner, cust, shop, _ = await _create_test_entities(session, rider_offsets=[])

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=150.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        assert deliv.dispatch_attempts == 1
        assert deliv.dispatch_started_at is not None
        assert deliv.awaiting_rider is False

        offers = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == deliv.id)
        )).scalars().all()
        assert len(offers) == 0


@pytest.mark.asyncio
async def test_get_offers_shows_only_authenticated_rider_open_offers(async_client: AsyncClient, monkeypatch):
    """Verify GET /api/v1/riders/me/offers filters accurately and computes distance & seconds."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.008, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(
            id=uuid.uuid4(),
            customer_id=cust.id,
            shop_id=shop.id,
            total_amount=300.0,
            status=OrderStatus.pending,
        )
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

    # Rider 1 queries offers
    res1 = await async_client.get(
        "/api/v1/riders/me/offers",
        headers=_auth_headers(rider1_user),
    )
    assert res1.status_code == 200
    offers1 = res1.json()
    assert len(offers1) == 1
    o1 = offers1[0]
    assert o1["shop"]["name"] == shop.name
    assert o1["shop"]["address"] == shop.address
    assert o1["pickup_distance_meters"] > 400.0
    assert o1["pickup_distance_meters"] < 700.0
    assert o1["estimated_earnings"] == 40.0
    assert o1["seconds_remaining"] > 0
    assert o1["seconds_remaining"] <= settings.DISPATCH_OFFER_TTL_SECONDS

    # Rider 2 queries offers
    res2 = await async_client.get(
        "/api/v1/riders/me/offers",
        headers=_auth_headers(rider2_user),
    )
    assert res2.status_code == 200
    offers2 = res2.json()
    assert len(offers2) == 1
    # Different offer ID for Rider 2
    assert offers2[0]["id"] != offers1[0]["id"]


@pytest.mark.asyncio
async def test_get_offers_excludes_expired_and_declined(async_client: AsyncClient, monkeypatch):
    """Verify GET /api/v1/riders/me/offers excludes expired and declined offers."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", False)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order1 = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, status=OrderStatus.confirmed, total_amount=100.0)
        order2 = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, status=OrderStatus.confirmed, total_amount=150.0)
        session.add_all([order1, order2])
        await session.flush()

        deliv1 = Delivery(id=uuid.uuid4(), order_id=order1.id, status=DeliveryStatus.pending, dispatch_attempts=1)
        deliv2 = Delivery(id=uuid.uuid4(), order_id=order2.id, status=DeliveryStatus.pending, dispatch_attempts=1)
        session.add_all([deliv1, deliv2])
        await session.flush()

        # 1. Expired offer on delivery 1
        o_expired = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=deliv1.id,
            rider_id=rider_profile.id,
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        # 2. Declined offer on delivery 2
        o_declined = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=deliv2.id,
            rider_id=rider_profile.id,
            attempt_no=1,
            status=DeliveryOfferStatus.declined.value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=20),
        )
        session.add_all([o_expired, o_declined])
        await session.commit()

    res = await async_client.get(
        "/api/v1/riders/me/offers",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 200
    assert len(res.json()) == 0


@pytest.mark.asyncio
async def test_get_offers_never_exposes_customer_details(async_client: AsyncClient, monkeypatch):
    """Security verification: GET /api/v1/riders/me/offers never includes customer details or drop address."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=200.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

    res = await async_client.get(
        "/api/v1/riders/me/offers",
        headers=_auth_headers(rider_user),
    )
    assert res.status_code == 200
    offer_dict = res.json()[0]

    # Must NOT expose customer sensitive info
    assert "customer_name" not in offer_dict
    assert "customer_phone" not in offer_dict
    assert "customer_email" not in offer_dict
    assert "customer_id" not in offer_dict
    assert "drop_address" not in offer_dict
    assert "destination_latitude" not in offer_dict
    assert "destination_longitude" not in offer_dict


@pytest.mark.asyncio
async def test_decline_ownership_and_idempotency(async_client: AsyncClient, monkeypatch):
    """Verify 403 on foreign offer decline, and idempotency on duplicate decline."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0), (0.006, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=200.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer1 = (await session.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.delivery_id == deliv.id,
                DeliveryOffer.rider_id == rider1_profile.id,
            )
        )).scalar_one()

    # 1. Rider 2 attempts to decline Rider 1's offer -> 403 Forbidden
    res_forbidden = await async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/decline",
        headers=_auth_headers(rider2_user),
    )
    assert res_forbidden.status_code == 403

    # 2. Rider 1 declines their own offer -> 200 OK
    res_decline1 = await async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/decline",
        headers=_auth_headers(rider1_user),
    )
    assert res_decline1.status_code == 200
    assert res_decline1.json()["status"] == "declined"
    resp_time = res_decline1.json()["responded_at"]
    assert resp_time is not None

    # 3. Rider 1 declines again -> 200 OK idempotent return
    res_decline2 = await async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/decline",
        headers=_auth_headers(rider1_user),
    )
    assert res_decline2.status_code == 200
    assert res_decline2.json()["status"] == "declined"
    assert res_decline2.json()["responded_at"] == resp_time


@pytest.mark.asyncio
async def test_immediate_escalation_after_last_decline(async_client: AsyncClient, monkeypatch):
    """Verify delivery escalates to attempt 2 immediately when the last open offer is declined."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Rider 1 is within 3km (Attempt 1). Rider 2 is at 4km (Attempt 2 only).
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.009, 0.0), (0.036, 0.0)]  # ~1km and ~4km
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=200.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        deliv = (await session.execute(
            select(Delivery).where(Delivery.order_id == order.id)
        )).scalar_one()

        offer1 = (await session.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.delivery_id == deliv.id,
                DeliveryOffer.rider_id == rider1_profile.id,
            )
        )).scalar_one()

    # Decline the only offer in attempt 1
    res = await async_client.post(
        f"/api/v1/riders/me/offers/{offer1.id}/decline",
        headers=_auth_headers(rider1_user),
    )
    assert res.status_code == 200

    # Verify delivery escalated immediately to attempt 2 and Rider 2 now has an offer
    async with async_session_maker() as session:
        deliv_refreshed = (await session.execute(
            select(Delivery).where(Delivery.id == deliv.id)
        )).scalar_one()
        assert deliv_refreshed.dispatch_attempts == 2

        offers_att2 = (await session.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.delivery_id == deliv.id,
                DeliveryOffer.attempt_no == 2,
            )
        )).scalars().all()
        assert len(offers_att2) == 1
        assert offers_att2[0].rider_id == rider2_profile.id
        assert offers_att2[0].status == "offered"


@pytest.mark.asyncio
async def test_stale_recovery_resets_awaiting_rider_and_reenters_dispatch(monkeypatch):
    """Verify order_recovery unassigns stale rider, resets awaiting_rider to False, and re-enters dispatch."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Shop and a candidate rider
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, status=OrderStatus.confirmed, total_amount=150.0)
        session.add(order)
        await session.flush()

        # Create delivery assigned 30 minutes ago (stale)
        old_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        deliv = Delivery(
            id=uuid.uuid4(),
            order_id=order.id,
            rider_id=rider_profile.id,
            status=DeliveryStatus.assigned,
            assigned_at=old_time,
            destination_location=WKTElement(f"POINT({SHOP_LON} {SHOP_LAT})", srid=4326),
            awaiting_rider=True,  # Old stale state
            dispatch_attempts=3,
        )
        rider_profile.is_available = False
        session.add(deliv)
        await session.commit()

        # Run stale delivery reconciliation
        recovered = await _reconcile_stale_deliveries_async(cutoff_seconds=600)
        assert recovered == 1

        # Previous rider freed
        await session.refresh(rider_profile)
        assert rider_profile.is_available is True

        # Replacement delivery exists, in pending, awaiting_rider is False, and re-entered dispatch
        new_deliv = (await session.execute(
            select(Delivery).where(
                Delivery.order_id == order.id,
                Delivery.status == DeliveryStatus.pending,
            )
        )).scalar_one()

        assert new_deliv.awaiting_rider is False
        assert new_deliv.dispatch_attempts == 1
        assert new_deliv.dispatch_started_at is not None


@pytest.mark.asyncio
async def test_get_offers_rate_limiting(async_client: AsyncClient, monkeypatch):
    """Verify GET /api/v1/riders/me/offers enforces rate limiting and returns 429 when threshold exceeded."""
    from app.core.rate_limit import rider_offers_rate_limiter
    # Temporarily set limit to 3 requests
    monkeypatch.setattr(rider_offers_rate_limiter, "_limit_getter", lambda: 3)
    await rider_offers_rate_limiter.reset()

    try:
        async with async_session_maker() as session:
            owner, cust, shop, riders = await _create_test_entities(session, rider_offsets=[(0.005, 0.0)])
            rider_user, _ = riders[0]

        headers = _auth_headers(rider_user)
        # Requests 1, 2, 3 should succeed
        for _ in range(3):
            res = await async_client.get("/api/v1/riders/me/offers", headers=headers)
            assert res.status_code == 200

        # 4th request must fail with 429 Too Many Requests
        res4 = await async_client.get("/api/v1/riders/me/offers", headers=headers)
        assert res4.status_code == 429
        assert "Retry-After" in res4.headers
        assert "Rate limit exceeded" in res4.json()["detail"]
    finally:
        await rider_offers_rate_limiter.reset()


@pytest.mark.asyncio
async def test_offer_ttl_matches_config(monkeypatch):
    """Verify offer expires_at is dynamically calculated from settings.DISPATCH_OFFER_TTL_SECONDS."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.005, 0.0)]
        )
        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=100.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

        await transition_order(
            db=session,
            order_id=order.id,
            to_status=OrderStatus.confirmed,
            actor=owner,
            actor_role="shop_owner",
        )

        offers = (await session.execute(
            select(DeliveryOffer).order_by(DeliveryOffer.offered_at.desc())
        )).scalars().all()
        assert len(offers) >= 1
        offer = offers[0]
        # Calculate duration between offered_at and expires_at
        ttl_seconds = (offer.expires_at - offer.offered_at).total_seconds()
        assert abs(ttl_seconds - settings.DISPATCH_OFFER_TTL_SECONDS) <= 1.0
        assert settings.DISPATCH_OFFER_TTL_SECONDS == 30


@pytest.mark.asyncio
async def test_periodic_escalation_by_time_widens_radius(monkeypatch):
    """Verify Celery escalation task advances attempt 1 to attempt 2 and widens radius to 5000m on offer expiration."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        # Shop at (SHOP_LON, SHOP_LAT)
        # Rider 1 close (0.01 deg lon ~ 1000m)
        # Rider 2 further out (0.035 deg lon ~ 3600m - outside 3000m, inside 5000m)
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.01, 0.0), (0.035, 0.0)]
        )
        rider1_user, rider1_profile = riders[0]
        rider2_user, rider2_profile = riders[1]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.pending)
        session.add(order)
        await session.commit()

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

        # In attempt 1: only rider 1 received offer
        offers_a1 = (await session.execute(
            select(DeliveryOffer).where(DeliveryOffer.delivery_id == delivery.id)
        )).scalars().all()
        assert len(offers_a1) == 1
        assert offers_a1[0].rider_id == rider1_profile.id
        assert offers_a1[0].attempt_no == 1

        # Simulate time passing: set offer 1 expires_at into the past
        past_time = datetime.now(timezone.utc) - timedelta(seconds=10)
        await session.execute(
            update(DeliveryOffer)
            .where(DeliveryOffer.id == offers_a1[0].id)
            .values(expires_at=past_time)
        )
        await session.commit()

        # Trigger periodic escalation task
        from app.tasks.order_recovery import _escalate_unassigned_dispatch_offers_async
        escalated_count = await _escalate_unassigned_dispatch_offers_async()
        assert escalated_count == 1

        # Re-fetch delivery and offers
        await session.refresh(delivery)
        assert delivery.dispatch_attempts == 2
        assert delivery.awaiting_rider is False

        # Attempt 1 offer is now marked expired
        await session.refresh(offers_a1[0])
        assert offers_a1[0].status == DeliveryOfferStatus.expired.value

        # Attempt 2 offer was created for rider 2 in the 5000m radius
        offers_a2 = (await session.execute(
            select(DeliveryOffer).where(
                DeliveryOffer.delivery_id == delivery.id,
                DeliveryOffer.attempt_no == 2,
            )
        )).scalars().all()
        assert len(offers_a2) == 1
        assert offers_a2[0].rider_id == rider2_profile.id
        assert offers_a2[0].status == DeliveryOfferStatus.offered.value


@pytest.mark.asyncio
async def test_escalation_exhaustion_marks_awaiting_rider(monkeypatch):
    """Verify that when maximum dispatch attempts are exhausted, delivery is marked awaiting_rider=True."""
    monkeypatch.setattr(settings, "DISPATCH_AUTO_ENABLED", True)

    async with async_session_maker() as session:
        owner, cust, shop, riders = await _create_test_entities(
            session,
            rider_offsets=[(0.01, 0.0)]
        )
        rider_user, rider_profile = riders[0]

        order = Order(id=uuid.uuid4(), customer_id=cust.id, shop_id=shop.id, total_amount=150.0, status=OrderStatus.confirmed)
        session.add(order)
        await session.flush()

        # Delivery on attempt 3 (max attempts) with expired offer
        deliv = Delivery(
            id=uuid.uuid4(),
            order_id=order.id,
            status=DeliveryStatus.pending,
            destination_location=WKTElement(f"POINT({SHOP_LON} {SHOP_LAT})", srid=4326),
            awaiting_rider=False,
            dispatch_attempts=settings.DISPATCH_MAX_ATTEMPTS,
            dispatch_started_at=datetime.now(timezone.utc) - timedelta(minutes=2),
        )
        session.add(deliv)
        await session.flush()

        offer = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=deliv.id,
            rider_id=rider_profile.id,
            attempt_no=settings.DISPATCH_MAX_ATTEMPTS,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        session.add(offer)
        await session.commit()

        # Run escalation task
        from app.tasks.order_recovery import _escalate_unassigned_dispatch_offers_async
        await _escalate_unassigned_dispatch_offers_async()

        await session.refresh(deliv)
        assert deliv.awaiting_rider is True
        assert deliv.dispatch_attempts == settings.DISPATCH_MAX_ATTEMPTS
