import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

logger = logging.getLogger(__name__)

from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.models.rider import RiderProfile
from app.models.shop import Shop
from app.schemas.delivery import DeliveryEtaResponse, DeliveryPreparationUpdate

async def create_delivery(db: AsyncSession, order_id: uuid.UUID, owner: User, dest_lat: float | None = None, dest_lon: float | None = None) -> Delivery:
    # Fetch Order
    stmt = select(Order).where(Order.id == order_id)
    order = (await db.execute(stmt)).scalar_one_or_none()
    
    if not order:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
        
    # Authorization: Admin, or Shop Owner of the shop
    if owner.role == UserRole.shop_owner:
        shop_stmt = select(Shop).where(Shop.id == order.shop_id)
        shop = (await db.execute(shop_stmt)).scalar_one_or_none()
        if not shop or shop.owner_id != owner.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to manage this order's delivery")
    elif owner.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to create delivery")
        
    # Business Rules
    if order.status == OrderStatus.pending:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Cannot create delivery for unpaid/pending order")
        
    delivery = Delivery(
        order_id=order_id,
        status=DeliveryStatus.pending
    )
    
    if dest_lat is not None and dest_lon is not None:
        delivery.destination_location = f"SRID=4326;POINT({dest_lon} {dest_lat})"
    
    db.add(delivery)
    try:
        await db.commit()
        await db.refresh(delivery)
        
        try:
            from app.services.delivery_eta import eta_service
            await eta_service.update_and_persist_delivery_eta(db, delivery.id, update_reason="order_confirmed", force=True)
        except Exception as e:
            logger.warning(f"Initial ETA calculation skipped for delivery {delivery.id}: {e}")
    except IntegrityError as exc:
        await db.rollback()
        err_msg = f"{exc} {getattr(exc, 'orig', '')}".lower()
        if "idx_active_delivery_per_order" in err_msg or "ix_deliveries_order_id" in err_msg:
            raise HTTPException(status.HTTP_409_CONFLICT, "Delivery already exists for this order")
        raise
        
    return delivery

async def assign_rider(db: AsyncSession, delivery_id: uuid.UUID, rider_id: uuid.UUID, owner: User) -> Delivery:
    stmt = select(Delivery).where(Delivery.id == delivery_id)
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    # Authorization: Admin or Shop Owner
    if owner.role == UserRole.shop_owner:
        # Check order -> shop -> owner
        order_stmt = select(Order).where(Order.id == delivery.order_id)
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        if not order:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
            
        shop_stmt = select(Shop).where(Shop.id == order.shop_id)
        shop = (await db.execute(shop_stmt)).scalar_one_or_none()
        if not shop or shop.owner_id != owner.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to assign rider to this delivery")
    elif owner.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to assign rider")
        
    # Validation: Delivery must be pending
    if delivery.status != DeliveryStatus.pending:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delivery is not in a pending state")
        
    # Validation: Rider must exist and be available
    rider_stmt = select(RiderProfile).where(RiderProfile.id == rider_id)
    rider = (await db.execute(rider_stmt)).scalar_one_or_none()
    
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider not found")
    if not rider.is_available:
        raise HTTPException(status.HTTP_409_CONFLICT, "Rider is not available")
        
    delivery.rider_id = rider_id
    delivery.status = DeliveryStatus.assigned
    delivery.assigned_at = datetime.now(timezone.utc)
    delivery.awaiting_rider = False
    
    # Rider should also become unavailable
    rider.is_available = False
    db.add(rider)
    db.add(delivery)
    
    # Cancel any open automated dispatch offers for this delivery
    from app.models.delivery_offer import DeliveryOffer
    await db.execute(
        update(DeliveryOffer)
        .where(
            DeliveryOffer.delivery_id == delivery.id,
            DeliveryOffer.status == "offered",
        )
        .values(status="cancelled", responded_at=datetime.now(timezone.utc))
    )
    
    # Check partial unique index exception
    try:
        await db.commit()
        await db.refresh(delivery)
        
        try:
            from app.services.delivery_eta import eta_service
            await eta_service.update_and_persist_delivery_eta(db, delivery.id, update_reason="rider_assigned", force=True)
        except Exception as e:
            logger.warning(f"ETA recalculation skipped on rider assignment {delivery.id}: {e}")

        # Publish real-time event
        from app.websockets.redis_pubsub import publish_delivery_event
        await publish_delivery_event(str(delivery.id), {
            "event": "delivery.status_changed",
            "version": 1,
            "delivery_id": str(delivery.id),
            "timestamp": delivery.assigned_at.isoformat() if delivery.assigned_at else datetime.now(timezone.utc).isoformat(),
            "data": {
                "status": delivery.status.value,
                "rider_id": str(rider_id)
            }
        })
        
        # Trigger background notification task
        from app.tasks.notifications import create_notification
        
        # Fetch the order customer to notify
        stmt = select(Order).where(Order.id == delivery.order_id)
        order = (await db.execute(stmt)).scalar_one_or_none()
        if order:
            create_notification.delay(
                user_id=str(order.customer_id),
                title="Rider Assigned",
                body="A rider has been assigned to your delivery.",
                notification_type="DELIVERY_ASSIGNED",
                reference_id=str(delivery.id),
                data={"delivery_id": str(delivery.id), "rider_id": str(rider_id)}
            )
    except IntegrityError as exc:
        await db.rollback()
        err_msg = f"{exc} {getattr(exc, 'orig', '')}".lower()
        if "idx_active_delivery_per_rider" in err_msg:
            raise HTTPException(status.HTTP_409_CONFLICT, "Rider already has an active delivery")
        raise
        
    return delivery

