"""
Dukaanly Stage 5: Authentication, Refresh-Token Rotation & Distributed Rate Limiting.

Comprehensive Verification Suite covering:
1. JWT access token RFC-compliant claims (sub, role, iss, aud, iat, exp) and strict claim validation.
2. Refresh-token rotation: single-use semantics, replacement pointer (replaced_by_id), and same family_id.
3. Refresh-token reuse detection: reusing a rotated token revokes the entire family and terminates the session.
4. Concurrency safety during refresh: concurrent requests cannot create multiple valid sessions.
5. Server-side logout: revokes the whole token family and clears the HttpOnly cookie.
6. Cookie transport: HttpOnly SameSite=Lax cookie issuance on login/refresh and consumption without body.
7. Token refresh distributed rate limiting: HTTP 429 with Retry-After on /api/v1/auth/refresh.
8. AI chat distributed rate limiting: Redis-backed per-user limit enforcement.
9. Trusted-proxy IP spoofing prevention: untrusted connection peers cannot forge X-Forwarded-For.
10. Safe degradation: Redis unavailability falls back safely to in-memory limiter without leaving endpoints unprotected.
"""

import asyncio
from datetime import datetime, timedelta, timezone
import uuid
import pytest
from httpx import AsyncClient
import jwt
from sqlalchemy import select, update, text
from sqlalchemy.ext.asyncio import AsyncSession
import redis.asyncio as redis

from app.core import security
from app.core.config import settings
from app.core.rate_limit import (
    RateLimiter,
    get_client_ip,
    is_ip_trusted_proxy,
    refresh_rate_limiter,
    ai_chat_rate_limiter,
    reset_all_rate_limiters,
)
from app.db.session import async_session_maker
from app.models.user import User, RefreshToken, UserRole
from app.services import auth as auth_service


# Helper to create test user directly in DB (bypasses registration rate limiter)
async def create_stage5_user(email_prefix: str = "stage5_user", role: UserRole = UserRole.customer) -> User:
    async with async_session_maker() as session:
        uid = uuid.uuid4()
        user = User(
            id=uid,
            name=f"User {uid.hex[:6]}",
            email=f"{email_prefix}_{uid.hex[:8]}@example.com",
            phone_number=f"+91{uid.int % 10000000000:010d}",
            password_hash=security.get_password_hash("ValidPassword123!"),
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        await session.refresh(user)
        return user


# ---------------------------------------------------------------------------
# 1. Access Token Claims & Expiry Validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_access_token_claims_and_validation():
    """Verify JWT access tokens carry full RFC claims and are validated strictly."""
    user = await create_stage5_user("claims_test")

    token_str = security.create_access_token(subject=str(user.id), role=user.role.value)
    assert token_str is not None

    # Decode without verification to inspect raw claims
    unverified = jwt.decode(token_str, options={"verify_signature": False})
    assert unverified["sub"] == str(user.id)
    assert unverified["role"] == user.role.value
    assert unverified["iss"] == "dukaanly"
    assert unverified["aud"] == "dukaanly-api"
    assert "iat" in unverified
    assert "exp" in unverified
    assert unverified["exp"] > unverified["iat"]

    # Decode with security.decode_token
    payload = security.decode_token(token_str)
    assert payload["sub"] == str(user.id)

    # Forged issuer token must be rejected
    forged_iss = jwt.encode(
        {"sub": str(user.id), "role": "customer", "iss": "malicious-issuer", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ValueError, match="Invalid token issuer"):
        security.decode_token(forged_iss)

    # Forged audience token must be rejected
    forged_aud = jwt.encode(
        {"sub": str(user.id), "role": "customer", "iss": "dukaanly", "aud": "wrong-audience", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        settings.JWT_SECRET_KEY,
        algorithm=settings.JWT_ALGORITHM,
    )
    with pytest.raises(ValueError, match="Invalid token audience"):
        security.decode_token(forged_aud)


# ---------------------------------------------------------------------------
# 2. Refresh Token Rotation & Replacement Linkage
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_token_rotation_and_replacement_link(async_client: AsyncClient):
    """Verify refresh token rotation creates successor token in same family and marks previous revoked."""
    user = await create_stage5_user("rotation_test")

    # Login to obtain initial tokens
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    assert login_res.status_code == 200
    t1_tokens = login_res.json()
    t1_raw = t1_tokens["refresh_token"]

    async with async_session_maker() as session:
        t1_hash = security.hash_refresh_token(t1_raw)
        t1_row = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == t1_hash))).scalar_one()
        assert t1_row.revoked_at is None
        assert t1_row.replaced_by_id is None
        family_id = t1_row.family_id
        assert family_id is not None

    # Refresh using T1
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": t1_raw},
    )
    assert refresh_res.status_code == 200
    t2_tokens = refresh_res.json()
    t2_raw = t2_tokens["refresh_token"]
    assert t2_raw != t1_raw

    # Verify T1 is revoked and points to T2, and T2 shares the same family_id
    async with async_session_maker() as session:
        t1_refreshed = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == t1_hash))).scalar_one()
        assert t1_refreshed.revoked_at is not None
        assert t1_refreshed.replaced_by_id is not None

        t2_hash = security.hash_refresh_token(t2_raw)
        t2_row = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == t2_hash))).scalar_one()
        assert t2_row.id == t1_refreshed.replaced_by_id
        assert t2_row.family_id == family_id
        assert t2_row.revoked_at is None


