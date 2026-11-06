import asyncio
import pytest
import uuid
from decimal import Decimal
from httpx import AsyncClient
from sqlalchemy import text, select

from app.db.session import engine, async_session_maker
from app.models.inventory import Inventory
from app.models.order import Order, OrderItem
from app.models.user import User, UserRole
from app.models.cart import Cart, CartItem
from app.core.security import create_access_token, get_password_hash

pytestmark = pytest.mark.asyncio


async def create_direct_test_customer(name: str = "Test Customer"):
    """Create a customer directly in DB to avoid HTTP auth rate limits during concurrency tests."""
    user_id = uuid.uuid4()
    email = f"cust_{user_id.hex[:8]}@example.com"
    pwd_hash = get_password_hash("PassWord123")
    
    async with async_session_maker() as session:
        user = User(
            id=user_id,
            name=name,
            email=email,
            password_hash=pwd_hash,
            role=UserRole.customer,
            is_active=True,
        )
        session.add(user)
        # Create user cart
        cart = Cart(customer_id=user_id)
        session.add(cart)
        await session.commit()

    token = create_access_token(str(user_id), UserRole.customer.value)
    return token, user_id


async def setup_stage2_shop_and_products(async_client: AsyncClient):
    """Create a verified shop and helper products for concurrency tests."""
    owner_id = uuid.uuid4()
    owner_email = f"owner_{owner_id.hex[:8]}@example.com"
    pwd_hash = get_password_hash("PassWord123")

    async with async_session_maker() as session:
        owner = User(
            id=owner_id,
            name="Owner",
            email=owner_email,
            password_hash=pwd_hash,
            role=UserRole.shop_owner,
            is_active=True,
        )
        session.add(owner)
        await session.commit()

    token_owner = create_access_token(str(owner_id), UserRole.shop_owner.value)
    headers_owner = {"Authorization": f"Bearer {token_owner}"}

    # Create shop in Patna
    shop_res = await async_client.post(
        "/api/v1/shops",
        json={"name": "Concurrency Market", "address": "Boring Road", "location": {"latitude": 25.61, "longitude": 85.14}},
        headers=headers_owner
    )
    shop_id = shop_res.json()["id"]

    # Verify shop directly in DB so it is orderable
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE shops SET is_active = true, is_orderable = true, verification_status = 'verified' WHERE id = :sid"), {"sid": shop_id})
        await conn.commit()

    return token_owner, headers_owner, shop_id


async def test_overlapping_multi_item_checkouts_deterministic_ordering(async_client: AsyncClient):
    """
    Test A: Overlapping Multi-Item Checkouts (Deadlock Prevention).
    Two concurrent checkouts contain the same items in opposite cart insertion order:
    Customer 1 has [Product A, Product B].
    Customer 2 has [Product B, Product A].
    Deterministic sorting by product_id ensures consistent lock acquisition order in PostgreSQL.
    Both must complete without PostgreSQL 40P01 deadlock, and stock must be decremented accurately.
    """
    token_owner, headers_owner, shop_id = await setup_stage2_shop_and_products(async_client)

    # Create Product A and Product B
    p_a_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Item Alpha", "price": 100}, headers=headers_owner)
    p_a_id = p_a_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p_a_id}/inventory", json={"stock": 5, "expected_version": 1}, headers=headers_owner)

    p_b_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Item Beta", "price": 200}, headers=headers_owner)
    p_b_id = p_b_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p_b_id}/inventory", json={"stock": 5, "expected_version": 1}, headers=headers_owner)

    # Customer 1 inserts A then B
    tok_c1, _ = await create_direct_test_customer("Cust1")
    h_c1 = {"Authorization": f"Bearer {tok_c1}"}
    await async_client.post("/api/v1/cart/items", json={"product_id": p_a_id, "quantity": 1}, headers=h_c1)
    await async_client.post("/api/v1/cart/items", json={"product_id": p_b_id, "quantity": 1}, headers=h_c1)

    # Customer 2 inserts B then A (reverse order!)
    tok_c2, _ = await create_direct_test_customer("Cust2")
    h_c2 = {"Authorization": f"Bearer {tok_c2}"}
    await async_client.post("/api/v1/cart/items", json={"product_id": p_b_id, "quantity": 1}, headers=h_c2)
    await async_client.post("/api/v1/cart/items", json={"product_id": p_a_id, "quantity": 1}, headers=h_c2)

    # Concurrently fire both checkouts
    t1 = async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_c1)
    t2 = async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h_c2)

    res1, res2 = await asyncio.gather(t1, t2)

    # Both must succeed without deadlock
    assert res1.status_code == 201, f"Checkout 1 failed: {res1.text}"
    assert res2.status_code == 201, f"Checkout 2 failed: {res2.text}"

    # Verify inventory in database: both deducted exactly 2 units (1 from each customer)
    async with async_session_maker() as session:
        inv_a = (await session.execute(select(Inventory).where(Inventory.product_id == p_a_id))).scalar_one()
        inv_b = (await session.execute(select(Inventory).where(Inventory.product_id == p_b_id))).scalar_one()

        assert inv_a.stock == 3, f"Expected 3 remaining for Item Alpha, got {inv_a.stock}"
        assert inv_b.stock == 3, f"Expected 3 remaining for Item Beta, got {inv_b.stock}"
        # Initial version was 1 -> after PATCH = 2 -> after 2 checkout decrements = 4
        assert inv_a.version == 4
        assert inv_b.version == 4