async def update_delivery_status(db: AsyncSession, delivery_id: uuid.UUID, new_status: DeliveryStatus, actor: User, reason: str | None = None) -> Delivery:
    """Update delivery operational status using centralized state machine."""
    from app.services.state_machine import transition_delivery
    return await transition_delivery(
        db=db,
        delivery_id=delivery_id,
        to_status=new_status,
        actor=actor,
        reason=reason,
    )

async def get_delivery(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> Delivery:
    stmt = select(Delivery).where(Delivery.id == delivery_id)
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    if actor.role == UserRole.admin:
        return delivery
        
    order_stmt = select(Order).where(Order.id == delivery.order_id)
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    
    if actor.role == UserRole.customer:
        if not order or order.customer_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this delivery")
    elif actor.role == UserRole.shop_owner:
        shop_stmt = select(Shop).where(Shop.id == order.shop_id)
        shop = (await db.execute(shop_stmt)).scalar_one_or_none()
        if not shop or shop.owner_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this delivery")
    elif actor.role == UserRole.rider:
        rider_stmt = select(RiderProfile).where(RiderProfile.user_id == actor.id)
        rider = (await db.execute(rider_stmt)).scalar_one_or_none()
        if not rider or delivery.rider_id != rider.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view this delivery")
            
    return delivery

async def get_rider_deliveries(db: AsyncSession, actor: User, page: int = 1, size: int = 20):
    if actor.role != UserRole.rider:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Only riders can access their deliveries")
        
    rider_stmt = select(RiderProfile).where(RiderProfile.user_id == actor.id)
    rider = (await db.execute(rider_stmt)).scalar_one_or_none()
    if not rider:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Rider profile not found")
        
    stmt = select(Delivery).where(Delivery.rider_id == rider.id).order_by(Delivery.created_at.desc()).offset((page - 1) * size).limit(size)
    deliveries = (await db.execute(stmt)).scalars().all()
    return deliveries

from typing import List, Dict, Any
from sqlalchemy import func, and_, exists, cast
from sqlalchemy.orm import joinedload
from app.core.config import settings
from datetime import timedelta
from app.services.osrm import (
    osrm_service,
    OSRMError,
    OSRMInvalidCoordinatesError,
    OSRMNoRouteError,
    OSRMTimeoutError,
    OSRMProviderError,
)

async def get_rider_candidates(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> List[Dict[str, Any]]:
    # 1. Authorize & Get Delivery
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop)
        )
        .where(Delivery.id == delivery_id)
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    if actor.role == UserRole.shop_owner:
        if not delivery.order:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
        shop = delivery.order.shop
        if not shop or shop.owner_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to manage this delivery")
    elif actor.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
        
    if delivery.destination_location is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delivery has no destination location")
        
    # 2. Candidate Discovery using PostgreSQL PostGIS ST_DWithin and ST_Distance
    active_deliveries = select(Delivery.id).where(
        and_(
            Delivery.rider_id == RiderProfile.id,
            Delivery.status.in_([DeliveryStatus.assigned, DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery])
        )
    ).correlate(RiderProfile)
    
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=settings.RIDER_LOCATION_MAX_AGE_SECONDS)
    radius = settings.RIDER_SEARCH_RADIUS_METERS
    
    from geoalchemy2.types import Geography
    from geoalchemy2.shape import to_shape
    
    dest_query = select(Delivery.destination_location).where(Delivery.id == delivery_id).scalar_subquery()
    
    # Distance in meters (casting Geometry to Geography)
    dist_func = func.ST_Distance(
        cast(RiderProfile.location, Geography()),
        cast(dest_query, Geography())
    )
    
    query = (
        select(
            RiderProfile.id,
            RiderProfile.is_available,
            RiderProfile.location_updated_at,
            RiderProfile.location,
            dist_func.label("distance_meters")
        )
        .where(
            RiderProfile.is_available == True,
            RiderProfile.location.is_not(None),
            RiderProfile.location_updated_at >= cutoff_time,
            ~exists(active_deliveries),
            func.ST_DWithin(
                cast(RiderProfile.location, Geography()),
                cast(dest_query, Geography()),
                radius
            )
        )
        .order_by("distance_meters", RiderProfile.id)
        .limit(10)
    )
    
    results = await db.execute(query)

    dest_shape = to_shape(delivery.destination_location)
    dest_lat, dest_lon = dest_shape.y, dest_shape.x
    
    candidates = []
    for row in results:
        cand: Dict[str, Any] = {
            "rider_id": row.id,
            "distance_meters": float(row.distance_meters),
            "road_distance_meters": None,
            "estimated_duration_seconds": None,
            "estimated_duration_minutes": None,
            "is_available": row.is_available,
            "location_updated_at": row.location_updated_at,
            "routing_status": "straight_line_fallback",
        }
        if row.location:
            shape = to_shape(row.location)
            cand["latitude"] = float(shape.y)
            cand["longitude"] = float(shape.x)
        candidates.append(cand)

    # Rank top candidates using OSRM Table API
    max_to_route = settings.RIDER_MAX_CANDIDATES_TO_ROUTE
    candidates_to_route = [c for c in candidates[:max_to_route] if "latitude" in c and "longitude" in c]

    if candidates_to_route:
        try:
            sources = [(c["latitude"], c["longitude"]) for c in candidates_to_route]
            destinations = [(dest_lat, dest_lon)]
            matrix = await osrm_service.get_table_matrix(sources, destinations)

            durations = matrix.get("durations", [])
            distances = matrix.get("distances", [])

            for i, c in enumerate(candidates_to_route):
                has_duration = i < len(durations) and durations[i] and durations[i][0] is not None
                has_distance = i < len(distances) and distances[i] and distances[i][0] is not None
                if has_duration:
                    c["estimated_duration_seconds"] = round(float(durations[i][0]), 1)
                    c["estimated_duration_minutes"] = round(float(durations[i][0]) / 60.0, 1)
                    c["routing_status"] = "routed"
                else:
                    c["routing_status"] = "unroutable"

                if has_distance:
                    c["road_distance_meters"] = round(float(distances[i][0]), 1)

            # Re-rank routed candidates according to documented policy:
            # 1. Routable candidates ('routed') always precede unroutable candidates ('unroutable').
            # 2. Routable candidates sort by estimated_duration_seconds, tie-broken by distance_meters.
            # 3. Unroutable candidates are placed behind all routed candidates, sorting amongst themselves by distance_meters.
            candidates_to_route.sort(
                key=lambda x: (
                    0 if x.get("routing_status") == "routed" else 1,
                    x["estimated_duration_seconds"] if x["estimated_duration_seconds"] is not None else float("inf"),
                    x["distance_meters"]
                )
            )

            # Candidates beyond max_to_route retain 'not_evaluated'
            for c in candidates[len(candidates_to_route):]:
                c["routing_status"] = "not_evaluated"

            # Recombine with unrouted candidates
            remaining = candidates[len(candidates_to_route):]
            candidates = candidates_to_route + remaining

        except OSRMError as e:
            logger.warning(
                "OSRM candidate ranking unavailable (%s). Falling back to pure PostGIS distance ranking.",
                e,
            )
            for c in candidates:
                c["routing_status"] = "straight_line_fallback"
        except Exception as e:
            logger.warning(
                "Unexpected error during OSRM candidate ranking (%s). Falling back to pure PostGIS distance.",
                e,
            )
            for c in candidates:
                c["routing_status"] = "straight_line_fallback"

    # Clean up temporary lat/lon helper keys before returning to match RiderCandidateResponse schema
    for c in candidates:
        c.pop("latitude", None)
        c.pop("longitude", None)

    return candidates