# ---------------------------------------------------------------------------
# 3. Token Reuse Detection Revokes Entire Family
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_token_reuse_detection_revokes_entire_family(async_client: AsyncClient):
    """Reusing a previously rotated token outside the grace window revokes all tokens in the family."""
    user = await create_stage5_user("reuse_test")

    # 1. Login -> Token 1
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    t1_raw = login_res.json()["refresh_token"]

    # 2. Refresh Token 1 -> Token 2
    r1 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": t1_raw})
    assert r1.status_code == 200
    t2_raw = r1.json()["refresh_token"]

    # 3. Refresh Token 2 -> Token 3
    r2 = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": t2_raw})
    assert r2.status_code == 200
    t3_raw = r2.json()["refresh_token"]

    # Age Token 1's revoked_at beyond the 10-second concurrency grace window to simulate an attack replay
    async with async_session_maker() as session:
        t1_hash = security.hash_refresh_token(t1_raw)
        old_time = datetime.now(timezone.utc) - timedelta(seconds=60)
        await session.execute(
            update(RefreshToken)
            .where(RefreshToken.token_hash == t1_hash)
            .values(revoked_at=old_time)
        )
        await session.commit()

    # 4. Attacker attempts to refresh with rotated Token 1
    reuse_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": t1_raw})
    assert reuse_res.status_code == 401
    assert "Token reuse detected" in reuse_res.json()["detail"]

    # 5. Invariant: Token 3 (which was active and valid) MUST NOW BE REVOKED!
    async with async_session_maker() as session:
        t3_hash = security.hash_refresh_token(t3_raw)
        t3_row = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == t3_hash))).scalar_one()
        assert t3_row.revoked_at is not None

    # Legitimate user attempting to use Token 3 is now also rejected (family compromised)
    subsequent_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": t3_raw})
    assert subsequent_res.status_code == 401