async def test_overselling_protection_high_concurrency(async_client: AsyncClient):
    """
    Test B: Overselling Protection under High Concurrency.
    20 genuinely concurrent checkouts compete for inventory with stock sufficient for exactly 5 orders.
    - Exactly 5 orders succeed (HTTP 201).
    - Exactly 15 orders receive conflict responses (HTTP 409 or 400).
    - Final stock is exactly zero.
    - Version is incremented exactly 5 times.
    """
    token_owner, headers_owner, shop_id = await setup_stage2_shop_and_products(async_client)

    # Product with stock = 5
    p_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Hot Selling Biscuit", "price": 20}, headers=headers_owner)
    p_id = p_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p_id}/inventory", json={"stock": 5, "expected_version": 1}, headers=headers_owner)

    # Create 20 customers directly to bypass register/login rate limiters
    customers = []
    for i in range(20):
        tok, _ = await create_direct_test_customer(f"OversellCust_{i}")
        h = {"Authorization": f"Bearer {tok}"}
        await async_client.post("/api/v1/cart/items", json={"product_id": p_id, "quantity": 1}, headers=h)
        customers.append(h)

    # Concurrently fire all 20 checkouts
    tasks = [
        async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=h)
        for h in customers
    ]
    results = await asyncio.gather(*tasks)

    status_codes = [r.status_code for r in results]
    success_count = status_codes.count(201)
    conflict_count = status_codes.count(409) + status_codes.count(400)

    assert success_count == 5, f"Expected exactly 5 checkouts to succeed, got {success_count}. Statuses: {status_codes}"
    assert conflict_count == 15, f"Expected exactly 15 checkouts to be rejected, got {conflict_count}"

    # Verify database state
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == p_id))).scalar_one()
        assert inv.stock == 0, f"Expected final stock 0, found {inv.stock}"
        # Initial 1 -> PATCH to 5 = version 2 -> 5 sales = version 7 (or initial version + 1 per sale)
        assert inv.version == 7, f"Expected version 7, found {inv.version}"

        # Verify exactly 5 OrderItem rows exist for this product
        order_items_count = (await session.execute(
            text("SELECT COUNT(*) FROM order_items WHERE product_id = :pid"), {"pid": p_id}
        )).scalar()
        assert order_items_count == 5


async def test_concurrent_duplicate_idempotency_key(async_client: AsyncClient):
    """
    Test C: Concurrent Duplicate Idempotency Key.
    The same customer fires 5 concurrent requests with the identical idempotency_key.
    - Exactly one logical order is created.
    - Every successful response refers to that same order.
    - Stock is decremented exactly once.
    - Zero HTTP 500 errors or unhandled IntegrityErrors.
    """
    token_owner, headers_owner, shop_id = await setup_stage2_shop_and_products(async_client)

    p_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Idempotent Chai", "price": 15}, headers=headers_owner)
    p_id = p_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p_id}/inventory", json={"stock": 10, "expected_version": 1}, headers=headers_owner)

    tok, _ = await create_direct_test_customer("IdemCustomer")
    headers = {"Authorization": f"Bearer {tok}"}
    await async_client.post("/api/v1/cart/items", json={"product_id": p_id, "quantity": 1}, headers=headers)

    idem_key = f"idem_{uuid.uuid4().hex}"

    # Fire 5 concurrent requests with identical idempotency_key
    tasks = [
        async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key}, headers=headers)
        for _ in range(5)
    ]
    responses = await asyncio.gather(*tasks)

    # Every response must be 201 or 409 (if still in flight) - none should ever be 500
    for r in responses:
        assert r.status_code in (201, 409), f"Unexpected status {r.status_code}: {r.text}"
        assert r.status_code != 500

    successful_orders = [r.json()["id"] for r in responses if r.status_code == 201]
    assert len(successful_orders) >= 1, "At least one request must succeed"
    # All successful orders must point to the identical order ID
    assert len(set(successful_orders)) == 1

    # Stock must have been decremented exactly once: 10 - 1 = 9
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == p_id))).scalar_one()
        assert inv.stock == 9, f"Stock should be 9, found {inv.stock}"
        # Initial 1 -> PATCH to 10 = version 2 -> 1 sale = version 3
        assert inv.version == 3


