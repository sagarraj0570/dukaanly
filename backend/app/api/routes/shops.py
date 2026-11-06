import uuid
from fastapi import APIRouter, Depends, Query, status, HTTPException, File, UploadFile, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.rate_limit import image_upload_rate_limiter

from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.shop import (
    ShopCreate,
    ShopUpdate,
    ShopResponse,
    ShopListResponse,
    DeliveryEligibilityResponse,
)
from app.services import shop as shop_service
from app.api.dependencies import get_current_user, get_current_user_optional, require_role

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
    active_only: bool = Query(True, description="Filter only active shops"),
    latitude: float | None = Query(None, ge=-90.0, le=90.0, description="Customer latitude for nearby discovery (-90.0 to 90.0)"),
    longitude: float | None = Query(None, ge=-180.0, le=180.0, description="Customer longitude for nearby discovery (-180.0 to 180.0)"),
    radius_meters: int = Query(5000, ge=100, le=10000, description="Search radius in meters (100m to 10km)"),
    delivery_only: bool = Query(False, description="Filter only delivery-eligible shops"),
    verified_only: bool = Query(False, description="Filter only verified partner shops with registered owners"),
    include_test: bool = Query(False, description="Whether to include test shops (internal/testing only)"),
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional)
):
    """
    List active shops.
    If latitude and longitude are supplied, searches using PostGIS ST_DWithin and orders closest first.
    """
    if (latitude is None) != (longitude is None):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both latitude and longitude must be provided together for location-based search."
        )
    is_test_user = bool(
        current_user
        and current_user.email
        and (current_user.email.startswith("systest-") or "st_" in current_user.email)
    )
    effective_include_test = include_test or is_test_user

    shops, total = await shop_service.get_shops(
        db=db,
        page=page,
        size=size,
        active_only=active_only,
        latitude=latitude,
        longitude=longitude,
        radius_meters=radius_meters,
        delivery_only=delivery_only,
        verified_only=verified_only,
        include_test=effective_include_test
    )
    return {
        "items": shops,
        "total": total,
        "page": page,
        "size": size,
        "user_latitude": latitude,
        "user_longitude": longitude,
        "radius_meters": radius_meters if (latitude is not None and longitude is not None) else None
    }

@router.get("/me", response_model=ShopResponse)
async def get_my_shop(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Get the authenticated shop owner's shop (active or inactive)."""
    shop = await shop_service.get_shop_by_owner_id(db=db, owner_id=current_user.id)
    if not shop:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shop not found for current user"
        )
    return shop

@router.get("/{shop_id}/delivery-eligibility", response_model=DeliveryEligibilityResponse)
async def check_shop_delivery_eligibility(
    shop_id: str,
    latitude: float = Query(..., ge=-90.0, le=90.0, description="Customer latitude"),
    longitude: float = Query(..., ge=-180.0, le=180.0, description="Customer longitude"),
    db: AsyncSession = Depends(get_db)
):
    """Check if a shop can deliver to the customer's coordinates."""
    return await shop_service.check_shop_delivery_eligibility(
        db=db,
        shop_id=shop_id,
        latitude=latitude,
        longitude=longitude
    )

@router.get("/{shop_id}", response_model=ShopResponse)
async def get_shop(
    shop_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Get shop details."""
    return await shop_service.get_shop_by_id_or_identifier(db=db, identifier=shop_id)

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

@router.post("/{shop_id}/products/{product_id}/image", response_model=ProductResponse)
async def upload_shop_product_image(
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner)),
):
    """
    Upload and normalize a product image for a specific shop.
    Rate limited, strictly validates file type & size (5MB max), and normalizes to WebP.
    """
    allowed, retry_after = await image_upload_rate_limiter.check_and_record(str(current_user.id))
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many image upload attempts. Please try again later.",
            headers={"Retry-After": str(int(retry_after or 60))},
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty.",
        )
    if len(file_bytes) > 5 * 1024 * 1024:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File size exceeds the 5MB limit.",
        )

    return await product_service.upload_product_image(
        db=db,
        shop_id=shop_id,
        product_id=product_id,
        file_bytes=file_bytes,
        owner=current_user,
    )

@router.delete("/{shop_id}/products/{product_id}/image", response_model=ProductResponse)
async def delete_shop_product_image(
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner)),
):
    """
    Delete custom uploaded image for a product and revert to the master catalog image.
    """
    return await product_service.delete_product_image(
        db=db,
        shop_id=shop_id,
        product_id=product_id,
        owner=current_user,
    )

from app.schemas.order import OrderListResponse, OrderResponse, OrderStatusUpdate, OrderRejectRequest
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
        db=db,
        shop_id=shop_id,
        order_id=order_id,
        new_status=status_update.status,
        owner=current_user,
        reason=status_update.reason,
    )

@router.post("/{shop_id}/orders/{order_id}/reject", response_model=OrderResponse)
async def reject_shop_order(
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
    request: OrderRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Reject a pending order (owner only). Mandatory rejection reason required."""
    return await order_service.reject_shop_order(
        db=db,
        shop_id=shop_id,
        order_id=order_id,
        owner=current_user,
        reason=request.reason,
    )

@router.post("/{shop_id}/orders/{order_id}/cancel", response_model=OrderResponse)
async def cancel_shop_order(
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
    request: OrderRejectRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.shop_owner))
):
    """Cancel an active order prior to delivery pickup (owner only). Mandatory reason required."""
    from app.models.order import OrderStatus
    return await order_service.update_order_status(
        db=db,
        shop_id=shop_id,
        order_id=order_id,
        new_status=OrderStatus.cancelled,
        owner=current_user,
        reason=request.reason,
    )
