"""
Automated Security and Configuration Test Suite for HTTPS Deployment,
Reverse Proxy Handling, and Geolocation Authorization.

Covers:
1. Reverse proxy header processing (X-Forwarded-For, X-Real-IP) and client IP extraction.
2. Proxy configuration settings (FORWARDED_ALLOW_IPS, TRUSTED_PROXIES, HTTPS CORS origins).
3. HTTPS CORS preflight enforcement: authorized HTTPS origins allowed; unauthorized blocked.
4. Rider location update RBAC and coordinate bounds validation (latitude/longitude boundaries).
5. Delivery route authorization isolation: strictly prevents data leakage to unauthorized users (401/403).
6. WebSocket delivery stream RBAC (authorize_delivery_ws): enforces complete resource ownership.
"""

import uuid
import pytest
from httpx import AsyncClient
from unittest.mock import MagicMock
from starlette.datastructures import Headers, Address

from app.core.config import Settings, settings
from app.core.rate_limit import get_client_ip
from app.models.user import User, UserRole
from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order
from app.models.shop import Shop
from app.models.rider import RiderProfile
from app.api.routes.ws_deliveries import authorize_delivery_ws
from app.db.session import engine


# ---------------------------------------------------------------------------
# 1. Reverse Proxy Client IP Extraction & Forwarded Header Tests
# ---------------------------------------------------------------------------

def test_client_ip_extraction_forwarded_for():
    """Verify that get_client_ip properly parses X-Forwarded-For chains from reverse proxies."""
    # Multi-hop proxy chain: client, proxy1, proxy2
    mock_request = MagicMock()
    mock_request.headers = Headers({"x-forwarded-for": "203.0.113.195, 192.168.1.1, 10.0.0.1"})
    mock_request.client = Address("10.0.0.1", 54321)

    ip = get_client_ip(mock_request)
    assert ip == "203.0.113.195"


def test_client_ip_extraction_x_real_ip():
    """Verify fallback to X-Real-IP when X-Forwarded-For is absent."""
    mock_request = MagicMock()
    mock_request.headers = Headers({"x-real-ip": "198.51.100.42"})
    mock_request.client = Address("10.0.0.1", 54321)

    ip = get_client_ip(mock_request)
    assert ip == "198.51.100.42"


def test_client_ip_extraction_direct_connection_fallback():
    """Verify fallback to direct socket client host when no proxy headers exist."""
    mock_request = MagicMock()
    mock_request.headers = Headers({})
    mock_request.client = Address("192.168.1.50", 12345)

    ip = get_client_ip(mock_request)
    assert ip == "192.168.1.50"


def test_client_ip_extraction_handles_empty_values():
    """Verify safe fallback when headers are empty or whitespace."""
    mock_request = MagicMock()
    mock_request.headers = Headers({"x-forwarded-for": "   "})
    mock_request.client = Address("127.0.0.1", 8000)

    ip = get_client_ip(mock_request)
    assert ip == "127.0.0.1"


# ---------------------------------------------------------------------------
# 2. Reverse Proxy & HTTPS Configuration Settings Tests
# ---------------------------------------------------------------------------

def test_forwarded_allow_ips_and_trusted_proxies_defaults():
    """Verify default reverse-proxy settings are properly configured for production deployments."""
    s = Settings()
    assert hasattr(s, "FORWARDED_ALLOW_IPS")
    assert s.FORWARDED_ALLOW_IPS == "*"
    assert hasattr(s, "TRUSTED_PROXIES")
    assert "127.0.0.1" in s.TRUSTED_PROXIES


def test_cors_origins_https_parsing():
    """Verify ALLOWED_ORIGINS correctly splits and normalizes multiple HTTPS origins."""
    s = Settings(
        ALLOWED_ORIGINS="https://dukaanly.com, https://staging.dukaanly.com , https://pilot-patna.dukaanly.com"
    )
    origins = s.cors_origins
    assert len(origins) == 3
    assert "https://dukaanly.com" in origins
    assert "https://staging.dukaanly.com" in origins
    assert "https://pilot-patna.dukaanly.com" in origins


