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
