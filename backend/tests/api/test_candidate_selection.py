"""
Candidate Selection Test Suite (Stage A2).

Verifies the PostgreSQL PostGIS proximity candidate discovery service:
1. Radius filter per attempt (3000m for attempt 1, 5000m for attempt 2).
2. Stale location excluded (> 120s old relative to database clock).
3. NULL location excluded.
4. Off-duty riders (is_available=False) excluded.
5. Inactive user accounts (User.is_active=False) excluded.
6. Riders with an active delivery excluded across all three active states (assigned, picked_up, out_for_delivery).
7. Prior-attempt riders excluded while newly reachable riders in the wider radius are included.
8. Distance ordering strictly ascending by straight-line PostGIS distance.
9. Batch limit strictly capped to DISPATCH_BATCH_SIZE (default 5).
10. Empty list returned when no candidates match.
11. Riders with open offers on OTHER deliveries remain eligible (documented concurrency decision).
"""

import uuid
import pytest
from datetime import datetime, timezone, timedelta
from geoalchemy2.elements import WKTElement
from sqlalchemy import text

from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.order import Order, OrderStatus
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus
from app.services.dispatch import select_dispatch_candidates, get_dispatch_radius
from app.core.config import settings


# Reference Shop Location: Boring Road Crossing, Patna (25.6144, 85.1158)
SHOP_LAT = 25.6144
SHOP_LON = 85.1158

# Offsets for distances relative to (25.6144, 85.1158):
# 1 degree lat is ~111,000 meters.
# ~1.0 km away: +0.009 lat
# ~2.5 km away: +0.0225 lat (inside attempt 1: 3000m)
# ~4.0 km away: +0.0360 lat (outside attempt 1: 3000m, inside attempt 2: 5000m)
# ~6.5 km away: +0.0585 lat (outside attempt 2: 5000m)


async def _create_test_env(session):
    """Sets up a clean test merchant and delivery."""
    suffix = uuid.uuid4().hex[:8]
    cust = User(
        id=uuid.uuid4(),
        name=f"Customer {suffix}",
        email=f"cust_{suffix}@test.com",
        password_hash="h",
        role=UserRole.customer,
        is_active=True,
    )
    owner = User(
        id=uuid.uuid4(),
        name=f"Owner {suffix}",
        email=f"owner_{suffix}@test.com",
        password_hash="h",
        role=UserRole.shop_owner,
        is_active=True,
    )
    session.add_all([cust, owner])
    await session.flush()

    shop = Shop(
        id=uuid.uuid4(),
        owner_id=owner.id,
        name=f"Dispatch Shop {suffix}",
        address="Boring Road, Patna",
        location=WKTElement(f"SRID=4326;POINT({SHOP_LON} {SHOP_LAT})"),
        is_active=True,
    )
    session.add(shop)
    await session.flush()

    order = Order(
        id=uuid.uuid4(),
        customer_id=cust.id,
        shop_id=shop.id,
        status=OrderStatus.confirmed,
        total_amount=200.0,
    )
    session.add(order)
    await session.flush()

    delivery = Delivery(
        id=uuid.uuid4(),
        order_id=order.id,
        status=DeliveryStatus.pending,
        destination_location=WKTElement(f"SRID=4326;POINT({SHOP_LON + 0.01} {SHOP_LAT + 0.01})"),
    )
    session.add(delivery)
    await session.commit()
    return shop, order, delivery


async def _create_rider(
    session,
    lat: float | None = None,
    lon: float | None = None,
    is_available: bool = True,
    is_active: bool = True,
    location_updated_seconds_ago: int = 10,
) -> tuple[User, RiderProfile]:
    """Helper to create a rider with specific spatial and state attributes."""
    suffix = uuid.uuid4().hex[:8]
    user = User(
        id=uuid.uuid4(),
        name=f"Rider {suffix}",
        email=f"rider_{suffix}@test.com",
        password_hash="h",
        role=UserRole.rider,
        is_active=is_active,
    )
    session.add(user)
    await session.flush()

    loc = None
    if lat is not None and lon is not None:
        loc = WKTElement(f"SRID=4326;POINT({lon} {lat})")

    loc_updated = datetime.now(timezone.utc) - timedelta(seconds=location_updated_seconds_ago)

    rider = RiderProfile(
        id=uuid.uuid4(),
        user_id=user.id,
        is_available=is_available,
        location=loc,
        location_updated_at=loc_updated,
    )
    session.add(rider)
    await session.commit()
    return user, rider