# ---------------------------------------------------------------------------
# 3. CORS Preflight & HTTPS Ingress Security Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cors_preflight_allowed_https_origin(monkeypatch):
    """Verify CORS preflight accepts configured HTTPS origins."""
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://dukaanly.com,https://staging.dukaanly.com")
    from app.main import create_app
    from httpx import ASGITransport
    test_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://dukaanly.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        assert response.status_code == 200
        assert response.headers.get("access-control-allow-origin") == "https://dukaanly.com"
        assert response.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_preflight_rejects_unauthorized_origin(monkeypatch):
    """Verify CORS preflight does not authorize unrecognized origins."""
    monkeypatch.setattr(settings, "ALLOWED_ORIGINS", "https://dukaanly.com")
    from app.main import create_app
    from httpx import ASGITransport
    test_app = create_app()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        response = await client.options(
            "/api/v1/auth/login",
            headers={
                "Origin": "https://malicious-site.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type",
            },
        )
        # When origin is not allowed, Starlette CORSMiddleware returns 400 or omits access-control-allow-origin
        assert response.headers.get("access-control-allow-origin") is None


# ---------------------------------------------------------------------------
# 4. Rider Location Update Authorization & Bounds Validation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_rider_location_update_forbidden_for_customer(async_client: AsyncClient):
    """Verify that a customer cannot update rider location (HTTP 403 Forbidden)."""
    email = f"cust_loc_{uuid.uuid4()}@example.com"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"name": "Customer User", "email": email, "password": "Password123!"},
    )
    assert reg_res.status_code == 201

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    assert login_res.status_code == 200
    token = login_res.json()["access_token"]

    patch_res = await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 25.6144, "longitude": 85.1158},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert patch_res.status_code == 403


@pytest.mark.asyncio
async def test_rider_location_update_out_of_bounds_validation(async_client: AsyncClient):
    """Verify coordinates exceeding Earth boundaries are rejected with 422 Unprocessable Entity."""
    from sqlalchemy import text

    email = f"rider_bounds_{uuid.uuid4()}@example.com"
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"name": "Rider Bounds", "email": email, "password": "Password123!"},
    )
    assert reg_res.status_code == 201

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'rider' WHERE email = :e"), {"e": email})
        await conn.commit()

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login_res.json()["access_token"]

    # Initialize rider profile
    await async_client.post(
        "/api/v1/riders/profile",
        headers={"Authorization": f"Bearer {token}"},
    )

    # Invalid latitude > 90
    res_lat = await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 95.0, "longitude": 85.1158},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_lat.status_code == 422

    # Invalid longitude > 180
    res_lng = await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 25.6144, "longitude": 195.0},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_lng.status_code == 422

    # Valid coordinates within Patna (Boring Road)
    res_valid = await async_client.patch(
        "/api/v1/riders/me/location",
        json={"latitude": 25.6144, "longitude": 85.1158},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert res_valid.status_code == 200
    data = res_valid.json()
    assert abs(data["latitude"] - 25.6144) < 1e-4
    assert abs(data["longitude"] - 85.1158) < 1e-4


# ---------------------------------------------------------------------------
# 5. Delivery Route & Location Authorization Isolation Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_delivery_route_unauthenticated_rejected(async_client: AsyncClient):
    """Verify unauthenticated requests to delivery route receive 401 Unauthorized."""
    fake_id = uuid.uuid4()
    response = await async_client.get(f"/api/v1/deliveries/{fake_id}/route")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_delivery_route_unauthorized_user_forbidden(async_client: AsyncClient):
    """Verify that an unrelated user cannot inspect another user's delivery route (HTTP 403)."""
    from sqlalchemy import text

    # Create Owner, Customer, Unrelated Customer
    owner_email = f"owner_{uuid.uuid4()}@example.com"
    cust1_email = f"cust1_{uuid.uuid4()}@example.com"
    cust2_email = f"cust2_{uuid.uuid4()}@example.com"

    for email in (owner_email, cust1_email, cust2_email):
        await async_client.post(
            "/api/v1/auth/register",
            json={"name": "User", "email": email, "password": "Password123!"},
        )

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()

    owner_token = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "Password123!"})).json()["access_token"]
    cust1_token = (await async_client.post("/api/v1/auth/login", json={"email": cust1_email, "password": "Password123!"})).json()["access_token"]
    cust2_token = (await async_client.post("/api/v1/auth/login", json={"email": cust2_email, "password": "Password123!"})).json()["access_token"]

    # Create Shop, Product, Order, Delivery
    shop_res = await async_client.post(
        "/api/v1/shops",
        json={"name": "Auth Test Shop", "address": "Patna", "location": {"latitude": 25.6144, "longitude": 85.1158}},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    shop_id = shop_res.json()["id"]

    prod_res = await async_client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "Item", "price": 50},
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    prod_id = prod_res.json()["id"]

    await async_client.patch(
        f"/api/v1/products/{prod_id}/inventory",
        json={"stock": 10, "expected_version": 1},
        headers={"Authorization": f"Bearer {owner_token}"},
    )

    # Customer 1 adds to cart and checks out
    await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": prod_id, "quantity": 1},
        headers={"Authorization": f"Bearer {cust1_token}"},
    )

    order_res = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": str(uuid.uuid4())},
        headers={"Authorization": f"Bearer {cust1_token}"},
    )
    order_id = order_res.json()["id"]

    # Confirm order and create delivery
    async with engine.connect() as conn:
        await conn.execute(text("UPDATE orders SET status = 'confirmed' WHERE id = :oid"), {"oid": order_id})
        await conn.commit()

    deliv_res = await async_client.post(
        "/api/v1/deliveries",
        json={
            "order_id": order_id,
            "destination_latitude": 25.5947,
            "destination_longitude": 85.1588,
        },
        headers={"Authorization": f"Bearer {owner_token}"},
    )
    assert deliv_res.status_code == 201
    delivery_id = deliv_res.json()["id"]

    # Unrelated Customer 2 attempts to view delivery route -> MUST be 403 Forbidden
    unauthorized_res = await async_client.get(
        f"/api/v1/deliveries/{delivery_id}/route",
        headers={"Authorization": f"Bearer {cust2_token}"},
    )
    assert unauthorized_res.status_code == 403
    assert "Not authorized" in unauthorized_res.json()["detail"]


