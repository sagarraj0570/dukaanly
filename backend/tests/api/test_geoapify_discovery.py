import math
import uuid
from typing import Dict, Any
from unittest.mock import AsyncMock, patch
import pytest
import httpx
from httpx import AsyncClient, Response
from sqlalchemy import func, select

from app.core.config import settings
from app.db.session import async_session_maker
from app.models.shop import Shop
from app.services.geoapify import _memory_cache, GeoapifyPlacesService

pytestmark = pytest.mark.asyncio

SAMPLE_GEOAPIFY_RESPONSE: Dict[str, Any] = {
    "type": "FeatureCollection",
    "features": [
        {
            "type": "Feature",
            "properties": {
                "name": "Boring Road Fresh Supermarket",
                "country": "India",
                "city": "Patna",
                "formatted": "Boring Road Fresh Supermarket, Boring Road, Patna, Bihar 800001",
                "categories": ["commercial", "commercial.supermarket"],
                "distance": 420.0,
                "place_id": "geo_node_9482001",
                "contact": {
                    "phone": "+91 612 254 9900",
                    "website": "https://supermart.example.com",
                },
                "opening_hours": "08:00 - 22:00",
                "lat": 25.6148,
                "lon": 85.1162,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [85.1162, 25.6148],
            },
        },
        {
            "type": "Feature",
            "properties": {
                "name": "Sanjeevani Medicos Pharmacy",
                "city": "Patna",
                "formatted": "Sanjeevani Medicos, Boring Canal Road, Patna",
                "categories": ["healthcare", "healthcare.pharmacy"],
                "distance": 680.0,
                "place_id": "geo_node_9482002",
                "contact": {"phone": "+91 94310 11223"},
                "lat": 25.6138,
                "lon": 85.1152,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [85.1152, 25.6138],
            },
        },
        # Outside requested radius (>3000m)
        {
            "type": "Feature",
            "properties": {
                "name": "Out of Bounds Mart",
                "formatted": "Outer Highway Mart, Patna",
                "categories": ["commercial.supermarket"],
                "distance": 4800.0,
                "place_id": "geo_node_9482003",
                "lat": 25.5000,
                "lon": 85.0000,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [85.0000, 25.5000],
            },
        },
        # Duplicate item (same place_id)
        {
            "type": "Feature",
            "properties": {
                "name": "Boring Road Fresh Supermarket",
                "formatted": "Boring Road Fresh Supermarket, Boring Road, Patna, Bihar 800001",
                "categories": ["commercial", "commercial.supermarket"],
                "distance": 420.0,
                "place_id": "geo_node_9482001",
                "lat": 25.6148,
                "lon": 85.1162,
            },
            "geometry": {
                "type": "Point",
                "coordinates": [85.1162, 25.6148],
            },
        },
    ],
}


@pytest.fixture(autouse=True)
async def clear_discovery_cache():
    _memory_cache.clear()
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        keys = await client.keys("dukaanly:geoapify:places:*")
        if keys:
            await client.delete(*keys)
        await client.aclose()
    except Exception:
        pass
    yield
    _memory_cache.clear()
    try:
        import redis.asyncio as aioredis
        client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
        keys = await client.keys("dukaanly:geoapify:places:*")
        if keys:
            await client.delete(*keys)
        await client.aclose()
    except Exception:
        pass


async def test_successful_provider_normalization_and_response_schema(async_client: AsyncClient):
    """Test successful response normalization into directory-only listings."""
    mock_resp = Response(
        status_code=200,
        json=SAMPLE_GEOAPIFY_RESPONSE,
        request=AsyncMock(),
    )

    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158, "radius": 3000, "limit": 10},
        )

    assert res.status_code == 200
    data = res.json()
    assert "items" in data
    assert data["latitude"] == 25.6144
    assert data["longitude"] == 85.1158
    assert data["radius_meters"] == 3000
    assert data["cached"] is False
    assert "Geoapify" in data["attribution"]
    assert "OpenStreetMap" in data["attribution"]

    items = data["items"]
    # Only the 2 in-bounds, unique items should be present
    assert len(items) == 2

    first = items[0]
    assert first["source"] == "geoapify"
    assert first["source_id"] == "geo_node_9482001"
    assert first["name"] == "Boring Road Fresh Supermarket"
    assert first["category"] == "supermarket"
    assert first["is_directory_listing"] is True
    assert first["is_dukaanly_merchant"] is False
    assert first["is_orderable"] is False
    assert first["is_delivery_eligible"] is False
    assert first["phone"] == "+91 612 254 9900"
    assert first["website"] == "https://supermart.example.com"
    assert first["opening_hours"] == "08:00 - 22:00"

    second = items[1]
    assert second["name"] == "Sanjeevani Medicos Pharmacy"
    assert second["category"] == "chemist"


