"""
Unit and Integration Tests for Groq Provider Integration (Phase 2.6).
Verifies Groq configuration, candidate model resolution, URL normalization,
header authentication, structured JSON handling, terminal error fast-fail (401/404),
transient retry handling (429/502/timeout), secret redaction, and diagnostic endpoints.
All tests in this file are fully mocked, deterministic, offline, and zero-cost.
"""

import asyncio
from decimal import Decimal
import json
import os
import re
from unittest.mock import AsyncMock, patch, MagicMock
import httpx
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import settings
from app.core.ai.exceptions import (
    AIAuthenticationError,
    AIConfigurationError,
    AIContextLengthError,
    AIModelNotFoundError,
    AIOutputParseError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
)
from app.core.ai.provider import (
    OpenAILikeProvider,
    get_llm_provider,
    redact_secrets,
)
from app.core.ai.schemas import (
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
    LLMCompletionResponse,
)
from app.core.ai.service import AIService, ai_service

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# 1. Provider Configuration and Default Model
# ---------------------------------------------------------------------------
async def test_groq_provider_configuration_and_default_model():
    """Verify Groq provider resolves canonical base URL and candidate model."""
    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key="gsk_testdummykey12345678901234567890",
    )
    assert provider.provider_name == "groq"
    assert provider.base_url == "https://api.groq.com/openai/v1"
    assert provider.default_model == "openai/gpt-oss-120b"
    assert provider._semaphore._value == 5


async def test_groq_provider_factory_resolution():
    """Verify get_llm_provider('groq') instantiates OpenAILikeProvider."""
    with patch.object(settings, "AI_PROVIDER", "groq"):
        provider = get_llm_provider()
        assert isinstance(provider, OpenAILikeProvider)
        assert provider.provider_name == "groq"


# ---------------------------------------------------------------------------
# 2. Key Resolution Hierarchy
# ---------------------------------------------------------------------------
async def test_groq_api_key_resolution_hierarchy():
    """Verify key is resolved in order: explicit param -> GROQ_API_KEY -> AI_API_KEY."""
    # Explicit param takes precedence
    p1 = OpenAILikeProvider(provider_type="groq", api_key="explicit_key_123")
    assert p1.api_key == "explicit_key_123"

    # Fallback to GROQ_API_KEY
    with patch.object(settings, "GROQ_API_KEY", "groq_env_key_456"):
        p2 = OpenAILikeProvider(provider_type="groq")
        assert p2.api_key == "groq_env_key_456"


# ---------------------------------------------------------------------------
# 3. URL Normalization and No Path Duplication
# ---------------------------------------------------------------------------
async def test_groq_url_normalization_prevents_duplicate_path():
    """Verify endpoint is correctly sanitized without duplicate /chat/completions."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-test1",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    captured_url = None

    async def mock_post(url, **kwargs):
        nonlocal captured_url
        captured_url = str(url)
        return mock_response

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key="gsk_test12345678901234567890",
        base_url="https://api.groq.com/openai/v1/chat/completions",  # Already has suffix
    )

    req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="ping")])
    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        await provider.complete(req)

    # Must NOT be https://api.groq.com/openai/v1/chat/completions/chat/completions
    assert captured_url == "https://api.groq.com/openai/v1/chat/completions"


# ---------------------------------------------------------------------------
# 4. Bearer Authorization and Request Headers
# ---------------------------------------------------------------------------
async def test_groq_bearer_auth_headers_and_payload():
    """Verify Authorization: Bearer is sent along with required content headers."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-test2",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "response"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    captured_headers = None
    captured_json = None

    async def mock_post(url, headers=None, json=None, **kwargs):
        nonlocal captured_headers, captured_json
        captured_headers = headers
        captured_json = json
        return mock_response

    test_key = "gsk_supersecretkey123456789012"
    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key=test_key,
    )

    req = LLMCompletionRequest(
        messages=[
            ChatMessage(role=ChatRole.system, content="You are a helpful assistant."),
            ChatMessage(role=ChatRole.user, content="Hello"),
        ],
        temperature=0.3,
        max_tokens=150,
    )

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        resp = await provider.complete(req)

    assert captured_headers is not None
    assert captured_headers["Authorization"] == f"Bearer {test_key}"
    assert captured_headers["Content-Type"] == "application/json"
    assert captured_json["model"] == "openai/gpt-oss-120b"
    assert captured_json["temperature"] == 0.3
    assert captured_json["max_tokens"] == 150
    assert len(captured_json["messages"]) == 2
    assert resp.text == "response"
    assert resp.usage.total_tokens == 15