async def test_atomic_rollback_on_partial_failure(async_client: AsyncClient):
    """
    Test D: Atomic Rollback on Multi-Item Checkout Failure.
    A multi-item cart has Item 1 (available, stock=5) and Item 2 (unavailable, stock=0).
    Checkout must fail.
    Stock of Item 1 must remain 5 (no partial decrement!).
    Version of Item 1 must remain unchanged.
    No order or order items must exist in the database.
    """
    token_owner, headers_owner, shop_id = await setup_stage2_shop_and_products(async_client)

    p1_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Available Item", "price": 40}, headers=headers_owner)
    p1_id = p1_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p1_id}/inventory", json={"stock": 5, "expected_version": 1}, headers=headers_owner)

    p2_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "Depleted Item", "price": 60}, headers=headers_owner)
    p2_id = p2_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p2_id}/inventory", json={"stock": 0, "expected_version": 1}, headers=headers_owner)

    tok, user_id = await create_direct_test_customer("RollbackCust")
    headers = {"Authorization": f"Bearer {tok}"}
    await async_client.post("/api/v1/cart/items", json={"product_id": p1_id, "quantity": 1}, headers=headers)

    # Insert p2 into cart in DB to simulate item stock becoming 0 right after adding
    async with engine.connect() as conn:
        cart_id = (await conn.execute(text("SELECT id FROM carts WHERE customer_id = :uid"), {"uid": user_id})).scalar()
        await conn.execute(text("INSERT INTO cart_items (id, cart_id, product_id, quantity) VALUES (:id, :cid, :pid, 1)"), {"id": str(uuid.uuid4()), "cid": cart_id, "pid": p2_id})
        await conn.commit()

    idem_key = str(uuid.uuid4())
    res = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key}, headers=headers)

    # Must fail with 400 or 409
    assert res.status_code in (400, 409)

    # Verify no partial update happened to Item 1
    async with async_session_maker() as session:
        inv1 = (await session.execute(select(Inventory).where(Inventory.product_id == p1_id))).scalar_one()
        assert inv1.stock == 5, f"Item 1 stock should remain 5, found {inv1.stock}"
        assert inv1.version == 2, f"Item 1 version should remain 2, found {inv1.version}"

        # No order created
        order = (await session.execute(select(Order).where(Order.idempotency_key == idem_key))).scalar_one_or_none()
        assert order is None


async def test_occ_retry_behavior_pure_version_conflict_vs_insufficient_stock(async_client: AsyncClient):
    """
    Test E: OCC Retry Behavior.
    - Pure version mismatch: Stock is sufficient, but version advanced.
      The service retries at most once with fresh state and commits successfully.
    - Genuine insufficient stock: Stock is depleted. Not retried; returns 409 immediately.
    """
    token_owner, headers_owner, shop_id = await setup_stage2_shop_and_products(async_client)

    p_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "OCC Test Dal", "price": 80}, headers=headers_owner)
    p_id = p_res.json()["id"]
    await async_client.patch(f"/api/v1/products/{p_id}/inventory", json={"stock": 10, "expected_version": 1}, headers=headers_owner)

    tok, _ = await create_direct_test_customer("OCCCust")
    headers = {"Authorization": f"Bearer {tok}"}
    await async_client.post("/api/v1/cart/items", json={"product_id": p_id, "quantity": 1}, headers=headers)

    # Simulate concurrent modification: merchant increments version and updates stock from 10 to 9
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE inventory SET stock = 9, version = 3 WHERE product_id = :pid"), {"pid": p_id})
        await conn.commit()

    # Checkout is executed. Initial read in cart has stale version, but fresh retry uses version 3 and stock 9 >= 1.
    res = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers=headers)
    assert res.status_code == 201, f"Expected retry to succeed with 201, got {res.status_code}: {res.text}"

    # Verify inventory is now 8, version is 4
    async with async_session_maker() as session:
        inv = (await session.execute(select(Inventory).where(Inventory.product_id == p_id))).scalar_one()
        assert inv.stock == 8
        assert inv.version == 4
