import uuid
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from fastapi import HTTPException, status
from sqlalchemy.exc import IntegrityError

from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order, OrderStatus
from app.models.user import User, UserRole
from app.models.rider import RiderProfile
from app.models.shop import Shop

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
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Delivery already exists for this order")
        
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
    
    # Rider should also become unavailable
    rider.is_available = False
    db.add(rider)
    
    # Check partial unique index exception
    try:
        await db.commit()
        await db.refresh(delivery)
        
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
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Rider already has an active delivery")
        
    return delivery

async def update_delivery_status(db: AsyncSession, delivery_id: uuid.UUID, new_status: DeliveryStatus, actor: User) -> Delivery:
    stmt = select(Delivery).where(Delivery.id == delivery_id)
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    # Authorize Rider or Admin
    if actor.role == UserRole.rider:
        rider_stmt = select(RiderProfile).where(RiderProfile.user_id == actor.id)
        rider = (await db.execute(rider_stmt)).scalar_one_or_none()
        if not rider or delivery.rider_id != rider.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to update this delivery")
    elif actor.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to update delivery status")
        
    # Validate transition
    valid_transitions = {
        DeliveryStatus.pending: [DeliveryStatus.assigned, DeliveryStatus.cancelled],
        DeliveryStatus.assigned: [DeliveryStatus.picked_up, DeliveryStatus.cancelled],
        DeliveryStatus.picked_up: [DeliveryStatus.out_for_delivery],
        DeliveryStatus.out_for_delivery: [DeliveryStatus.delivered]
    }
    
    if new_status not in valid_transitions.get(delivery.status, []):
        raise HTTPException(status.HTTP_409_CONFLICT, f"Invalid transition from {delivery.status.value} to {new_status.value}")
        
    delivery.status = new_status
    now = datetime.now(timezone.utc)
    
    if new_status == DeliveryStatus.picked_up:
        delivery.picked_up_at = now
    elif new_status == DeliveryStatus.delivered:
        delivery.delivered_at = now
        
    # Sync with Order
    order_stmt = select(Order).where(Order.id == delivery.order_id)
    order = (await db.execute(order_stmt)).scalar_one_or_none()
    if order:
        if new_status == DeliveryStatus.picked_up:
            order.status = OrderStatus.ready_for_delivery # Optional sync logically
        elif new_status == DeliveryStatus.out_for_delivery:
            order.status = OrderStatus.out_for_delivery
        elif new_status == DeliveryStatus.delivered:
            order.status = OrderStatus.delivered
            
    # Auto-reactivate rider if delivery is terminal
    if new_status in [DeliveryStatus.delivered, DeliveryStatus.cancelled] and delivery.rider_id:
        rider_stmt = select(RiderProfile).where(RiderProfile.id == delivery.rider_id)
        rider = (await db.execute(rider_stmt)).scalar_one_or_none()
        if rider:
            rider.is_available = True
            db.add(rider)
            
    await db.commit()
    await db.refresh(delivery)
    
    from app.websockets.redis_pubsub import publish_delivery_event
    await publish_delivery_event(str(delivery.id), {
        "event": "delivery.status_changed",
        "version": 1,
        "delivery_id": str(delivery.id),
        "timestamp": now.isoformat(),
        "data": {
            "status": delivery.status.value
        }
    })
    
    # Trigger background notification task
    from app.tasks.notifications import create_notification
    if order:
        create_notification.delay(
            user_id=str(order.customer_id),
            title="Delivery Update",
            body=f"Your delivery is now {new_status.value.replace('_', ' ')}.",
            notification_type=f"DELIVERY_{new_status.name.upper()}",
            reference_id=str(delivery.id),
            data={"delivery_id": str(delivery.id), "status": new_status.value}
        )
    
    return delivery

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
from app.core.config import settings
from datetime import timedelta

async def get_rider_candidates(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> List[Dict[str, Any]]:
    # 1. Authorize & Get Delivery
    stmt = select(Delivery).where(Delivery.id == delivery_id)
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Delivery not found")
        
    if actor.role == UserRole.shop_owner:
        order_stmt = select(Order).where(Order.id == delivery.order_id)
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        if not order:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Order not found")
        shop_stmt = select(Shop).where(Shop.id == order.shop_id)
        shop = (await db.execute(shop_stmt)).scalar_one_or_none()
        if not shop or shop.owner_id != actor.id:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized to manage this delivery")
    elif actor.role != UserRole.admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Not authorized")
        
    if delivery.destination_location is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "Delivery has no destination location")
        
    # 2. Candidate Discovery
    # Subquery: Active deliveries for a rider
    active_deliveries = select(Delivery.id).where(
        and_(
            Delivery.rider_id == RiderProfile.id,
            Delivery.status.in_([DeliveryStatus.assigned, DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery])
        )
    ).correlate(RiderProfile)
    
    # max_age
    cutoff_time = datetime.now(timezone.utc) - timedelta(seconds=settings.RIDER_LOCATION_MAX_AGE_SECONDS)
    radius = settings.RIDER_SEARCH_RADIUS_METERS
    
    from geoalchemy2.types import Geography
    
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
    )
    
    results = await db.execute(query)
    
    candidates = []
    for row in results:
        candidates.append({
            "rider_id": row.id,
            "distance_meters": float(row.distance_meters),
            "is_available": row.is_available,
            "location_updated_at": row.location_updated_at
        })
        
    return candidates

async def auto_assign_delivery(db: AsyncSession, delivery_id: uuid.UUID, actor: User) -> Delivery:
    candidates = await get_rider_candidates(db, delivery_id, actor)
    
    if not candidates:
        raise HTTPException(status.HTTP_409_CONFLICT, "NO_AVAILABLE_RIDER")
        
    nearest_rider_id = candidates[0]["rider_id"]
    
    # Attempt assignment transactionally using existing assign_rider logic
    delivery = await assign_rider(db, delivery_id, nearest_rider_id, actor)
        
    return delivery
