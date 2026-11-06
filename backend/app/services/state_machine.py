"""
State machine service for managing Order and Delivery state transitions.
Enforces actor permissions, row-level concurrency locking (SELECT ... FOR UPDATE),
idempotent repeated transitions, audit trail recording (OrderEvent),
and atomic order cancellation with exactly-once deterministic stock restoration.
"""
import uuid
import logging
from datetime import datetime, timezone
from typing import Optional, Sequence
from fastapi import HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.user import User, UserRole
from app.models.order import Order, OrderStatus, OrderEvent
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile
from app.models.inventory import Inventory
from app.models.shop import Shop
from app.core.config import settings

logger = logging.getLogger(__name__)

# Permitted Order transitions
ORDER_TRANSITIONS: dict[OrderStatus, list[OrderStatus]] = {
    OrderStatus.pending: [OrderStatus.confirmed, OrderStatus.cancelled],
    OrderStatus.confirmed: [OrderStatus.preparing, OrderStatus.cancelled],
    OrderStatus.preparing: [OrderStatus.ready_for_delivery, OrderStatus.cancelled],
    OrderStatus.ready_for_delivery: [OrderStatus.out_for_delivery, OrderStatus.cancelled],
    OrderStatus.out_for_delivery: [OrderStatus.delivered],
    OrderStatus.delivered: [],
    OrderStatus.cancelled: [],
}

# Permitted Delivery transitions
DELIVERY_TRANSITIONS: dict[DeliveryStatus, list[DeliveryStatus]] = {
    DeliveryStatus.pending: [DeliveryStatus.assigned, DeliveryStatus.cancelled],
    DeliveryStatus.assigned: [DeliveryStatus.picked_up, DeliveryStatus.cancelled],
    DeliveryStatus.picked_up: [DeliveryStatus.out_for_delivery],
    DeliveryStatus.out_for_delivery: [DeliveryStatus.delivered],
    DeliveryStatus.delivered: [],
    DeliveryStatus.cancelled: [],
}


def _validate_order_actor_permission(
    order: Order,
    to_status: OrderStatus,
    actor: Optional[User],
    effective_role: str,
    shop: Optional[Shop],
    reason: Optional[str],
) -> None:
    """Enforce server-side permissions and role invariants for order transitions."""
    if effective_role in ["admin", UserRole.admin.value, "system"]:
        return

    if effective_role in ["customer", UserRole.customer.value]:
        # Customer can only transition an order to cancelled
        if to_status != OrderStatus.cancelled:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Customers are only authorized to cancel orders"
            )
        # Check current order state for customer cancellation
        if order.status == OrderStatus.pending:
            return  # Pending orders can be cancelled freely by customer
        elif order.status in [OrderStatus.confirmed, OrderStatus.preparing]:
            # Mandatory nonempty cancellation reason when already confirmed or preparing
            if not reason or not reason.strip():
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Cancellation reason is required when order is already confirmed or preparing"
                )
            # Cannot cancel if active delivery has already progressed past assigned
            if order.delivery and order.delivery.status in [
                DeliveryStatus.picked_up,
                DeliveryStatus.out_for_delivery,
                DeliveryStatus.delivered
            ]:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail="Cannot cancel order once the delivery has been picked up"
                )
            return
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Customers cannot cancel orders in state '{order.status.value}'"
            )

    if effective_role in ["shop_owner", UserRole.shop_owner.value]:
        # Shop owner transitions
        if order.status == OrderStatus.pending:
            if to_status == OrderStatus.confirmed:
                return
            elif to_status == OrderStatus.cancelled:
                # Rejection requires mandatory reason
                if not reason or not reason.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Rejection reason is required"
                    )
                return
        elif order.status == OrderStatus.confirmed:
            if to_status == OrderStatus.preparing:
                return
            elif to_status == OrderStatus.cancelled:
                if not reason or not reason.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cancellation reason is required"
                    )
                if order.delivery and order.delivery.status in [
                    DeliveryStatus.picked_up,
                    DeliveryStatus.out_for_delivery,
                    DeliveryStatus.delivered
                ]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cannot cancel order after delivery has been picked up"
                    )
                return
        elif order.status == OrderStatus.preparing:
            if to_status == OrderStatus.ready_for_delivery:
                return
            elif to_status == OrderStatus.cancelled:
                if not reason or not reason.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cancellation reason is required"
                    )
                if order.delivery and order.delivery.status in [
                    DeliveryStatus.picked_up,
                    DeliveryStatus.out_for_delivery,
                    DeliveryStatus.delivered
                ]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cannot cancel order after delivery has been picked up"
                    )
                return
        elif order.status == OrderStatus.ready_for_delivery:
            if to_status == OrderStatus.cancelled:
                if not reason or not reason.strip():
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="Cancellation reason is required"
                    )
                if order.delivery and order.delivery.status in [
                    DeliveryStatus.picked_up,
                    DeliveryStatus.out_for_delivery,
                    DeliveryStatus.delivered
                ]:
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="Cannot cancel order after delivery has been picked up"
                    )
                return
            elif to_status == OrderStatus.out_for_delivery:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Only assigned riders can mark deliveries out for delivery"
                )

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Shop owner cannot transition order from '{order.status.value}' to '{to_status.value}'"
        )

    if effective_role in ["rider", UserRole.rider.value]:
        # Riders modify deliveries, not orders directly (unless system sync)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Riders cannot update orders directly; update the assigned delivery instead"
        )

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized actor role")

    if effective_role == "rider" or effective_role == UserRole.rider.value:
        # Riders modify deliveries, not orders directly (unless system sync)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Riders cannot update orders directly; update the assigned delivery instead"
        )

    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Unauthorized actor role")


