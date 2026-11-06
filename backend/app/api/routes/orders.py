import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.order import CheckoutRequest, OrderResponse, OrderListResponse, OrderCancelRequest, OrderEventResponse, OrderReservationResponse
from app.services import order as order_service
from app.services.reservation import get_order_reservation_summary
from app.api.dependencies import require_role, get_current_user

router = APIRouter()

@router.post("/checkout", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def checkout(
    request: CheckoutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """
    Checkout the current cart.
    Idempotent operation: supply a unique `idempotency_key` per checkout attempt.
    """
    return await order_service.checkout(
        db=db,
        customer=current_user,
        idempotency_key=request.idempotency_key,
        destination_latitude=request.destination_latitude,
        destination_longitude=request.destination_longitude,
    )

@router.get("", response_model=OrderListResponse)
async def list_customer_orders(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """List customer's orders."""
    orders, total = await order_service.get_customer_orders(db=db, customer=current_user, page=page, size=size)
    return {"items": orders, "total": total, "page": page, "size": size}

@router.get("/{order_id}", response_model=OrderResponse)
async def get_customer_order(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Get a specific customer order."""
    return await order_service.get_customer_order(db=db, customer=current_user, order_id=order_id)

@router.get("/{order_id}/reservation", response_model=OrderReservationResponse)
async def get_order_reservation(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Get real-time inventory reservation status and authoritative countdown for an order."""
    order = await order_service.get_customer_order(db=db, customer=current_user, order_id=order_id)
    return await get_order_reservation_summary(db=db, order_id=order.id)

@router.post("/{order_id}/cancel", response_model=OrderResponse)
async def cancel_customer_order(
    order_id: uuid.UUID,
    request: OrderCancelRequest = OrderCancelRequest(),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """
    Cancel a customer order.
    Allowed without reason when pending. Requires reason when preparing.
    Restores inventory stock atomically and releases active delivery/rider.
    """
    return await order_service.cancel_customer_order(
        db=db,
        customer=current_user,
        order_id=order_id,
        reason=request.reason,
    )

@router.get("/{order_id}/events", response_model=list[OrderEventResponse])
async def get_order_events(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get chronological audit events for an order."""
    return await order_service.get_order_events(db=db, order_id=order_id, actor=current_user)