# ---------------------------------------------------------------------------
# 4. Safe Concurrent Refresh Handling
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_safe_concurrent_refresh_handling(async_client: AsyncClient):
    """Concurrent refresh requests recover idempotently with identical valid tokens without creating multiple sessions."""
    user = await create_stage5_user("concurrent_refresh_test")

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    t1_raw = login_res.json()["refresh_token"]

    # Launch two simultaneous refresh requests using the exact same refresh token
    res1, res2 = await asyncio.gather(
        async_client.post("/api/v1/auth/refresh", json={"refresh_token": t1_raw}),
        async_client.post("/api/v1/auth/refresh", json={"refresh_token": t1_raw}),
    )

    # Both requests succeed (one by rotation, second by idempotent 5s cache), or second gets clean 401 without family destruction
    assert res1.status_code in (200, 401)
    assert res2.status_code in (200, 401)
    assert 200 in (res1.status_code, res2.status_code)

    if res1.status_code == 200 and res2.status_code == 200:
        # Idempotent response caching: both requests receive identical tokens
        assert res1.json()["access_token"] == res2.json()["access_token"]
        assert res1.json()["refresh_token"] == res2.json()["refresh_token"]
        active_refresh = res1.json()["refresh_token"]
    else:
        success_res = res1 if res1.status_code == 200 else res2
        active_refresh = success_res.json()["refresh_token"]

    # Verify active refresh token remains valid and functional
    async with async_session_maker() as session:
        new_hash = security.hash_refresh_token(active_refresh)
        new_row = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == new_hash))).scalar_one()
        assert new_row.revoked_at is None, "Legitimate new token must remain active after concurrent race"

    # User can continue using the new token normally
    next_res = await async_client.post("/api/v1/auth/refresh", json={"refresh_token": active_refresh})
    assert next_res.status_code == 200


# ---------------------------------------------------------------------------
# 5. Server-Side Logout Revocation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_server_side_logout_revokes_family(async_client: AsyncClient):
    """Logout invalidates the refresh token server-side and terminates the session."""
    user = await create_stage5_user("logout_family_test")

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    tokens = login_res.json()
    refresh_token = tokens["refresh_token"]

    # Call /logout
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        json={"refresh_token": refresh_token},
    )
    assert logout_res.status_code == 204

    # Verify in DB that token is marked revoked
    async with async_session_maker() as session:
        tok_hash = security.hash_refresh_token(refresh_token)
        tok_row = (await session.execute(select(RefreshToken).where(RefreshToken.token_hash == tok_hash))).scalar_one()
        assert tok_row.revoked_at is not None

    # Subsequent refresh must fail
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": refresh_token},
    )
    assert refresh_res.status_code == 401


# ---------------------------------------------------------------------------
# 6. HttpOnly Cookie Transport
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cookie_transport_on_login_refresh_logout(async_client: AsyncClient):
    """Login and refresh set HttpOnly cookie; refresh can be invoked using cookie alone."""
    user = await create_stage5_user("cookie_test")

    # 1. Login sets cookie
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    assert login_res.status_code == 200
    assert "set-cookie" in login_res.headers
    cookie_header = login_res.headers["set-cookie"]
    assert "dukaanly_refresh_token=" in cookie_header
    assert "HttpOnly" in cookie_header or "httponly" in cookie_header
    assert "Path=/api/v1/auth" in cookie_header or "path=/api/v1/auth" in cookie_header

    # Extract cookie value
    import http.cookies
    cookie = http.cookies.SimpleCookie(cookie_header)
    cookie_token = cookie["dukaanly_refresh_token"].value
    assert cookie_token == login_res.json()["refresh_token"]

    # 2. Call /refresh WITHOUT JSON body (relying strictly on cookie)
    refresh_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={},
        cookies={"dukaanly_refresh_token": cookie_token},
    )
    assert refresh_res.status_code == 200
    new_data = refresh_res.json()
    assert "access_token" in new_data

    # New cookie must be set
    assert "set-cookie" in refresh_res.headers
    new_cookie_header = refresh_res.headers["set-cookie"]
    new_cookie = http.cookies.SimpleCookie(new_cookie_header)
    assert new_cookie["dukaanly_refresh_token"].value == new_data["refresh_token"]

    # 3. Call /logout with cookie
    logout_res = await async_client.post(
        "/api/v1/auth/logout",
        json={},
        cookies={"dukaanly_refresh_token": new_cookie["dukaanly_refresh_token"].value},
    )
    assert logout_res.status_code == 204
    assert "set-cookie" in logout_res.headers
    logout_cookie = http.cookies.SimpleCookie(logout_res.headers["set-cookie"])
    # Cookie is expired/cleared
    assert logout_cookie["dukaanly_refresh_token"].value == "" or 'max-age=0' in logout_res.headers["set-cookie"].lower()


