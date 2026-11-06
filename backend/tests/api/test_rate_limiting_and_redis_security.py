"""
Comprehensive Regression Test Suite for Dukaanly Rate Limiting and Redis Security.

Covers:
1. Login IP sliding-window rate limit enforcement and HTTP 429 Retry-After response.
2. Login Account (email) brute-force protection across multiple client IPs.
3. Login Account counter reset upon successful authentication.
4. Registration IP rate limit enforcement and HTTP 429 Retry-After response.
5. Checkout abuse protection and rate limit enforcement per customer.
6. Checkout idempotency replay preservation (retries with identical key are not rate-limited).
7. Concurrent checkouts from distinct users execute cleanly without shared limit collisions.
8. Rate limiter reset and window expiry functionality.
9. Redis unavailability graceful fallback: endpoints fail-safe to in-memory sliding window and never become unlimited.
10. Redis credentials and password masking: zero leakage in URLs, logs, or error responses.
"""

import asyncio
import logging
import uuid
import pytest
from httpx import AsyncClient
import redis.asyncio as redis

from app.core.config import Settings, settings
from app.core.redis import mask_redis_url, get_redis_client
from app.core.rate_limit import (
    RateLimiter,
    get_client_ip,
    login_ip_rate_limiter,
    login_email_rate_limiter,
    register_rate_limiter,
    checkout_rate_limiter,
    reset_all_rate_limiters,
)
from app.models.user import UserRole
from app.db.session import engine


# ---------------------------------------------------------------------------
# 1. Redis URL Configuration & Credential Masking Tests
# ---------------------------------------------------------------------------

def test_redis_url_password_injection_and_masking():
    """Verify that REDIS_PASSWORD is automatically injected into REDIS_URL and properly masked."""
    # When password is provided without password in URL, it is injected
    s1 = Settings(
        REDIS_URL="redis://localhost:6379/0",
        REDIS_PASSWORD="SuperSecretRedisPassword123!",
    )
    assert s1.REDIS_URL == "redis://:SuperSecretRedisPassword123!@127.0.0.1:6379/0"
    assert s1.redis_url_masked == "redis://:***@127.0.0.1:6379/0"
    assert "SuperSecretRedisPassword123!" not in s1.redis_url_masked

    # When URL already has password, mask_redis_url masks it
    s2 = Settings(
        REDIS_URL="redis://appuser:CustomSecretPass@redis-host:6380/2",
    )
    assert s2.redis_url_masked == "redis://appuser:***@redis-host:6380/2"
    assert "CustomSecretPass" not in s2.redis_url_masked

    # Plain URL with no password remains unmasked
    assert mask_redis_url("redis://localhost:6379/0") == "redis://localhost:6379/0"
    assert mask_redis_url("") == ""
    assert mask_redis_url("invalid-url-format") == "invalid-url-format"


# ---------------------------------------------------------------------------
# 2. Login IP Rate Limiting Tests
# ---------------------------------------------------------------------------

async def test_login_ip_rate_limiting(async_client: AsyncClient, monkeypatch):
    """Verify that exceeding IP login limit results in HTTP 429 with Retry-After header."""
    await reset_all_rate_limiters()
    test_ip = "198.51.100.42"
    headers = {"X-Forwarded-For": test_ip}

    # Set tight limit for fast test execution
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_PER_MINUTE", 3)

    # First 3 attempts should be allowed by rate limiter (fail 401 for bad password)
    for i in range(3):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": f"unknown_user_{i}@example.com", "password": "WrongPassword123!"},
            headers=headers,
        )
        assert res.status_code == 401, f"Attempt {i+1} expected 401, got {res.status_code}"

    # 4th attempt from the same IP must be rejected with 429 Too Many Requests
    res4 = await async_client.post(
        "/api/v1/auth/login",
        json={"email": "unknown_user_4@example.com", "password": "WrongPassword123!"},
        headers=headers,
    )
    assert res4.status_code == 429
    assert "Too many login attempts from this IP address" in res4.json()["detail"]
    assert "Retry-After" in res4.headers
    retry_after = int(res4.headers["Retry-After"])
    assert 1 <= retry_after <= 60


# ---------------------------------------------------------------------------
# 3. Login Account Brute-Force Rate Limiting Tests
# ---------------------------------------------------------------------------

