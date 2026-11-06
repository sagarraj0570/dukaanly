import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, cast
from sqlalchemy.ext.asyncio import AsyncSession
from geoalchemy2.types import Geography
from geoalchemy2.shape import to_shape

from app.db.session import get_db
from app.models.user import User, UserRole
from app.models.rider import RiderProfile
from app.models.delivery import Delivery, DeliveryStatus
from app.models.delivery_offer import DeliveryOffer, DeliveryOfferStatus
from app.models.order import Order
from app.models.shop import Shop
from app.schemas.rider import RiderProfileResponse, RiderAvailabilityUpdate, RiderLocationUpdate
from app.schemas.delivery import (
    DeliveryResponse,
    RiderOfferResponse,
    OfferShopInfo,
    OfferDeclineResponse,
    OfferAcceptResponse,
)
from app.services import rider as rider_service
from app.services import delivery as delivery_service
from app.api.dependencies import require_role
from app.core.rate_limit import rider_offers_rate_limiter

router = APIRouter()

@router.post("/profile", response_model=RiderProfileResponse, status_code=201)
async def create_rider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Create a rider profile for the current user."""
    return await rider_service.create_rider_profile(db=db, user=current_user)

@router.get("/me", response_model=RiderProfileResponse)
async def get_my_rider_profile(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Get the current rider's profile."""
    return await rider_service.get_rider_profile_by_user(db=db, user_id=current_user.id)

@router.patch("/me/availability", response_model=RiderProfileResponse)
async def update_my_availability(
    request: RiderAvailabilityUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Update the current rider's availability."""
    return await rider_service.update_rider_availability(db=db, user=current_user, is_available=request.is_available)

from app.schemas.rider import RiderLocationUpdate

@router.patch("/me/location", response_model=RiderProfileResponse)
async def update_my_location(
    request: RiderLocationUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Update the current rider's location."""
    return await rider_service.update_rider_location(db=db, user=current_user, latitude=request.latitude, longitude=request.longitude)


@router.get("/me/deliveries", response_model=list[DeliveryResponse])
async def get_my_deliveries(
    skip: int = 0,
    limit: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider))
):
    """Get all deliveries assigned to the current rider."""
    page = (skip // limit) + 1
    return await delivery_service.get_rider_deliveries(db=db, actor=current_user, page=page, size=limit)


@router.get("/me/offers", response_model=list[RiderOfferResponse])
async def get_my_offers(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider)),
):
    """
    Get active dispatch offers for the authenticated rider.
    Enforces:
    - Rate limiting using rider_offers_rate_limiter.
    - Only status == 'offered'.
    - expires_at > func.now() (database clock).
    - Delivery is still pending with rider_id IS NULL.
    - Calculates pickup distance using PostGIS ST_Distance.
    - Server-side seconds_remaining computed via database clock.
    - Never includes customer name, customer phone, or drop address.
    """
    allowed, retry_after = await rider_offers_rate_limiter.check_and_record(str(current_user.id))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Rate limit exceeded. Try again in {retry_after} seconds.",
            headers={"Retry-After": str(retry_after)},
        )

    # 1. Fetch rider profile
    rp_stmt = select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    rider_profile = (await db.execute(rp_stmt)).scalar_one_or_none()
    if not rider_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rider profile not found")

    # 2. Query open offers
    dist_expr = func.ST_Distance(
        cast(RiderProfile.location, Geography()),
        cast(Shop.location, Geography()),
    )
    sec_remaining_expr = func.extract(
        "epoch",
        DeliveryOffer.expires_at - func.now()
    )

    stmt = (
        select(
            DeliveryOffer.id,
            DeliveryOffer.delivery_id,
            DeliveryOffer.expires_at,
            DeliveryOffer.offered_at,
            Shop.id.label("shop_id"),
            Shop.name.label("shop_name"),
            Shop.address.label("shop_address"),
            Shop.location.label("shop_location"),
            dist_expr.label("pickup_distance_meters"),
            sec_remaining_expr.label("seconds_remaining"),
        )
        .join(Delivery, Delivery.id == DeliveryOffer.delivery_id)
        .join(Order, Order.id == Delivery.order_id)
        .join(Shop, Shop.id == Order.shop_id)
        .join(RiderProfile, RiderProfile.id == DeliveryOffer.rider_id)
        .where(
            DeliveryOffer.rider_id == rider_profile.id,
            DeliveryOffer.status == DeliveryOfferStatus.offered.value,
            DeliveryOffer.expires_at > func.now(),
            Delivery.status == DeliveryStatus.pending,
            Delivery.rider_id.is_(None),
        )
        .order_by(DeliveryOffer.offered_at.desc())
    )

    rows = (await db.execute(stmt)).all()

    offers: list[RiderOfferResponse] = []
    for r in rows:
        lat = None
        lon = None
        if r.shop_location is not None:
            pt = to_shape(r.shop_location)
            lat = pt.y
            lon = pt.x

        dist = float(r.pickup_distance_meters) if r.pickup_distance_meters is not None else 0.0
        sec_rem = max(0, int(r.seconds_remaining)) if r.seconds_remaining is not None else 0

        offers.append(
            RiderOfferResponse(
                id=r.id,
                delivery_id=r.delivery_id,
                shop=OfferShopInfo(
                    id=r.shop_id,
                    name=r.shop_name,
                    address=r.shop_address,
                    latitude=lat,
                    longitude=lon,
                ),
                pickup_distance_meters=round(dist, 1),
                estimated_earnings=40.0,
                expires_at=r.expires_at,
                seconds_remaining=sec_rem,
                offered_at=r.offered_at,
            )
        )

    return offers