async def auto_assign_delivery(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> Delivery:
    candidates = await get_rider_candidates(db, delivery_id, actor)
    
    if not candidates:
        raise HTTPException(status.HTTP_409_CONFLICT, "NO_AVAILABLE_RIDER")
        
    nearest_rider_id = candidates[0]["rider_id"]
    
    # Attempt assignment transactionally using existing assign_rider logic
    delivery = await assign_rider(db, delivery_id, nearest_rider_id, actor)
        
    return delivery

async def get_delivery_route(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> Dict[str, Any]:
    """Retrieve full multi-leg road route from OSRM for this delivery."""
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop),
            joinedload(Delivery.rider)
        )
        .where(Delivery.id == delivery_id)
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    # Authorization checks
    is_authorized = False
    if actor.role == UserRole.admin or getattr(actor, "is_superuser", False):
        is_authorized = True
    elif actor.role == UserRole.customer and delivery.order and delivery.order.customer_id == actor.id:
        is_authorized = True
    elif actor.role == UserRole.shop_owner and delivery.order and delivery.order.shop and delivery.order.shop.owner_id == actor.id:
        is_authorized = True
    elif actor.role == UserRole.rider and delivery.rider and delivery.rider.user_id == actor.id:
        is_authorized = True

    if not is_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view route for this delivery")

    from geoalchemy2.shape import to_shape

    # 1. Shop Location
    shop = delivery.order.shop if delivery.order else None
    if not shop or not shop.location:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Shop location missing")
    shop_shape = to_shape(shop.location)
    shop_lat, shop_lon = float(shop_shape.y), float(shop_shape.x)
    shop_info = {"latitude": shop_lat, "longitude": shop_lon, "name": shop.name or "Merchant Shop"}

    # 2. Destination Location
    if not delivery.destination_location:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Delivery destination location missing")
    dest_shape = to_shape(delivery.destination_location)
    dest_lat, dest_lon = float(dest_shape.y), float(dest_shape.x)
    dest_info = {"latitude": dest_lat, "longitude": dest_lon, "name": "Customer Delivery Address"}

    # 3. Rider Location (if assigned and reporting)
    rider_loc = None
    rider_info = None
    if delivery.rider and delivery.rider.location:
        rider_shape = to_shape(delivery.rider.location)
        rider_lat, rider_lon = float(rider_shape.y), float(rider_shape.x)
        rider_loc = (rider_lat, rider_lon)
        rider_info = {"latitude": rider_lat, "longitude": rider_lon, "name": "Delivery Partner"}

    # 4. Terminal delivery check: cancelled or delivered deliveries have no active road route
    status_str = delivery.status.value if hasattr(delivery.status, "value") else str(delivery.status)
    if status_str in ("delivered", "cancelled"):
        return {
            "delivery_id": delivery.id,
            "status": delivery.status,
            "rider_location": rider_info,
            "shop_location": shop_info,
            "customer_location": dest_info,
            "legs": [],
            "total_distance_meters": 0.0,
            "total_duration_seconds": 0.0,
            "total_duration_minutes": 0.0,
            "combined_geometry": [],
            "active_leg_index": 0,
            "is_fallback": False,
            "cached": True,
            "attribution": "Delivery terminal (tracking closed)",
        }

    # 5. Fetch Multi-Leg OSRM Route
    try:
        route_data = await osrm_service.get_multi_leg_delivery_route(
            rider_loc=rider_loc,
            shop_loc=(shop_lat, shop_lon),
            customer_loc=(dest_lat, dest_lon),
            delivery_status=delivery.status.value,
        )
    except OSRMInvalidCoordinatesError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    except OSRMNoRouteError:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "No drivable route found between delivery locations")
    except OSRMTimeoutError:
        raise HTTPException(status.HTTP_504_GATEWAY_TIMEOUT, "Routing service timed out while calculating delivery route")
    except (OSRMProviderError, OSRMError) as e:
        logger.warning(f"OSRM routing provider error: {e}")
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, "Routing service temporarily unavailable")

    return {
        "delivery_id": delivery.id,
        "status": delivery.status,
        "rider_location": rider_info,
        "shop_location": shop_info,
        "customer_location": dest_info,
        "legs": route_data["legs"],
        "total_distance_meters": route_data["total_distance_meters"],
        "total_duration_seconds": route_data["total_duration_seconds"],
        "total_duration_minutes": route_data["total_duration_minutes"],
        "combined_geometry": route_data["combined_geometry"],
        "active_leg_index": route_data["active_leg_index"],
        "is_fallback": route_data["is_fallback"],
        "cached": route_data["cached"],
        "attribution": route_data["attribution"],
    }


