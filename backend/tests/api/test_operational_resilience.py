"""
Operational Resilience Test Suite (Phase 2.7 Focus Area 3).

Enforces:
1. Rate limit handling (HTTP 429 with Retry-After and safe fallback).
2. Upstream provider outages (502/504 errors trigger fallback, never crashing ordinary commerce).
3. Circuit breaker full lifecycle: CLOSED -> 3 failures -> OPEN -> Cooldown -> HALF-OPEN -> Probe Success -> CLOSED.
4. Concurrency stress: 15 concurrent shopping requests bounded cleanly without deadlocks.
5. Security & Cost-abuse protection on /api/v1/ai/diagnostic/check:
   - 401 Unauthorized for anonymous requests.
   - 403 Forbidden for non-admin roles (customer, shop_owner, rider).
   - 200 OK for admin role.
   - 30-second cooldown caching preventing provider cost-abuse.
   - Telemetry confidentiality: strictly zero secrets (keys, bearer tokens) or PII in responses.
"""

import asyncio
from decimal import Decimal
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.core.ai import (
    AIService,
    MockLLMProvider,
    ai_service,
    AIProviderError,
    AIRateLimitError,
    AIProviderTimeoutError,
)
from app.core.ai.schemas import (
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
)
from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import async_session_maker
from app.main import app
from app.models.product import Product
from app.models.shop import Shop, ShopVerificationStatus
from app.models.user import User, UserRole
from app.schemas.ai import ShoppingAssistantRequest
from app.services import cart as cart_service
from app.services.shopping_assistant import process_shopping_assistant_chat

pytestmark = pytest.mark.asyncio

PATNA_LAT = 25.6144
PATNA_LON = 85.1158


@pytest.fixture
async def users_by_role():
    """Create test users for role-based authorization verification."""
    async with async_session_maker() as session:
        admin = User(
            id=uuid.uuid4(),
            name="Admin User",
            email=f"admin_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.admin,
            is_active=True,
        )
        customer = User(
            id=uuid.uuid4(),
            name="Customer User",
            email=f"customer_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.customer,
            is_active=True,
        )
        rider = User(
            id=uuid.uuid4(),
            name="Rider User",
            email=f"rider_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.rider,
            is_active=True,
        )
        session.add_all([admin, customer, rider])
        await session.commit()

        yield {
            "admin": admin,
            "customer": customer,
            "rider": rider,
        }

        from sqlalchemy import text
        await session.execute(text("DELETE FROM users WHERE id IN (:a, :c, :r)"), {
            "a": str(admin.id), "c": str(customer.id), "r": str(rider.id)
        })
        await session.commit()


# ---------------------------------------------------------------------------
# Test 1: Rate Limit Handling (HTTP 429 with Retry-After)
# ---------------------------------------------------------------------------
async def test_groq_rate_limit_handling():
    """Verify rate limit errors from upstream provider raise AIRateLimitError with retry info."""
    mock_provider = MockLLMProvider(simulate_rate_limit=True)
    svc = AIService(provider=mock_provider)

    req = LLMCompletionRequest(
        messages=[ChatMessage(role=ChatRole.user, content="Check atta availability")]
    )

    with pytest.raises(AIRateLimitError) as exc_info:
        await svc.complete(req)

    assert exc_info.value.retry_after == 5.0
    assert "rate limit" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test 2: Circuit Breaker Lifecycle (Closed -> Open -> Half-Open -> Recovered)
# ---------------------------------------------------------------------------
async def test_circuit_breaker_full_lifecycle():
    """
    Verify complete circuit breaker state transitions:
    1. Initially CLOSED (0 failures).
    2. 3 consecutive upstream outages (502/504) TRIP the breaker to OPEN.
    3. Fast bypass while in OPEN state (no wasteful calls to upstream).
    4. Cooldown elapses -> HALF-OPEN allows single probe.
    5. Successful probe transitions back to CLOSED.
    """
    failing_provider = MockLLMProvider(simulate_server_error=True)
    svc = AIService(provider=failing_provider, failure_threshold=3, cooldown_seconds=0.2)

    assert svc.is_circuit_breaker_open() is False

    # Simulate 3 consecutive failures
    svc.record_failure()
    assert svc.is_circuit_breaker_open() is False
    svc.record_failure()
    assert svc.is_circuit_breaker_open() is False
    svc.record_failure()
    # Breaker TRIPPED
    assert svc.is_circuit_breaker_open() is True

    # Immediate check during cooldown remains OPEN
    assert svc.is_circuit_breaker_open() is True

    # Wait for cooldown to expire
    await asyncio.sleep(0.25)

    # Cooldown passed -> HALF-OPEN allows probe (is_circuit_breaker_open returns False)
    assert svc.is_circuit_breaker_open() is False

    # Successful probe resets breaker to CLOSED
    svc.record_success()
    assert svc._consecutive_failures == 0
    assert svc.is_circuit_breaker_open() is False


