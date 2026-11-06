import uuid
import asyncio
from decimal import Decimal
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, func, cast
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, status
from geoalchemy2 import Geography

from app.models.order import Order, OrderItem, OrderStatus, OrderEvent
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.models.inventory import Inventory
from app.models.shop import Shop, ShopVerificationStatus
from app.models.user import User
from app.models.inventory_reservation import InventoryReservation, ReservationStatus
from app.schemas.order import OrderResponse

from app.services.cart import get_or_create_cart
from app.services.reservation import create_order_reservations
from app.core.rate_limit import checkout_rate_limiter

def _populate_order_reservation_fields(order: Order) -> None:
    res_list = getattr(order, "reservations", None) or []
    active_res = [r for r in res_list if r.status == ReservationStatus.active]
    if active_res:
        setattr(order, "reservation_expires_at", active_res[0].expires_at)
        setattr(order, "reservation_status", "active")
    elif any(r.status == ReservationStatus.consumed for r in res_list):
        setattr(order, "reservation_expires_at", None)
        setattr(order, "reservation_status", "consumed")
    elif any(r.status == ReservationStatus.expired for r in res_list):
        setattr(order, "reservation_expires_at", None)
        setattr(order, "reservation_status", "expired")
    elif any(r.status == ReservationStatus.released for r in res_list):
        setattr(order, "reservation_expires_at", None)
        setattr(order, "reservation_status", "released")

