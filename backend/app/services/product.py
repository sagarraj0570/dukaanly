import uuid
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.schemas.product import ProductCreate, ProductUpdate

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