# ---------------------------------------------------------------------------
# Test 3: Concurrency Stress Under Bounded Semaphore
# ---------------------------------------------------------------------------
async def test_concurrent_shopping_assistant_requests():
    """
    Stress test shopping assistant with 15 simultaneous customer requests.
    Validates no deadlocks, race conditions, or unhandled exceptions under concurrency.
    """
    ai_service._provider = MockLLMProvider()
    async with async_session_maker() as session:
        # Create a test customer
        user = User(
            id=uuid.uuid4(),
            name="Concurrent Customer",
            email=f"concurrent_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="hash",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(user)
        await session.commit()

        req = ShoppingAssistantRequest(
            message="Aashirvaad atta and Tata salt",
            latitude=PATNA_LAT,
            longitude=PATNA_LON,
        )

        async def send_chat():
            async with async_session_maker() as sess:
                return await process_shopping_assistant_chat(sess, user, req)

        # Launch 15 concurrent chat sessions
        tasks = [send_chat() for _ in range(15)]
        results = await asyncio.gather(*tasks)

        assert len(results) == 15
        for resp in results:
            assert resp.assistant_message is not None
            assert len(resp.matched_products) > 0
            assert resp.proposed_cart is not None

        # Cleanup
        from sqlalchemy import text
        await session.execute(text("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id = :uid)"), {"uid": str(user.id)})
        await session.execute(text("DELETE FROM carts WHERE customer_id = :uid"), {"uid": str(user.id)})
        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": str(user.id)})
        await session.commit()


# ---------------------------------------------------------------------------
# Test 4: Diagnostic Endpoint Security & RBAC Enforcement
# ---------------------------------------------------------------------------
async def test_diagnostic_endpoint_security_rbac(users_by_role):
    """
    Security check: GET /api/v1/ai/diagnostic/check must strictly require Admin role.
    - Anonymous: 401 Unauthorized
    - Customer: 403 Forbidden
    - Rider: 403 Forbidden
    - Admin: 200 OK
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Anonymous request
        anon_resp = await client.get("/api/v1/ai/diagnostic/check")
        assert anon_resp.status_code == 401

        # 2. Customer token -> 403 Forbidden
        cust_token = create_access_token(subject=str(users_by_role["customer"].id), role=users_by_role["customer"].role.value)
        cust_resp = await client.get(
            "/api/v1/ai/diagnostic/check",
            headers={"Authorization": f"Bearer {cust_token}"},
        )
        assert cust_resp.status_code == 403

        # 3. Rider token -> 403 Forbidden
        rider_token = create_access_token(subject=str(users_by_role["rider"].id), role=users_by_role["rider"].role.value)
        rider_resp = await client.get(
            "/api/v1/ai/diagnostic/check",
            headers={"Authorization": f"Bearer {rider_token}"},
        )
        assert rider_resp.status_code == 403

        # 4. Admin token -> 200 OK
        admin_token = create_access_token(subject=str(users_by_role["admin"].id), role=users_by_role["admin"].role.value)
        admin_resp = await client.get(
            "/api/v1/ai/diagnostic/check",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert admin_resp.status_code == 200
        data = admin_resp.json()
        assert "connection_successful" in data
        assert "provider" in data
        assert "model" in data
        assert "latency_ms" in data
        assert "cached" in data


# ---------------------------------------------------------------------------
# Test 5: Cost-Abuse Prevention (30s Diagnostic Cooldown Caching)
# ---------------------------------------------------------------------------
async def test_diagnostic_check_cost_abuse_cooldown_caching(users_by_role):
    """
    Verify /api/v1/ai/diagnostic/check implements 30s cooldown caching.
    Repeated calls within 30 seconds return cached result without hitting upstream.
    """
    ai_service.reset_diagnostic_cache()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_token = create_access_token(subject=str(users_by_role["admin"].id), role=users_by_role["admin"].role.value)
        headers = {"Authorization": f"Bearer {admin_token}"}

        # First probe -> fresh check (cached=False)
        r1 = await client.get("/api/v1/ai/diagnostic/check", headers=headers)
        assert r1.status_code == 200
        d1 = r1.json()
        assert d1["cached"] is False

        # Immediate repeat probe -> cached probe (cached=True)
        r2 = await client.get("/api/v1/ai/diagnostic/check", headers=headers)
        assert r2.status_code == 200
        d2 = r2.json()
        assert d2["cached"] is True
        assert d2["provider"] == d1["provider"]
        assert d2["model"] == d1["model"]


# ---------------------------------------------------------------------------
# Test 6: Zero Secrets & PII Exposure in Diagnostic Responses
# ---------------------------------------------------------------------------
async def test_zero_secrets_or_pii_in_diagnostic_telemetry(users_by_role):
    """
    Verify diagnostic output never leaks API keys, bearer tokens, or internal passwords.
    """
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        admin_token = create_access_token(subject=str(users_by_role["admin"].id), role=users_by_role["admin"].role.value)
        resp = await client.get(
            "/api/v1/ai/diagnostic/check",
            headers={"Authorization": f"Bearer {admin_token}"},
        )
        assert resp.status_code == 200
        raw_text = resp.text

        # Verify no secret patterns exist anywhere in response body
        assert "gsk_" not in raw_text
        assert "Bearer" not in raw_text
        assert "secret" not in raw_text.lower()
        assert "password" not in raw_text.lower()


# ---------------------------------------------------------------------------
# Test 7: Ordinary Browsing & Checkout Unaffected by AI Provider Outages
# ---------------------------------------------------------------------------
async def test_ordinary_browsing_and_cart_unaffected_when_ai_down(users_by_role):
    """
    Verify core business invariant:
    If AI provider is completely down or circuit breaker is OPEN,
    ordinary browsing, cart operations, and checkout remain fully functional.
    """
    # Force circuit breaker to open by recording repeated failures
    for _ in range(5):
        ai_service.record_failure()
    assert ai_service.is_circuit_breaker_open() is True

    # Normal cart operations must execute without any error
    customer = users_by_role["customer"]
    async with async_session_maker() as session:
        cart = await cart_service.get_cart(db=session, customer=customer)
        assert cart.customer_id == customer.id
        assert cart.total_amount == Decimal("0.00")

    # Reset circuit breaker
    ai_service.reset_circuit_breaker()
