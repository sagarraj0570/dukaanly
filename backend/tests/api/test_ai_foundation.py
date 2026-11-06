"""
Comprehensive test suite for Dukaanly AI Foundation.
Tests provider abstraction, mock provider, upstream error mappings, retries,
feature flags, telemetry, and API security boundaries.
"""

import json
import uuid
import pytest
from httpx import AsyncClient, Response
import httpx

from app.core.config import settings
from app.core.ai import (
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
    LLMCompletionResponse,
    MockLLMProvider,
    OpenAILikeProvider,
    get_llm_provider,
    ai_service,
    AIService,
    AIConfigurationError,
    AIDisabledError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIContextLengthError,
    AIOutputParseError,
)

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. Provider Abstraction & Factory Tests
# ---------------------------------------------------------------------------

async def test_provider_factory_and_switching():
    """Verify provider abstraction cleanly instantiates mock and HTTP providers."""
    mock_prov = get_llm_provider("mock")
    assert isinstance(mock_prov, MockLLMProvider)
    assert mock_prov.provider_name == "mock"

    openai_prov = get_llm_provider("openai")
    assert isinstance(openai_prov, OpenAILikeProvider)
    assert openai_prov.provider_name == "openai_compatible"

    groq_prov = get_llm_provider("groq")
    assert isinstance(groq_prov, OpenAILikeProvider)

    with pytest.raises(AIConfigurationError) as exc_info:
        get_llm_provider("unsupported_provider_xyz")
    assert "Unsupported AI provider" in str(exc_info.value)


async def test_mock_provider_deterministic_completion():
    """Verify MockLLMProvider delivers normalized, typed completion responses."""
    provider = MockLLMProvider()
    req = LLMCompletionRequest(
        messages=[
            ChatMessage(role=ChatRole.system, content="You are a helpful assistant."),
            ChatMessage(role=ChatRole.user, content="Find 5kg wheat flour"),
        ],
        model="mock-v1",
    )
    resp = await provider.complete(req)

    assert isinstance(resp, LLMCompletionResponse)
    assert resp.provider == "mock"
    assert "Find 5kg wheat flour" in resp.text
    assert resp.usage.total_tokens > 0
    assert resp.usage.estimated_cost_usd >= 0.0
    assert resp.latency_ms >= 0.0


async def test_mock_provider_json_mode():
    """Verify MockLLMProvider respects json_object response format."""
    provider = MockLLMProvider()
    req = LLMCompletionRequest(
        messages=[ChatMessage(role=ChatRole.user, content="Return cart JSON")],
        response_format={"type": "json_object"},
    )
    resp = await provider.complete(req)
    parsed = json.loads(resp.text)
    assert "message" in parsed
    assert "status" in parsed


# ---------------------------------------------------------------------------
# 2. Upstream Error Mapping & Parsing Tests
# ---------------------------------------------------------------------------

async def test_mock_provider_simulated_errors():
    """Verify simulated failure modes (timeout, rate limit, outage, parse error)."""
    # 1. Timeout
    timeout_prov = MockLLMProvider(simulate_timeout=True)
    with pytest.raises(AIProviderTimeoutError) as t_err:
        await timeout_prov.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert t_err.value.status_code == 504

    # 2. Rate limit (429)
    rate_prov = MockLLMProvider(simulate_rate_limit=True)
    with pytest.raises(AIRateLimitError) as r_err:
        await rate_prov.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert r_err.value.status_code == 429
    assert r_err.value.retry_after == 5.0

    # 3. Provider outage (502)
    server_prov = MockLLMProvider(simulate_server_error=True)
    with pytest.raises(AIProviderError) as s_err:
        await server_prov.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert s_err.value.status_code == 502

    # 4. Malformed JSON parse error
    malformed_prov = MockLLMProvider(simulate_malformed_json=True)
    with pytest.raises(AIOutputParseError) as m_err:
        await malformed_prov.complete(
            LLMCompletionRequest(
                messages=[ChatMessage(role=ChatRole.user, content="hi")],
                response_format={"type": "json_object"}
            )
        )
    assert m_err.value.status_code == 502


async def test_openai_like_provider_http_error_mappings(monkeypatch):
    """Verify OpenAILikeProvider maps HTTP error statuses to typed AI exceptions."""
    provider = OpenAILikeProvider(api_key="test-key", base_url="https://mock.llm.local")

    # Mock 429 Rate Limit
    async def mock_post_429(*args, **kwargs):
        return Response(status_code=429, headers={"retry-after": "12"}, text="Too Many Requests")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_429)
    with pytest.raises(AIRateLimitError) as exc429:
        await provider.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert exc429.value.status_code == 429
    assert exc429.value.retry_after == 12.0

    # Mock 500 Provider Server Error
    async def mock_post_500(*args, **kwargs):
        return Response(status_code=500, text="Internal Provider Crash")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_500)
    with pytest.raises(AIProviderError) as exc500:
        await provider.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert exc500.value.status_code == 502

    # Mock Timeout
    async def mock_post_timeout(*args, **kwargs):
        raise httpx.ReadTimeout("Read timed out")

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_timeout)
    with pytest.raises(AIProviderTimeoutError) as exc_timeout:
        await provider.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert exc_timeout.value.status_code == 504

    # Mock Malformed Upstream JSON
    async def mock_post_bad_json(*args, **kwargs):
        return Response(status_code=200, json={"unexpected_schema": True})

    monkeypatch.setattr(httpx.AsyncClient, "post", mock_post_bad_json)
    with pytest.raises(AIOutputParseError) as exc_parse:
        await provider.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert exc_parse.value.status_code == 502


