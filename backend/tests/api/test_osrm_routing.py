import pytest
import uuid
import httpx
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, Response

from app.services.osrm import (
    osrm_service,
    haversine_distance,
    estimate_fallback_duration,
    generate_osrm_cache_key,
    validate_coordinates,
    OSRMError,
    OSRMInvalidCoordinatesError,
    OSRMNoRouteError,
    OSRMTimeoutError,
    OSRMProviderError,
)

pytestmark = pytest.mark.asyncio


async def test_haversine_distance():
    # Patna Boring Road to Patna Station approx 3-4km
    d = haversine_distance(25.6144, 85.1158, 25.6022, 85.1376)
    assert 2000 < d < 4000


async def test_estimate_fallback_duration():
    duration = estimate_fallback_duration(2200)  # ~2.2km
    # At ~22 km/h (6.11 m/s), 2200m takes ~360s (6 mins)
    assert 300 < duration < 400


async def test_generate_osrm_cache_key():
    k1 = generate_osrm_cache_key(25.61441, 85.11581, 25.62001, 85.12001)
    k2 = generate_osrm_cache_key(25.61444, 85.11583, 25.62002, 85.12004)
    # Coordinates rounded to 4 decimals should produce identical key
    assert k1 == k2


async def test_validate_coordinates():
    # Valid
    validate_coordinates(25.6144, 85.1158)
    
    # Latitude out of bounds
    with pytest.raises(OSRMInvalidCoordinatesError):
        validate_coordinates(95.0, 85.1158)

    with pytest.raises(OSRMInvalidCoordinatesError):
        validate_coordinates(-95.0, 85.1158)

    # Longitude out of bounds
    with pytest.raises(OSRMInvalidCoordinatesError):
        validate_coordinates(25.6144, 185.0)

    # NaN / Inf
    with pytest.raises(OSRMInvalidCoordinatesError):
        validate_coordinates(float("nan"), 85.1158)


async def test_osrm_service_two_point_success():
    mock_osrm_payload = {
        "code": "Ok",
        "routes": [
            {
                "distance": 2100.5,
                "duration": 340.2,
                "geometry": {
                    "type": "LineString",
                    "coordinates": [
                        [85.1158, 25.6144],
                        [85.1170, 25.6160],
                        [85.1200, 25.6200],
                    ],
                },
                "legs": [{"distance": 2100.5, "duration": 340.2}],
            }
        ],
    }

    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, json=mock_osrm_payload)

            result = await osrm_service.get_two_point_route(
                start_lat=25.6144,
                start_lon=85.1158,
                end_lat=25.6200,
                end_lon=85.1200,
                from_name="Pickup",
                to_name="Dropoff",
            )

            assert result["from_name"] == "Pickup"
            assert result["to_name"] == "Dropoff"
            assert result["distance_meters"] == 2100.5
            assert result["duration_seconds"] == 340.2
            assert result["duration_minutes"] == 5.7
            assert result["is_fallback"] is False
            # Leaflet polyline must be [[lat, lon], ...]
            assert result["geometry"] == [
                [25.6144, 85.1158],
                [25.6160, 85.1170],
                [25.6200, 85.1200],
            ]


async def test_osrm_service_raises_on_timeout():
    """Never invent a successful route when OSRM fails due to timeout."""
    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.side_effect = httpx.TimeoutException("Read timeout")

            with pytest.raises(OSRMTimeoutError) as exc_info:
                await osrm_service.get_two_point_route(
                    start_lat=25.7144,
                    start_lon=85.2158,
                    end_lat=25.7200,
                    end_lon=85.2200,
                )
            assert "timed out" in str(exc_info.value).lower()


async def test_osrm_service_raises_on_no_route():
    """Raise OSRMNoRouteError when OSRM reports NoRoute."""
    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, json={"code": "NoRoute", "routes": []})

            with pytest.raises(OSRMNoRouteError):
                await osrm_service.get_two_point_route(
                    start_lat=25.7144,
                    start_lon=85.2158,
                    end_lat=25.7200,
                    end_lon=85.2200,
                )


