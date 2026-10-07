import pytest
import uuid
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def setup_test_users(async_client, engine):
    from sqlalchemy import text
    
    r_email = f"rider_{uuid.uuid4()}@example.com"
    c_email = f"cust_{uuid.uuid4()}@example.com"
    
    await async_client.post("/api/v1/auth/register", json={"name": "Rider", "email": r_email, "password": "PassWord123"})
    await async_client.post("/api/v1/auth/register", json={"name": "Cust", "email": c_email, "password": "PassWord123"})
    
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e1"), {"e1": r_email})
        await conn.commit()
        
    t_rider = (await async_client.post("/api/v1/auth/login", json={"email": r_email, "password": "PassWord123"})).json()["access_token"]
    t_cust = (await async_client.post("/api/v1/auth/login", json={"email": c_email, "password": "PassWord123"})).json()["access_token"]
    
    return t_rider, t_cust

async def test_rider_profile_creation_and_availability(async_client: AsyncClient):
    from app.db.session import engine
    t_rider, t_cust = await setup_test_users(async_client, engine)
    
    # 1. Customer cannot create rider profile
    res_cust = await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {t_cust}"})
    assert res_cust.status_code == 403
    
    # 2. Rider creates profile
    res_rider = await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {t_rider}"})
    assert res_rider.status_code == 201
    assert res_rider.json()["is_available"] == False
    
    # 3. Duplicate profile rejected
    res_dup = await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {t_rider}"})
    assert res_dup.status_code == 409
    
    # 4. Update availability
    res_avail = await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {t_rider}"})
    assert res_avail.status_code == 200
    assert res_avail.json()["is_available"] == True
    
    # 5. Fetch profile
    res_me = await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {t_rider}"})
    assert res_me.status_code == 200
    assert res_me.json()["is_available"] == True