async def checkout(
    db: AsyncSession,
    customer: User,
    idempotency_key: str,
    destination_latitude: float | None = None,
    destination_longitude: float | None = None,
    _retry_count: int = 0
) -> OrderResponse:
    customer_id = customer.id

    # 1. Idempotency Check (Fast-path read)
    stmt = select(Order).options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events), selectinload(Order.reservations)).where(Order.customer_id == customer_id, Order.idempotency_key == idempotency_key)
    existing_order = (await db.execute(stmt)).scalar_one_or_none()
    if existing_order:
        _populate_order_reservation_fields(existing_order)
        return existing_order

    # 1.1 Checkout Abuse Protection (Rate Limiting) - Only evaluated on initial attempt
    if _retry_count == 0:
        allowed, retry_after = await checkout_rate_limiter.check_and_record(str(customer_id))
        if not allowed:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many checkout attempts. Please wait {int(retry_after or 60)} seconds before trying again.",
                headers={"Retry-After": str(int(retry_after or 60))},
            )

    # 2. Read Authoritative Cart Data
    cart = await get_or_create_cart(db, customer)
    if not cart.items:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cart is empty")

    # 2.1 Verify Shop Active Status and Delivery Distance
    if cart.shop_id:
        shop_stmt = select(Shop).where(Shop.id == cart.shop_id)
        shop_obj = (await db.execute(shop_stmt)).scalar_one_or_none()
        if not shop_obj or not shop_obj.is_active or not shop_obj.is_orderable or shop_obj.verification_status != ShopVerificationStatus.verified:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Shop is not activated for online commerce. Order cannot be placed."
            )

        if destination_latitude is not None and destination_longitude is not None:
            user_point = func.ST_SetSRID(func.ST_MakePoint(destination_longitude, destination_latitude), 4326)
            user_geog = cast(user_point, Geography())
            shop_geog = cast(Shop.location, Geography())

            dist_query = select(func.ST_Distance(shop_geog, user_geog)).where(Shop.id == cart.shop_id)
            dist_val = (await db.execute(dist_query)).scalar_one_or_none()
            if dist_val is not None:
                DEFAULT_DELIVERY_RADIUS_METERS = 5000.0
                if float(dist_val) > DEFAULT_DELIVERY_RADIUS_METERS:
                    dist_km = round(float(dist_val) / 1000.0, 1)
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Your delivery address ({dist_km} km away) is outside this shop's {int(DEFAULT_DELIVERY_RADIUS_METERS / 1000)} km delivery service zone."
                    )

    # 3. Deterministic Item Ordering & Validation
    # Sorting deterministically by product_id prevents lock-inversion deadlocks across concurrent multi-item checkouts
    sorted_items = sorted(cart.items, key=lambda item: str(item.product_id))

    total_amount = Decimal("0.00")
    order_items_data = []
    inventory_plan = []

    for item in sorted_items:
        product = item.product
        if not product or not product.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, 
                detail=f"Product {product.name if product else 'Unknown'} is no longer available."
            )
            
        inv_stmt = select(Inventory).where(Inventory.product_id == item.product_id)
        inv = (await db.execute(inv_stmt)).scalar_one_or_none()
        current_stock = inv.stock if inv else 0
        current_version = inv.version if inv else 1

        if not inv or current_stock < item.quantity:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, 
                detail=f"Insufficient stock for {product.name}. Only {current_stock} left."
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

        inventory_plan.append({
            "product_id": product.id,
            "product_name": product.name,
            "quantity": item.quantity,
            "expected_version": current_version,
        })

    try:
        # 4. Atomic Inventory Deduction in Deterministic Lock Order
        for plan_item in inventory_plan:
            pid = plan_item["product_id"]
            qty = plan_item["quantity"]
            expected_ver = plan_item["expected_version"]
            pname = plan_item["product_name"]

            upd_stmt = (
                update(Inventory)
                .where(Inventory.product_id == pid)
                .where(Inventory.version == expected_ver)
                .where(Inventory.stock >= qty)
                .values(
                    stock=Inventory.stock - qty,
                    version=Inventory.version + 1
                )
            )
            res = await db.execute(upd_stmt)
            if res.rowcount == 0:
                # Deduction failed: OCC version mismatch or stock depleted concurrently.
                # Rollback transaction immediately to clear failed state before querying fresh data.
                await db.rollback()

                # Query fresh inventory state
                fresh_stmt = select(Inventory).where(Inventory.product_id == pid)
                fresh_inv = (await db.execute(fresh_stmt)).scalar_one_or_none()
                fresh_stock = fresh_inv.stock if fresh_inv else 0

                if fresh_stock < qty:
                    # Genuine stock depletion: DO NOT RETRY
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"Stock for {pname} was depleted during checkout. Available: {fresh_stock}, requested: {qty}."
                    )
                else:
                    # Pure OCC version conflict (sufficient stock exists, but version advanced)
                    MAX_OCC_RETRIES = 5
                    if _retry_count < MAX_OCC_RETRIES:
                        import asyncio, random
                        # Small jittered backoff to alleviate high concurrency lock contention
                        await asyncio.sleep(0.01 * (1.5 ** _retry_count) + random.uniform(0.002, 0.01))
                        # Reload customer freshly after rollback to avoid expired instance MissingGreenlet
                        cust_stmt = select(User).where(User.id == customer_id)
                        fresh_customer = (await db.execute(cust_stmt)).scalar_one()
                        # Retry checkout with fresh state
                        return await checkout(
                            db=db,
                            customer=fresh_customer,
                            idempotency_key=idempotency_key,
                            destination_latitude=destination_latitude,
                            destination_longitude=destination_longitude,
                            _retry_count=_retry_count + 1
                        )
                    else:
                        # Retry also collided: return structured HTTP 409
                        raise HTTPException(
                            status_code=status.HTTP_409_CONFLICT,
                            detail=f"Item '{pname}' was concurrently modified. Available stock: {fresh_stock}. Please review your cart and try again."
                        )

        # 5. Create Order
        new_order = Order(
            customer_id=customer_id,
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

        # 6b. Create Inventory Reservations (Stage 8)
        await create_order_reservations(
            db=db,
            order=new_order,
            items=inventory_plan,
            customer_id=customer_id,
        )

        # Record initial OrderEvent
        initial_event = OrderEvent(
            order_id=new_order.id,
            from_state="created",
            to_state=OrderStatus.pending.value,
            actor_id=customer_id,
            actor_role="customer",
            reason="Order placed at checkout",
        )
        db.add(initial_event)

        # 7. Clear Cart
        del_stmt = delete(CartItem).where(CartItem.cart_id == cart.id)
        await db.execute(del_stmt)
        cart.shop_id = None
        cart.items.clear()
        
        # 8. Commit Transaction
        await db.commit()
        stmt = select(Order).options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events), selectinload(Order.reservations)).where(Order.id == new_order.id)
        committed_order = (await db.execute(stmt)).scalar_one()
        _populate_order_reservation_fields(committed_order)
        return committed_order

    except IntegrityError as exc:
        await db.rollback()
        err_str = f"{exc} {getattr(exc, 'orig', '')}".lower()
        if "uq_order_customer_idempotency" in err_str:
            # Concurrent duplicate checkout attempt for same customer & idempotency key.
            # Bounded poll for the committed order from the winning concurrent transaction.
            for _ in range(10):
                fetch_stmt = (
                    select(Order)
                    .options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events), selectinload(Order.reservations))
                    .where(
                        Order.customer_id == customer_id,
                        Order.idempotency_key == idempotency_key,
                    )
                )
                committed_order = (await db.execute(fetch_stmt)).scalar_one_or_none()
                if committed_order:
                    _populate_order_reservation_fields(committed_order)
                    return committed_order
                await asyncio.sleep(0.05)

            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="A concurrent checkout with this idempotency key is already in progress. Please retry."
            )
        # Re-raise unrelated database integrity constraint failures as 409
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Database constraint violation during checkout: {getattr(exc, 'orig', exc)}"
        )
        
    except HTTPException:
        await db.rollback()
        raise
    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during checkout."
        )