async def test_osrm_service_raises_on_upstream_500():
    """Raise OSRMProviderError on HTTP 500 error from OSRM."""
    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(502, text="Bad Gateway upstream")

            with pytest.raises(OSRMProviderError):
                await osrm_service.get_two_point_route(
                    start_lat=25.7144,
                    start_lon=85.2158,
                    end_lat=25.7200,
                    end_lon=85.2200,
                )


async def test_osrm_redis_cache_hit_and_failure_tolerance():
    """Test Redis caching: cache miss writes to Redis, cache hit returns cached data, and Redis failure proceeds."""
    mock_redis = AsyncMock()
    # Cache hit scenario
    mock_redis.get.return_value = '{"from_name": "Cached", "distance_meters": 1500, "duration_seconds": 250, "duration_minutes": 4.2, "geometry": [[25.6, 85.1]], "is_fallback": false}'

    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as get_client:
        get_client.return_value = mock_redis

        res = await osrm_service.get_two_point_route(
            start_lat=25.6000,
            start_lon=85.1000,
            end_lat=25.6100,
            end_lon=85.1100,
        )
        assert res["cached"] is True
        assert res["distance_meters"] == 1500

    # Redis failure scenario
    mock_failing_redis = AsyncMock()
    mock_failing_redis.get.side_effect = Exception("Redis connection refused")

    mock_osrm_payload = {
        "code": "Ok",
        "routes": [{"distance": 900, "duration": 120, "geometry": {"coordinates": [[85.1, 25.6]]}}],
    }

    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as get_client:
        get_client.return_value = mock_failing_redis
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, json=mock_osrm_payload)

            res = await osrm_service.get_two_point_route(
                start_lat=25.6000,
                start_lon=85.1000,
                end_lat=25.6100,
                end_lon=85.1100,
            )
            assert res["distance_meters"] == 900
            assert res["cached"] is False


async def test_osrm_table_matrix():
    """Test OSRM Table API matrix calculation."""
    sources = [(25.6100, 85.1100), (25.6200, 85.1200)]
    destinations = [(25.6150, 85.1150)]

    mock_table_payload = {
        "code": "Ok",
        "durations": [[180.5], [420.0]],
        "distances": [[1200.0], [2800.0]],
    }

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json=mock_table_payload)

        res = await osrm_service.get_table_matrix(sources, destinations)
        assert res["durations"] == [[180.5], [420.0]]
        assert res["distances"] == [[1200.0], [2800.0]]


async def test_osrm_multi_leg_route():
    with patch.object(osrm_service, "get_two_point_route") as mock_leg:
        # Leg 1: Rider -> Shop
        mock_leg.side_effect = [
            {
                "from_name": "Rider",
                "to_name": "Shop",
                "from_latitude": 25.6100,
                "from_longitude": 85.1100,
                "to_latitude": 25.6144,
                "to_longitude": 85.1158,
                "distance_meters": 1000.0,
                "duration_seconds": 180.0,
                "duration_minutes": 3.0,
                "geometry": [[25.6100, 85.1100], [25.6144, 85.1158]],
                "is_fallback": False,
                "cached": False,
            },
            # Leg 2: Shop -> Customer
            {
                "from_name": "Shop",
                "to_name": "Customer",
                "from_latitude": 25.6144,
                "from_longitude": 85.1158,
                "to_latitude": 25.6200,
                "to_longitude": 85.1200,
                "distance_meters": 2000.0,
                "duration_seconds": 360.0,
                "duration_minutes": 6.0,
                "geometry": [[25.6144, 85.1158], [25.6200, 85.1200]],
                "is_fallback": False,
                "cached": False,
            },
        ]

        multi_res = await osrm_service.get_multi_leg_delivery_route(
            rider_loc=(25.6100, 85.1100),
            shop_loc=(25.6144, 85.1158),
            customer_loc=(25.6200, 85.1200),
            delivery_status="assigned",
        )

        assert len(multi_res["legs"]) == 2
        assert multi_res["total_distance_meters"] == 3000.0
        assert multi_res["total_duration_seconds"] == 540.0
        assert multi_res["total_duration_minutes"] == 9.0
        assert multi_res["active_leg_index"] == 0  # assigned = heading to shop
        assert len(multi_res["combined_geometry"]) == 3  # deduped junction point
        assert "OSRM" in multi_res["attribution"]