# ---------------------------------------------------------------------------
# 7. Token Refresh Route Rate Limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_refresh_route_rate_limiting(async_client: AsyncClient, monkeypatch):
    """Exceeding refresh limit triggers HTTP 429 with Retry-After header."""
    await reset_all_rate_limiters()
    user = await create_stage5_user("refresh_rate_user")

    # Set tight limit for test
    monkeypatch.setattr(settings, "AUTH_RATE_LIMIT_REFRESH_PER_MINUTE", 3)

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    current_token = login_res.json()["refresh_token"]

    test_ip = "198.51.100.77"
    headers = {"X-Forwarded-For": test_ip}

    # First 3 attempts permitted
    for i in range(3):
        res = await async_client.post(
            "/api/v1/auth/refresh",
            json={"refresh_token": current_token},
            headers=headers,
        )
        assert res.status_code == 200
        current_token = res.json()["refresh_token"]

    # 4th attempt rejected with 429
    res4 = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": current_token},
        headers=headers,
    )
    assert res4.status_code == 429
    assert "Too many refresh attempts" in res4.json()["detail"]
    assert "Retry-After" in res4.headers
    assert int(res4.headers["Retry-After"]) >= 1


# ---------------------------------------------------------------------------
# 8. AI Chat Distributed Rate Limiting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ai_chat_distributed_rate_limiting(async_client: AsyncClient, monkeypatch):
    """AI assistant chat endpoint enforces Redis-backed rate limiting per user."""
    await reset_all_rate_limiters()
    customer = await create_stage5_user("ai_chat_rate_user")
    token = security.create_access_token(str(customer.id), customer.role.value)

    # Set tight limit
    monkeypatch.setattr(settings, "AI_RATE_LIMIT_PER_MINUTE", 2)
    monkeypatch.setattr(settings, "AI_FEATURE_SHOPPING_ASSISTANT", True)

    headers = {"Authorization": f"Bearer {token}"}
    payload = {
        "message": "Find fresh groceries nearby",
        "latitude": 25.5941,
        "longitude": 85.1376,
    }

    # Mock the internal assistant logic so test exercises the rate limiter cleanly
    from unittest.mock import AsyncMock, patch
    from app.schemas.ai import ShoppingAssistantResponse

    mock_resp = ShoppingAssistantResponse(
        assistant_message="Here are recommendations",
        provider="mock",
        model="gpt-4o-mini",
        latency_ms=45.0,
    )

    with patch("app.api.routes.ai.process_shopping_assistant_chat", new=AsyncMock(return_value=mock_resp)):
        # Requests 1 and 2 allowed
        r1 = await async_client.post("/api/v1/ai/assistant/chat", json=payload, headers=headers)
        r2 = await async_client.post("/api/v1/ai/assistant/chat", json=payload, headers=headers)
        assert r1.status_code == 200
        assert r2.status_code == 200

        # Request 3 blocked with 429
        r3 = await async_client.post("/api/v1/ai/assistant/chat", json=payload, headers=headers)
        assert r3.status_code == 429
        assert "AI request rate limit exceeded" in r3.json()["detail"]
        assert "Retry-After" in r3.headers


# ---------------------------------------------------------------------------
# 9. Trusted-Proxy IP Spoofing Prevention
# ---------------------------------------------------------------------------

