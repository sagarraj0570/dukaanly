"""
Automated Proximity Dispatch Service (Stage A2).

Provides PostGIS candidate rider discovery for automated proximity dispatch.
All spatial filters use database-indexed PostGIS functions (ST_DWithin, ST_Distance)
against PostgreSQL geometry/geography types. Distance math in Python is strictly prohibited.
"""

import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime, timezone

from sqlalchemy import select, update, func, and_, exists, cast
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload
from sqlalchemy.exc import IntegrityError
from geoalchemy2.types import Geography
from geoalchemy2.shape import to_shape
from fastapi import HTTPException, status

from app.core.config import settings
from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order, OrderEvent
from app.models.shop import Shop
from app.models.user import User
from app.models.rider import RiderProfile
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus

logger = logging.getLogger(__name__)


def get_dispatch_radius(attempt_no: int) -> int:
    """Returns search radius in meters for the given dispatch attempt."""
    if attempt_no <= 1:
        return settings.DISPATCH_ATTEMPT_1_RADIUS_METERS
    return settings.DISPATCH_ATTEMPT_2_RADIUS_METERS


def rerank_candidates_osrm(candidates: List[Dict[str, Any]], shop: Shop) -> List[Dict[str, Any]]:
    """
    Hook function for candidate re-ranking (e.g. road-network ETA).
    In Stage A2, this is a strict no-op passthrough returning candidates in straight-line PostGIS order,
    eliminating external network failure modes.
    """
    return candidates


async def select_dispatch_candidates(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    attempt_no: int = 1,
) -> List[Dict[str, Any]]:
    """
    Discovers candidate riders for a delivery attempt based on proximity to the shop.

    Filtering invariants (enforced purely in PostgreSQL PostGIS):
    1. is_available is True (on-duty and not currently assigned).
    2. location is not NULL.
    3. location_updated_at is fresh within RIDER_LOCATION_MAX_AGE_SECONDS using database time (func.now()).
    4. User.is_active is True.
    5. ST_DWithin(rider.location::geography, shop.location::geography, radius) matches.
    6. Rider does NOT currently hold an active delivery in ('assigned', 'picked_up', 'out_for_delivery').
    7. Rider was NOT already offered this delivery in prior attempts (any offer status).
    8. Documented concurrency policy: Riders with open offers on OTHER deliveries remain eligible;
       the first accept wins and the loser gets a clean HTTP 409 from idx_active_delivery_per_rider.
    9. Ordered by PostGIS straight-line distance ASC.
    10. Limited to settings.DISPATCH_BATCH_SIZE (default 5).
    """
    # 1. Fetch delivery with Order and Shop
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop)
        )
        .where(Delivery.id == delivery_id)
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery or not delivery.order or not delivery.order.shop:
        logger.warning(f"Delivery {delivery_id} has missing order or shop association")
        return []

    shop = delivery.order.shop
    if shop.location is None:
        logger.warning(f"Shop {shop.id} for delivery {delivery_id} has no location coordinates")
        return []

    radius_meters = get_dispatch_radius(attempt_no)

    # 2. Correlated subquery: Rider must not have an active delivery (protects idx_active_delivery_per_rider)
    active_deliveries = select(Delivery.id).where(
        and_(
            Delivery.rider_id == RiderProfile.id,
            Delivery.status.in_([
                DeliveryStatus.assigned,
                DeliveryStatus.picked_up,
                DeliveryStatus.out_for_delivery,
            ])
        )
    ).correlate(RiderProfile)

    # 3. Correlated subquery: Rider must not have been offered this delivery in any attempt
    prior_offers = select(DeliveryOffer.id).where(
        and_(
            DeliveryOffer.delivery_id == delivery.id,
            DeliveryOffer.rider_id == RiderProfile.id,
        )
    ).correlate(RiderProfile)

    # 4. Shop location subquery: evaluated directly in PostgreSQL without Python parameter serialization
    shop_loc = select(Shop.location).where(Shop.id == shop.id).scalar_subquery()

    # 5. Straight-line PostGIS distance from rider to shop (in meters)
    dist_expr = func.ST_Distance(
        cast(RiderProfile.location, Geography()),
        cast(shop_loc, Geography())
    )

    # 6. Database-time cutoff interval for location freshness
    location_freshness_check = (
        RiderProfile.location_updated_at >= func.now() - func.make_interval(0, 0, 0, 0, 0, 0, settings.RIDER_LOCATION_MAX_AGE_SECONDS)
    )

    query = (
        select(
            RiderProfile.id,
            RiderProfile.user_id,
            RiderProfile.is_available,
            RiderProfile.location_updated_at,
            RiderProfile.location,
            dist_expr.label("distance_meters"),
        )
        .join(User, User.id == RiderProfile.user_id)
        .where(
            User.is_active == True,
            RiderProfile.is_available == True,
            RiderProfile.location.is_not(None),
            location_freshness_check,
            ~exists(active_deliveries),
            ~exists(prior_offers),
            func.ST_DWithin(
                cast(RiderProfile.location, Geography()),
                cast(shop_loc, Geography()),
                radius_meters
            )
        )
        .order_by(dist_expr.asc(), RiderProfile.id.asc())
        .limit(settings.DISPATCH_BATCH_SIZE)
    )

    results = await db.execute(query)
    rows = results.all()

    candidates: List[Dict[str, Any]] = []
    for row in rows:
        candidates.append({
            "rider_id": row.id,
            "user_id": row.user_id,
            "distance_meters": float(row.distance_meters),
            "is_available": row.is_available,
            "location_updated_at": row.location_updated_at,
            "routing_status": "straight_line_postgis",
        })

    return rerank_candidates_osrm(candidates, shop)