# ---------------------------------------------------------------------------
# 6. WebSocket Authorization (authorize_delivery_ws) Unit Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_authorize_delivery_ws_unit():
    """Unit test authorize_delivery_ws for all roles and ownership invariants."""
    owner_id = uuid.uuid4()
    cust_id = uuid.uuid4()
    other_cust_id = uuid.uuid4()
    rider_user_id = uuid.uuid4()
    other_rider_user_id = uuid.uuid4()

    mock_shop = MagicMock(spec=Shop)
    mock_shop.owner_id = owner_id

    mock_order = MagicMock(spec=Order)
    mock_order.customer_id = cust_id
    mock_order.shop = mock_shop

    mock_rider_profile = MagicMock(spec=RiderProfile)
    mock_rider_profile.user_id = rider_user_id

    mock_delivery = MagicMock(spec=Delivery)
    mock_delivery.order = mock_order
    mock_delivery.rider = mock_rider_profile

    # 1. Owning Customer -> Authorized
    user_cust = MagicMock(spec=User)
    user_cust.id = cust_id
    user_cust.role = UserRole.customer
    assert await authorize_delivery_ws(user_cust, mock_delivery) is True

    # 2. Unrelated Customer -> Denied
    user_other_cust = MagicMock(spec=User)
    user_other_cust.id = other_cust_id
    user_other_cust.role = UserRole.customer
    assert await authorize_delivery_ws(user_other_cust, mock_delivery) is False

    # 3. Assigned Rider -> Authorized
    user_rider = MagicMock(spec=User)
    user_rider.id = rider_user_id
    user_rider.role = UserRole.rider
    assert await authorize_delivery_ws(user_rider, mock_delivery) is True

    # 4. Other Rider -> Denied
    user_other_rider = MagicMock(spec=User)
    user_other_rider.id = other_rider_user_id
    user_other_rider.role = UserRole.rider
    assert await authorize_delivery_ws(user_other_rider, mock_delivery) is False

    # 5. Shop Owner of the store -> Authorized
    user_owner = MagicMock(spec=User)
    user_owner.id = owner_id
    user_owner.role = UserRole.shop_owner
    assert await authorize_delivery_ws(user_owner, mock_delivery) is True

    # 6. Admin -> Authorized
    user_admin = MagicMock(spec=User)
    user_admin.id = uuid.uuid4()
    user_admin.role = UserRole.admin
    assert await authorize_delivery_ws(user_admin, mock_delivery) is True