async def get_customer_orders(db: AsyncSession, customer: User, page: int = 1, size: int = 20):
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events), selectinload(Order.reservations))
        .where(Order.customer_id == customer.id)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    orders = (await db.execute(stmt)).scalars().all()
    for o in orders:
        _populate_order_reservation_fields(o)
    
    count_stmt = select(func.count(Order.id)).where(Order.customer_id == customer.id)
    total = (await db.execute(count_stmt)).scalar()
    
    return orders, total

async def get_customer_order(db: AsyncSession, customer: User, order_id: uuid.UUID):
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events), selectinload(Order.reservations))
        .where(Order.id == order_id, Order.customer_id == customer.id)
    )
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")
    _populate_order_reservation_fields(order)
    return order

async def get_shop_orders(db: AsyncSession, shop_id: uuid.UUID, owner: User, page: int = 1, size: int = 20):
    from app.services.shop import get_shop_by_id
    shop = await get_shop_by_id(db, shop_id)
    if shop.owner_id != owner.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    
    stmt = (
        select(Order)
        .options(selectinload(Order.items), selectinload(Order.delivery), selectinload(Order.events))
        .where(Order.shop_id == shop_id)
        .order_by(Order.created_at.desc())
        .offset((page - 1) * size)
        .limit(size)
    )
    orders = (await db.execute(stmt)).scalars().all()
    
    count_stmt = select(func.count(Order.id)).where(Order.shop_id == shop_id)
    total = (await db.execute(count_stmt)).scalar()
    
    return orders, total

async def update_order_status(
    db: AsyncSession,
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
    new_status: OrderStatus,
    owner: User,
    reason: str | None = None
):
    """Update order status via centralized state machine (owner only)."""
    from app.services.state_machine import transition_order
    from app.models.user import UserRole
    return await transition_order(
        db=db,
        order_id=order_id,
        to_status=new_status,
        actor=owner,
        actor_role=UserRole.shop_owner.value,
        reason=reason,
        shop_id=shop_id,
    )

async def cancel_customer_order(
    db: AsyncSession,
    customer: User,
    order_id: uuid.UUID,
    reason: str | None = None
):
    """Customer-initiated cancellation via state machine with atomic stock restoration."""
    from app.services.state_machine import transition_order
    from app.models.user import UserRole
    return await transition_order(
        db=db,
        order_id=order_id,
        to_status=OrderStatus.cancelled,
        actor=customer,
        actor_role=UserRole.customer.value,
        reason=reason,
    )

async def reject_shop_order(
    db: AsyncSession,
    shop_id: uuid.UUID,
    order_id: uuid.UUID,
    owner: User,
    reason: str
):
    """Shop owner rejects a pending order with mandatory reason and restores stock."""
    from app.services.state_machine import transition_order
    from app.models.user import UserRole
    return await transition_order(
        db=db,
        order_id=order_id,
        to_status=OrderStatus.cancelled,
        actor=owner,
        actor_role=UserRole.shop_owner.value,
        reason=reason,
        shop_id=shop_id,
    )

async def get_order_events(db: AsyncSession, order_id: uuid.UUID, actor: User):
    """Get chronological audit trail events for an order."""
    from app.models.user import UserRole
    from app.services.shop import get_shop_by_id

    stmt = select(Order).options(selectinload(Order.events)).where(Order.id == order_id)
    order = (await db.execute(stmt)).scalar_one_or_none()
    if not order:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Order not found")

    if actor.role == UserRole.customer and order.customer_id != actor.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")
    elif actor.role == UserRole.shop_owner:
        shop = await get_shop_by_id(db, order.shop_id)
        if shop.owner_id != actor.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not authorized")

    return order.events