@router.post("/me/offers/{offer_id}/decline", response_model=OfferDeclineResponse)
async def decline_offer(
    offer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider)),
):
    """
    Decline an automated proximity dispatch offer.
    Enforces:
    - Ownership check: 403 Forbidden if offer does not belong to authenticated rider.
    - Idempotency: declining an already declined offer returns the current state cleanly.
    - Sets status to 'declined' and responded_at to func.now().
    - Immediate escalation: if 0 open offers remain for that attempt, escalates immediately
      to the wider radius (or marks awaiting_rider=True) without waiting for TTL expiry.
    """
    # 1. Fetch rider profile
    rp_stmt = select(RiderProfile).where(RiderProfile.user_id == current_user.id)
    rider_profile = (await db.execute(rp_stmt)).scalar_one_or_none()
    if not rider_profile:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Rider profile not found")

    # 2. Lock offer row
    offer_stmt = select(DeliveryOffer).where(DeliveryOffer.id == offer_id).with_for_update()
    offer = (await db.execute(offer_stmt)).scalar_one_or_none()
    if not offer:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offer not found")

    # 3. Ownership check: Must belong to authenticated rider
    if offer.rider_id != rider_profile.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not own this offer",
        )

    # 4. Idempotency: if already declined, return current state
    if offer.status == DeliveryOfferStatus.declined.value:
        return OfferDeclineResponse(
            id=offer.id,
            status=offer.status,
            responded_at=offer.responded_at,
        )

    # 5. Transition offer to declined
    now_dt = datetime.now(timezone.utc)
    offer.status = DeliveryOfferStatus.declined.value
    offer.responded_at = now_dt
    db.add(offer)
    await db.flush()

    # 6. Immediate Escalation Check:
    # Count remaining open ('offered') offers for this delivery in the same attempt
    open_stmt = select(func.count(DeliveryOffer.id)).where(
        DeliveryOffer.delivery_id == offer.delivery_id,
        DeliveryOffer.attempt_no == offer.attempt_no,
        DeliveryOffer.status == DeliveryOfferStatus.offered.value,
    )
    open_count = (await db.execute(open_stmt)).scalar() or 0

    if open_count == 0:
        # No more open offers remain for this attempt. Immediately escalate delivery.
        from app.services.dispatch import escalate_dispatch
        await escalate_dispatch(db, offer.delivery_id)

    await db.commit()

    return OfferDeclineResponse(
        id=offer.id,
        status=offer.status,
        responded_at=offer.responded_at,
    )


@router.post("/me/offers/{offer_id}/accept", response_model=OfferAcceptResponse)
async def accept_offer(
    offer_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.rider)),
):
    """
    Atomically claims an automated proximity dispatch offer.
    Enforces all invariants within a single database transaction:
    - Ownership verification (403 if offer does not belong to rider)
    - State and database-time expiry checks (409 if expired or not in 'offered')
    - Rider on-duty and active check (409 if unavailable or inactive)
    - Row-level lock (SELECT ... FOR UPDATE) and conditional delivery update
    - Atomically sets is_available = False
    - Cancels competing open offers for the delivery
    - idx_active_delivery_per_rider IntegrityError rolls back all updates cleanly
    - Records OrderEvent audit entry
    - AFTER commit only: triggers ETA recalculation and publishes WebSocket delivery event
    """
    from app.services.dispatch import accept_dispatch_offer
    result = await accept_dispatch_offer(db=db, offer_id=offer_id, current_user=current_user)
    return OfferAcceptResponse(
        id=result["id"],
        delivery_id=result["delivery_id"],
        status=result["status"],
        responded_at=result["responded_at"],
        assigned_at=result["assigned_at"],
    )
