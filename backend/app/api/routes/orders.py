import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.order import CheckoutRequest, OrderResponse, OrderListResponse
from app.services import order as order_service
from app.api.dependencies import require_role

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
    return await order_service.checkout(db=db, customer=current_user, idempotency_key=request.idempotency_key)

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
