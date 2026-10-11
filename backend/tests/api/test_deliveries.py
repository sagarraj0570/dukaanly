import pytest
import uuid
from httpx import AsyncClient
import asyncio

pytestmark = pytest.mark.asyncio

async def setup_delivery_test_data(async_client, engine):
    from sqlalchemy import text
    
    # Create Users
    emails = [f"d_{r}_{uuid.uuid4()}@example.com" for r in ("owner", "cust", "admin", "rider1", "rider2")]
    roles = ["shop_owner", "customer", "admin", "rider", "rider"]
    
    for email in emails:
        await async_client.post("/api/v1/auth/register", json={"name": "User", "email": email, "password": "PassWord123"})
        
    async with engine.connect() as conn:
        for email, role in zip(emails, roles):
            await conn.execute(text("UPDATE users SET role = :r WHERE email = :e"), {"r": role, "e": email})
        await conn.commit()
        
    tokens = {r: (await async_client.post("/api/v1/auth/login", json={"email": e, "password": "PassWord123"})).json()["access_token"] for r, e in zip(roles + ["rider2"], emails)}
    # Tokens dict has: shop_owner, customer, admin, rider, rider2
    
    # Initialize Riders
    await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {tokens['rider']}"})
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    rider1_id = (await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {tokens['rider']}"})).json()["id"]

    # Setup Order
    shop_id = (await async_client.post("/api/v1/shops", json={"name": "S1", "address": "1", "location": {"latitude": 1.0, "longitude": 1.0}}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})).json()["id"]
    p_id = (await async_client.post(f"/api/v1/shops/{shop_id}/products", json={"name": "P1", "price": 100}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})).json()["id"]
    await async_client.patch(f"/api/v1/products/{p_id}/inventory", json={"stock": 10, "expected_version": 1}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    
    await async_client.post("/api/v1/cart/items", json={"product_id": p_id, "quantity": 1}, headers={"Authorization": f"Bearer {tokens['customer']}"})
    order_id = (await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": str(uuid.uuid4())}, headers={"Authorization": f"Bearer {tokens['customer']}"})).json()["id"]
    
    # Confirm order via DB so we can create delivery
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE orders SET status = 'confirmed' WHERE id = :oid"), {"oid": order_id})
        await conn.commit()
        
    return tokens, order_id, rider1_id, shop_id

async def test_delivery_lifecycle(async_client: AsyncClient):
    from app.db.session import engine
    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)
    
    # 1. Delivery creation (Shop Owner)
    res_create = await async_client.post("/api/v1/deliveries", json={"order_id": order_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_create.status_code == 201
    delivery_id = res_create.json()["id"]
    
    # Duplicate delivery
    res_dup = await async_client.post("/api/v1/deliveries", json={"order_id": order_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_dup.status_code == 409
    
    # 2. Assign Rider (Shop Owner)
    res_assign = await async_client.post(f"/api/v1/deliveries/{delivery_id}/assign", json={"rider_id": rider1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_assign.status_code == 200
    assert res_assign.json()["status"] == "assigned"
    
    # 3. Rider Updates Status
    res_pick = await async_client.patch(f"/api/v1/deliveries/{delivery_id}/status", json={"status": "picked_up"}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    assert res_pick.status_code == 200
    
    # 4. Check Order Sync & Delivery Summary
    res_order = await async_client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {tokens['customer']}"})
    order_data = res_order.json()
    assert order_data["status"] == "ready_for_delivery"
    assert order_data["delivery"] is not None
    assert order_data["delivery"]["id"] == delivery_id
    assert order_data["delivery"]["status"] == "picked_up"
    
    res_out = await async_client.patch(f"/api/v1/deliveries/{delivery_id}/status", json={"status": "out_for_delivery"}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    assert res_out.status_code == 200
    
    res_del = await async_client.patch(f"/api/v1/deliveries/{delivery_id}/status", json={"status": "delivered"}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    assert res_del.status_code == 200
    
    # 5. Invalid transition
    res_inv = await async_client.patch(f"/api/v1/deliveries/{delivery_id}/status", json={"status": "pending"}, headers={"Authorization": f"Bearer {tokens['rider']}"})
    assert res_inv.status_code == 409
    
async def test_rider_workload_concurrency(async_client: AsyncClient):
    from app.db.session import engine
    # We need a rider and TWO orders
    tokens, order_id1, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)
    
    # Create a second order manually
    from sqlalchemy import text
    async with engine.connect() as conn:
        customer_id = (await conn.execute(text("SELECT id FROM users WHERE role = 'customer' LIMIT 1"))).scalar()
        o2 = (await conn.execute(text("INSERT INTO orders (id, customer_id, shop_id, status, total_amount) VALUES (:id, :cid, :sid, 'confirmed', 100) RETURNING id"), 
             {"id": str(uuid.uuid4()), "cid": customer_id, "sid": shop_id})).scalar()
        await conn.commit()
        
    order_id2 = str(o2)
    
    # Create two deliveries
    d1 = (await async_client.post("/api/v1/deliveries", json={"order_id": order_id1}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})).json()["id"]
    d2 = (await async_client.post("/api/v1/deliveries", json={"order_id": order_id2}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})).json()["id"]
    
    # Assign concurrently
    t1 = async_client.post(f"/api/v1/deliveries/{d1}/assign", json={"rider_id": rider1_id}, headers={"Authorization": f"Bearer {tokens['admin']}"})
    t2 = async_client.post(f"/api/v1/deliveries/{d2}/assign", json={"rider_id": rider1_id}, headers={"Authorization": f"Bearer {tokens['admin']}"})
    
    r1, r2 = await asyncio.gather(t1, t2)
    
    # One succeeds, one fails due to partial index
    status_codes = [r1.status_code, r2.status_code]
    assert 200 in status_codes
    assert 409 in status_codes

async def test_customer_order_delivery_tracking_contract(async_client: AsyncClient):
    from app.db.session import engine
    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # 1. Before delivery is created, order returns delivery: None
    res_before = await async_client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {tokens['customer']}"})
    assert res_before.status_code == 200
    assert res_before.json()["delivery"] is None

    # 2. Shop owner creates delivery
    res_create = await async_client.post("/api/v1/deliveries", json={"order_id": order_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    assert res_create.status_code == 201
    delivery_id = res_create.json()["id"]

    # 3. Customer retrieves order, now sees delivery summary with pending status
    res_after = await async_client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {tokens['customer']}"})
    assert res_after.status_code == 200
    deliv_summary = res_after.json()["delivery"]
    assert deliv_summary is not None
    assert deliv_summary["id"] == delivery_id
    assert deliv_summary["status"] == "pending"
    assert deliv_summary["rider_id"] is None

    # 4. Assign rider -> Customer sees assigned status and rider_id
    await async_client.post(f"/api/v1/deliveries/{delivery_id}/assign", json={"rider_id": rider1_id}, headers={"Authorization": f"Bearer {tokens['shop_owner']}"})
    res_assigned = await async_client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {tokens['customer']}"})
    deliv_assigned = res_assigned.json()["delivery"]
    assert deliv_assigned["status"] == "assigned"
    assert deliv_assigned["rider_id"] == rider1_id

    # 5. Customer list endpoint also includes delivery summary
    res_list = await async_client.get("/api/v1/orders", headers={"Authorization": f"Bearer {tokens['customer']}"})
    assert res_list.status_code == 200
    orders_items = res_list.json()["items"]
    matched = [o for o in orders_items if o["id"] == order_id]
    assert len(matched) == 1
    assert matched[0]["delivery"]["id"] == delivery_id

    # 6. Unauthorized / different customer cannot view this order or delivery
    other_cust_email = f"other_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Other", "email": other_cust_email, "password": "PassWord123"})
    other_token = (await async_client.post("/api/v1/auth/login", json={"email": other_cust_email, "password": "PassWord123"})).json()["access_token"]
    
    # Cross-customer access to order is 404 (isolation)
    res_unauth_order = await async_client.get(f"/api/v1/orders/{order_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert res_unauth_order.status_code == 404

    # Cross-customer access to delivery directly is 403 (forbidden)
    res_unauth_deliv = await async_client.get(f"/api/v1/deliveries/{delivery_id}", headers={"Authorization": f"Bearer {other_token}"})
    assert res_unauth_deliv.status_code == 403
