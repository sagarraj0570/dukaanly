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

async def create_delivery(db: AsyncSession, order_id: uuid.UUID, owner: User) -> Delivery:
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
    
    # Check partial unique index exception
    try:
        await db.commit()
        await db.refresh(delivery)
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
            
    await db.commit()
    await db.refresh(delivery)
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