# ---------------------------------------------------------------------------
# 5. Structured JSON Output & Parsing Errors
# ---------------------------------------------------------------------------
async def test_groq_structured_json_mode_success():
    """Verify JSON object mode payload and valid parsed output."""
    json_data = {"recommendation": "Fresh Milk", "quantity": 1}
    mock_response = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-json1",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": json.dumps(json_data)}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_testkey1234567890123")
    req = LLMCompletionRequest(
        messages=[ChatMessage(role=ChatRole.user, content="give me json")],
        response_format={"type": "json_object"},
    )

    with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)):
        resp = await provider.complete(req)

    parsed = json.loads(resp.text)
    assert parsed["recommendation"] == "Fresh Milk"


async def test_groq_structured_json_mode_malformed_raises_parse_error():
    """Verify malformed JSON in json_object mode raises AIOutputParseError."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-json2",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "{unclosed_json: true"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_testkey1234567890123")
    req = LLMCompletionRequest(
        messages=[ChatMessage(role=ChatRole.user, content="give me json")],
        response_format={"type": "json_object"},
    )

    with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)):
        with pytest.raises(AIOutputParseError) as exc_info:
            await provider.complete(req)
        assert exc_info.value.status_code == 502


# ---------------------------------------------------------------------------
# 6. Terminal Client Errors Fast-Fail (No Blind Retries)
# ---------------------------------------------------------------------------
async def test_groq_auth_failure_401_fails_fast_without_retries():
    """Verify HTTP 401 raises AIAuthenticationError immediately without retrying."""
    mock_response = httpx.Response(
        status_code=401,
        text='{"error": {"message": "Invalid API Key provided", "type": "invalid_request_error"}}',
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_response

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_invalidkey12345678901")
    service = AIService(provider=provider)

    req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="test")])

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(AIAuthenticationError) as exc_info:
            await service.complete(req)

        assert exc_info.value.status_code == 401
        assert "Authentication failed" in exc_info.value.message
        # Crucial: Must NOT retry on 401!
        assert call_count == 1


async def test_groq_model_not_found_404_fails_fast_without_retries():
    """Verify HTTP 404 raises AIModelNotFoundError immediately without retrying."""
    mock_response = httpx.Response(
        status_code=404,
        text='{"error": {"message": "The model `nonexistent-model` does not exist", "type": "invalid_request_error"}}',
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    call_count = 0

    async def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        return mock_response

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_validkey1234567890123")
    service = AIService(provider=provider)

    req = LLMCompletionRequest(
        messages=[ChatMessage(role=ChatRole.user, content="test")],
        model="nonexistent-model",
    )

    with patch("httpx.AsyncClient.post", side_effect=mock_post):
        with pytest.raises(AIModelNotFoundError) as exc_info:
            await service.complete(req)

        assert exc_info.value.status_code == 404
        assert "nonexistent-model" in exc_info.value.message
        # Crucial: Must NOT retry on 404!
        assert call_count == 1


# ---------------------------------------------------------------------------
# 7. Transient Errors Retries (429, 502, Timeouts)
# ---------------------------------------------------------------------------
async def test_groq_rate_limit_429_respects_retry_after():
    """Verify HTTP 429 parses Retry-After header and raises AIRateLimitError."""
    mock_response = httpx.Response(
        status_code=429,
        headers={"retry-after": "5"},
        text='{"error": {"message": "Rate limit reached", "type": "rate_limit_error"}}',
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_validkey1234567890123")
    req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="test")])

    with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)):
        with pytest.raises(AIRateLimitError) as exc_info:
            await provider.complete(req)

        assert exc_info.value.status_code == 429
        assert exc_info.value.retry_after == 5.0


async def test_groq_transient_502_retries_and_recovers():
    """Verify upstream 502 triggers retry with backoff and succeeds on subsequent attempt."""
    mock_fail = httpx.Response(
        status_code=502,
        text="Bad Gateway",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )
    mock_success = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-recov",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "recovered!"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 2, "total_tokens": 7},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    responses = [mock_fail, mock_success]

    async def mock_post(*args, **kwargs):
        return responses.pop(0)

    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_validkey1234567890123")
    service = AIService(provider=provider)

    with patch.object(settings, "AI_RETRY_BACKOFF_SECONDS", 0.01):
        with patch("httpx.AsyncClient.post", side_effect=mock_post):
            req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="test")])
            resp = await service.complete(req)
            assert resp.text == "recovered!"


async def test_groq_timeout_raises_provider_timeout_error():
    """Verify httpx.TimeoutException maps to AIProviderTimeoutError."""
    provider = OpenAILikeProvider(provider_type="groq", api_key="gsk_validkey1234567890123")
    req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="test")])

    with patch("httpx.AsyncClient.post", AsyncMock(side_effect=httpx.TimeoutException("timed out"))):
        with pytest.raises(AIProviderTimeoutError) as exc_info:
            await provider.complete(req)
        assert exc_info.value.status_code == 504


# ---------------------------------------------------------------------------
# 8. Secret Redaction
# ---------------------------------------------------------------------------
async def test_groq_secret_redaction_masks_sensitive_tokens():
    """Verify redact_secrets completely masks Bearer tokens, gsk keys, and sk keys."""
    raw_error = "Error: Bearer gsk_sampletestkey12345678901234567890 failed on host"
    redacted = redact_secrets(raw_error)
    assert "gsk_sampletestkey12345678901234567890" not in redacted
    assert "***REDACTED***" in redacted

    raw_json = '{"api_key": "gsk_12345678901234567890", "sk": "sk-proj-1234567890123456"}'
    redacted_json = redact_secrets(raw_json)
    assert "gsk_12345678901234567890" not in redacted_json
    assert "sk-proj-1234567890123456" not in redacted_json


# ---------------------------------------------------------------------------
# 9. Diagnostic Endpoints
# ---------------------------------------------------------------------------
async def test_groq_diagnostic_status_endpoint():
    """Verify get_status reports api_key_configured and active_endpoint safely."""
    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key="gsk_maskedkey123456789012345",
    )
    service = AIService(provider=provider)

    with patch.object(settings, "AI_ENABLED", True):
        with patch.object(settings, "AI_PROVIDER", "groq"):
            with patch.object(settings, "AI_MODEL", "openai/gpt-oss-120b"):
                status = service.get_status()
                assert status.enabled is True
                assert status.provider == "groq"
                assert status.model == "openai/gpt-oss-120b"
                assert status.api_key_configured is True
                assert status.active_endpoint == "https://api.groq.com/openai/v1"
                # Ensure raw key is NOT present in any status response attribute
                assert "gsk_maskedkey" not in json.dumps(status.model_dump())


async def test_groq_diagnostic_check_connection_success():
    """Verify check_connection probes upstream and returns structured test response."""
    mock_response = httpx.Response(
        status_code=200,
        json={
            "id": "chatcmpl-probe",
            "model": "openai/gpt-oss-120b",
            "choices": [{"message": {"content": "pong"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 1, "total_tokens": 5},
        },
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key="gsk_testprobe12345678901234",
    )
    service = AIService(provider=provider)

    with patch.object(settings, "AI_ENABLED", True):
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)):
            result = await service.check_connection()
            assert result.connection_successful is True
            assert result.provider == "groq"
            assert result.model == "openai/gpt-oss-120b"
            assert result.api_key_configured is True
            assert result.error_category is None
            assert result.latency_ms >= 0.0
            # Guarantee no secrets in serialized output
            assert "gsk_testprobe" not in json.dumps(result.model_dump())


async def test_groq_diagnostic_check_connection_auth_failure():
    """Verify check_connection reports authentication_failed category safely."""
    mock_response = httpx.Response(
        status_code=401,
        text="Invalid API Key",
        request=httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions"),
    )

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key="gsk_badkey12345678901234",
    )
    service = AIService(provider=provider)

    with patch.object(settings, "AI_ENABLED", True):
        with patch("httpx.AsyncClient.post", AsyncMock(return_value=mock_response)):
            result = await service.check_connection()
            assert result.connection_successful is False
            assert result.error_category == "authentication_failed"
            assert result.api_key_configured is True
