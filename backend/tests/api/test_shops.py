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
    list_res = await async_client.get("/api/v1/shops?page=1&size=100")
    assert list_res.status_code == 200
    list_data = list_res.json()
    assert list_data["total"] >= 1
    assert any(s["id"] == shop_id for s in list_data["items"])

    # 6. Test /shops/me endpoint when active
    me_res = await async_client.get("/api/v1/shops/me", headers={"Authorization": f"Bearer {token1}"})
    assert me_res.status_code == 200
    assert me_res.json()["id"] == shop_id
    assert me_res.json()["is_active"] is True

    # 7. Toggle shop offline
    toggle_res = await async_client.patch(f"/api/v1/shops/{shop_id}", json={"is_active": False}, headers={"Authorization": f"Bearer {token1}"})
    assert toggle_res.status_code == 200
    assert toggle_res.json()["is_active"] is False

    # 8. Verify /shops/me still succeeds when shop is offline
    me_offline_res = await async_client.get("/api/v1/shops/me", headers={"Authorization": f"Bearer {token1}"})
    assert me_offline_res.status_code == 200
    assert me_offline_res.json()["id"] == shop_id
    assert me_offline_res.json()["is_active"] is False

    # 9. Toggle shop back online
    toggle_online_res = await async_client.patch(f"/api/v1/shops/{shop_id}", json={"is_active": True}, headers={"Authorization": f"Bearer {token1}"})
    assert toggle_online_res.status_code == 200
    assert toggle_online_res.json()["is_active"] is True

async def test_shop_geospatial_discovery_and_eligibility(async_client: AsyncClient):
    from app.db.session import engine
    from sqlalchemy import text

    owner_email = f"geo_owner_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Geo Owner", "email": owner_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()
    token = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "PassWord123"})).json()["access_token"]

    # Create a shop in Central Bengaluru (MG Road)
    shop_payload = {
        "name": "MG Road Grocery",
        "description": "Hyperlocal Kirana",
        "address": "Brigade Road, Bengaluru",
        "location": {"latitude": 12.9716, "longitude": 77.5946}
    }
    create_res = await async_client.post("/api/v1/shops", json=shop_payload, headers={"Authorization": f"Bearer {token}"})
    assert create_res.status_code == 201
    shop_id = create_res.json()["id"]

    # 1. Query with location right next to the shop (0 km)
    res_close = await async_client.get("/api/v1/shops?latitude=12.9716&longitude=77.5946&radius_meters=1000")
    assert res_close.status_code == 200
    data_close = res_close.json()
    assert data_close["radius_meters"] == 1000
    matching_close = [s for s in data_close["items"] if s["id"] == shop_id]
    assert len(matching_close) == 1
    assert matching_close[0]["distance_meters"] is not None
    assert matching_close[0]["distance_meters"] <= 10.0
    assert matching_close[0]["is_delivery_eligible"] is True

    # 2. Query from HSR Layout (~8.2 km away) with 5 km radius -> Should NOT include the shop
    res_5km = await async_client.get("/api/v1/shops?latitude=12.9116&longitude=77.6389&radius_meters=5000")
    assert res_5km.status_code == 200
    data_5km = res_5km.json()
    assert not any(s["id"] == shop_id for s in data_5km["items"])

    # 3. Query from HSR Layout with expanded 10 km radius -> Should include the shop with is_delivery_eligible=False
    res_10km = await async_client.get("/api/v1/shops?latitude=12.9116&longitude=77.6389&radius_meters=10000&size=100")
    assert res_10km.status_code == 200
    data_10km = res_10km.json()
    matching_10km = [s for s in data_10km["items"] if s["id"] == shop_id]
    assert len(matching_10km) == 1
    assert matching_10km[0]["distance_meters"] > 5000.0
    assert matching_10km[0]["is_delivery_eligible"] is False

    # 4. Query with delivery_only=true from HSR Layout -> Excluded because distance > 5km
    res_delivery_only = await async_client.get("/api/v1/shops?latitude=12.9116&longitude=77.6389&radius_meters=10000&delivery_only=true")
    assert res_delivery_only.status_code == 200
    assert not any(s["id"] == shop_id for s in res_delivery_only.json()["items"])

    # 5. Check dedicated delivery-eligibility endpoint
    # Close location (eligible)
    elig_close = await async_client.get(f"/api/v1/shops/{shop_id}/delivery-eligibility?latitude=12.9716&longitude=77.5946")
    assert elig_close.status_code == 200
    assert elig_close.json()["is_delivery_eligible"] is True

    # Far location (ineligible)
    elig_far = await async_client.get(f"/api/v1/shops/{shop_id}/delivery-eligibility?latitude=12.9116&longitude=77.6389")
    assert elig_far.status_code == 200
    assert elig_far.json()["is_delivery_eligible"] is False
    assert "exceeds" in elig_far.json()["message"]

