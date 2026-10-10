import pytest
from httpx import AsyncClient
import uuid
import asyncio
from sqlalchemy import text
from app.db.session import engine

# Helper setup to get tokens, shop, and a few riders
async def setup_geo_test_data(async_client: AsyncClient, engine):
    # Customer
    c_email = f"c_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Customer", "email": c_email, "password": "PassWord123"})
    c_token = (await async_client.post("/api/v1/auth/login", json={"email": c_email, "password": "PassWord123"})).json()["access_token"]
    
    # Shop owner
    so_email = f"so_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Shop Owner", "email": so_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": so_email})
        await conn.commit()
    so_token = (await async_client.post("/api/v1/auth/login", json={"email": so_email, "password": "PassWord123"})).json()["access_token"]
    
    # Create shop
    shop = (await async_client.post("/api/v1/shops", json={
        "name": "Geo Shop",
        "address": "Geo St",
        "location": {"latitude": 40.0, "longitude": -70.0}
    }, headers={"Authorization": f"Bearer {so_token}"})).json()
    shop_id = shop["id"]
    
    # Create order (confirmed)
    async with engine.connect() as conn:
        c_id = (await conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": c_email})).scalar()
        o_id = (await conn.execute(
            text("INSERT INTO orders (id, customer_id, shop_id, status, total_amount) VALUES (:id, :cid, :sid, 'confirmed', 100) RETURNING id"),
            {"id": str(uuid.uuid4()), "cid": c_id, "sid": shop_id}
        )).scalar()
        await conn.commit()
        
    order_id = str(o_id)
    
    # Create 3 riders
    riders = []
    for i in range(3):
        r_email = f"r{i}_{uuid.uuid4()}@example.com"
        await async_client.post("/api/v1/auth/register", json={"name": f"Rider {i}", "email": r_email, "password": "PassWord123"})
        async with engine.connect() as conn:
            await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": r_email})
            await conn.commit()
        r_token = (await async_client.post("/api/v1/auth/login", json={"email": r_email, "password": "PassWord123"})).json()["access_token"]
        
        # Create profile
        p_res = await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {r_token}"})
        riders.append({
            "email": r_email,
            "token": r_token,
            "rider_id": p_res.json()["id"],
            "user_id": p_res.json()["user_id"]
        })
        
    return c_token, so_token, shop_id, order_id, riders

@pytest.mark.asyncio
async def test_location_update_and_candidate_discovery(async_client: AsyncClient):
    c_token, so_token, shop_id, order_id, riders = await setup_geo_test_data(async_client, engine)
    
    r1 = riders[0]
    r2 = riders[1]
    r3 = riders[2]
    
    # R1: available, very close
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r1['token']}"})
    await async_client.patch("/api/v1/riders/me/location", json={"latitude": 40.001, "longitude": -70.001}, headers={"Authorization": f"Bearer {r1['token']}"})
    
    # R2: available, farther but within 5000m
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r2['token']}"})
    await async_client.patch("/api/v1/riders/me/location", json={"latitude": 40.020, "longitude": -70.020}, headers={"Authorization": f"Bearer {r2['token']}"})
    
    # R3: available, way outside radius (e.g. lat 45)
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r3['token']}"})
    await async_client.patch("/api/v1/riders/me/location", json={"latitude": 45.0, "longitude": -75.0}, headers={"Authorization": f"Bearer {r3['token']}"})
    
    # 1. Create delivery with destination (40.0, -70.0)
    del_res = await async_client.post("/api/v1/deliveries", json={
        "order_id": order_id,
        "destination_latitude": 40.0,
        "destination_longitude": -70.0
    }, headers={"Authorization": f"Bearer {so_token}"})
    assert del_res.status_code == 201
    delivery_id = del_res.json()["id"]
    
    # 2. Get candidates
    cand_res = await async_client.get(f"/api/v1/deliveries/{delivery_id}/rider-candidates", headers={"Authorization": f"Bearer {so_token}"})
    assert cand_res.status_code == 200
    all_candidates = cand_res.json()
    
    # Filter candidates to only those created in this test
    test_rider_ids = {r["rider_id"] for r in riders}
    candidates = [c for c in all_candidates if c["rider_id"] in test_rider_ids]
    
    # Only R1 and R2 should be included
    assert len(candidates) == 2
    # R1 should be first because they are closer
    assert candidates[0]["rider_id"] == r1["rider_id"]
    assert candidates[1]["rider_id"] == r2["rider_id"]
    assert candidates[0]["distance_meters"] < candidates[1]["distance_meters"]