@pytest.mark.asyncio
async def test_radius_filter_per_attempt():
    """Verify attempt 1 uses 3000m radius and attempt 2 expands to 5000m radius."""
    assert get_dispatch_radius(1) == 3000
    assert get_dispatch_radius(2) == 5000

    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Rider 1: ~2.0 km away (inside attempt 1 & 2)
        _, r_near = await _create_rider(session, lat=SHOP_LAT + 0.018, lon=SHOP_LON)
        # Rider 2: ~4.0 km away (outside attempt 1 [3km], inside attempt 2 [5km])
        _, r_mid = await _create_rider(session, lat=SHOP_LAT + 0.036, lon=SHOP_LON)
        # Rider 3: ~6.5 km away (outside both attempts)
        _, r_far = await _create_rider(session, lat=SHOP_LAT + 0.0585, lon=SHOP_LON)

        # Attempt 1: only r_near matches
        cands_att1 = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids_att1 = [c["rider_id"] for c in cands_att1]
        assert r_near.id in cand_ids_att1
        assert r_mid.id not in cand_ids_att1
        assert r_far.id not in cand_ids_att1

        # Attempt 2: both r_near and r_mid match (r_far still excluded)
        cands_att2 = await select_dispatch_candidates(session, delivery.id, attempt_no=2)
        cand_ids_att2 = [c["rider_id"] for c in cands_att2]
        assert r_near.id in cand_ids_att2
        assert r_mid.id in cand_ids_att2
        assert r_far.id not in cand_ids_att2


@pytest.mark.asyncio
async def test_stale_location_excluded():
    """Verify riders with location older than RIDER_LOCATION_MAX_AGE_SECONDS (120s) are excluded."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Fresh location (15 seconds ago) -> included
        _, r_fresh = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, location_updated_seconds_ago=15)
        # Stale location (300 seconds ago > 120s threshold) -> excluded
        _, r_stale = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, location_updated_seconds_ago=300)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids = [c["rider_id"] for c in cands]
        assert r_fresh.id in cand_ids
        assert r_stale.id not in cand_ids


@pytest.mark.asyncio
async def test_null_location_excluded():
    """Verify riders with location IS NULL are excluded."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        _, r_null = await _create_rider(session, lat=None, lon=None)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids = [c["rider_id"] for c in cands]
        assert r_null.id not in cand_ids


@pytest.mark.asyncio
async def test_off_duty_riders_excluded():
    """Verify is_available=False riders are excluded."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        _, r_offduty = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, is_available=False)
        _, r_onduty = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, is_available=True)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids = [c["rider_id"] for c in cands]
        assert r_offduty.id not in cand_ids
        assert r_onduty.id in cand_ids


@pytest.mark.asyncio
async def test_inactive_users_excluded():
    """Verify User.is_active=False riders are excluded."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        _, r_inactive = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, is_active=False)
        _, r_active = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON, is_active=True)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids = [c["rider_id"] for c in cands]
        assert r_inactive.id not in cand_ids
        assert r_active.id in cand_ids


@pytest.mark.asyncio
async def test_riders_with_active_deliveries_excluded():
    """Verify riders holding an active delivery (assigned, picked_up, out_for_delivery) are excluded."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Create distinct orders for each background delivery to respect idx_active_delivery_per_order
        async def _make_order():
            o = Order(id=uuid.uuid4(), customer_id=order.customer_id, shop_id=shop.id, status=OrderStatus.confirmed, total_amount=100.0)
            session.add(o)
            await session.flush()
            return o

        o1 = await _make_order()
        o2 = await _make_order()
        o3 = await _make_order()
        o4 = await _make_order()

        # Rider on 'assigned' delivery
        _, r_assigned = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON)
        d_assigned = Delivery(id=uuid.uuid4(), order_id=o1.id, rider_id=r_assigned.id, status=DeliveryStatus.assigned)
        session.add(d_assigned)

        # Rider on 'picked_up' delivery
        _, r_picked = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON)
        d_picked = Delivery(id=uuid.uuid4(), order_id=o2.id, rider_id=r_picked.id, status=DeliveryStatus.picked_up)
        session.add(d_picked)

        # Rider on 'out_for_delivery'
        _, r_out = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON)
        d_out = Delivery(id=uuid.uuid4(), order_id=o3.id, rider_id=r_out.id, status=DeliveryStatus.out_for_delivery)
        session.add(d_out)

        # Rider on 'delivered' (completed) -> eligible
        _, r_delivered = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON)
        d_delivered = Delivery(id=uuid.uuid4(), order_id=o4.id, rider_id=r_delivered.id, status=DeliveryStatus.delivered)
        session.add(d_delivered)

        await session.commit()

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        cand_ids = [c["rider_id"] for c in cands]
        assert r_assigned.id not in cand_ids
        assert r_picked.id not in cand_ids
        assert r_out.id not in cand_ids
        assert r_delivered.id in cand_ids


@pytest.mark.asyncio
async def test_prior_attempt_riders_excluded_while_new_wider_riders_included():
    """Verify riders offered in attempt 1 (regardless of status) are excluded in attempt 2, allowing new riders."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Rider 1 (near, 1km away) - offered in attempt 1
        _, r1_prior = await _create_rider(session, lat=SHOP_LAT + 0.009, lon=SHOP_LON)
        # Rider 2 (mid, 4km away) - only in range for attempt 2
        _, r2_new = await _create_rider(session, lat=SHOP_LAT + 0.036, lon=SHOP_LON)

        # Record prior offer for r1 on this delivery (expired/declined)
        offer1 = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            rider_id=r1_prior.id,
            attempt_no=1,
            status=DeliveryOfferStatus.expired.value,
            expires_at=datetime.now(timezone.utc) - timedelta(seconds=10),
        )
        session.add(offer1)
        await session.commit()

        # In attempt 2, r1_prior must be excluded, and r2_new must be returned
        cands_att2 = await select_dispatch_candidates(session, delivery.id, attempt_no=2)
        cand_ids = [c["rider_id"] for c in cands_att2]
        assert r1_prior.id not in cand_ids, "Prior-attempt riders must be excluded from subsequent attempts"
        assert r2_new.id in cand_ids, "Newly reached riders in wider attempt radius must be discovered"