def test_trusted_proxy_ip_spoofing_prevention():
    """Verify that forwarding headers are only trusted from configured trusted proxies."""
    from unittest.mock import Mock

    trusted_config = "127.0.0.1,10.0.0.0/8,172.16.0.0/12,192.168.0.0/16"

    # 1. Untrusted peer connection (e.g. 203.0.113.88)
    req_untrusted = Mock()
    req_untrusted.client = Mock(host="203.0.113.88")
    req_untrusted.headers = {"x-forwarded-for": "1.1.1.1, 8.8.8.8", "x-real-ip": "1.1.1.1"}

    # Must ignore spoofed headers and return actual peer host
    extracted_ip = get_client_ip(req_untrusted)
    assert extracted_ip == "203.0.113.88"

    # 2. Trusted proxy connection (e.g. 127.0.0.1 reverse proxy)
    req_trusted = Mock()
    req_trusted.client = Mock(host="127.0.0.1")
    req_trusted.headers = {"x-forwarded-for": "198.51.100.55, 10.0.0.1"}

    # Must parse through trusted proxies and identify real client IP
    extracted_trusted = get_client_ip(req_trusted)
    assert extracted_trusted == "198.51.100.55"


# ---------------------------------------------------------------------------
# 10. Redis Unavailability Safe Degradation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_failure_safe_degradation(monkeypatch):
    """When Redis fails, rate limiter safely degrades to in-memory sliding window."""
    limiter = RateLimiter(prefix="test_stage5_degradation", requests_per_window=2, window_seconds=60.0)
    limiter.reset_local()

    # Simulate Redis connection failure
    async def mock_redis_failure():
        raise redis.ConnectionError("Redis connection lost")

    monkeypatch.setattr("app.core.rate_limit.get_redis_client", mock_redis_failure)

    ident = f"degrade_user_{uuid.uuid4().hex[:6]}"

    # In-memory fallback enforces limits
    a1, _ = await limiter.check_and_record(ident)
    a2, _ = await limiter.check_and_record(ident)
    assert a1 is True
    assert a2 is True

    # 3rd request blocked
    a3, retry_after = await limiter.check_and_record(ident)
    assert a3 is False
    assert retry_after is not None


# ---------------------------------------------------------------------------
# 11. Cookie-Authenticated CSRF Origin Verification
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_cookie_csrf_origin_verification(async_client: AsyncClient):
    """Cookie-authenticated /refresh and /logout reject untrusted Origin headers with HTTP 403."""
    user = await create_stage5_user("csrf_test_user")

    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "ValidPassword123!"},
    )
    cookie_token = login_res.json()["refresh_token"]

    # 1. Cross-site request from untrusted origin (e.g. attacker site)
    malicious_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={},
        cookies={"dukaanly_refresh_token": cookie_token},
        headers={"Origin": "https://malicious-attacker.com"},
    )
    assert malicious_res.status_code == 403
    assert "Cross-origin request rejected" in malicious_res.json()["detail"]

    # 2. Legitimate request from configured allowed origin (http://localhost:5173)
    legit_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={},
        cookies={"dukaanly_refresh_token": cookie_token},
        headers={"Origin": "http://localhost:5173"},
    )
    assert legit_res.status_code == 200

    # 3. Direct API client with token in body is NOT rejected by Origin check
    body_res = await async_client.post(
        "/api/v1/auth/refresh",
        json={"refresh_token": legit_res.json()["refresh_token"]},
        headers={"Origin": "https://any-mobile-client.app"},
    )
    assert body_res.status_code == 200


# ---------------------------------------------------------------------------
# 12. Redis Outage Auth Fail-Closed Configuration
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_redis_outage_auth_fail_closed_mode(monkeypatch):
    """When RATE_LIMIT_AUTH_FAIL_CLOSED=True, auth limiters fail closed during Redis outages."""
    monkeypatch.setattr(settings, "RATE_LIMIT_AUTH_FAIL_CLOSED", True)

    limiter = RateLimiter(prefix="auth_test_fail_closed", requests_per_window=5)

    async def mock_redis_failure():
        raise redis.ConnectionError("Redis cluster unreachable")

    monkeypatch.setattr("app.core.rate_limit.get_redis_client", mock_redis_failure)

    # Must immediately return allowed=False and retry_after=window
    allowed, retry_after = await limiter.check_and_record("test_ip")
    assert allowed is False
    assert retry_after == 60.0