async def test_delivery_route_api_endpoint(async_client: AsyncClient):
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # 1. Create delivery with customer coordinates
    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    assert res_create.status_code == 201
    delivery_id = res_create.json()["id"]

    # 2. Assign rider with rider location
    await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 25.6100, "longitude": 85.1100},
        headers={"Authorization": f"Bearer {tokens['rider']}"},
    )
    await async_client.post(
        f"/api/v1/deliveries/{delivery_id}/assign",
        json={"rider_id": rider1_id},
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )

    # Mock OSRM route response for clean end-to-end API test
    mock_multi_leg = {
        "legs": [
            {
                "from_name": "Shop",
                "to_name": "Customer",
                "from_latitude": 25.6144,
                "from_longitude": 85.1158,
                "to_latitude": 25.6180,
                "to_longitude": 85.1220,
                "distance_meters": 1800.0,
                "duration_seconds": 300.0,
                "duration_minutes": 5.0,
                "geometry": [[25.6144, 85.1158], [25.6180, 85.1220]],
                "is_fallback": False,
                "cached": False,
            }
        ],
        "total_distance_meters": 1800.0,
        "total_duration_seconds": 300.0,
        "total_duration_minutes": 5.0,
        "combined_geometry": [[25.6144, 85.1158], [25.6180, 85.1220]],
        "active_leg_index": 0,
        "is_fallback": False,
        "cached": False,
        "attribution": "Route data © OpenStreetMap contributors, powered by OSRM",
    }

    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.return_value = mock_multi_leg

        # 3. Customer retrieves route
        res_route = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_route.status_code == 200
        route_json = res_route.json()

        assert route_json["delivery_id"] == delivery_id
        assert route_json["status"] == "assigned"
        assert route_json["shop_location"]["name"] is not None
        assert route_json["customer_location"]["name"] is not None
        assert route_json["total_distance_meters"] == 1800.0
        assert route_json["total_duration_minutes"] == 5.0
        assert len(route_json["legs"]) == 1
        assert "combined_geometry" in route_json
        assert "attribution" in route_json

    # 4. Unauthorized customer cannot view route
    unauth_email = f"unauth_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "U", "email": unauth_email, "password": "PassWord123"})
    unauth_token = (await async_client.post("/api/v1/auth/login", json={"email": unauth_email, "password": "PassWord123"})).json()["access_token"]

    res_unauth = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
        headers={"Authorization": f"Bearer {unauth_token}"},
    )
    assert res_unauth.status_code == 403


async def test_delivery_route_api_handles_osrm_timeout(async_client: AsyncClient):
    """Test that upstream OSRM timeout returns sanitized 504 Gateway Timeout."""
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.side_effect = OSRMTimeoutError("OSRM read timeout after 5s")

        res = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res.status_code == 504
        assert "timed out" in res.json()["detail"].lower()


async def test_delivery_route_api_handles_no_route(async_client: AsyncClient):
    """Test that NoRoute from OSRM returns sanitized 404 Not Found."""
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.side_effect = OSRMNoRouteError("No route found between delivery locations")

        res = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res.status_code == 404
        assert "no drivable route" in res.json()["detail"].lower()


