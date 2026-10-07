import pytest
import uuid
from httpx import AsyncClient
import asyncio

pytestmark = pytest.mark.asyncio

async def setup_test_data(async_client, engine):
    from sqlalchemy import text
    
    # 1. Setup owner and customer
    owner1_email = f"o_owner_{uuid.uuid4()}@example.com"
    customer1_email = f"o_cust1_{uuid.uuid4()}@example.com"
    customer2_email = f"o_cust2_{uuid.uuid4()}@example.com"
    
    await async_client.post("/api/v1/auth/register", json={"name": "Owner", "email": owner1_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer 1", "email": customer1_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer 2", "email": customer2_email, "password": "PassWord123"})
    
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e1"), {"e1": owner1_email})
        await conn.commit()
        
    token_owner = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "PassWord123"})).json()["access_token"]
    token_cust1 = (await async_client.post("/api/v1/auth/login", json={"email": customer1_email, "password": "PassWord123"})).json()["access_token"]
    token_cust2 = (await async_client.post("/api/v1/auth/login", json={"email": customer2_email, "password": "PassWord123"})).json()["access_token"]
    
    # 2. Create shop
    shop1_id = (await async_client.post("/api/v1/shops", json={"name": "Order Shop", "address": "1", "location": {"latitude": 1.0, "longitude": 1.0}}, headers={"Authorization": f"Bearer {token_owner}"})).json()["id"]
    
    # 3. Create products
    p1_id = (await async_client.post(f"/api/v1/shops/{shop1_id}/products", json={"name": "O_P1", "price": 50.0}, headers={"Authorization": f"Bearer {token_owner}"})).json()["id"]
    p2_id = (await async_client.post(f"/api/v1/shops/{shop1_id}/products", json={"name": "O_P2", "price": 10.0}, headers={"Authorization": f"Bearer {token_owner}"})).json()["id"]
    
    # 4. Stock inventory
    await async_client.patch(f"/api/v1/products/{p1_id}/inventory", json={"stock": 5, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner}"})
    await async_client.patch(f"/api/v1/products/{p2_id}/inventory", json={"stock": 10, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner}"})
    
    return token_owner, token_cust1, token_cust2, shop1_id, p1_id, p2_id

async def test_order_checkout_flow(async_client: AsyncClient):
    from app.db.session import engine
    token_owner, token_cust1, token_cust2, shop_id, p1_id, p2_id = await setup_test_data(async_client, engine)
    
    headers_cust = {"Authorization": f"Bearer {token_cust1}"}
    headers_owner = {"Authorization": f"Bearer {token_owner}"}
    
    # 1. Fill Cart
    await async_client.post("/api/v1/cart/items", json={"product_id": p1_id, "quantity": 2}, headers=headers_cust)
    await async_client.post("/api/v1/cart/items", json={"product_id": p2_id, "quantity": 1}, headers=headers_cust)
    
    # 2. Checkout
    idem_key = str(uuid.uuid4())
    res = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key}, headers=headers_cust)
    assert res.status_code == 201
    order = res.json()
    assert order["status"] == "pending"
    assert order["total_amount"] == "110.00" # 2*50 + 1*10
    assert len(order["items"]) == 2
    order_id = order["id"]
    
    # 3. Check Cart is empty
    cart_res = await async_client.get("/api/v1/cart", headers=headers_cust)
    assert len(cart_res.json()["items"]) == 0
    
    # 4. Check Inventory is deducted
    inv_p1 = (await async_client.get(f"/api/v1/products/{p1_id}/inventory", headers=headers_cust)).json()
    assert inv_p1["stock"] == 3 # 5 - 2
    
    # 5. Check Idempotency (Repeat checkout with SAME key)
    res2 = await async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key}, headers=headers_cust)
    assert res2.status_code == 201 # Returns 201 but with the SAME order
    assert res2.json()["id"] == order_id
    
    # 6. Check Order Retrieval (Customer)
    list_res = await async_client.get("/api/v1/orders", headers=headers_cust)
    assert list_res.json()["total"] == 1
    
    # 7. Check Order Retrieval Isolation (Cust 2 should see 0)
    list_res2 = await async_client.get("/api/v1/orders", headers={"Authorization": f"Bearer {token_cust2}"})
    assert list_res2.json()["total"] == 0
    
    # 8. Check Order Retrieval (Owner)
    shop_list_res = await async_client.get(f"/api/v1/shops/{shop_id}/orders", headers=headers_owner)
    assert shop_list_res.json()["total"] == 1
    
    # 9. Update Order Status (Owner)
    upd_res = await async_client.patch(f"/api/v1/shops/{shop_id}/orders/{order_id}/status", json={"status": "confirmed"}, headers=headers_owner)
    assert upd_res.status_code == 200
    assert upd_res.json()["status"] == "confirmed"

async def test_concurrent_checkout_and_insufficient_stock(async_client: AsyncClient):
    from app.db.session import engine
    token_owner, token_cust1, token_cust2, shop_id, p1_id, p2_id = await setup_test_data(async_client, engine)
    
    # P1 has 5 stock.
    # Cust 1 wants 4. Cust 2 wants 4.
    await async_client.post("/api/v1/cart/items", json={"product_id": p1_id, "quantity": 4}, headers={"Authorization": f"Bearer {token_cust1}"})
    await async_client.post("/api/v1/cart/items", json={"product_id": p1_id, "quantity": 4}, headers={"Authorization": f"Bearer {token_cust2}"})
    
    # Fire checkouts concurrently
    idem_key1 = str(uuid.uuid4())
    idem_key2 = str(uuid.uuid4())
    
    # Using asyncio.gather to fire simultaneously
    t1 = async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key1}, headers={"Authorization": f"Bearer {token_cust1}"})
    t2 = async_client.post("/api/v1/orders/checkout", json={"idempotency_key": idem_key2}, headers={"Authorization": f"Bearer {token_cust2}"})
    
    res1, res2 = await asyncio.gather(t1, t2)
    
    # One should succeed (201), one should fail (409 or 400 depending on race condition timing)
    status_codes = [res1.status_code, res2.status_code]
    assert 201 in status_codes
    assert (409 in status_codes) or (400 in status_codes)
    
    # Check inventory is exactly 1
    inv_p1 = (await async_client.get(f"/api/v1/products/{p1_id}/inventory", headers={"Authorization": f"Bearer {token_cust1}"})).json()
    assert inv_p1["stock"] == 1
