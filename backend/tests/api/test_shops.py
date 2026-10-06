import pytest
from httpx import AsyncClient
import uuid

pytestmark = pytest.mark.asyncio

async def test_shop_authorization(async_client: AsyncClient):
    # Register customer
    cust_email = f"cust_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={
        "name": "Customer", "email": cust_email, "password": "PassWord123"
    })
    cust_token = (await async_client.post("/api/v1/auth/login", json={"email": cust_email, "password": "PassWord123"})).json()["access_token"]
    
    # Try to create shop as customer
    shop_payload = {
        "name": "My Shop",
        "address": "123 Street",
        "location": {"latitude": 12.9716, "longitude": 77.5946}
    }
    
    res = await async_client.post("/api/v1/shops", json=shop_payload, headers={"Authorization": f"Bearer {cust_token}"})
    assert res.status_code == 403

async def test_shop_crud_and_ownership(async_client: AsyncClient):
    # To create a shop, we need a user with shop_owner role.
    # Currently the /register endpoint defaults to 'customer'. 
    # For testing, we can either manually set the role in DB or add a test helper to bypass.
    # We will register a user, then use SQLAlchemy to upgrade them to shop_owner.
    
    # We can create a dependency override or just hit the DB directly.
    # Since we don't have DB session in test easily, let's just create an admin route or use the DB engine.
    from app.db.session import engine
    from app.models.user import UserRole
    from sqlalchemy import text
    
    owner1_email = f"owner1_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 1", "email": owner1_email, "password": "PassWord123"})
    
    owner2_email = f"owner2_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Owner 2", "email": owner2_email, "password": "PassWord123"})
    
    # Upgrade both to shop_owner manually in DB
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email IN (:e1, :e2)"), {"e1": owner1_email, "e2": owner2_email})
        await conn.commit()
        
    token1 = (await async_client.post("/api/v1/auth/login", json={"email": owner1_email, "password": "PassWord123"})).json()["access_token"]
    token2 = (await async_client.post("/api/v1/auth/login", json={"email": owner2_email, "password": "PassWord123"})).json()["access_token"]
    
    # 1. Create shop
    shop_payload = {
        "name": "Owner 1 Shop",
        "description": "Best shop",
        "address": "456 Market St",
        "location": {"latitude": 40.7128, "longitude": -74.0060}
    }
    create_res = await async_client.post("/api/v1/shops", json=shop_payload, headers={"Authorization": f"Bearer {token1}"})
    assert create_res.status_code == 201
    shop = create_res.json()
    assert shop["name"] == "Owner 1 Shop"
    assert shop["location"]["latitude"] == 40.7128
    assert shop["location"]["longitude"] == -74.0060
    shop_id = shop["id"]
    owner_id_1 = shop["owner_id"]
    
    # 2. Get shop
    get_res = await async_client.get(f"/api/v1/shops/{shop_id}")
    assert get_res.status_code == 200
    assert get_res.json()["name"] == "Owner 1 Shop"
    
    # 3. Update shop as owner1
    update_res = await async_client.patch(f"/api/v1/shops/{shop_id}", json={"name": "Owner 1 Updated Shop"}, headers={"Authorization": f"Bearer {token1}"})
    assert update_res.status_code == 200
    assert update_res.json()["name"] == "Owner 1 Updated Shop"
    
    # 4. Attempt update shop as owner2 (ownership isolation test)
    bad_update_res = await async_client.patch(f"/api/v1/shops/{shop_id}", json={"name": "Hacked Shop"}, headers={"Authorization": f"Bearer {token2}"})
    assert bad_update_res.status_code == 403
    
    # 5. List shops (Pagination test)
    list_res = await async_client.get("/api/v1/shops?page=1&size=10")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(s["id"] == shop_id for s in list_data["items"])