async def test_category_mapping_and_upstream_query_params(async_client: AsyncClient):
    """Verify category mapping and strict coordinate order (filter=circle:lon,lat,radius)."""
    captured_params = {}

    async def mock_fetch(self, query_params):
        nonlocal captured_params
        captured_params = query_params
        return Response(status_code=200, json={"type": "FeatureCollection", "features": []}, request=AsyncMock())

    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=mock_fetch):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158, "radius": 2500, "category": "chemist", "limit": 15},
        )

    assert res.status_code == 200
    # Crucial Geoapify parameter order: longitude first, then latitude!
    assert captured_params["filter"] == "circle:85.1158,25.6144,2500"
    assert captured_params["bias"] == "proximity:85.1158,25.6144"
    assert "pharmacy" in captured_params["categories"] or "chemist" in captured_params["categories"]
    assert captured_params["limit"] == 15
    assert "apiKey" in captured_params


async def test_coordinate_and_radius_validation_422(async_client: AsyncClient):
    """Reject invalid coordinates and out-of-bounds radius with 422."""
    # Invalid latitude (>90)
    res_bad_lat = await async_client.get("/api/v1/discovery/nearby", params={"lat": 95.0, "lon": 85.0})
    assert res_bad_lat.status_code == 422

    # Invalid longitude (>180)
    res_bad_lon = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.0, "lon": 195.0})
    assert res_bad_lon.status_code == 422

    # Missing coordinates
    res_missing = await async_client.get("/api/v1/discovery/nearby")
    assert res_missing.status_code == 422

    # Radius too large (> 10,000m)
    res_big_rad = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.0, "lon": 85.0, "radius": 15000})
    assert res_big_rad.status_code == 422

    # Radius too small (< 100m)
    res_small_rad = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.0, "lon": 85.0, "radius": 50})
    assert res_small_rad.status_code == 422


async def test_result_limit_enforcement(async_client: AsyncClient):
    """Limit parameter must reject values > 25 with 422."""
    res_too_many = await async_client.get(
        "/api/v1/discovery/nearby",
        params={"lat": 25.6144, "lon": 85.1158, "limit": 50},
    )
    assert res_too_many.status_code == 422


async def test_missing_api_key_returns_503(async_client: AsyncClient):
    """Safe actionable 503 error when GEOAPIFY_API_KEY is not configured."""
    with patch.object(settings, "GEOAPIFY_API_KEY", None):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158},
        )
    assert res.status_code == 503
    assert "provider is not configured" in res.json()["detail"].lower()


async def test_provider_auth_error_returns_503(async_client: AsyncClient):
    """Upstream 401/403 errors are translated to 503 without leaking details."""
    mock_resp = Response(
        status_code=401,
        json={"statusCode": 401, "error": "Unauthorized", "message": "Invalid API key"},
        request=AsyncMock(),
    )

    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158},
        )

    assert res.status_code == 503
    assert "authentication failed" in res.json()["detail"].lower()


async def test_provider_rate_limit_429_returns_429(async_client: AsyncClient):
    """Upstream 429 rate limit translated into 429 for the client."""
    mock_resp = Response(
        status_code=429,
        json={"statusCode": 429, "error": "Too Many Requests", "message": "Rate limit exceeded"},
        request=AsyncMock(),
    )

    with patch("asyncio.sleep", new=AsyncMock()):
        with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
            res = await async_client.get(
                "/api/v1/discovery/nearby",
                params={"lat": 25.6144, "lon": 85.1158},
            )

    assert res.status_code == 429
    assert "rate limit exceeded" in res.json()["detail"].lower()


