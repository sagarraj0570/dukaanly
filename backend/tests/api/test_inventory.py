import pytest
from httpx import AsyncClient
import uuid

pytestmark = pytest.mark.asyncio

async def setup_test_users(async_client, engine):
    from sqlalchemy import text
    
    owner1_email = f"i_owner1_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 1", "email": owner1_email, "password": "PassWord123"})
    
    owner2_email = f"i_owner2_{uuid.uuid4()}@example.com"
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

async def test_inventory_creation_and_ownership(async_client: AsyncClient):
    from app.db.session import engine
    token1, shop1_id, token2, shop2_id = await setup_test_users(async_client, engine)
    
    # 1. Create product for shop1
    payload = {
        "name": "Inventory Test Product",
        "description": "Test",
        "category": "Tools",
        "price": 99.99
    }
    create_res = await async_client.post(f"/api/v1/shops/{shop1_id}/products", json=payload, headers={"Authorization": f"Bearer {token1}"})
    assert create_res.status_code == 201
    product_id = create_res.json()["id"]
    
    # 2. Check inventory automatically created
    inv_res = await async_client.get(f"/api/v1/products/{product_id}/inventory", headers={"Authorization": f"Bearer {token1}"})
    assert inv_res.status_code == 200
    inv = inv_res.json()
    assert inv["stock"] == 0
    assert inv["version"] == 1
    assert inv["product_id"] == product_id
    
    # 3. Try to update inventory as owner 2 (Isolation Check)
    bad_update = await async_client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json={"stock": 10, "expected_version": 1},
        headers={"Authorization": f"Bearer {token2}"}
    )
    assert bad_update.status_code == 403
    
    # 4. Try negative stock (Application level / Schema validation)
    bad_schema = await async_client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json={"stock": -5, "expected_version": 1},
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert bad_schema.status_code == 422 # Pydantic check

async def test_inventory_optimistic_concurrency(async_client: AsyncClient):
    from app.db.session import engine
    token1, shop1_id, _, _ = await setup_test_users(async_client, engine)
    
    payload = {
        "name": "Concurrency Product",
        "price": 10.0
    }
    create_res = await async_client.post(f"/api/v1/shops/{shop1_id}/products", json=payload, headers={"Authorization": f"Bearer {token1}"})
    product_id = create_res.json()["id"]
    
    # Initial inventory fetch
    inv = (await async_client.get(f"/api/v1/products/{product_id}/inventory", headers={"Authorization": f"Bearer {token1}"})).json()
    version = inv["version"]
    assert version == 1
    
    # First update succeeds
    first_update = await async_client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json={"stock": 10, "expected_version": version},
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert first_update.status_code == 200
    assert first_update.json()["version"] == 2
    assert first_update.json()["stock"] == 10
    
    # Second update with the SAME version fails
    second_update = await async_client.patch(
        f"/api/v1/products/{product_id}/inventory",
        json={"stock": 20, "expected_version": version}, # Still using version 1!
        headers={"Authorization": f"Bearer {token1}"}
    )
    assert second_update.status_code == 409
    
    # The stock must still be 10, not 20
    final_inv = (await async_client.get(f"/api/v1/products/{product_id}/inventory", headers={"Authorization": f"Bearer {token1}"})).json()
    assert final_inv["stock"] == 10
    assert final_inv["version"] == 2
