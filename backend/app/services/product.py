import uuid
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate
from app.services.storage import process_and_store_image, InvalidImageError

async def verify_shop_ownership(db: AsyncSession, shop_id: uuid.UUID, user: User) -> Shop:
    stmt = select(Shop).where(Shop.id == shop_id)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    if shop.owner_id != user.id and user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to manage this shop's products")
        
    return shop

from app.models.inventory import Inventory

async def create_product(db: AsyncSession, shop_id: uuid.UUID, product_in: ProductCreate, owner: User) -> Product:
    await verify_shop_ownership(db, shop_id, owner)
    
    db_product = Product(
        shop_id=shop_id,
        name=product_in.name,
        description=product_in.description,
        category=product_in.category,
        price=product_in.price,
        image_url=product_in.image_url,
        is_active=True
    )
    
    # Initialize inventory explicitly
    db_inventory = Inventory(
        product=db_product,
        stock=0,
        version=1
    )
    
    db.add(db_product)
    db.add(db_inventory)
    await db.commit()
    await db.refresh(db_product)
    return db_product

async def get_product_by_id(db: AsyncSession, product_id: uuid.UUID) -> Product:
    stmt = select(Product).where(Product.id == product_id)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")
        
    return product

async def update_product(db: AsyncSession, product_id: uuid.UUID, product_in: ProductUpdate, current_user: User) -> Product:
    product = await get_product_by_id(db, product_id)
    
    await verify_shop_ownership(db, product.shop_id, current_user)
        
    update_data = product_in.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(product, field, value)
        
    db.add(product)
    await db.commit()
    await db.refresh(product)
    
    return product

async def get_shop_products(
    db: AsyncSession,
    shop_id: uuid.UUID,
    page: int = 1,
    size: int = 20,
    category: str | None = None,
    active_only: bool | None = True
) -> Tuple[list[Product], int]:
    # Check if shop exists
    stmt = select(Shop).where(Shop.id == shop_id)
    result = await db.execute(stmt)
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    stmt = select(Product).where(Product.shop_id == shop_id)
    
    if active_only is not None:
        stmt = stmt.where(Product.is_active == active_only)
        
    if category:
        stmt = stmt.where(Product.category == category)
        
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    
    stmt = stmt.offset((page - 1) * size).limit(size)
    products = (await db.execute(stmt)).scalars().all()
    
    return list(products), total


async def upload_product_image(
    db: AsyncSession,
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    file_bytes: bytes,
    owner: User,
) -> Product:
    """
    Upload and normalize a custom product image for a specific shop's product.
    Verifies shop ownership, enforces 5MB limit, normalizes to 600x600 WebP with
    Warm Ivory background, generates thumbnail, and sets image_source='shop_upload'.
    """
    shop = await verify_shop_ownership(db, shop_id, owner)
    product = await get_product_by_id(db, product_id)
    if product.shop_id != shop_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in this shop",
        )

    try:
        full_url, thumb_url, sha256_hash = process_and_store_image(file_bytes)
    except InvalidImageError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    product.custom_image_url = full_url
    product.custom_thumb_url = thumb_url
    product.image_url = full_url
    product.thumb_url = thumb_url
    product.image_source = "shop_upload"
    product.image_license = "Proprietary / Shop Owner Upload"
    product.image_attribution = f"Uploaded by {shop.name}"
    product.image_source_url = None
    product.image_match_confidence = 1.0
    product.image_reviewed = True

    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product


async def delete_product_image(
    db: AsyncSession,
    shop_id: uuid.UUID,
    product_id: uuid.UUID,
    owner: User,
) -> Product:
    """
    Remove the shop's custom uploaded image and revert to the master catalog item's
    image if linked, or placeholder fallback if no master item is linked.
    """
    await verify_shop_ownership(db, shop_id, owner)
    stmt = (
        select(Product)
        .options(selectinload(Product.master_item))
        .where(Product.id == product_id, Product.shop_id == shop_id)
    )
    res = await db.execute(stmt)
    product = res.scalar_one_or_none()
    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Product not found in this shop",
        )

    # Clear custom image overrides
    product.custom_image_url = None
    product.custom_thumb_url = None

    # Revert to master catalog item if available
    if product.master_item:
        product.image_url = product.master_item.image_url
        product.thumb_url = product.master_item.thumb_url
        product.image_source = product.master_item.image_source
        product.image_license = product.master_item.image_license
        product.image_attribution = product.master_item.image_attribution
        product.image_source_url = product.master_item.image_source_url
        product.image_match_confidence = product.master_item.image_match_confidence
        product.image_reviewed = product.master_item.image_reviewed
    else:
        product.image_url = None
        product.thumb_url = None
        product.image_source = "placeholder"
        product.image_license = None
        product.image_attribution = None
        product.image_source_url = None
        product.image_match_confidence = None
        product.image_reviewed = False

    db.add(product)
    await db.commit()
    await db.refresh(product)
    return product
