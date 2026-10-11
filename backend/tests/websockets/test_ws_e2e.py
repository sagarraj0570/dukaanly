import pytest
import asyncio
import subprocess
import time
import httpx
import websockets
import json
import uuid
import sys

# We skip this test if we can't spawn the server (e.g. in some CI), but we'll try to run it.
@pytest.fixture(scope="module")
def live_server():
    # Start Uvicorn
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", "8005"],
        stdout=None,
        stderr=None,
    )
    
    # Wait for it to be up
    started = False
    for _ in range(30):
        try:
            res = httpx.get("http://localhost:8005/api/v1/health/live")
            if res.status_code == 200:
                started = True
                break
        except Exception:
            pass
        time.sleep(0.5)
        
    if not started:
        proc.kill()
        pytest.fail("Failed to start live server")
        
    yield "http://localhost:8005", "ws://localhost:8005"
    proc.terminate()
    proc.wait()

@pytest.mark.asyncio
async def test_websocket_e2e(live_server):
    http_base, ws_base = live_server
    
    async with httpx.AsyncClient(base_url=http_base, timeout=30.0) as client:
        # Create Customer
        c_email = f"c_{uuid.uuid4()}@example.com"
        await client.post("/api/v1/auth/register", json={"name": "Cust", "email": c_email, "password": "PassWord123"})
        c_token = (await client.post("/api/v1/auth/login", json={"email": c_email, "password": "PassWord123"})).json()["access_token"]
        
        # Create Shop Owner
        so_email = f"so_{uuid.uuid4()}@example.com"
        await client.post("/api/v1/auth/register", json={"name": "Owner", "email": so_email, "password": "PassWord123"})
        so_token = (await client.post("/api/v1/auth/login", json={"email": so_email, "password": "PassWord123"})).json()["access_token"]
        
        # Create Rider
        r_email = f"r_{uuid.uuid4()}@example.com"
        await client.post("/api/v1/auth/register", json={"name": "Rider", "email": r_email, "password": "PassWord123"})
        r_token = (await client.post("/api/v1/auth/login", json={"email": r_email, "password": "PassWord123"})).json()["access_token"]
        
        # Upgrade roles via hack API? No, we don't have a hack API.
        # But wait! I can just use the DB to upgrade them.
        from sqlalchemy.ext.asyncio import create_async_engine
        from app.core.config import settings
        from sqlalchemy import text
        engine = create_async_engine(settings.database_url)
        async with engine.connect() as conn:
            await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": so_email})
            await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": r_email})
            c_id = (await conn.execute(text("SELECT id FROM users WHERE email = :e"), {"e": c_email})).scalar()
            await conn.commit()
            
        # Re-login to get roles in JWT
        so_token = (await client.post("/api/v1/auth/login", json={"email": so_email, "password": "PassWord123"})).json()["access_token"]
        r_token = (await client.post("/api/v1/auth/login", json={"email": r_email, "password": "PassWord123"})).json()["access_token"]
        
        # Create Shop
        shop = (await client.post("/api/v1/shops", json={
            "name": "Live Shop", "address": "St", "location": {"latitude": 40.0, "longitude": -70.0}
        }, headers={"Authorization": f"Bearer {so_token}"})).json()
        
        async with engine.connect() as conn:
            o_id = (await conn.execute(
                text("INSERT INTO orders (id, customer_id, shop_id, status, total_amount) VALUES (:id, :cid, :sid, 'confirmed', 100) RETURNING id"),
                {"id": str(uuid.uuid4()), "cid": c_id, "sid": shop["id"]}
            )).scalar()
            await conn.commit()
        await engine.dispose()
        order_id = str(o_id)
        
        # Create Rider Profile
        rider_id = (await client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {r_token}"})).json()["id"]
        
        # Make rider available
        await client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r_token}"})
        
        # Create Delivery
        delivery_id = (await client.post("/api/v1/deliveries", json={
            "order_id": order_id, "destination_latitude": 40.0, "destination_longitude": -70.0
        }, headers={"Authorization": f"Bearer {so_token}"})).json()["id"]
        
        # Assign Rider
        assign_res = await client.post(f"/api/v1/deliveries/{delivery_id}/assign", json={"rider_id": rider_id}, headers={"Authorization": f"Bearer {so_token}"})
        if assign_res.status_code != 200:
            print("Assign failed:", assign_res.text, flush=True)
            assert assign_res.status_code == 200
        
    # Now test websockets!
    async with websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={c_token}") as c_ws, \
               websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={so_token}") as so_ws, \
               websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={r_token}") as r_ws:
        
        print("Connected websockets, waiting for ready snapshots...", flush=True)
        # Read snapshots
        ready_r = json.loads(await r_ws.recv())
        print("Rider ready:", ready_r, flush=True)
        assert ready_r["event"] == "connection.ready"
        
        ready_c = json.loads(await c_ws.recv())
        print("Customer ready:", ready_c, flush=True)
        ready_so = json.loads(await so_ws.recv())
        print("Shop owner ready:", ready_so, flush=True)
        
        # Send location
        print("Sending location...", flush=True)
        await r_ws.send(json.dumps({"type": "location_update", "latitude": 41.0, "longitude": -71.0}))
        
        # Both c and so should receive it
        print("Waiting for broadcasts...", flush=True)
        evt_c = json.loads(await c_ws.recv())
        print("Customer evt:", evt_c, flush=True)
        evt_so = json.loads(await so_ws.recv())
        print("Shop owner evt:", evt_so, flush=True)
        
        assert evt_c["event"] == "delivery.location_updated"
        assert evt_c["data"]["latitude"] == 41.0
        
        assert evt_so["event"] == "delivery.location_updated"
        
    # Test unauthorized access
    # Register bad customer
    async with httpx.AsyncClient(base_url=http_base) as client:
        bc_email = f"bc_{uuid.uuid4()}@example.com"
        await client.post("/api/v1/auth/register", json={"name": "BCust", "email": bc_email, "password": "PassWord123"})
        bc_token = (await client.post("/api/v1/auth/login", json={"email": bc_email, "password": "PassWord123"})).json()["access_token"]
        
    try:
        async with websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={bc_token}") as bc_ws:
            assert False, "Should have been rejected"
    except websockets.exceptions.InvalidStatus as e:
        pass
    except websockets.exceptions.ConnectionClosedError as e:
        assert e.code == 1008