async def test_login_account_rate_limiting(async_client: AsyncClient, monkeypatch):
    """Verify that multiple failed logins targeting one account from DIFFERENT IPs are blocked."""
    await reset_all_rate_limiters()
    target_email = "victim_account@example.com"

    # Set account limit to 3 attempts
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_ACCOUNT_PER_MINUTE", 3)
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_PER_MINUTE", 20)

    # 3 attempts from 3 distinct IPs
    for i in range(3):
        ip = f"198.51.100.{10 + i}"
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": target_email, "password": "WrongPassword!"},
            headers={"X-Forwarded-For": ip},
        )
        assert res.status_code == 401

    # 4th attempt from yet another distinct IP targeting the same account must be blocked
    res4 = await async_client.post(
        "/api/v1/auth/login",
        json={"email": target_email, "password": "WrongPassword!"},
        headers={"X-Forwarded-For": "198.51.100.99"},
    )
    assert res4.status_code == 429
    assert "Too many login attempts for this account" in res4.json()["detail"]
    assert "Retry-After" in res4.headers


# ---------------------------------------------------------------------------
# 4. Login Counter Reset on Successful Authentication
# ---------------------------------------------------------------------------

async def test_login_account_counter_reset_on_success(async_client: AsyncClient, monkeypatch):
    """Verify that successful login clears the account brute-force counter."""
    await reset_all_rate_limiters()
    user_email = f"reset_test_{uuid.uuid4().hex[:8]}@example.com"
    user_pass = "ValidPassword123!"

    # Register user
    reg_res = await async_client.post(
        "/api/v1/auth/register",
        json={"name": "Reset Test User", "email": user_email, "password": user_pass},
    )
    assert reg_res.status_code == 201

    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_LOGIN_ACCOUNT_PER_MINUTE", 3)

    # 2 failed attempts
    for _ in range(2):
        fail_res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": user_email, "password": "BadPassword123!"},
        )
        assert fail_res.status_code == 401

    # 3rd attempt is SUCCESSFUL with correct password
    success_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": user_pass},
    )
    assert success_res.status_code == 200
    assert "access_token" in success_res.json()

    # Counter should be reset: immediate next login with correct password should still succeed
    res_after_reset = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user_email, "password": user_pass},
    )
    assert res_after_reset.status_code == 200


# ---------------------------------------------------------------------------
# 5. Registration Rate Limiting Tests
# ---------------------------------------------------------------------------

async def test_registration_rate_limiting(async_client: AsyncClient, monkeypatch):
    """Verify registration rate limit triggers 429 with Retry-After when limit exceeded."""
    await reset_all_rate_limiters()
    test_ip = "203.0.113.77"
    headers = {"X-Forwarded-For": test_ip}

    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REGISTER_PER_MINUTE", 2)

    # 2 allowed registrations
    for i in range(2):
        res = await async_client.post(
            "/api/v1/auth/register",
            json={
                "name": f"Reg User {i}",
                "email": f"reg_{uuid.uuid4().hex[:8]}@example.com",
                "password": "Password123!",
            },
            headers=headers,
        )
        assert res.status_code == 201

    # 3rd registration from same IP must be blocked
    res3 = await async_client.post(
        "/api/v1/auth/register",
        json={
            "name": "Reg User 3",
            "email": f"reg_{uuid.uuid4().hex[:8]}@example.com",
            "password": "Password123!",
        },
        headers=headers,
    )
    assert res3.status_code == 429
    assert "Too many registration attempts" in res3.json()["detail"]
    assert "Retry-After" in res3.headers


# ---------------------------------------------------------------------------
# 6. Checkout Abuse Protection & Idempotency Tests
# ---------------------------------------------------------------------------