async def test_rider_candidates_osrm_ranking_and_fallback(async_client: AsyncClient):
    """Test candidate ranking: with OSRM Table duration sorting, and fallback to PostGIS distance on OSRM error."""
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # Register and activate second rider
    from sqlalchemy import text
    r2_email = f"r2_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "Rider 2", "email": r2_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": r2_email})
        await conn.commit()
    r2_token = (await async_client.post("/api/v1/auth/login", json={"email": r2_email, "password": "PassWord123"})).json()["access_token"]

    await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {r2_token}"})
    await async_client.patch("/api/v1/riders/me/availability", json={"is_available": True}, headers={"Authorization": f"Bearer {r2_token}"})
    rider2_id = (await async_client.get("/api/v1/riders/me", headers={"Authorization": f"Bearer {r2_token}"})).json()["id"]

    # Unique base coordinates for complete test isolation
    base_lat = 21.0 + float(uuid.uuid4().int % 5000) / 1000.0
    base_lon = 81.0 + float(uuid.uuid4().int % 5000) / 1000.0

    # Position rider 1 at base + 0.0010 (~140m away)
    await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": base_lat + 0.0010, "longitude": base_lon + 0.0010},
        headers={"Authorization": f"Bearer {tokens['rider']}"},
    )
    # Position rider 2 at base + 0.0050 (~700m away)
    await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": base_lat + 0.0050, "longitude": base_lon + 0.0050},
        headers={"Authorization": f"Bearer {r2_token}"},
    )

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": base_lat,
            "destination_longitude": base_lon,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    # Scenario A: OSRM Table returns faster driving duration for Rider 2 (180s vs 600s)
    mock_table_matrix = {
        "durations": [[600.0], [180.0]],
        "distances": [[1500.0], [800.0]],
    }

    with patch.object(osrm_service, "get_table_matrix", new_callable=AsyncMock) as mock_table:
        mock_table.return_value = mock_table_matrix

        res = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/rider-candidates",
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res.status_code == 200
        candidates = res.json()
        assert len(candidates) >= 2
        # Candidate with shortest road duration (180s) is ranked first!
        assert candidates[0]["estimated_duration_seconds"] == 180.0
        assert candidates[0]["road_distance_meters"] == 800.0
        assert candidates[0]["routing_status"] == "routed"
        # Longer road duration candidate is ranked behind
        assert candidates[1]["estimated_duration_seconds"] == 600.0
        assert candidates[1]["road_distance_meters"] == 1500.0
        assert candidates[1]["routing_status"] == "routed"

    # Scenario B: OSRM fails (timeout/error) -> Falls back to pure PostGIS straight-line ranking without failing!
    with patch.object(osrm_service, "get_table_matrix", new_callable=AsyncMock) as mock_table:
        mock_table.side_effect = OSRMTimeoutError("OSRM Table timeout")

        res_fallback = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/rider-candidates",
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_fallback.status_code == 200
        fb_candidates = res_fallback.json()
        assert len(fb_candidates) >= 2
        # In fallback, PostGIS distance ordering is preserved and OSRM fields are None
        assert fb_candidates[0]["road_distance_meters"] is None
        assert fb_candidates[0]["estimated_duration_seconds"] is None
        assert fb_candidates[0]["routing_status"] == "straight_line_fallback"
        assert fb_candidates[0]["distance_meters"] <= fb_candidates[1]["distance_meters"]

    # Scenario C: Unroutable candidates handling policy
    # Rider 1 is closer in straight-line distance, but unroutable (null duration/distance).
    # Rider 2 is further in straight-line distance, but has valid road route (250s duration).
    mock_unroutable_matrix = {
        "durations": [[None], [250.0]],
        "distances": [[None], [750.0]],
    }
    with patch.object(osrm_service, "get_table_matrix", new_callable=AsyncMock) as mock_table:
        mock_table.return_value = mock_unroutable_matrix

        res_unroutable = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/rider-candidates",
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_unroutable.status_code == 200
        unr_candidates = res_unroutable.json()
        assert len(unr_candidates) >= 2

        # Documented policy: routable candidate (Rider 2) MUST outrank unroutable candidate (Rider 1),
        # even though Rider 1 has closer Euclidean straight-line distance!
        assert unr_candidates[0]["routing_status"] == "routed"
        assert unr_candidates[0]["estimated_duration_seconds"] == 250.0
        assert unr_candidates[0]["road_distance_meters"] == 750.0

        assert unr_candidates[1]["routing_status"] == "unroutable"
        assert unr_candidates[1]["estimated_duration_seconds"] is None
        assert unr_candidates[1]["road_distance_meters"] is None
        assert unr_candidates[1]["distance_meters"] < unr_candidates[0]["distance_meters"]


