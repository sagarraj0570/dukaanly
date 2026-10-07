import uuid
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User
from app.schemas.product import ProductUpdate, ProductResponse
from app.services import product as product_service
from app.api.dependencies import get_current_user

router = APIRouter()

@router.get("/{product_id}", response_model=ProductResponse)
async def get_product(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get product details."""
    return await product_service.get_product_by_id(db=db, product_id=product_id)

@router.patch("/{product_id}", response_model=ProductResponse)
async def update_product(
    product_id: uuid.UUID,
    product_in: ProductUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update product details. Requires ownership of the parent shop."""
    return await product_service.update_product(
        db=db, 
        product_id=product_id, 
        product_in=product_in, 
        current_user=current_user
    )

from app.schemas.inventory import InventoryResponse, InventoryUpdate
from app.services import inventory as inventory_service
from app.api.dependencies import require_role
from app.models.user import UserRole

@router.get("/{product_id}/inventory", response_model=InventoryResponse)
async def get_inventory(
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get inventory for a product."""
    # Anyone authenticated can view inventory in this simple design, 
    # but the service layer will enforce any specific rules.
    return await inventory_service.get_inventory(db=db, product_id=product_id)

@router.patch("/{product_id}/inventory", response_model=InventoryResponse)
async def update_inventory(
    product_id: uuid.UUID,
    inventory_in: InventoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Update inventory for a product. Requires shop_owner role and ownership of the product's shop."""
    return await inventory_service.update_inventory(
        db=db,
        product_id=product_id,
        inventory_in=inventory_in,
        current_user=current_user
    )
