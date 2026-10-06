import uuid
from typing import Tuple
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from fastapi import HTTPException, status

from app.models.shop import Shop
from app.models.user import User
from app.schemas.shop import ShopCreate, ShopUpdate

async def create_shop(db: AsyncSession, shop_in: ShopCreate, owner: User) -> Shop:
    # We use ST_MakePoint(longitude, latitude)
    point_wkt = f"SRID=4326;POINT({shop_in.location.longitude} {shop_in.location.latitude})"

    db_shop = Shop(
        owner_id=owner.id,
        name=shop_in.name,
        description=shop_in.description,
        address=shop_in.address,
        location=point_wkt,
        is_active=True
    )
    
    db.add(db_shop)
    await db.commit()
    await db.refresh(db_shop)
    return db_shop

async def get_shop_by_id(db: AsyncSession, shop_id: uuid.UUID) -> Shop:
    stmt = select(Shop).where(Shop.id == shop_id)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shop not found")
        
    return shop

async def update_shop(db: AsyncSession, shop_id: uuid.UUID, shop_in: ShopUpdate, current_user: User) -> Shop:
    shop = await get_shop_by_id(db, shop_id)
    
    # Ownership isolation
    if shop.owner_id != current_user.id and current_user.role.value != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to modify this shop"
        )
        
    update_data = shop_in.model_dump(exclude_unset=True)
    
    if "location" in update_data and update_data["location"]:
        loc = update_data.pop("location")
        shop.location = f"SRID=4326;POINT({loc['longitude']} {loc['latitude']})"
        
    for field, value in update_data.items():
        setattr(shop, field, value)
        
    db.add(shop)
    await db.commit()
    await db.refresh(shop)
    
    return shop

async def get_shops(
    db: AsyncSession,
    page: int = 1,
    size: int = 20,
    active_only: bool = True
) -> Tuple[list[Shop], int]:
    # Base query
    stmt = select(Shop)
    if active_only:
        stmt = stmt.where(Shop.is_active == True)
        
    # Total count
    count_stmt = select(func.count()).select_from(stmt.subquery())
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()
    
    # Pagination
    stmt = stmt.offset((page - 1) * size).limit(size)
    result = await db.execute(stmt)
    shops = result.scalars().all()
    
    return list(shops), total