async def test_delivery_route_authorization_and_privacy(async_client: AsyncClient):
    """
    Test strict authorization and route privacy:
    - Order customer: Allowed (200)
    - Fulfilling shop owner: Allowed (200)
    - Assigned rider: Allowed (200)
    - Superuser / Admin: Allowed (200)
    - Unrelated customer: Forbidden (403)
    - Unrelated shop owner: Forbidden (403)
    - Unassigned rider: Forbidden (403)
    - Manipulated non-existent delivery ID: Not Found (404)
    - Manipulated malformed delivery ID: Validation Error (422)
    - Unauthenticated request: Unauthorized (401)
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data
    from sqlalchemy import text

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # 1. Create delivery
    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    assert res_create.status_code == 201
    delivery_id = res_create.json()["id"]

    # Assign rider 1
    await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 25.6100, "longitude": 85.1100},
        headers={"Authorization": f"Bearer {tokens['rider']}"},
    )
    await async_client.post(
        f"/api/v1/deliveries/{delivery_id}/assign",
        json={"rider_id": rider1_id},
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )

    # Mock OSRM route response
    mock_multi_leg = {
        "legs": [
            {
                "from_name": "Shop",
                "to_name": "Customer",
                "from_latitude": 25.6144,
                "from_longitude": 85.1158,
                "to_latitude": 25.6180,
                "to_longitude": 85.1220,
                "distance_meters": 1800.0,
                "duration_seconds": 300.0,
                "duration_minutes": 5.0,
                "geometry": [[25.6144, 85.1158], [25.6180, 85.1220]],
                "is_fallback": False,
                "cached": False,
            }
        ],
        "total_distance_meters": 1800.0,
        "total_duration_seconds": 300.0,
        "total_duration_minutes": 5.0,
        "combined_geometry": [[25.6144, 85.1158], [25.6180, 85.1220]],
        "active_leg_index": 0,
        "is_fallback": False,
        "cached": False,
        "attribution": "Route data © OpenStreetMap contributors, powered by OSRM",
    }

    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.return_value = mock_multi_leg

        # A. Authorized Customer -> 200 OK
        res_cust = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_cust.status_code == 200

        # B. Authorized Fulfilling Shop Owner -> 200 OK
        res_owner = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
        )
        assert res_owner.status_code == 200

        # C. Authorized Assigned Rider -> 200 OK
        res_rider = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['rider']}"},
        )
        assert res_rider.status_code == 200

        # D. Superuser / Admin -> 200 OK
        res_admin = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['admin']}"},
        )
        assert res_admin.status_code == 200

    # E. Unrelated Customer -> 403 Forbidden
    other_cust_email = f"other_cust_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "OC", "email": other_cust_email, "password": "PassWord123"})
    other_cust_token = (await async_client.post("/api/v1/auth/login", json={"email": other_cust_email, "password": "PassWord123"})).json()["access_token"]
    res_other_cust = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
        headers={"Authorization": f"Bearer {other_cust_token}"},
    )
    assert res_other_cust.status_code == 403

    # F. Unrelated Shop Owner -> 403 Forbidden
    other_owner_email = f"other_owner_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "OO", "email": other_owner_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": other_owner_email})
        await conn.commit()
    other_owner_token = (await async_client.post("/api/v1/auth/login", json={"email": other_owner_email, "password": "PassWord123"})).json()["access_token"]
    res_other_owner = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
        headers={"Authorization": f"Bearer {other_owner_token}"},
    )
    assert res_other_owner.status_code == 403

    # G. Unassigned Rider -> 403 Forbidden
    other_rider_email = f"other_rider_{uuid.uuid4()}@example.com"
    await async_client.post("/api/v1/auth/register", json={"name": "OR", "email": other_rider_email, "password": "PassWord123"})
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": other_rider_email})
        await conn.commit()
    other_rider_token = (await async_client.post("/api/v1/auth/login", json={"email": other_rider_email, "password": "PassWord123"})).json()["access_token"]
    await async_client.post("/api/v1/riders/profile", headers={"Authorization": f"Bearer {other_rider_token}"})

    res_other_rider = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
        headers={"Authorization": f"Bearer {other_rider_token}"},
    )
    assert res_other_rider.status_code == 403

    # H. Manipulated Non-Existent Delivery ID (Random UUID) -> 404 Not Found
    random_delivery_id = str(uuid.uuid4())
    res_nonexistent = await async_client.get(
        f"/api/v1/deliveries/{random_delivery_id}/route",
        headers={"Authorization": f"Bearer {tokens['customer']}"},
    )
    assert res_nonexistent.status_code == 404

    # I. Manipulated Malformed Delivery ID -> 422 Unprocessable Entity
    res_malformed = await async_client.get(
        "/api/v1/deliveries/invalid-manipulated-id-12345/route",
        headers={"Authorization": f"Bearer {tokens['customer']}"},
    )
    assert res_malformed.status_code == 422

    # J. Unauthenticated Request (No Token) -> 401 Unauthorized
    res_no_auth = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
    )
    assert res_no_auth.status_code == 401


async def test_delivery_route_fallback_transparency(async_client: AsyncClient):
    """
    Test that when OSRM fails:
    1. Delivery route API never synthesizes fake straight-line geometry as a verified road route.
    2. Candidate discovery keeps road_distance_meters as None with routing_status='straight_line_fallback'.
    """
    from app.db.session import engine
    from tests.api.test_deliveries import setup_delivery_test_data

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.6180,
            "destination_longitude": 85.1220,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    delivery_id = res_create.json()["id"]

    # 1. When OSRM times out on route request -> returns 504 Gateway Timeout, never fake 200
    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.side_effect = OSRMTimeoutError("Routing service timed out")

        res = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res.status_code == 504
        assert "timed out" in res.json()["detail"].lower()

    # 2. When OSRM returns NoRoute -> returns 404 Not Found, never fake straight-line polyline
    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        mock_route.side_effect = OSRMNoRouteError("No route found")

        res_no_route = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res_no_route.status_code == 404
        assert "no drivable route" in res_no_route.json()["detail"].lower()


async def test_osrm_service_raises_on_malformed_json():
    """Raise OSRMProviderError when upstream returns HTTP 200 but content is not valid JSON."""
    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, text="<html><body>Gateway Error</body></html>")

            with pytest.raises(OSRMProviderError) as exc_info:
                await osrm_service.get_two_point_route(
                    start_lat=25.6144,
                    start_lon=85.1158,
                    end_lat=25.6200,
                    end_lon=85.1200,
                )
            assert "malformed json" in str(exc_info.value).lower()


async def test_osrm_service_raises_on_empty_routes():
    """Raise OSRMNoRouteError when code is Ok but routes list is empty."""
    with patch.object(osrm_service, "_get_redis_client", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = None
        with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = Response(200, json={"code": "Ok", "routes": []})

            with pytest.raises(OSRMNoRouteError):
                await osrm_service.get_two_point_route(
                    start_lat=25.6144,
                    start_lon=85.1158,
                    end_lat=25.6200,
                    end_lon=85.1200,
                )


async def test_osrm_table_matrix_malformed_json():
    """Raise OSRMProviderError when table API returns malformed JSON."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, text="non-json output")

        with pytest.raises(OSRMProviderError) as exc_info:
            await osrm_service.get_table_matrix([(25.6144, 85.1158)], [(25.6200, 85.1200)])
        assert "malformed json" in str(exc_info.value).lower()


