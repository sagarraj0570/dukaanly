import pytest
from httpx import AsyncClient
import uuid

pytestmark = pytest.mark.asyncio

async def setup_test_users(async_client, engine):
    from sqlalchemy import text
    
    owner1_email = f"p_owner1_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 1", "email": owner1_email, "password": "PassWord123"})
    
    owner2_email = f"p_owner2_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 2", "email": owner2_email, "password": "PassWord123"})
    
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email IN (:e1, :e2)"), {"e1": owner1_email, "e2": owner2_email})
        await conn.commit()
        
    token1 = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "PassWord123"})).json()["access_token"]
    token2 = (await async_client.post("/api/v1/auth/login", json={"email": owner2_email, "password": "PassWord123"})).json()["access_token"]
    
    # Create shop for owner1
    shop1_res = await async_client.post("/api/v1/shops", json={
        "name": "Shop 1", "address": "123", "location": {"latitude": 10.0, "longitude": 10.0}
    }, headers={"Authorization": f"Bearer {token1}"})
    shop1_id = shop1_res.json()["id"]
    
    # Create shop for owner2
    shop2_res = await async_client.post("/api/v1/shops", json={
        "name": "Shop 2", "address": "456", "location": {"latitude": 20.0, "longitude": 20.0}
    }, headers={"Authorization": f"Bearer {token2}"})
    shop2_id = shop2_res.json()["id"]
    
    return token1, shop1_id, token2, shop2_id

async def test_product_crud_and_isolation(async_client: AsyncClient):
    from app.db.session import engine
    token1, shop1_id, token2, shop2_id = await setup_test_users(async_client, engine)
    
    # 1. Create product for shop1
    payload = {
        "name": "Widget",
        "description": "A widget",
        "category": "Tools",
        "price": 19.99
    }
    create_res = await async_client.post(f"/api/v1/shops/{shop1_id}/products", json=payload, headers={"Authorization": f"Bearer {token1}"})
    assert create_res.status_code == 201
    product = create_res.json()
    assert product["name"] == "Widget"
    assert product["price"] == "19.99"
    assert product["shop_id"] == shop1_id
    
    product_id = product["id"]
    
    # 2. Try creating product for shop2 using token1 (Isolation check)
    bad_create = await async_client.post(f"/api/v1/shops/{shop2_id}/products", json=payload, headers={"Authorization": f"Bearer {token1}"})
    assert bad_create.status_code == 403
    
    # 3. Get product
    get_res = await async_client.get(f"/api/v1/products/{product_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Widget"
    
    # 4. Update product using token1
    update_res = await async_client.patch(f"/api/v1/products/{product_id}", json={"price": 14.50}, headers={"Authorization": f"Bearer {token1}"})
    assert update_res.status_code == 200
    assert update_res.json()["price"] == "14.50"
    
    # 5. Try updating product using token2 (Isolation check)
    bad_update = await async_client.patch(f"/api/v1/products/{product_id}", json={"price": 10.00}, headers={"Authorization": f"Bearer {token2}"})
    assert bad_update.status_code == 403
    
    # 6. List products for shop1
    list_res = await async_client.get(f"/api/v1/shops/{shop1_id}/products")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 1
    
    # 7. List products for shop2
    list_res2 = await async_client.get(f"/api/v1/shops/{shop2_id}/products")
    assert list_res2.status_code == 200
    assert list_res2.json()["total"] == 0