async def transition_order(
    db: AsyncSession,
    order_id: uuid.UUID,
    to_status: OrderStatus,
    actor: Optional[User] = None,
    actor_role: Optional[str] = None,
    reason: Optional[str] = None,
    shop_id: Optional[uuid.UUID] = None,
) -> Order:
    """
    Centralized, concurrency-safe transition for an Order.
    - Acquires row lock (SELECT ... FOR UPDATE).
    - Checks actor authorization and ownership.
    - Enforces idempotency: returns order directly if already in target state.
    - Validates state machine transition rules (HTTP 409 on illegal jump).
    - Restores inventory stock atomically in deterministic product_id order on cancellation.
    - Cancels active delivery and frees rider on cancellation.
    - Records OrderEvent audit record.
    """
    effective_role = actor_role or (actor.role.value if actor and hasattr(actor, "role") else "system")

    # 1. Fetch Order with row-level lock
    stmt = (
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.delivery),
            selectinload(Order.events),
        )
        .where(Order.id == order_id)
        .with_for_update()
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if shop_id and order.shop_id != shop_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found in this shop")

    # 2. Fetch Shop if shop owner
    shop = None
    if effective_role in ["shop_owner", UserRole.shop_owner.value]:
        shop_stmt = select(Shop).where(Shop.id == order.shop_id)
        shop = (await db.execute(shop_stmt)).scalar_one_or_none()

    # 3. Verify actor ownership & resource access
    if effective_role in ["customer", UserRole.customer.value]:
        if not actor or order.customer_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify this order"
            )
    elif effective_role in ["shop_owner", UserRole.shop_owner.value]:
        if not actor:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Authentication required")
        if not shop or shop.owner_id != actor.id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Not authorized to modify orders for this shop"
            )
    elif effective_role in ["rider", UserRole.rider.value]:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Riders cannot update orders directly; update the assigned delivery instead"
        )

    # 4. Idempotency Guard: if already in target state, return cleanly without side effects
    if order.status == to_status:
        logger.info(f"Order {order_id} is already in state '{to_status.value}'. Idempotent return.")
        return order

    # 5. Validate State Machine Transition (Lifecycle jump violation -> 409 Conflict)
    allowed_next = ORDER_TRANSITIONS.get(order.status, [])
    if to_status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": f"Cannot transition order from {order.status.value} to {to_status.value}",
                "current_state": order.status.value,
                "allowed_next_states": [s.value for s in allowed_next],
            }
        )

    # 6. Check actor role permissions and transition prerequisites
    _validate_order_actor_permission(
        order=order,
        to_status=to_status,
        actor=actor,
        effective_role=effective_role,
        shop=shop,
        reason=reason,
    )

    # 6. Perform State Transition & Side Effects
    from_status = order.status
    order.status = to_status

    # 6a. Cancellation: Exactly-once inventory restoration & delivery release
    if to_status == OrderStatus.cancelled:
        from app.services.reservation import release_order_reservations
        from app.models.inventory_reservation import InventoryReservation, ReservationStatus
        from app.models.payment import Payment, PaymentStatus
        from sqlalchemy import func

        # Synchronize payment records following canonical lock hierarchy (Order -> Payment -> InventoryReservation -> Inventory)
        pay_stmt = select(Payment).where(Payment.order_id == order.id).with_for_update()
        order_payments = (await db.execute(pay_stmt)).scalars().all()
        for p in order_payments:
            if p.status in [PaymentStatus.created, PaymentStatus.pending, PaymentStatus.authorized]:
                p.status = PaymentStatus.cancelled
                p.failure_reason = reason or f"Order cancelled from state '{from_status.value}'"
                db.add(p)
            elif p.status == PaymentStatus.captured:
                p.status = PaymentStatus.refunded
                p.failure_reason = reason or f"Order cancelled from state '{from_status.value}' (simulated mock refund)"
                db.add(p)

        # Check if reservations exist for this order
        res_count_stmt = select(func.count(InventoryReservation.id)).where(InventoryReservation.order_id == order.id)
        total_order_reservations = (await db.execute(res_count_stmt)).scalar() or 0

        if total_order_reservations > 0:
            # All reservation-backed orders MUST use the centralized reservation service for stock restoration.
            # If the order was confirmed/preparing, its reservations were in 'consumed' status.
            # If the order was pending, its reservations were in 'active' status.
            allowed_from = [ReservationStatus.active]
            if from_status in [OrderStatus.confirmed, OrderStatus.preparing]:
                allowed_from.append(ReservationStatus.consumed)

            await release_order_reservations(
                db=db,
                order_id=order.id,
                release_reason=reason or f"Order cancelled from state '{from_status.value}'",
                to_status=ReservationStatus.released,
                from_statuses=allowed_from,
            )
            # Reservation-backed orders NEVER execute direct update(Inventory)
        else:
            # Fallback ONLY for legacy orders created without reservation records (total_order_reservations == 0)
            valid_items = [i for i in order.items if i.product_id]
            sorted_items = sorted(valid_items, key=lambda i: str(i.product_id))

            for item in sorted_items:
                await db.execute(
                    update(Inventory)
                    .where(Inventory.product_id == item.product_id)
                    .values(
                        stock=Inventory.stock + item.quantity,
                        version=Inventory.version + 1,
                    )
                )

        # Cancel active delivery and release assigned rider
        if order.delivery and order.delivery.status in [
            DeliveryStatus.pending,
            DeliveryStatus.assigned,
        ]:
            order.delivery.status = DeliveryStatus.cancelled
            if order.delivery.rider_id:
                rider_stmt = select(RiderProfile).where(RiderProfile.id == order.delivery.rider_id)
                rider = (await db.execute(rider_stmt)).scalar_one_or_none()
                if rider:
                    rider.is_available = True
                    db.add(rider)

            # Cancel any open automated dispatch offers
            from app.models.delivery_offer import DeliveryOffer
            await db.execute(
                update(DeliveryOffer)
                .where(
                    DeliveryOffer.delivery_id == order.delivery.id,
                    DeliveryOffer.status == "offered",
                )
                .values(status="cancelled", responded_at=datetime.now(timezone.utc))
            )
            db.add(order.delivery)

    # 6b. Preparing: record preparation_started_at on delivery snapshot
    elif to_status == OrderStatus.preparing and order.delivery:
        if not order.delivery.preparation_started_at:
            order.delivery.preparation_started_at = datetime.now(timezone.utc)
            db.add(order.delivery)

    # 6c. Confirmed: Automated proximity dispatch trigger
    elif to_status == OrderStatus.confirmed:
        if settings.DISPATCH_AUTO_ENABLED and settings.DISPATCH_TRIGGER == "confirmed":
            if order.delivery is None:
                order.delivery = Delivery(
                    order_id=order.id,
                    status=DeliveryStatus.pending,
                )
                db.add(order.delivery)
                await db.flush()

            from app.services.dispatch import create_dispatch_batch
            await create_dispatch_batch(db, order.delivery.id)

    # 7. Record OrderEvent audit record
    event = OrderEvent(
        order_id=order.id,
        from_state=from_status.value,
        to_state=to_status.value,
        actor_id=actor.id if actor else None,
        actor_role=effective_role,
        reason=reason,
    )
    db.add(event)

    # 8. Commit atomically
    await db.commit()

    # 9. Reload with updated relationships
    reload_stmt = (
        select(Order)
        .options(
            selectinload(Order.items),
            selectinload(Order.delivery),
            selectinload(Order.events),
        )
        .where(Order.id == order_id)
    )
    order = (await db.execute(reload_stmt)).scalar_one()

    # 10. Post-commit hooks (ETA update & delivery notification if delivery exists)
    if order.delivery:
        try:
            from app.services.delivery_eta import eta_service
            await eta_service.update_and_persist_delivery_eta(
                db, order.delivery.id, update_reason=f"order_{to_status.value}", force=True
            )
        except Exception as e:
            logger.warning(f"ETA recalculation skipped on order transition {order.id}: {e}")

        if to_status == OrderStatus.cancelled:
            try:
                from app.websockets.redis_pubsub import publish_delivery_event
                await publish_delivery_event(str(order.delivery.id), {
                    "event": "delivery.status_changed",
                    "version": 1,
                    "delivery_id": str(order.delivery.id),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "data": {
                        "status": DeliveryStatus.cancelled.value,
                        "reason": reason or "Order cancelled",
                    }
                })
            except Exception as e:
                logger.warning(f"PubSub event failed on order cancellation {order.id}: {e}")

    return order