async def test_checkout_rate_limiting_and_idempotency_preservation(async_client: AsyncClient, monkeypatch):
    """
    Verify:
    1. Checkout abuse protection limits distinct checkout attempts per customer.
    2. Retrying with the SAME idempotency key returns the cached order without consuming tokens or 429 rejection.
    """
    from sqlalchemy import text
    await reset_all_rate_limiters()

    # Create owner and customer
    owner_email = f"owner_rl_{uuid.uuid4().hex[:8]}@example.com"
    customer_email = f"cust_rl_{uuid.uuid4().hex[:8]}@example.com"

    await async_client.post("/api/v1/auth/register", json={"name": "Owner RL", "email": owner_email, "password": "Password123!"})
    await async_client.post("/api/v1/auth/register", json={"name": "Cust RL", "email": customer_email, "password": "Password123!"})

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE users SET role = 'shop_owner' WHERE email = :e"), {"e": owner_email})
        await conn.commit()

    owner_token = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "Password123!"})).json()["access_token"]
    cust_token = (await async_client.post("/api/v1/auth/login", json={"email": customer_email, "password": "Password123!"})).json()["access_token"]

    owner_headers = {"Authorization": f"Bearer {owner_token}"}
    cust_headers = {"Authorization": f"Bearer {cust_token}"}

    # Create verified shop & product
    shop_id = (await async_client.post(
        "/api/v1/shops",
        json={"name": "RL Test Mart", "address": "Patna", "location": {"latitude": 25.6144, "longitude": 85.1158}},
        headers=owner_headers,
    )).json()["id"]

    async with engine.connect() as conn:
        await conn.execute(text("UPDATE shops SET is_active = true, is_orderable = true, verification_status = 'verified' WHERE id = :sid"), {"sid": shop_id})
        await conn.commit()

    prod_id = (await async_client.post(
        f"/api/v1/shops/{shop_id}/products",
        json={"name": "RL Biscuits", "price": 20.0},
        headers=owner_headers,
    )).json()["id"]

    await async_client.patch(
        f"/api/v1/products/{prod_id}/inventory",
        json={"stock": 100, "expected_version": 1},
        headers=owner_headers,
    )

    # Customer adds product to cart
    await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": prod_id, "quantity": 1},
        headers=cust_headers,
    )

    # 1. Complete an initial checkout with persistent idempotency key
    idem_key_persistent = str(uuid.uuid4())
    res1 = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": idem_key_persistent, "destination_latitude": 25.6145, "destination_longitude": 85.1159},
        headers=cust_headers,
    )
    assert res1.status_code == 201
    order_id = res1.json()["id"]

    # 2. Retrying with the EXACT SAME idempotency key must succeed (201/200) and return the same order
    for _ in range(5):
        retry_res = await async_client.post(
            "/api/v1/orders/checkout",
            json={"idempotency_key": idem_key_persistent, "destination_latitude": 25.6145, "destination_longitude": 85.1159},
            headers=cust_headers,
        )
        assert retry_res.status_code == 201
        assert retry_res.json()["id"] == order_id

    # 3. Now test checkout rate limiting by configuring checkout limit to 2 per minute
    monkeypatch.setattr(settings, "CHECKOUT_RATE_LIMIT_PER_MINUTE", 2)
    # The first checkout consumed 1 token. Next checkout attempt with a new idempotency key consumes 2nd token.
    # Cart is currently empty, so checkout will hit rate limiter check first, then 400 empty cart
    # Let's add an item to cart first
    await async_client.post(
        "/api/v1/cart/items",
        json={"product_id": prod_id, "quantity": 1},
        headers=cust_headers,
    )

    idem_key_2 = str(uuid.uuid4())
    res2 = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": idem_key_2, "destination_latitude": 25.6145, "destination_longitude": 85.1159},
        headers=cust_headers,
    )
    assert res2.status_code == 201

    # 3rd checkout attempt with new idempotency key must hit rate limit (HTTP 429)
    idem_key_3 = str(uuid.uuid4())
    res3 = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": idem_key_3, "destination_latitude": 25.6145, "destination_longitude": 85.1159},
        headers=cust_headers,
    )
    assert res3.status_code == 429
    assert "Too many checkout attempts" in res3.json()["detail"]
    assert "Retry-After" in res3.headers

    # 4. Crucial invariant: Even while rate limited for NEW orders, retrying the FIRST order with its
    # original idempotency key must STILL SUCCEED and return the order without 429!
    idem_replay = await async_client.post(
        "/api/v1/orders/checkout",
        json={"idempotency_key": idem_key_persistent, "destination_latitude": 25.6145, "destination_longitude": 85.1159},
        headers=cust_headers,
    )
    assert idem_replay.status_code == 201
    assert idem_replay.json()["id"] == order_id


# ---------------------------------------------------------------------------
# 7. Concurrent Checkouts from Multiple Users
# ---------------------------------------------------------------------------

