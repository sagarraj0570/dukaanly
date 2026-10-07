import uuid
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.inventory import Inventory
from app.models.product import Product
from app.models.shop import Shop
from app.models.user import User
from app.schemas.inventory import InventoryUpdate

async def verify_inventory_ownership(db: AsyncSession, product_id: uuid.UUID, user: User) -> None:
    # Resolve ownership from Inventory -> Product -> Shop -> owner_id
    stmt = select(Shop).join(Product).where(Product.id == product_id, Product.shop_id == Shop.id)
    result = await db.execute(stmt)
    shop = result.scalar_one_or_none()
    
    if not shop:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product or Shop not found")
        
    if shop.owner_id != user.id and user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized to manage this product's inventory")

async def get_inventory(db: AsyncSession, product_id: uuid.UUID) -> Inventory:
    stmt = select(Inventory).where(Inventory.product_id == product_id)
    result = await db.execute(stmt)
    inventory = result.scalar_one_or_none()
    
    if not inventory:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found for this product")
        
    return inventory

async def update_inventory(db: AsyncSession, product_id: uuid.UUID, inventory_in: InventoryUpdate, current_user: User) -> Inventory:
    # 1. Verify Authorization
    await verify_inventory_ownership(db, product_id, current_user)
    
    # 2. Atomic Optimistic Locking Update
    stmt = (
        update(Inventory)
        .where(Inventory.product_id == product_id)
        .where(Inventory.version == inventory_in.expected_version)
        .values(
            stock=inventory_in.stock,
            version=Inventory.version + 1
        )
        .execution_options(synchronize_session="fetch")
    )
    
    result = await db.execute(stmt)
    
    if result.rowcount == 0:
        # Either the product doesn't exist, or version mismatch
        # Let's check if the inventory exists at all
        check_stmt = select(Inventory.id).where(Inventory.product_id == product_id)
        check_res = await db.execute(check_stmt)
        if not check_res.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory not found for this product")
            
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Inventory mismatch or stock was modified by another transaction. Please fetch the latest version and retry."
        )
        
    await db.commit()
    
    # Fetch the updated row to return it
    return await get_inventory(db, product_id)
