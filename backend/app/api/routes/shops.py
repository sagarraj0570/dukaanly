import uuid
from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.shop import ShopCreate, ShopUpdate, ShopResponse, ShopListResponse
from app.services import shop as shop_service
from app.api.dependencies import get_current_user, require_role

router = APIRouter()

@router.post("", response_model=ShopResponse, status_code=status.HTTP_201_CREATED)
async def create_shop(
    shop_in: ShopCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Create a new shop. Requires shop_owner role."""
    return await shop_service.create_shop(db=db, shop_in=shop_in, owner=current_user)

@router.get("", response_model=ShopListResponse)
async def list_shops(
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db)
):
    """List active shops."""
    shops, total = await shop_service.get_shops(db=db, page=page, size=size, active_only=True)
    return {
        "items": shops,
        "total": total,
        "page": page,
        "size": size
    }

@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: uuid.UUID,
    db: AsyncSession = Depends(get_db)
):
    """Get shop details."""
    return await shop_service.get_shop_by_id(db=db, shop_id=shop_id)

@router.patch("/{shop_id}", response_model=ShopResponse)
async def update_shop(
    shop_id: uuid.UUID,
    shop_in: ShopUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Update shop details. Only the owner or an admin can update."""
    return await shop_service.update_shop(db=db, shop_id=shop_id, shop_in=shop_in, current_user=current_user)
