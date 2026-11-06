"""
Opt-in Live Smoke Tests for Groq Real Provider (Phase 2.6).
Marked with @pytest.mark.live_provider.
Excluded from default test runs via pytest.ini: addopts = -m "not live_provider".

To run these tests:
    pytest -m live_provider backend/tests/api/test_groq_live_smoke.py -v
"""

import json
import os
import pytest

from app.core.config import settings
from app.core.ai.provider import OpenAILikeProvider
from app.core.ai.schemas import ChatMessage, ChatRole, LLMCompletionRequest
from app.core.ai.service import ai_service

pytestmark = [pytest.mark.asyncio, pytest.mark.live_provider]


def get_live_groq_key() -> str | None:
    return settings.GROQ_API_KEY or settings.AI_API_KEY or os.getenv("GROQ_API_KEY")


async def test_live_groq_text_completion():
    """Verify live outbound completion to Groq API using candidate model openai/gpt-oss-120b."""
    key = get_live_groq_key()
    if not key:
        pytest.skip("GROQ_API_KEY is not configured; skipping live provider smoke test.")

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key=key,
        model="openai/gpt-oss-120b",
    )

    req = LLMCompletionRequest(
        messages=[
            ChatMessage(role=ChatRole.system, content="You are Dukaanly AI. Be concise."),
            ChatMessage(role=ChatRole.user, content="What is Dukaanly? Answer in 10 words or less."),
        ],
        temperature=0.2,
        max_tokens=250,
    )

    resp = await provider.complete(req)

    assert resp.provider == "groq"
    assert resp.model == "openai/gpt-oss-120b"
    assert len(resp.text.strip()) > 0
    assert resp.usage.total_tokens > 0
    assert resp.latency_ms > 0
    assert resp.finish_reason in ("stop", "length")


async def test_live_groq_structured_json_completion():
    """Verify live outbound completion to Groq API supports response_format={"type": "json_object"}."""
    key = get_live_groq_key()
    if not key:
        pytest.skip("GROQ_API_KEY is not configured; skipping live provider smoke test.")

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key=key,
        model="openai/gpt-oss-120b",
    )

    req = LLMCompletionRequest(
        messages=[
            ChatMessage(
                role=ChatRole.system,
                content="Return ONLY a JSON object with keys: store_name, city, is_open.",
            ),
            ChatMessage(
                role=ChatRole.user,
                content="Generate store details for Anand Kirana in Patna.",
            ),
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=200,
    )

    resp = await provider.complete(req)
    parsed = json.loads(resp.text)

    assert "store_name" in parsed
    assert "city" in parsed
    assert "is_open" in parsed
    assert "Patna" in str(parsed.get("city"))


async def test_live_groq_diagnostic_connection_check():
    """Verify ai_service.check_connection() successfully connects to live Groq endpoint."""
    key = get_live_groq_key()
    if not key:
        pytest.skip("GROQ_API_KEY is not configured; skipping live provider smoke test.")

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key=key,
        model="openai/gpt-oss-120b",
    )

    orig_prov = ai_service._provider
    orig_enabled = settings.AI_ENABLED
    try:
        settings.AI_ENABLED = True
        ai_service._provider = provider
        diag = await ai_service.check_connection()

        assert diag.connection_successful is True
        assert diag.provider == "groq"
        assert diag.model == "openai/gpt-oss-120b"
        assert diag.api_key_configured is True
        assert diag.error_category is None
        assert diag.latency_ms > 0

        # Guarantee no secrets in serialized output
        serialized = json.dumps(diag.model_dump())
        assert key not in serialized
    finally:
        ai_service._provider = orig_prov
        settings.AI_ENABLED = orig_enabled