async def transition_delivery(
    db: AsyncSession,
    delivery_id: uuid.UUID,
    to_status: DeliveryStatus,
    actor: User,
    reason: Optional[str] = None,
) -> Delivery:
    """
    Centralized, concurrency-safe transition for a Delivery.
    - Acquires row lock (SELECT ... FOR UPDATE).
    - Checks rider assignment or admin authorization.
    - Enforces idempotency.
    - Synchronizes Order status and records OrderEvent audit records.
    - Releases rider on terminal delivery status.
    - Publishes Redis events and updates ETAs.
    """
    stmt = (
        select(Delivery)
        .where(Delivery.id == delivery_id)
        .with_for_update()
    )
    delivery = (await db.execute(stmt)).scalar_one_or_none()
    if not delivery:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Delivery not found")

    # Authorize Rider or Admin
    if actor.role == UserRole.rider:
        rider_stmt = select(RiderProfile).where(RiderProfile.user_id == actor.id)
        rider = (await db.execute(rider_stmt)).scalar_one_or_none()
        if not rider or delivery.rider_id != rider.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update this delivery")
    elif actor.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to update delivery status")

    # Idempotency check
    if delivery.status == to_status:
        logger.info(f"Delivery {delivery_id} is already in state '{to_status.value}'. Idempotent return.")
        return delivery

    # Validate transition
    allowed_next = DELIVERY_TRANSITIONS.get(delivery.status, [])
    if to_status not in allowed_next:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Invalid transition from {delivery.status.value} to {to_status.value}"
        )

    delivery.status = to_status
    now = datetime.now(timezone.utc)

    if to_status == DeliveryStatus.picked_up:
        delivery.picked_up_at = now
    elif to_status == DeliveryStatus.delivered:
        delivery.delivered_at = now

    # Synchronize with Order
    if delivery.order_id:
        order_stmt = select(Order).where(Order.id == delivery.order_id).with_for_update()
        order = (await db.execute(order_stmt)).scalar_one_or_none()
        if order:
            actor_role_str = actor.role.value if actor and hasattr(actor, "role") else "system"

            if to_status == DeliveryStatus.picked_up:
                if order.status in [OrderStatus.pending, OrderStatus.confirmed, OrderStatus.preparing]:
                    order_from = order.status
                    order.status = OrderStatus.ready_for_delivery
                    db.add(OrderEvent(
                        order_id=order.id,
                        from_state=order_from.value,
                        to_state=OrderStatus.ready_for_delivery.value,
                        actor_id=actor.id if actor else None,
                        actor_role=actor_role_str,
                        reason="Synchronized from delivery pickup",
                    ))
            elif to_status == DeliveryStatus.out_for_delivery:
                if order.status != OrderStatus.out_for_delivery:
                    order_from = order.status
                    order.status = OrderStatus.out_for_delivery
                    db.add(OrderEvent(
                        order_id=order.id,
                        from_state=order_from.value,
                        to_state=OrderStatus.out_for_delivery.value,
                        actor_id=actor.id if actor else None,
                        actor_role=actor_role_str,
                        reason="Synchronized from delivery out for delivery",
                    ))
            elif to_status == DeliveryStatus.delivered:
                if order.status != OrderStatus.delivered:
                    order_from = order.status
                    order.status = OrderStatus.delivered
                    db.add(OrderEvent(
                        order_id=order.id,
                        from_state=order_from.value,
                        to_state=OrderStatus.delivered.value,
                        actor_id=actor.id if actor else None,
                        actor_role=actor_role_str,
                        reason="Synchronized from delivery completion",
                    ))
            elif to_status == DeliveryStatus.cancelled:
                # If delivery is cancelled directly, keep order in sync or handle if needed
                pass

    # Auto-reactivate rider if delivery reaches terminal state
    if to_status in [DeliveryStatus.delivered, DeliveryStatus.cancelled] and delivery.rider_id:
        rider_stmt = select(RiderProfile).where(RiderProfile.id == delivery.rider_id)
        rider = (await db.execute(rider_stmt)).scalar_one_or_none()
        if rider:
            rider.is_available = True
            db.add(rider)

    await db.commit()
    await db.refresh(delivery)

    try:
        from app.services.delivery_eta import eta_service
        await eta_service.update_and_persist_delivery_eta(
            db, delivery.id, update_reason=f"status_{to_status.value}", force=True
        )
    except Exception as e:
        logger.warning(f"ETA recalculation skipped on status change {delivery.id}: {e}")

    try:
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
    except Exception as e:
        logger.warning(f"Redis event failed on status change {delivery.id}: {e}")

    try:
        from app.tasks.notifications import create_notification
        if delivery.order_id:
            order_user_stmt = select(Order.customer_id).where(Order.id == delivery.order_id)
            cust_id = (await db.execute(order_user_stmt)).scalar_one_or_none()
            if cust_id:
                create_notification.delay(
                    user_id=str(cust_id),
                    title="Delivery Update",
                    body=f"Your delivery is now {to_status.value.replace('_', ' ')}.",
                    notification_type=f"DELIVERY_{to_status.name.upper()}",
                    reference_id=str(delivery.id),
                    data={"delivery_id": str(delivery.id), "status": to_status.value}
                )
    except Exception as e:
        logger.warning(f"Notification task trigger failed on delivery status change {delivery.id}: {e}")

    return delivery