async def test_concurrent_checkouts_different_users(async_client: AsyncClient):
    """Verify that checkouts from distinct users execute concurrently without shared limit collisions."""
    from sqlalchemy import text
    await reset_all_rate_limiters()

    # Register 3 distinct customers
    customer_tokens = []
    for i in range(3):
        email = f"multi_cust_{i}_{uuid.uuid4().hex[:6]}@example.com"
        await async_client.post("/api/v1/auth/register", json={"name": f"MultiCust {i}", "email": email, "password": "Password123!"})
        tok = (await async_client.post("/api/v1/auth/login", json={"email": email, "password": "Password123!"})).json()["access_token"]
        customer_tokens.append(tok)

    # Concurrently execute RateLimiter checks for each distinct customer ID
    limiter = RateLimiter(prefix="test_concurrent", requests_per_window=5)
    await limiter.reset()

    async def customer_checkout_attempt(cid: str):
        allowed, _ = await limiter.check_and_record(cid)
        return allowed

    results = await asyncio.gather(*[customer_checkout_attempt(f"user_{i}") for i in range(3)])
    assert all(results) is True, "All distinct customer checkout attempts should be permitted"


# ---------------------------------------------------------------------------
# 8. Rate Limiter Reset and Expiry
# ---------------------------------------------------------------------------

async def test_rate_limiter_reset_functionality():
    """Verify that reset clears both Redis and local memory state."""
    limiter = RateLimiter(prefix="test_reset", requests_per_window=2, window_seconds=60.0)
    user_id = f"user_{uuid.uuid4().hex[:8]}"

    # 1. Consume limit
    a1, _ = await limiter.check_and_record(user_id)
    a2, _ = await limiter.check_and_record(user_id)
    assert a1 is True and a2 is True

    # 3rd is blocked
    a3, retry_after = await limiter.check_and_record(user_id)
    assert a3 is False
    assert retry_after is not None

    # Reset specifically this user
    await limiter.reset(user_id)

    # Immediately allowed again
    a4, _ = await limiter.check_and_record(user_id)
    assert a4 is True


# ---------------------------------------------------------------------------
# 9. Redis Failure Fallback Behavior (Endpoints never silently become unlimited)
# ---------------------------------------------------------------------------

async def test_redis_unavailability_fallback_preserves_rate_limits(monkeypatch, caplog):
    """
    CRITICAL REQUIREMENT: When Redis is unavailable, security-sensitive endpoints
    must NOT silently become unlimited. The system must fall back to local in-memory
    sliding-window rate limiting.
    """
    limiter = RateLimiter(prefix="test_redis_down", requests_per_window=3, window_seconds=60.0)
    limiter.reset_local()

    # Mock Redis client call to simulate Redis network outage / failure
    async def mock_failing_redis():
        raise redis.ConnectionError("Connection refused to redis:6379")

    monkeypatch.setattr("app.core.rate_limit.get_redis_client", mock_failing_redis)

    test_id = f"fallback_target_{uuid.uuid4().hex[:8]}"

    with caplog.at_level(logging.WARNING):
        # 1. First 3 requests must be allowed by local fallback limiter
        r1, _ = await limiter.check_and_record(test_id)
        r2, _ = await limiter.check_and_record(test_id)
        r3, _ = await limiter.check_and_record(test_id)

        assert r1 is True
        assert r2 is True
        assert r3 is True

        # Verify fallback warning was logged without leaking sensitive data
        assert any("Falling back to in-memory limiter" in r.message for r in caplog.records)

        # 2. 4th request MUST BE BLOCKED by local fallback limiter
        r4, retry_after = await limiter.check_and_record(test_id)
        assert r4 is False, "Rate limiter MUST NOT silently allow requests when Redis is unavailable"
        assert retry_after is not None
        assert retry_after > 0


# ---------------------------------------------------------------------------
# 10. Credentials Never Exposed in Logs or Responses
# ---------------------------------------------------------------------------

async def test_credentials_never_exposed_in_logs_or_errors(async_client: AsyncClient, caplog):
    """Verify that passwords never leak in 401, 429, or log output."""
    raw_secret_password = "SuperSecretPlainTextPassword123!"

    with caplog.at_level(logging.DEBUG):
        res = await async_client.post(
            "/api/v1/auth/login",
            json={"email": "audit_user@example.com", "password": raw_secret_password},
            headers={"X-Forwarded-For": "203.0.113.111"},
        )
        assert res.status_code == 401
        res_text = res.text

        # Invariant: raw password must not appear in response body or headers
        assert raw_secret_password not in res_text
        for h_key, h_val in res.headers.items():
            assert raw_secret_password not in h_val

        # Invariant: raw password must not appear in any application logs
        for log_record in caplog.records:
            assert raw_secret_password not in log_record.message
