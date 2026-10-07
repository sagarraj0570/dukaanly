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

from app.schemas.product import ProductCreate, ProductResponse, ProductListResponse
from app.services import product as product_service

@router.post("/{shop_id}/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    shop_id: uuid.UUID,
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Create a product in a shop. Requires shop_owner role and ownership of the shop."""
    return await product_service.create_product(db=db, shop_id=shop_id, product_in=product_in, owner=current_user)

@router.get("/{shop_id}/products", response_model=ProductListResponse)
async def list_shop_products(
    shop_id: uuid.UUID,
    page: int = Query(1, ge=1, description="Page number"),
    size: int = Query(20, ge=1, le=100, description="Items per page"),
    category: str | None = Query(None, description="Filter by category"),
    active_only: bool = Query(True, description="Only show active products"),
    db: AsyncSession = Depends(get_db)
):
    """List products for a given shop."""
    products, total = await product_service.get_shop_products(
        db=db, shop_id=shop_id, page=page, size=size, category=category, active_only=active_only
    )
    return {
        "items": products,
        "total": total,
        "page": page,
        "size": size
    }

from app.schemas.order import OrderListResponse, OrderResponse, OrderStatusUpdate
from app.services import order as order_service

@router.get("/{shop_id}/orders", response_model=OrderListResponse)
async def list_shop_orders(
    shop_id: uuid.UUID,
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """List orders belonging to a shop (owner only)."""
    orders, total = await order_service.get_shop_orders(db=db, shop_id=shop_id, owner=current_user, page=page, size=size)
    return {"items": orders, "total": total, "page": page, "size": size}

@router.patch("/{shop_id}/orders/{order_id}/status", response_model=OrderResponse)
async def update_shop_order_status(
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
    status_update: OrderStatusUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Update order status (owner only)."""
    return await order_service.update_order_status(
        db=db, shop_id=shop_id, order_id=order_id, new_status=status_update.status, owner=current_user
    )