async def test_osrm_bounded_concurrency_semaphore():
    """Verify that get_osrm_semaphore initializes and limits concurrent tasks."""
    from app.services.osrm import get_osrm_semaphore
    from app.core.config import settings
    sem = get_osrm_semaphore()
    assert sem._value == settings.OSRM_MAX_CONCURRENT_REQUESTS


async def test_check_routing_health_healthy():
    """Verify check_routing_health returns healthy when OSRM responds with Ok."""
    from app.core.config import settings
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json={"code": "Ok", "waypoints": []})
        health = await osrm_service.check_routing_health()
        assert health["status"] == "healthy"
        assert health["provider"] == settings.ROUTING_PROVIDER


async def test_check_routing_health_degraded():
    """Verify check_routing_health returns degraded on unexpected code."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = Response(200, json={"code": "InvalidQuery"})
        health = await osrm_service.check_routing_health()
        assert health["status"] == "degraded"


async def test_check_routing_health_unreachable_on_timeout():
    """Verify check_routing_health returns unreachable on timeout."""
    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.TimeoutException("Read timeout")
        health = await osrm_service.check_routing_health()
        assert health["status"] == "unreachable"
        assert "timed out" in health["details"].lower()


async def test_routing_health_api_endpoint(async_client: AsyncClient):
    """Test /api/v1/health/routing endpoint for healthy (200) and unreachable (503)."""
    with patch.object(osrm_service, "check_routing_health", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {
            "status": "healthy",
            "provider": "osrm",
            "base_url": "http://localhost:5000",
            "details": "OSRM routing service operational",
        }
        res_ok = await async_client.get("/api/v1/health/routing")
        assert res_ok.status_code == 200
        assert res_ok.json()["status"] == "healthy"

    with patch.object(osrm_service, "check_routing_health", new_callable=AsyncMock) as mock_probe:
        mock_probe.return_value = {
            "status": "unreachable",
            "provider": "osrm",
            "base_url": "http://localhost:5000",
            "details": "OSRM service offline",
        }
        res_fail = await async_client.get("/api/v1/health/routing")
        assert res_fail.status_code == 503
        assert res_fail.json()["status"] == "unreachable"


async def test_osrm_safe_shutdown():
    """Verify close_osrm_http_client resets the client singleton safely."""
    from app.services.osrm import get_osrm_http_client, close_osrm_http_client
    client = await get_osrm_http_client()
    assert client is not None
    await close_osrm_http_client()
    from app.services import osrm
    assert osrm._osrm_http_client is None


async def test_delivery_route_cancelled_or_delivered_returns_terminal_route_without_calling_osrm(async_client: AsyncClient):
    """When a delivery is cancelled or delivered, route endpoint returns a calm terminal route without hitting OSRM."""
    from tests.api.test_deliveries import setup_delivery_test_data
    from app.db.session import engine
    from app.models.delivery import DeliveryStatus

    tokens, order_id, rider1_id, shop_id = await setup_delivery_test_data(async_client, engine)

    # 1. Create delivery
    res_create = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.62,
            "destination_longitude": 85.12,
        },
        headers={"Authorization": f"Bearer {tokens['shop_owner']}"},
    )
    assert res_create.status_code == 201
    delivery_id = res_create.json()["id"]

    # 2. Cancel delivery
    from app.db.session import async_session_maker
    async with async_session_maker() as db:
        from app.models.delivery import Delivery
        deliv = await db.get(Delivery, uuid.UUID(delivery_id))
        deliv.status = DeliveryStatus.cancelled
        await db.commit()

    # 3. Retrieve route - must succeed with 200 without calling OSRM
    with patch.object(osrm_service, "get_multi_leg_delivery_route", new_callable=AsyncMock) as mock_route:
        res = await async_client.get(
            f"/api/v1/deliveries/{delivery_id}/route",
            headers={"Authorization": f"Bearer {tokens['customer']}"},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["status"] == "cancelled"
        assert len(data["legs"]) == 0
        assert data["total_distance_meters"] == 0.0
        assert "terminal" in data["attribution"].lower()
        mock_route.assert_not_called()