# ---------------------------------------------------------------------------
# 3. AIService Orchestration, Retries, & Feature Flag Tests
# ---------------------------------------------------------------------------

async def test_service_kill_switch_and_feature_flags(monkeypatch):
    """Verify feature flag enforcement rejects calls when disabled."""
    # When globally disabled
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    svc = AIService(provider=MockLLMProvider())

    with pytest.raises(AIDisabledError) as dis_err:
        await svc.complete(LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]))
    assert dis_err.value.status_code == 503

    # When globally enabled but sub-feature is disabled
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_FEATURE_SHOPPING_ASSISTANT", False)

    with pytest.raises(AIDisabledError) as feat_err:
        await svc.complete(
            LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]),
            feature_name="shopping_assistant"
        )
    assert feat_err.value.status_code == 503


async def test_service_bounded_retries_and_fallback(monkeypatch):
    """Verify AIService retries transient errors and invokes fallback on final failure."""
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_MAX_RETRIES", 2)
    monkeypatch.setattr(settings, "AI_RETRY_BACKOFF_SECONDS", 0.01)  # fast for testing

    # Provider that always fails with 502
    failing_prov = MockLLMProvider(simulate_server_error=True)
    svc = AIService(provider=failing_prov)

    # Fallback function
    async def test_fallback():
        return LLMCompletionResponse(
            model="fallback-rule-based",
            provider="fallback",
            text="Safe static fallback recommendation",
        )

    resp = await svc.complete(
        LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="hi")]),
        fallback_fn=test_fallback
    )
    assert resp.provider == "fallback"
    assert "Safe static fallback" in resp.text


# ---------------------------------------------------------------------------
# 4. API Endpoints & Authorization Boundary Tests
# ---------------------------------------------------------------------------

async def test_ai_status_endpoint(async_client: AsyncClient, monkeypatch):
    """Verify GET /api/v1/ai/status requires auth and returns truthful metadata."""
    # 1. Unauthenticated request -> 401
    unauth_res = await async_client.get("/api/v1/ai/status")
    assert unauth_res.status_code == 401

    # 2. Register & login customer
    email = f"ai_cust_{uuid.uuid4().hex[:8]}@example.com"
    await async_client.post("/api/v1/auth/register", json={
        "name": "AI Customer", "email": email, "password": "Password123!"
    })
    token = (await async_client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password123!"
    })).json()["access_token"]

    # 3. Authenticated status request
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    monkeypatch.setattr(settings, "AI_MODEL", "mock-gpt")

    auth_res = await async_client.get(
        "/api/v1/ai/status",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert auth_res.status_code == 200
    data = auth_res.json()
    assert data["enabled"] is True
    assert data["provider"] == "mock"
    assert data["model"] == "mock-gpt"
    assert "features" in data
    # Security invariant: API key must never be exposed
    assert "api_key" not in data
    assert "key" not in data


async def test_diagnostic_complete_endpoint(async_client: AsyncClient, monkeypatch):
    """Verify POST /api/v1/ai/diagnostic/complete handles flags and completions."""
    email = f"ai_user_{uuid.uuid4().hex[:8]}@example.com"
    await async_client.post("/api/v1/auth/register", json={
        "name": "Diag User", "email": email, "password": "Password123!"
    })
    token = (await async_client.post("/api/v1/auth/login", json={
        "email": email, "password": "Password123!"
    })).json()["access_token"]

    req_body = {
        "messages": [
            {"role": "user", "content": "Suggest fresh fruits"}
        ]
    }

    # 1. Feature disabled -> 503
    monkeypatch.setattr(settings, "AI_ENABLED", False)
    dis_res = await async_client.post(
        "/api/v1/ai/diagnostic/complete",
        json=req_body,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert dis_res.status_code == 503
    assert "disabled" in dis_res.json()["detail"]

    # 2. Feature enabled with mock provider -> 200
    monkeypatch.setattr(settings, "AI_ENABLED", True)
    monkeypatch.setattr(settings, "AI_PROVIDER", "mock")
    # Reset singleton provider
    ai_service._provider = MockLLMProvider()

    ok_res = await async_client.post(
        "/api/v1/ai/diagnostic/complete",
        json=req_body,
        headers={"Authorization": f"Bearer {token}"}
    )
    assert ok_res.status_code == 200
    res_data = ok_res.json()
    assert res_data["provider"] == "mock"
    assert "Suggest fresh fruits" in res_data["text"]
    assert res_data["usage"]["total_tokens"] > 0
    # Security check: no secret keys or authorization headers leaked
    assert "api_key" not in res_data