@pytest.mark.asyncio
async def test_stale_location_exclusion(async_client: AsyncClient):
    c_token, so_token, shop_id, order_id, riders = await setup_geo_test_data(async_client, engine)
    
    r1 = riders[0]
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r1['token']}"})
    await async_client.patch("/api/v1/riders/me/location", json={"latitude": 40.001, "longitude": -70.001}, headers={"Authorization": f"Bearer {r1['token']}"})
    
    # Manually make the location stale (>15 mins)
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE rider_profiles SET location_updated_at = NOW() - INTERVAL '20 minutes' WHERE id = :id"), {"id": r1["rider_id"]})
        await conn.commit()
        
    del_res = await async_client.post("/api/v1/deliveries", json={"order_id": order_id, "destination_latitude": 40.0, "destination_longitude": -70.0}, headers={"Authorization": f"Bearer {so_token}"})
    delivery_id = del_res.json()["id"]
    
    cand_res = await async_client.get(f"/api/v1/deliveries/{delivery_id}/rider-candidates", headers={"Authorization": f"Bearer {so_token}"})
    
    test_rider_ids = {r["rider_id"] for r in riders}
    candidates = [c for c in cand_res.json() if c["rider_id"] in test_rider_ids]
    assert len(candidates) == 0

@pytest.mark.asyncio
async def test_concurrent_auto_assignment(async_client: AsyncClient):
    c_token, so_token, shop_id, order_id, riders = await setup_geo_test_data(async_client, engine)
    
    r1 = riders[0]
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r1['token']}"})
    await async_client.patch("/api/v1/riders/me/location", json={"latitude": 80.001, "longitude": -150.001}, headers={"Authorization": f"Bearer {r1['token']}"})
    
    # Create two orders and two deliveries
    async with engine.connect() as conn:
        c_id = (await conn.execute(text("SELECT customer_id FROM orders WHERE id = :oid"), {"oid": order_id})).scalar()
        
        o_id2 = (await conn.execute(
            text("INSERT INTO orders (id, customer_id, shop_id, status, total_amount) VALUES (:id, :cid, :sid, 'confirmed', 100) RETURNING id"),
            {"id": str(uuid.uuid4()), "cid": c_id, "sid": shop_id}
        )).scalar()
        await conn.commit()
    
    del_res1 = await async_client.post("/api/v1/deliveries", json={"order_id": order_id, "destination_latitude": 80.0, "destination_longitude": -150.0}, headers={"Authorization": f"Bearer {so_token}"})
    del_res2 = await async_client.post("/api/v1/deliveries", json={"order_id": str(o_id2), "destination_latitude": 80.0, "destination_longitude": -150.0}, headers={"Authorization": f"Bearer {so_token}"})
    
    d1_id = del_res1.json()["id"]
    d2_id = del_res2.json()["id"]
    
    # Send two auto-assign requests concurrently
    res1, res2 = await asyncio.gather(
        async_client.post(f"/api/v1/deliveries/{d1_id}/auto-assign", headers={"Authorization": f"Bearer {so_token}"}),
        async_client.post(f"/api/v1/deliveries/{d2_id}/auto-assign", headers={"Authorization": f"Bearer {so_token}"})
    )
    
    statuses = sorted([res1.status_code, res2.status_code])
    assert statuses in ([200, 200], [200, 409])
    
    if statuses == [200, 200]:
        assert res1.json()["rider_id"] != res2.json()["rider_id"]
    
    # Verify r1 was marked unavailable
    r1_me = await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {r1['token']}"})
    assert r1_me.json()["is_available"] is False
    
    # Completing the winning delivery should reactivate the rider
    if res1.json().get("rider_id") == r1["rider_id"]:
        win_d_id = d1_id
    else:
        win_d_id = d2_id
        
    # update status -> picked_up -> out_for_delivery -> delivered
    await async_client.patch(f"/api/v1/deliveries/{win_d_id}/status", json={"status": "picked_up"}, headers={"Authorization": f"Bearer {r1['token']}"})
    await async_client.patch(f"/api/v1/deliveries/{win_d_id}/status", json={"status": "out_for_delivery"}, headers={"Authorization": f"Bearer {r1['token']}"})
    await async_client.patch(f"/api/v1/deliveries/{win_d_id}/status", json={"status": "delivered"}, headers={"Authorization": f"Bearer {r1['token']}"})
    
    r1_me = await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {r1['token']}"})
    assert r1_me.json()["is_available"] is True