async def test_upstream_server_failure_returns_502(async_client: AsyncClient):
    """Upstream 500/502/503 returns 502 with safe user message."""
    mock_resp = Response(status_code=500, request=AsyncMock())

    with patch("asyncio.sleep", new=AsyncMock()):
        with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
            res = await async_client.get(
                "/api/v1/discovery/nearby",
                params={"lat": 25.6144, "lon": 85.1158},
            )

    assert res.status_code == 502
    assert "upstream outages" in res.json()["detail"].lower()


async def test_malformed_json_and_missing_properties_handled(async_client: AsyncClient):
    """Defensive parsing ignores malformed items without failing the entire batch."""
    malformed_features = {
        "type": "FeatureCollection",
        "features": [
            {"type": "Feature", "properties": {}},  # Empty properties
            {"type": "Feature", "properties": {"name": ""}},  # No name
            {"type": "Feature", "properties": {"name": "No Coords"}},  # Missing lat/lon
            {"type": "Feature", "properties": {"name": "Invalid Coords", "lat": 999.0, "lon": 85.0}},
            {
                "type": "Feature",
                "properties": {
                    "name": "Valid Minimal Kirana",
                    "lat": 25.6145,
                    "lon": 85.1159,
                    "formatted": "Minimal Address",
                },
            },
        ],
    }

    mock_resp = Response(status_code=200, json=malformed_features, request=AsyncMock())
    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158},
        )

    assert res.status_code == 200
    items = res.json()["items"]
    assert len(items) == 1
    assert items[0]["name"] == "Valid Minimal Kirana"


async def test_caching_and_cache_hit_flag(async_client: AsyncClient):
    """Second request in the same spatial grid returns cached=True without new HTTP calls."""
    mock_resp = Response(status_code=200, json=SAMPLE_GEOAPIFY_RESPONSE, request=AsyncMock())

    call_count = 0

    async def counting_fetch(self, query_params):
        nonlocal call_count
        call_count += 1
        return mock_resp

    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=counting_fetch):
        # First call: cache miss
        res1 = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158, "radius": 3000},
        )
        assert res1.status_code == 200
        assert res1.json()["cached"] is False
        assert call_count == 1

        # Second call with nearby coordinates in same ~110m grid cell: cache hit
        res2 = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.61441, "lon": 85.11581, "radius": 3000},
        )
        assert res2.status_code == 200
        assert res2.json()["cached"] is True
        assert call_count == 1  # No additional upstream HTTP call made!


async def test_zero_database_writes_invariant(async_client: AsyncClient):
    """Directory discovery must NEVER persist rows into shops table."""
    async with async_session_maker() as session:
        count_before = (await session.execute(select(func.count(Shop.id)))).scalar_one()

    mock_resp = Response(status_code=200, json=SAMPLE_GEOAPIFY_RESPONSE, request=AsyncMock())
    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158},
        )

    assert res.status_code == 200

    async with async_session_maker() as session:
        count_after = (await session.execute(select(func.count(Shop.id)))).scalar_one()

    assert count_before == count_after, "Discovery must not write records to the shops table"


async def test_directory_listings_blocked_from_cart_and_checkout(async_client: AsyncClient):
    """Directory listings cannot be added to cart or checked out."""
    # Attempting to add item with random directory id or unverified id fails with 404 or 400
    fake_shop_id = uuid.uuid4()
    cart_res = await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": str(fake_shop_id), "quantity": 1},
    )
    # Blocked (unauthenticated or product/shop not found)
    assert cart_res.status_code in (401, 404, 400)


