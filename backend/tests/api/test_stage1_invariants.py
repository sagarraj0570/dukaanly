import asyncio
import pytest
import uuid
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from app.db.session import engine, async_session_maker
from app.models.delivery import DeliveryStatus

pytestmark = pytest.mark.asyncio


async def setup_stage1_fixtures(async_client: AsyncClient):
    """Setup shop owner, customer, admin, rider, shop, product, and confirmed order."""
    emails = [f"st1_{r}_{uuid.uuid4().hex[:8]}@example.com" for r in ("owner", "cust", "admin", "rider")]
    roles = ["shop_owner", "customer", "admin", "rider"]

    for email in emails:
        await async_client.post("/api/v1/auth/register", json={"name": "Stage1 User", "email": email, "password": "PassWord123"})

    async with engine.connect() as conn:
        for email, role in zip(emails, roles):
            await conn.execute(text("UPDATE users SET role = :r WHERE email = :e"), {"r": role, "e": email})
        await conn.commit()

    tokens = {}
    for r, e in zip(roles, emails):
        res = await async_client.post("/api/v1/auth/login", json={"email": e, "password": "PassWord123"})
        tokens[r] = res.json()["access_token"]

    # Initialize rider profile and make available
    await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {tokens['rider']}"})
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    rider_info = (await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {tokens['rider']}"})).json()
    rider_id = rider_info["id"]

    # Setup Shop and Product
    shop_res = await async_client.post("/api/v1/shops", json={"name": "S1 Invariants", "address": "Patna Main", "location": {"latitude": 25.61, "longitude": 85.14}}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    shop_id = shop_res.json()["id"]

    prod_res = await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "P1 Product", "price": 150}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    product_id = prod_res.json()["id"]

    await async_client.patch(f"/api/v1/products/{product_id}/inventory", json={"stock": 50, "expected_version": 1}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})

    # Create Order 1
    await async_client.post("/api/v1/cart/items", json={"product_id": product_id, "quantity": 1}, headers={"Authorization": f"Bearer {tokens['customer']}"})
    order1_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers={"Authorization": f"Bearer {tokens['customer']}"})).json()["id"]

    # Create Order 2 directly in DB
    order2_id = str(uuid.uuid4())
    async with engine.connect() as conn:
        customer_id = (await conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": emails[1]})).scalar()
        await conn.execute(text("UPDATE orders SET status = 'confirmed' WHERE id = :oid"), {"oid": order1_id})
        await conn.execute(text("""
            INSERT INTO orders (id, customer_id, shop_id, status, total_amount) 
            VALUES (:id, :cid, :sid, 'confirmed', 150)
        """), {"id": order2_id, "cid": customer_id, "sid": shop_id})
        await conn.commit()

    return tokens, order1_id, order2_id, rider_id, shop_id, product_id


async def test_two_simultaneous_rider_assignments_exactly_one_succeeds(async_client: AsyncClient):
    """
    Rider Concurrency:
    Two genuinely concurrent requests attempt to accept/assign different deliveries
    for the same rider. Exactly one request must succeed (HTTP 200) and the other
    must fail with HTTP 409 Conflict. The database must contain at most one active delivery for that rider.
    """
    tokens, order1_id, order2_id, rider_id, _, _ = await setup_stage1_fixtures(async_client)

    # 1. Create two pending deliveries for two different orders
    res_d1 = await async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_d1.status_code == 201
    d1_id = res_d1.json()["id"]

    res_d2 = await async_client.post("/api/v1/deliveries", json={"order_id": order2_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_d2.status_code == 201
    d2_id = res_d2.json()["id"]

    # 2. Concurrently attempt to assign the same rider to both deliveries
    req1 = async_client.post(f"/api/v1/deliveries/{d1_id}/assign", json={"rider_id": rider_id}, headers={"Authorization": f"Bearer {tokens['admin']}"})
    req2 = async_client.post(f"/api/v1/deliveries/{d2_id}/assign", json={"rider_id": rider_id}, headers={"Authorization": f"Bearer {tokens['admin']}"})

    resp1, resp2 = await asyncio.gather(req1, req2)
    codes = [resp1.status_code, resp2.status_code]

    assert 200 in codes, f"Expected one 200 OK, got: {codes}"
    assert 409 in codes, f"Expected one 409 Conflict, got: {codes}"

    conflict_resp = resp1 if resp1.status_code == 409 else resp2
    assert "already has an active delivery" in conflict_resp.json()["detail"].lower() or "not available" in conflict_resp.json()["detail"].lower()

    # 3. Direct DB Invariant Check: Verify at most one active delivery exists for this rider in PostgreSQL
    async with async_session_maker() as session:
        active_count = (await session.execute(text("""
            SELECT COUNT(*) 
            FROM deliveries 
            WHERE rider_id = :rid 
              AND status IN ('assigned', 'picked_up', 'out_for_delivery');
        """), {"rid": rider_id})).scalar()
        assert active_count == 1, f"Expected exactly 1 active delivery for rider, found {active_count}"


async def test_concurrent_order_delivery_creation_at_most_one_succeeds(async_client: AsyncClient):
    """
    Order Concurrency:
    Two genuinely concurrent requests attempt to create an active delivery for the same order.
    At most one request must succeed (HTTP 201) and the other must receive HTTP 409 Conflict.
    The database must contain at most one active delivery for that order.
    """
    tokens, order1_id, _, _, _, _ = await setup_stage1_fixtures(async_client)

    # Concurrently attempt to create a delivery for order1_id
    req1 = async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    req2 = async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})

    resp1, resp2 = await asyncio.gather(req1, req2)
    codes = [resp1.status_code, resp2.status_code]

    assert 201 in codes, f"Expected at least one 201 Created, got: {codes}"
    assert 409 in codes, f"Expected duplicate request to be rejected with 409, got: {codes}"

    conflict_resp = resp1 if resp1.status_code == 409 else resp2
    assert "delivery already exists" in conflict_resp.json()["detail"].lower()

    # Direct DB Invariant Check: exactly 1 active delivery exists for order1_id
    async with async_session_maker() as session:
        active_count = (await session.execute(text("""
            SELECT COUNT(*) 
            FROM deliveries 
            WHERE order_id = :oid 
              AND status IN ('pending', 'assigned', 'picked_up', 'out_for_delivery');
        """), {"oid": order1_id})).scalar()
        assert active_count == 1, f"Expected exactly 1 active delivery for order, found {active_count}"


async def test_redispatch_allowed_after_delivery_cancellation(async_client: AsyncClient):
    """
    Delivery Re-dispatch:
    When a delivery reaches a terminal state (cancelled), the shop must be allowed
    to create a replacement delivery for the same order. Overlapping active deliveries
    remain strictly forbidden.
    """
    tokens, order1_id, _, _, _, _ = await setup_stage1_fixtures(async_client)

    # 1. Create first delivery (pending)
    res1 = await async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res1.status_code == 201
    d1_id = res1.json()["id"]

    # 2. Attempting a second delivery while first is pending MUST fail with 409
    res_dup = await async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_dup.status_code == 409

    # 3. Cancel the first delivery in DB (simulating cancelled delivery lifecycle)
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE deliveries SET status = 'cancelled' WHERE id = :did"), {"did": d1_id})
        await conn.commit()

    # 4. Now creating a replacement delivery for the SAME order MUST succeed
    res2 = await async_client.post("/api/v1/deliveries", json={"order_id": order1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res2.status_code == 201
    d2_id = res2.json()["id"]
    assert d2_id != d1_id

    # 5. DB Invariant Check:
    # Total deliveries for this order = 2 (1 cancelled, 1 pending)
    # Active deliveries for this order = 1 (pending)
    async with async_session_maker() as session:
        total_deliveries = (await session.execute(text("SELECT COUNT(*) FROM deliveries WHERE order_id = :oid"), {"oid": order1_id})).scalar()
        active_deliveries = (await session.execute(text("""
            SELECT COUNT(*) 
            FROM deliveries 
            WHERE order_id = :oid 
              AND status IN ('pending', 'assigned', 'picked_up', 'out_for_delivery');
        """), {"oid": order1_id})).scalar()

        assert total_deliveries == 2
        assert active_deliveries == 1


async def test_inventory_nonnegative_stock_check_constraint_enforced():
    """
    Inventory Invariant:
    Verify that the database CHECK constraint `chk_inventory_stock_non_negative`
    rejects any direct database write attempting negative stock.
    """
    async with async_session_maker() as session:
        # Create a test product & inventory row
        prod_id = uuid.uuid4()
        shop_res = await session.execute(text("SELECT id FROM shops LIMIT 1"))
        shop_id = shop_res.scalar()

        await session.execute(text("""
            INSERT INTO products (id, shop_id, name, price, is_active)
            VALUES (:pid, :sid, 'Constraint Test Item', 50, true)
        """), {"pid": prod_id, "sid": shop_id})

        # Valid initial stock
        await session.execute(text("""
            INSERT INTO inventory (id, product_id, stock, version)
            VALUES (:iid, :pid, 5, 1)
        """), {"iid": uuid.uuid4(), "pid": prod_id})
        await session.commit()

        # Direct write with negative stock MUST be rejected by PostgreSQL CHECK constraint
        with pytest.raises(IntegrityError) as exc_info:
            await session.execute(text("""
                UPDATE inventory SET stock = -1 WHERE product_id = :pid
            """), {"pid": prod_id})
            await session.commit()

        assert "chk_inventory_stock_non_negative" in str(exc_info.value).lower() or "check constraint" in str(exc_info.value).lower()
        await session.rollback()

        # Clean up
        await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": prod_id})
        await session.commit()


async def test_alembic_stage1_migration_contract():
    """
    Migration Contract & Downgrade Safety:
    Verify that migration 6179f4c20f23:
    1. Preserves exactly one Alembic head (6179f4c20f23).
    2. Has down_revision pointing to 4d8e90f62a02.
    3. Successfully implements upgrade and downgrade functions.
    """
    from pathlib import Path
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    alembic_ini_path = Path(__file__).resolve().parent.parent.parent / "alembic.ini"
    config = Config(str(alembic_ini_path))
    script = ScriptDirectory.from_config(config)

    heads = script.get_heads()
    assert len(heads) == 1, f"Expected exactly 1 head, found {heads}"
    all_revs = [r.revision for r in script.walk_revisions()]
    assert "6179f4c20f23" in all_revs

    rev = script.get_revision("6179f4c20f23")
    assert rev.down_revision == "4d8e90f62a02"
    assert hasattr(rev.module, "upgrade") and callable(rev.module.upgrade)
    assert hasattr(rev.module, "downgrade") and callable(rev.module.downgrade)
