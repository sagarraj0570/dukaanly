import uuid
from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.cart import CartResponse, CartItemAdd, CartItemUpdate
from app.services import cart as cart_service
from app.api.dependencies import require_role

router = APIRouter()

@router.get("", response_model=CartResponse)
async def get_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Get the current customer's cart."""
    return await cart_service.get_cart(db=db, customer=current_user)

@router.post("/items", response_model=CartResponse, status_code=status.HTTP_200_OK)
async def add_item_to_cart(
    item_in: CartItemAdd,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Add a product to the cart. Enforces one-shop-per-cart."""
    return await cart_service.add_item_to_cart(
        db=db, 
        customer=current_user, 
        product_id=item_in.product_id, 
        quantity=item_in.quantity
    )

@router.patch("/items/{item_id}", response_model=CartResponse)
async def update_cart_item(
    item_id: uuid.UUID,
    item_in: CartItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Update the quantity of an item in the cart."""
    return await cart_service.update_item_quantity(
        db=db, 
        customer=current_user, 
        item_id=item_id, 
        quantity=item_in.quantity
    )

@router.delete("/items/{item_id}", response_model=CartResponse)
async def remove_cart_item(
    item_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Remove an item from the cart."""
    return await cart_service.remove_item_from_cart(db=db, customer=current_user, item_id=item_id)

@router.delete("", response_model=CartResponse)
async def clear_cart(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.customer))
):
    """Clear the entire cart."""
    return await cart_service.clear_cart(db=db, customer=current_user)
