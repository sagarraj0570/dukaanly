import uuid
from decimal import Decimal
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.user import User
from app.schemas.cart import CartResponse, CartItemResponse

async def _build_cart_response(cart: Cart) -> CartResponse:
    items = []
    total_amount = Decimal("0.00")
    for item in cart.items:
        # Pydantic schemas will be built using these mapped values
        item_total = item.product.price * item.quantity
        total_amount += item_total
        
        items.append(CartItemResponse(
            id=item.id,
            product_id=item.product_id,
            quantity=item.quantity,
            product_name=item.product.name,
            product_price=item.product.price,
            item_total=item_total
        ))
        
    return CartResponse(
        id=cart.id,
        customer_id=cart.customer_id,
        shop_id=cart.shop_id,
        items=items,
        total_amount=total_amount
    )

async def get_or_create_cart(db: AsyncSession, customer: User) -> Cart:
    stmt = select(Cart).options(
        selectinload(Cart.items).selectinload(CartItem.product).selectinload(Product.inventory)
    ).where(Cart.customer_id == customer.id)
    result = await db.execute(stmt)
    cart = result.scalar_one_or_none()
    
    if not cart:
        cart = Cart(customer_id=customer.id)
        db.add(cart)
        await db.commit()
        await db.refresh(cart)
        # Re-fetch with relations
        result = await db.execute(stmt)
        cart = result.scalar_one()
        
    return cart

async def get_cart(db: AsyncSession, customer: User) -> CartResponse:
    cart = await get_or_create_cart(db, customer)
    return await _build_cart_response(cart)

async def add_item_to_cart(db: AsyncSession, customer: User, product_id: uuid.UUID, quantity: int) -> CartResponse:
    cart = await get_or_create_cart(db, customer)
    
    # 1. Validate Product
    stmt = select(Product).options(selectinload(Product.inventory)).where(Product.id == product_id, Product.is_active == True)
    result = await db.execute(stmt)
    product = result.scalar_one_or_none()
    
    if not product:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found or inactive")
        
    # 2. Validate one-shop-per-cart rule
    if cart.shop_id and cart.shop_id != product.shop_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail="A cart can only contain products from one shop. Please clear your cart first."
        )
        
    # 3. Find if item already in cart
    existing_item = next((item for item in cart.items if item.product_id == product_id), None)
    new_quantity = existing_item.quantity + quantity if existing_item else quantity
    
    # 4. Check Inventory (Informational, we don't reserve)
    if product.inventory.stock < new_quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {product.inventory.stock} items available in stock."
        )
        
    # 5. Apply changes
    cart.shop_id = product.shop_id
    
    if existing_item:
        existing_item.quantity = new_quantity
    else:
        new_item = CartItem(cart_id=cart.id, product_id=product.id, quantity=quantity)
        new_item.product = product
        db.add(new_item)
        cart.items.append(new_item)
        
    await db.commit()
    return await get_cart(db, customer)

async def update_item_quantity(db: AsyncSession, customer: User, item_id: uuid.UUID, quantity: int) -> CartResponse:
    cart = await get_or_create_cart(db, customer)
    
    item = next((i for i in cart.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in cart")
        
    if item.product.inventory.stock < quantity:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Only {item.product.inventory.stock} items available in stock."
        )
        
    item.quantity = quantity
    await db.commit()
    return await get_cart(db, customer)

async def remove_item_from_cart(db: AsyncSession, customer: User, item_id: uuid.UUID) -> CartResponse:
    cart = await get_or_create_cart(db, customer)
    
    item = next((i for i in cart.items if i.id == item_id), None)
    if not item:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Item not found in cart")
        
    await db.delete(item)
    cart.items.remove(item)
    
    # If cart is now empty, clear the shop_id so user can shop elsewhere
    if not cart.items:
        cart.shop_id = None
        
    await db.commit()
    return await get_cart(db, customer)

async def clear_cart(db: AsyncSession, customer: User) -> CartResponse:
    cart = await get_or_create_cart(db, customer)
    
    stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
    await db.execute(stmt)
    
    cart.items.clear()
    cart.shop_id = None
    await db.commit()
    
    return await get_cart(db, customer)