@pytest.mark.asyncio
async def test_distance_ordering_ascending():
    """Verify candidates are ordered strictly ascending by PostGIS distance."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        created_riders = []
        for i in range(3):
            dist_offset = 0.003 * (i + 1)
            _, r = await _create_rider(session, lat=SHOP_LAT + dist_offset, lon=SHOP_LON)
            created_riders.append(r)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        distances = [c["distance_meters"] for c in cands]
        assert len(distances) >= 3
        assert distances == sorted(distances), "Candidates must be ordered strictly ascending by PostGIS distance"
        assert cands[0]["rider_id"] == created_riders[0].id
        assert cands[1]["rider_id"] == created_riders[1].id
        assert cands[2]["rider_id"] == created_riders[2].id


@pytest.mark.asyncio
async def test_batch_limit_capped():
    """Verify results are strictly capped at settings.DISPATCH_BATCH_SIZE (default 5)."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Create 8 riders within 3km
        for i in range(8):
            dist_offset = 0.002 * (i + 1)
            await _create_rider(session, lat=SHOP_LAT + dist_offset, lon=SHOP_LON)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        assert len(cands) == settings.DISPATCH_BATCH_SIZE
        assert len(cands) == 5


@pytest.mark.asyncio
async def test_no_candidates_returns_empty_list():
    """Verify returns empty list when no candidate meets the filters."""
    async with async_session_maker() as session:
        shop, order, delivery = await _create_test_env(session)

        # Place rider 20km away in Danapur/outer Patna
        _, r_distant = await _create_rider(session, lat=SHOP_LAT + 0.20, lon=SHOP_LON)

        cands = await select_dispatch_candidates(session, delivery.id, attempt_no=1)
        assert cands == []


@pytest.mark.asyncio
async def test_riders_with_offers_on_other_deliveries_stay_eligible():
    """
    DOCUMENTED CONCURRENCY POLICY TEST:
    A rider who has an open offer on Delivery X is NOT excluded from receiving an offer on Delivery Y.
    First accept will claim the delivery and set is_available=False; any concurrent claim gets HTTP 409
    from idx_active_delivery_per_rider.
    """
    async with async_session_maker() as session:
        shop, order1, delivery1 = await _create_test_env(session)
        # Create delivery 2
        order2 = Order(id=uuid.uuid4(), customer_id=order1.customer_id, shop_id=shop.id, status=OrderStatus.confirmed, total_amount=120.0)
        session.add(order2)
        await session.flush()
        delivery2 = Delivery(id=uuid.uuid4(), order_id=order2.id, status=DeliveryStatus.pending)
        session.add(delivery2)
        await session.flush()

        # Rider close to shop
        _, shared_rider = await _create_rider(session, lat=SHOP_LAT + 0.005, lon=SHOP_LON)

        # Open offer on delivery1
        offer_d1 = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=delivery1.id,
            rider_id=shared_rider.id,
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=30),
        )
        session.add(offer_d1)
        await session.commit()

        # Query candidates for delivery2: shared_rider MUST still be eligible
        cands_d2 = await select_dispatch_candidates(session, delivery2.id, attempt_no=1)
        cand_ids_d2 = [c["rider_id"] for c in cands_d2]
        assert shared_rider.id in cand_ids_d2, "Riders with open offers on other deliveries must remain discoverable"
