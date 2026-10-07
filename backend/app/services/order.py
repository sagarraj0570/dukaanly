import uuid
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status

from app.models.order import Order, OrderItem, OrderStatus
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.user import User
from app.schemas.order import OrderResponse

from app.services.cart import get_or_create_cart

async def checkout(db: AsyncSession, customer: User, idempotency_key: str) -> OrderResponse:
    # 1. Idempotency Check
    stmt = select(Order).options(selectinload(Order.items)).where(Order.customer_id == customer.id, Order.idempotency_key == idempotency_key)
    existing_order = (await db.execute(stmt)).scalar_one_or_none()
    if existing_order:
        return existing_order

    # 2. Read Authoritative Cart Data
    cart = await get_or_create_cart(db, customer)
    if not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    total_amount = Decimal("0.00")
    order_items_data = []

    # 3. Validation and Snapshotting
    for item in cart.items:
        product = item.product
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Product {product.name if product else 'Unknown'} is no longer available."
            )
            
        if product.inventory.stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Insufficient stock for {product.name}. Only {product.inventory.stock} left."
            )

        line_total = product.price * item.quantity
        total_amount += line_total
        
        order_items_data.append({
            "product_id": product.id,
            "product_name": product.name, # historical snapshot
            "unit_price": product.price,  # historical snapshot
            "quantity": item.quantity,
            "line_total": line_total
        })

    try:
        # 4. Atomic Inventory Deduction (Concurrency-Safe)
        for item in cart.items:
            upd_stmt = (
                update(Inventory)
                .where(Inventory.product_id == item.product_id)
                .where(Inventory.stock >= item.quantity)
                .values(
                    stock=Inventory.stock - item.quantity,
                    version=Inventory.version + 1
                )
            )
            res = await db.execute(upd_stmt)
            if res.rowcount == 0:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Stock for {item.product.name} was depleted during checkout. Please refresh cart."
                )

        # 5. Create Order
        new_order = Order(
            customer_id=customer.id,
            shop_id=cart.shop_id,
            total_amount=total_amount,
            idempotency_key=idempotency_key,
            status=OrderStatus.pending
        )
        db.add(new_order)
        await db.flush() # get new_order.id

        # 6. Create Order Items
        for oi_data in order_items_data:
            oi = OrderItem(order_id=new_order.id, **oi_data)
            db.add(oi)

        # 7. Clear Cart
        del_stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
        await db.execute(del_stmt)
        cart.shop_id = None
        cart.items.clear()
        
        # 8. Commit Transaction
        await db.commit()
        await db.refresh(new_order, ["items"])
        return new_order
        
    except HTTPException as e:
        await db.rollback()
        raise e
    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during checkout."
        )

async def get_customer_orders(db: AsyncSession, customer: User, page: int = 1, size: int = 20):
    stmt = select(Order).options(selectinload(Order.items)).where(Order.customer_id == customer.id).order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size)
    orders = (await db.execute(stmt)).scalars().all()
    
    count_stmt = select(func.count(Order.id)).where(Order.customer_id == customer.id)
    total = (await db.execute(count_stmt)).scalar()
    
    return orders, total

async def get_customer_order(db: AsyncSession, customer: User, order_id: uuid.UUID):
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.customer_id == customer.id)
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    return order

async def get_shop_orders(db: AsyncSession, shop_id: uuid.UUID, owner: User, page: int = 1, size: int = 20):
    from app.services.shop import get_shop_by_id
    shop = await get_shop_by_id(db, shop_id)
    if shop.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    stmt = select(Order).options(selectinload(Order.items)).where(Order.shop_id == shop_id).order_by(Order.created_at.desc()).offset((page - 1) * size).limit(size)
    orders = (await db.execute(stmt)).scalars().all()
    
    count_stmt = select(func.count(Order.id)).where(Order.shop_id == shop_id)
    total = (await db.execute(count_stmt)).scalar()
    
    return orders, total

async def update_order_status(db: AsyncSession, shop_id: uuid.UUID, order_id: uuid.UUID, new_status: OrderStatus, owner: User):
    from app.services.shop import get_shop_by_id
    shop = await get_shop_by_id(db, shop_id)
    if shop.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    stmt = select(Order).options(selectinload(Order.items)).where(Order.id == order_id, Order.shop_id == shop_id)
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
        
    # State machine validation (simplified for milestone)
    valid_transitions = {
        OrderStatus.pending: [OrderStatus.confirmed, OrderStatus.cancelled],
        OrderStatus.confirmed: [OrderStatus.preparing, OrderStatus.cancelled],
        OrderStatus.preparing: [OrderStatus.ready_for_delivery, OrderStatus.cancelled],
        OrderStatus.ready_for_delivery: [OrderStatus.out_for_delivery],
        OrderStatus.out_for_delivery: [OrderStatus.delivered],
        OrderStatus.delivered: [],
        OrderStatus.cancelled: []
    }
    
    if new_status not in valid_transitions[order.status]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, 
            detail=f"Cannot transition order from {order.status.value} to {new_status.value}"
        )
        
    order.status = new_status
    await db.commit()
    await db.refresh(order)
    return order