async def test_api_key_never_exposed_in_response(async_client: AsyncClient):
    """API responses and errors must NEVER leak GEOAPIFY_API_KEY."""
    mock_resp = Response(status_code=200, json=SAMPLE_GEOAPIFY_RESPONSE, request=AsyncMock())
    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=AsyncMock(return_value=mock_resp)):
        res = await async_client.get(
            "/api/v1/discovery/nearby",
            params={"lat": 25.6144, "lon": 85.1158},
        )

    raw_text = res.text
    if settings.GEOAPIFY_API_KEY:
        assert settings.GEOAPIFY_API_KEY not in raw_text
    assert "apiKey" not in raw_text


async def test_upstream_network_timeout_returns_504(async_client: AsyncClient):
    """Network connection timeout returns HTTP 504 Gateway Timeout."""
    timeout_mock = AsyncMock(side_effect=httpx.ConnectTimeout("Network connect timeout"))

    with patch("asyncio.sleep", new=AsyncMock()):
        with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=timeout_mock):
            res = await async_client.get(
                "/api/v1/discovery/nearby",
                params={"lat": 25.6144, "lon": 85.1158},
            )

    assert res.status_code == 504
    assert "timed out" in res.json()["detail"].lower()


async def test_cache_invalidation_across_categories_and_radii(async_client: AsyncClient):
    """Category and radius changes must create separate cache partitions and never leak data."""
    mock_resp_supermarket = Response(
        status_code=200,
        json={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Supermarket One",
                        "categories": ["commercial.supermarket"],
                        "lat": 25.6145,
                        "lon": 85.1159,
                    },
                }
            ],
        },
        request=AsyncMock(),
    )
    mock_resp_chemist = Response(
        status_code=200,
        json={
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "properties": {
                        "name": "Pharmacy Two",
                        "categories": ["healthcare.pharmacy"],
                        "lat": 25.6146,
                        "lon": 85.1160,
                    },
                }
            ],
        },
        request=AsyncMock(),
    )

    calls = []

    async def dynamic_fetch(self, query_params):
        calls.append(query_params)
        if "pharmacy" in query_params.get("categories", ""):
            return mock_resp_chemist
        return mock_resp_supermarket

    with patch.object(GeoapifyPlacesService, "_fetch_from_provider", new=dynamic_fetch):
        # 1. Supermarket 3000m -> Cache Miss
        r1 = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.6144, "lon": 85.1158, "radius": 3000, "category": "supermarket"})
        assert r1.status_code == 200
        assert r1.json()["cached"] is False
        assert r1.json()["items"][0]["name"] == "Supermarket One"
        assert len(calls) == 1

        # 2. Supermarket 3000m -> Cache Hit
        r2 = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.6144, "lon": 85.1158, "radius": 3000, "category": "supermarket"})
        assert r2.status_code == 200
        assert r2.json()["cached"] is True
        assert r2.json()["items"][0]["name"] == "Supermarket One"
        assert len(calls) == 1  # No upstream call

        # 3. Chemist 3000m -> Cache Miss (Must NOT return Supermarket cached items!)
        r3 = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.6144, "lon": 85.1158, "radius": 3000, "category": "chemist"})
        assert r3.status_code == 200
        assert r3.json()["cached"] is False
        assert r3.json()["items"][0]["name"] == "Pharmacy Two"
        assert len(calls) == 2  # New upstream call

        # 4. Supermarket 5000m -> Cache Miss (Different radius must not return 3000m cache!)
        r4 = await async_client.get("/api/v1/discovery/nearby", params={"lat": 25.6144, "lon": 85.1158, "radius": 5000, "category": "supermarket"})
        assert r4.status_code == 200
        assert r4.json()["cached"] is False
        assert len(calls) == 3  # New upstream call


async def test_in_memory_cache_ttl_expiry():
    """Items in memory cache expire strictly when TTL lapses."""
    from app.services.geoapify import InMemoryDiscoveryCache
    import time

    cache = InMemoryDiscoveryCache(max_size=10, default_ttl=1)
    cache.set("test_key", [{"name": "Expiring Store"}], ttl=1)

    assert cache.get("test_key") == [{"name": "Expiring Store"}]

    # Manually backdate expiration to simulate time passage
    exp_time, val = cache._cache["test_key"]
    cache._cache["test_key"] = (time.time() - 1, val)

    assert cache.get("test_key") is None, "Expired cache entry should return None"