async def get_delivery_eta(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> DeliveryEtaResponse:
    """Retrieve current Smart Delivery ETA for this delivery with strict ownership verification."""
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop),
            joinedload(Delivery.rider),
        )
        .where(Delivery.id == delivery_id)
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")

    # Strict authorization: Customer of order, fulfilling Shop Owner, Assigned Rider, or Admin
    is_authorized = False
    if actor.role == UserRole.admin or getattr(actor, "is_superuser", False):
        is_authorized = True
    elif actor.role == UserRole.customer and delivery.order and delivery.order.customer_id == actor.id:
        is_authorized = True
    elif actor.role == UserRole.shop_owner and delivery.order and delivery.order.shop and delivery.order.shop.owner_id == actor.id:
        is_authorized = True
    elif actor.role == UserRole.rider and delivery.rider and delivery.rider.user_id == actor.id:
        is_authorized = True

    if not is_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to view ETA for this delivery")

    from app.services.delivery_eta import eta_service
    shop = delivery.order.shop if delivery.order else None
    calc_data = await eta_service.calculate_delivery_eta(
        delivery=delivery,
        shop=shop,
        rider=delivery.rider,
    )
    return eta_service._build_response(delivery, calc_data=calc_data)


async def update_delivery_preparation(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    prep_in: DeliveryPreparationUpdate,
    actor: User,
) -> DeliveryEtaResponse:
    """Update shop preparation estimate and optional delay reason for an order's delivery."""
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop),
            joinedload(Delivery.rider),
        )
        .where(Delivery.id == delivery_id)
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")

    # Authorization: Shop owner of fulfilling shop or admin
    is_authorized = False
    if actor.role == UserRole.admin or getattr(actor, "is_superuser", False):
        is_authorized = True
    elif actor.role == UserRole.shop_owner and delivery.order and delivery.order.shop and delivery.order.shop.owner_id == actor.id:
        is_authorized = True

    if not is_authorized:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to update preparation for this delivery")

    now = datetime.now(timezone.utc)
    delivery.preparation_estimated_minutes = prep_in.estimated_minutes
    if prep_in.started_at:
        delivery.preparation_started_at = prep_in.started_at
    elif delivery.preparation_started_at is None:
        delivery.preparation_started_at = now

    if prep_in.delay_reason:
        delivery.eta_delay_reason = prep_in.delay_reason

    db.add(delivery)
    await db.commit()
    await db.refresh(delivery)

    from app.services.delivery_eta import eta_service
    return await eta_service.update_and_persist_delivery_eta(
        db, delivery.id, update_reason="preparation_updated", force=True
    )