async def test_shop_geospatial_validation_and_ranking(async_client: AsyncClient):
    from app.db.session import engine
    from sqlalchemy import text

    owner_email = f"rank_owner_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Rank Owner", "email": owner_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()
    token = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "PassWord123"})).json()["access_token"]

    # 1. Invalid coordinates validation (422)
    bad_lat = await async_client.get("/api/v1/shops?latitude=95.0&longitude=77.0")
    assert bad_lat.status_code == 422

    bad_lng = await async_client.get("/api/v1/shops?latitude=12.0&longitude=190.0")
    assert bad_lng.status_code == 422

    # 2. Unpaired coordinates validation (400)
    unpaired_lat = await async_client.get("/api/v1/shops?latitude=12.9716")
    assert unpaired_lat.status_code == 400
    assert "Both latitude and longitude must be provided together" in unpaired_lat.json()["detail"]

    unpaired_lng = await async_client.get("/api/v1/shops?longitude=77.5946")
    assert unpaired_lng.status_code == 400

    # 3. Radius boundaries (min 100m, max 10,000m)
    radius_too_large = await async_client.get("/api/v1/shops?latitude=12.9716&longitude=77.5946&radius_meters=15000")
    assert radius_too_large.status_code == 422

    radius_too_small = await async_client.get("/api/v1/shops?latitude=12.9716&longitude=77.5946&radius_meters=50")
    assert radius_too_small.status_code == 422

    # 4. Create an inactive shop within 1 km
    inactive_shop_payload = {
        "name": "Inactive Kirana",
        "address": "Closed Street, Bengaluru",
        "location": {"latitude": 12.9720, "longitude": 77.5950}
    }
    inactive_res = await async_client.post("/api/v1/shops", json=inactive_shop_payload, headers={"Authorization": f"Bearer {token}"})
    inactive_shop_id = inactive_res.json()["id"]

    # Deactivate the shop
    await async_client.patch(f"/api/v1/shops/{inactive_shop_id}", json={"is_active": False}, headers={"Authorization": f"Bearer {token}"})

    # Inactive shop should NOT be in active discovery results
    disc_res = await async_client.get("/api/v1/shops?latitude=12.9716&longitude=77.5946&radius_meters=5000")
    assert disc_res.status_code == 200
    assert not any(s["id"] == inactive_shop_id for s in disc_res.json()["items"])

    # Inactive shop delivery eligibility check should return is_delivery_eligible = False
    elig_inactive = await async_client.get(f"/api/v1/shops/{inactive_shop_id}/delivery-eligibility?latitude=12.9716&longitude=77.5946")
    assert elig_inactive.status_code == 200
    assert elig_inactive.json()["is_delivery_eligible"] is False
    assert "closed or inactive" in elig_inactive.json()["message"]

    # 5. Ranking preference: Shop A (1.5 km) vs Shop B (4.5 km)
    # Origin: 12.9716, 77.5946
    # Shop A (Koramangala north, ~1.5 km away)
    shop_a = (await async_client.post(
        "/api/v1/shops",
        json={"name": "Tier 1 Close Shop", "address": "Nearby St", "location": {"latitude": 12.9800, "longitude": 77.6000}},
        headers={"Authorization": f"Bearer {token}"}
    )).json()["id"]

    # Shop B (~4.5 km away, within 5 km but > 3 km)
    shop_b = (await async_client.post(
        "/api/v1/shops",
        json={"name": "Tier 2 Mid Shop", "address": "Mid St", "location": {"latitude": 12.9400, "longitude": 77.6200}},
        headers={"Authorization": f"Bearer {token}"}
    )).json()["id"]

    rank_res = await async_client.get("/api/v1/shops?latitude=12.9716&longitude=77.5946&radius_meters=5000&size=100")
    items = rank_res.json()["items"]
    indices = [s["id"] for s in items]
    assert shop_a in indices
    assert shop_b in indices
    # Preferred tier (<3km) must be ranked before (>3km)
    assert indices.index(shop_a) < indices.index(shop_b)


async def test_get_shop_by_identifier_and_directory_store(async_client: AsyncClient):
    """Verify that any store (by UUID, source_id, or name) can be fetched and viewed."""
    from app.services.geoapify import _memory_cache

    # 1. Populate mock cached discovery place in memory cache
    mock_place = {
        "source": "geoapify",
        "source_id": "geoapify:place:test-hometown-supermarket",
        "name": "Home town",
        "category": "supermarket",
        "address": "Home town, Gola Road, Patna - 801503, Bihar, India",
        "latitude": 25.6144,
        "longitude": 85.0500,
        "distance_meters": 1600.0,
        "phone": "+91 98765 43210",
        "website": "https://hometown.example.com",
        "opening_hours": "Mon-Sun 09:00 - 21:00",
        "is_directory_listing": True,
        "is_dukaanly_merchant": False,
        "is_orderable": False,
        "is_delivery_eligible": False,
        "attribution": "Powered by Geoapify",
    }
    _memory_cache.set("test_key", [mock_place], ttl=300)

    # 2. Query by source_id
    res_source = await async_client.get("/api/v1/shops/geoapify:place:test-hometown-supermarket")
    assert res_source.status_code == 200
    data_source = res_source.json()
    assert data_source["name"] == "Home town"
    assert data_source["is_orderable"] is False
    assert data_source["verification_status"] == "discovered"
    assert data_source["phone"] == "+91 98765 43210"

    # 3. Query delivery-eligibility for directory store -> is_delivery_eligible = False
    elig_res = await async_client.get(
        "/api/v1/shops/geoapify:place:test-hometown-supermarket/delivery-eligibility?latitude=25.6144&longitude=85.0500"
    )
    assert elig_res.status_code == 200
    assert elig_res.json()["is_delivery_eligible"] is False
    assert "directory listing" in elig_res.json()["message"]

    # 4. Unknown store returns 404
    res_404 = await async_client.get("/api/v1/shops/nonexistent-store-xyz-12345")
    assert res_404.status_code == 404