async def create_dispatch_batch(
    db: AsyncSession,
    delivery_id: uuid.UUID,
) -> List[DeliveryOffer]:
    """
    Creates the initial (attempt 1) proximity dispatch batch for a delivery.
    
    Locks the delivery row (SELECT ... FOR UPDATE).
    Checks dispatch_attempts: if > 0, returns immediately without creating a second batch.
    Increments dispatch_attempts to 1, sets dispatch_started_at.
    Discovers candidates and inserts DeliveryOffer rows with database-time TTL.
    If 0 candidates are discovered, dispatch_attempts is still incremented so the escalation
    engine can immediately expand the radius without waiting a full TTL.
    """
    stmt = (
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update()
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        logger.warning(f"Delivery {delivery_id} not found for dispatch batch creation")
        return []

    # Only pending, unassigned deliveries with 0 prior attempts can start initial batch
    if delivery.status != DeliveryStatus.pending or delivery.rider_id is not None:
        logger.info(f"Delivery {delivery_id} is in status '{delivery.status.value}' (rider={delivery.rider_id}). Skipping dispatch.")
        return []

    if (delivery.dispatch_attempts or 0) > 0:
        logger.info(f"Delivery {delivery_id} has already initiated dispatch (attempts={delivery.dispatch_attempts}). Idempotent skip.")
        return []

    # 1. Increment attempt counter & set start timestamp
    delivery.dispatch_attempts = 1
    delivery.dispatch_started_at = func.now()
    delivery.awaiting_rider = False
    db.add(delivery)

    # 2. Select candidates for attempt 1
    candidates = await select_dispatch_candidates(db, delivery.id, attempt_no=1)
    
    created_offers: List[DeliveryOffer] = []
    ttl_interval = func.make_interval(0, 0, 0, 0, 0, 0, settings.DISPATCH_OFFER_TTL_SECONDS)

    for cand in candidates:
        offer = DeliveryOffer(
            id=uuid.uuid4(),
            delivery_id=delivery.id,
            rider_id=cand["rider_id"],
            attempt_no=1,
            status=DeliveryOfferStatus.offered.value,
            expires_at=func.now() + ttl_interval,
        )
        db.add(offer)
        created_offers.append(offer)

    await db.flush()
    logger.info(
        f"Dispatch batch created for delivery {delivery.id} (attempt 1): "
        f"{len(created_offers)} offers created for {len(candidates)} candidates."
    )
    return created_offers


async def escalate_dispatch(
    db: AsyncSession,
    delivery_id: uuid.UUID,
) -> bool:
    """
    Advances a delivery's proximity dispatch lifecycle to the next attempt or marks it awaiting_rider.
    
    Triggered when:
    1. Celery periodic task detects all offers in the current attempt have expired.
    2. A rider's decline leaves 0 remaining open ('offered') offers for that attempt.
    3. An attempt found 0 candidates and can expand immediately.
    
    Returns True if a new attempt batch was created, False if waiting or exhausted (awaiting_rider=True).
    """
    stmt = (
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update()
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        return False

    if delivery.status != DeliveryStatus.pending or delivery.rider_id is not None:
        return False

    if delivery.awaiting_rider:
        return False

    # 1. Expire any overdue open offers relative to database clock
    await db.execute(
        update(DeliveryOffer)
        .where(
            DeliveryOffer.delivery_id == delivery.id,
            DeliveryOffer.status == DeliveryOfferStatus.offered.value,
            DeliveryOffer.expires_at <= func.now(),
        )
        .values(
            status=DeliveryOfferStatus.expired.value,
            responded_at=func.now(),
        )
    )

    # 2. Check if any offers are still active ('offered' and unexpired)
    open_count_stmt = select(func.count(DeliveryOffer.id)).where(
        DeliveryOffer.delivery_id == delivery.id,
        DeliveryOffer.status == DeliveryOfferStatus.offered.value,
    )
    open_count = (await db.execute(open_count_stmt)).scalar() or 0
    if open_count > 0:
        # Current attempt is still in-flight
        return False

    # 3. All offers in the current attempt are closed. Check if we can expand radius to next attempt
    current_attempts = delivery.dispatch_attempts or 0

    if current_attempts < settings.DISPATCH_MAX_ATTEMPTS:
        next_attempt = current_attempts + 1
        delivery.dispatch_attempts = next_attempt
        delivery.dispatch_started_at = func.now()
        db.add(delivery)

        candidates = await select_dispatch_candidates(db, delivery.id, attempt_no=next_attempt)
        ttl_interval = func.make_interval(0, 0, 0, 0, 0, 0, settings.DISPATCH_OFFER_TTL_SECONDS)

        for cand in candidates:
            offer = DeliveryOffer(
                id=uuid.uuid4(),
                delivery_id=delivery.id,
                rider_id=cand["rider_id"],
                attempt_no=next_attempt,
                status=DeliveryOfferStatus.offered.value,
                expires_at=func.now() + ttl_interval,
            )
            db.add(offer)

        await db.flush()
        logger.info(
            f"Escalated delivery {delivery.id} to attempt {next_attempt}: "
            f"{len(candidates)} new candidates discovered."
        )
        return True
    else:
        # All dispatch attempts exhausted: fall back to manual merchant assignment
        delivery.awaiting_rider = True
        db.add(delivery)
        await db.flush()
        logger.info(
            f"Delivery {delivery.id} exhausted {current_attempts} dispatch attempts. "
            f"Marked awaiting_rider=True for manual assignment fallback."
        )
        return False


async def accept_dispatch_offer(
    db: AsyncSession,
    offer_id: uuid.UUID,
    current_user: User,
) -> Dict[str, Any]:
    """
    Atomically claims an automated proximity dispatch offer in ONE transaction.
    
    1. Locks the delivery row (SELECT ... FOR UPDATE) and offer row.
    2. Verifies ownership: 403 Forbidden if offer.rider_id != rider_profile.id.
    3. Verifies offer status: 409 Conflict if offer.status != 'offered'.
    4. Verifies database-clock expiry: 409 Conflict if offer.expires_at <= func.now().
    5. Verifies rider availability: 409 Conflict if rider is not available or user inactive.
    6. Conditionally updates delivery:
       UPDATE deliveries SET rider_id = :rider_id, status = 'assigned', assigned_at = func.now(), awaiting_rider = false
       WHERE id = :delivery_id AND rider_id IS NULL AND status = 'pending'
       If rowcount == 0: 409 Conflict (taken or cancelled).
    7. Sets rider_profile.is_available = False.
    8. Marks this offer as 'accepted' with responded_at = func.now().
    9. Cancels all other open offers for that delivery: status = 'cancelled', responded_at = func.now().
    10. Writes OrderEvent row (actor_role='rider', reason='Delivery accepted via automated proximity dispatch').
    11. Commits atomically. Catches IntegrityError (idx_active_delivery_per_rider), rolls back fully, returns 409.
    12. AFTER commit only: triggers ETA recalculation and publishes WebSocket status event.
        Publishing or ETA failures do not fail or roll back the claim.
    """
    # 1. Fetch authenticated rider's profile
    rp_stmt = select(RiderProfile).where(RiderProfile.user_id == current_user.id).with_for_update()
    rider_profile = (await db.execute(rp_stmt)).scalar_one_or_none()
    if not rider_profile:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Rider profile not found",
        )

    # 2. Check rider active status and availability
    if not current_user.is_active:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rider user account is inactive",
        )

    if not rider_profile.is_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Rider is off duty or not available",
        )

    # 3. Fetch and lock the offer along with database-clock expiry evaluation
    offer_stmt = (
        select(
            DeliveryOffer,
            (func.now() >= DeliveryOffer.expires_at).label("is_expired"),
        )
        .where(DeliveryOffer.id == offer_id)
        .with_for_update()
    )
    row = (await db.execute(offer_stmt)).one_or_none()
    if not row:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Offer not found",
        )
    offer, is_expired = row

    # 4. Ownership check: Must belong to authenticated rider
    if offer.rider_id != rider_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not own this offer",
        )

    # 5. Offer state check: Must be 'offered'
    if offer.status != DeliveryOfferStatus.offered.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Offer cannot be accepted: status is '{offer.status}'",
        )

    # 6. Database clock expiry check
    if is_expired:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Offer has expired",
        )

    # 7. Lock the delivery row
    deliv_stmt = (
        select(Delivery)
        .where(Delivery.id == offer.delivery_id)
        .with_for_update()
    )
    delivery = (await db.execute(deliv_stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Delivery not found",
        )

    if delivery.status != DeliveryStatus.pending or delivery.rider_id is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Delivery is no longer available (already assigned or cancelled)",
        )

    # 8. Conditional atomic update on delivery and state transitions within single transaction
    try:
        delivery_update = (
            update(Delivery)
            .where(
                Delivery.id == delivery.id,
                Delivery.rider_id.is_(None),
                Delivery.status == DeliveryStatus.pending,
            )
            .values(
                rider_id=rider_profile.id,
                status=DeliveryStatus.assigned,
                assigned_at=func.now(),
                awaiting_rider=False,
            )
        )
        res = await db.execute(delivery_update)
        if res.rowcount == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Delivery is no longer available (already assigned or cancelled)",
            )

        # 9. Set rider availability to false in the same transaction
        rider_profile.is_available = False
        db.add(rider_profile)

        # 10. Mark winning offer accepted with responded_at
        now_dt = datetime.now(timezone.utc)
        offer.status = DeliveryOfferStatus.accepted.value
        offer.responded_at = now_dt
        db.add(offer)

        # 11. Cancel all other open offers for that delivery
        cancel_stmt = (
            update(DeliveryOffer)
            .where(
                DeliveryOffer.delivery_id == delivery.id,
                DeliveryOffer.id != offer.id,
                DeliveryOffer.status == DeliveryOfferStatus.offered.value,
            )
            .values(
                status=DeliveryOfferStatus.cancelled.value,
                responded_at=func.now(),
            )
        )
        await db.execute(cancel_stmt)

        # 12. Write OrderEvent row
        order_stmt = select(Order).where(Order.id == delivery.order_id)
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        current_order_state = order.status.value if order else "confirmed"

        audit_event = OrderEvent(
            id=uuid.uuid4(),
            order_id=delivery.order_id,
            from_state=current_order_state,
            to_state=current_order_state,
            actor_id=current_user.id,
            actor_role="rider",
            reason="Delivery accepted via automated proximity dispatch",
            created_at=now_dt,
        )
        db.add(audit_event)

        # 13. Commit transaction atomically
        await db.commit()

    except HTTPException:
        await db.rollback()
        raise
    except IntegrityError as exc:
        await db.rollback()
        err_msg = f"{exc} {getattr(exc, 'orig', '')}".lower()
        logger.warning(f"IntegrityError on dispatch offer accept {offer_id}: {err_msg}")
        if "idx_active_delivery_per_rider" in err_msg or "active_delivery" in err_msg or "uq_active_rider_delivery" in err_msg:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Rider already has an active delivery",
            )
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Conflict: Delivery claim failed constraint validation",
        )

    # 14. AFTER commit only: trigger ETA recalculation and WebSocket event publishing
    await db.refresh(delivery)
    await db.refresh(offer)

    try:
        from app.services.delivery_eta import eta_service
        await eta_service.update_and_persist_delivery_eta(db, delivery.id, update_reason="rider_assigned", force=True)
    except Exception as exc:
        logger.warning(f"ETA recalculation failed or skipped on offer accept for delivery {delivery.id}: {exc}")

    try:
        from app.websockets.redis_pubsub import publish_delivery_event
        await publish_delivery_event(str(delivery.id), {
            "event": "delivery.status_changed",
            "version": 1,
            "delivery_id": str(delivery.id),
            "timestamp": delivery.assigned_at.isoformat() if delivery.assigned_at else now_dt.isoformat(),
            "data": {
                "status": delivery.status.value,
                "rider_id": str(rider_profile.id),
                "order_id": str(delivery.order_id),
            }
        })
    except Exception as exc:
        logger.warning(f"WebSocket publishing failed on offer accept for delivery {delivery.id}: {exc}")

    return {
        "id": offer.id,
        "delivery_id": delivery.id,
        "status": offer.status,
        "responded_at": offer.responded_at,
        "assigned_at": delivery.assigned_at,
    }
