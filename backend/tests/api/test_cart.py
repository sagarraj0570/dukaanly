import pytest
from httpx import AsyncClient
import uuid

pytestmark = pytest.mark.asyncio

async def setup_test_data(async_client, engine):
    from sqlalchemy import text
    
    # 1. Setup owners and customer
    owner1_email = f"c_owner1_{uuid.uuid4()}@example.com"
    owner2_email = f"c_owner2_{uuid.uuid4()}@example.com"
    customer_email = f"c_cust_{uuid.uuid4()}@example.com"
    
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 1", "email": owner1_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 2", "email": owner2_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Customer", "email": customer_email, "password": "PassWord123"})
    
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email IN (:e1, :e2)"), {"e1": owner1_email, "e2": owner2_email})
        await conn.commit()
        
    token_owner1 = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "PassWord123"})).json()["access_token"]
    token_owner2 = (await async_client.post("/api/v1/auth/login", json={"email": owner2_email, "password": "PassWord123"})).json()["access_token"]
    token_cust = (await async_client.post("/api/v1/auth/login", json={"email": customer_email, "password": "PassWord123"})).json()["access_token"]
    
    # 2. Create shops
    shop1_id = (await async_client.post("/api/v1/shops", json={"name": "S1", "address": "1", "location": {"latitude": 1.0, "longitude": 1.0}}, headers={"Authorization": f"Bearer {token_owner1}"})).json()["id"]
    shop2_id = (await async_client.post("/api/v1/shops", json={"name": "S2", "address": "2", "location": {"latitude": 2.0, "longitude": 2.0}}, headers={"Authorization": f"Bearer {token_owner2}"})).json()["id"]
    
    # 3. Create products
    p1_s1_id = (await async_client.post(f"/api/v1/shops/{shop1_id}/products", json={"name": "P1S1", "price": 10.0}, headers={"Authorization": f"Bearer {token_owner1}"})).json()["id"]
    p2_s1_id = (await async_client.post(f"/api/v1/shops/{shop1_id}/products", json={"name": "P2S1", "price": 20.0}, headers={"Authorization": f"Bearer {token_owner1}"})).json()["id"]
    p1_s2_id = (await async_client.post(f"/api/v1/shops/{shop2_id}/products", json={"name": "P1S2", "price": 30.0}, headers={"Authorization": f"Bearer {token_owner2}"})).json()["id"]
    
    # 4. Stock inventory
    await async_client.patch(f"/api/v1/products/{p1_s1_id}/inventory", json={"stock": 5, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner1}"})
    await async_client.patch(f"/api/v1/products/{p2_s1_id}/inventory", json={"stock": 2, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner1}"})
    await async_client.patch(f"/api/v1/products/{p1_s2_id}/inventory", json={"stock": 10, "expected_version": 1}, headers={"Authorization": f"Bearer {token_owner2}"})
    
    return token_cust, shop1_id, shop2_id, p1_s1_id, p2_s1_id, p1_s2_id

async def test_cart_flows(async_client: AsyncClient):
    from app.db.session import engine
    token_cust, shop1_id, shop2_id, p1_s1_id, p2_s1_id, p1_s2_id = await setup_test_data(async_client, engine)
    
    headers = {"Authorization": f"Bearer {token_cust}"}
    
    # 1. Fetch empty cart
    res = await async_client.get("/api/v1/cart", headers=headers)
    assert res.status_code == 200
    assert res.json()["shop_id"] is None
    assert res.json()["total_amount"] == "0.00"
    
    # 2. Add product 1 from shop 1 to cart
    res = await async_client.post("/api/v1/cart/items", json={"product_id": p1_s1_id, "quantity": 2}, headers=headers)
    assert res.status_code == 200
    cart = res.json()
    assert cart["shop_id"] == shop1_id
    assert len(cart["items"]) == 1
    assert cart["total_amount"] == "20.00" # 2 * 10.0
    item1_id = cart["items"][0]["id"]
    
    # 3. Add product 2 from shop 1 to cart
    res = await async_client.post("/api/v1/cart/items", json={"product_id": p2_s1_id, "quantity": 1}, headers=headers)
    assert res.status_code == 200
    cart = res.json()
    assert len(cart["items"]) == 2
    assert cart["total_amount"] == "40.00" # 20.0 + 20.0
    
    # 4. ONE-SHOP-PER-CART rule check (Attempt adding product from shop 2)
    res = await async_client.post("/api/v1/cart/items", json={"product_id": p1_s2_id, "quantity": 1}, headers=headers)
    assert res.status_code == 400
    assert "one shop" in res.json()["detail"]
    
    # 5. Inventory validation check (Try adding more stock than available)
    # p2_s1 has 2 in stock. We already added 1. Trying to add 2 more -> total 3 -> exceeds stock of 2.
    res = await async_client.post("/api/v1/cart/items", json={"product_id": p2_s1_id, "quantity": 2}, headers=headers)
    assert res.status_code == 400
    assert "available in stock" in res.json()["detail"]
    
    # 6. Update item quantity
    res = await async_client.patch(f"/api/v1/cart/items/{item1_id}", json={"quantity": 3}, headers=headers)
    assert res.status_code == 200
    assert res.json()["total_amount"] == "50.00" # 3*10 + 1*20
    
    # 7. Remove item
    res = await async_client.delete(f"/api/v1/cart/items/{item1_id}", headers=headers)
    assert res.status_code == 200
    cart = res.json()
    assert len(cart["items"]) == 1
    assert cart["total_amount"] == "20.00"
    
    # 8. Clear cart
    res = await async_client.delete("/api/v1/cart", headers=headers)
    assert res.status_code == 200
    cart = res.json()
    assert len(cart["items"]) == 0
    assert cart["shop_id"] is None
    
    # 9. Now we can add from shop 2
    res = await async_client.post("/api/v1/cart/items", json={"product_id": p1_s2_id, "quantity": 1}, headers=headers)
    assert res.status_code == 200
    assert res.json()["shop_id"] == shop2_id
