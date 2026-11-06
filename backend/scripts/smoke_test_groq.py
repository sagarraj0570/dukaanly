"""
Standalone Opt-In Smoke Test Script for Groq LLM Provider.
Tests live connectivity, candidate model (openai/gpt-oss-120b),
JSON structured mode, and round-trip latency against Groq's official API.

Usage:
    python backend/scripts/smoke_test_groq.py
"""

import asyncio
import json
import os
import sys
import time

# Ensure backend root is on sys.path
backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)

from app.core.config import settings
from app.core.ai.provider import OpenAILikeProvider, redact_secrets
from app.core.ai.schemas import ChatMessage, ChatRole, LLMCompletionRequest
from app.core.ai.service import ai_service


def mask_key(key: str | None) -> str:
    if not key or len(key) < 10:
        return "<not-configured>"
    return f"{key[:4]}...{key[-4:]}"


async def run_smoke_test() -> int:
    print("=" * 60)
    print("  Dukaanly Groq Real-Provider Smoke Test (Phase 2.6)")
    print("=" * 60)

    key = settings.GROQ_API_KEY or settings.AI_API_KEY or os.getenv("GROQ_API_KEY")
    if not key:
        print("\n[FAIL] No Groq API key found in settings or environment.")
        print("Please configure GROQ_API_KEY in .env before running this smoke test.")
        return 1

    masked = mask_key(key)
    print(f"\n[1/4] Environment Check:")
    print(f"      - Provider: groq")
    print(f"      - Candidate Model: openai/gpt-oss-120b")
    print(f"      - API Key Configured: Yes ({masked})")
    print(f"      - Base URL: https://api.groq.com/openai/v1")

    provider = OpenAILikeProvider(
        provider_type="groq",
        api_key=key,
        model="openai/gpt-oss-120b",
    )

    # 1. Text Completion Test
    print(f"\n[2/4] Testing Text Completion with Candidate Model (openai/gpt-oss-120b)...")
    text_request = LLMCompletionRequest(
        messages=[
            ChatMessage(
                role=ChatRole.system,
                content="You are Dukaanly's hyperlocal shopping assistant in Patna, Bihar. Be concise.",
            ),
            ChatMessage(
                role=ChatRole.user,
                content="Name 3 staple grocery items sold in local Patna dukaans in one brief sentence.",
            ),
        ],
        temperature=0.2,
        max_tokens=300,
    )

    t0 = time.perf_counter()
    try:
        text_resp = await provider.complete(text_request)
        t_elapsed = round((time.perf_counter() - t0) * 1000, 2)
        safe_output = text_resp.text.encode("ascii", errors="replace").decode("ascii").strip()
        print(f"      [OK] Response received in {t_elapsed} ms (upstream reported {text_resp.latency_ms} ms)")
        print(f"      - Finish Reason: {text_resp.finish_reason}")
        print(f"      - Total Tokens: {text_resp.usage.total_tokens}")
        print(f"      - Output: {safe_output}")
    except Exception as exc:
        safe_err = redact_secrets(str(exc))
        print(f"      [FAIL] Text completion failed: {safe_err}")
        return 1

    # 2. Structured JSON Mode Test
    print(f"\n[3/4] Testing Structured JSON Object Mode...")
    json_request = LLMCompletionRequest(
        messages=[
            ChatMessage(
                role=ChatRole.system,
                content="You are a JSON generator. You must output ONLY a valid JSON object matching the requested schema.",
            ),
            ChatMessage(
                role=ChatRole.user,
                content='Return a JSON object with: {"store_type": "kirana", "city": "Patna", "serviceable": true}',
            ),
        ],
        response_format={"type": "json_object"},
        temperature=0.1,
        max_tokens=100,
    )

    t0 = time.perf_counter()
    try:
        json_resp = await provider.complete(json_request)
        t_elapsed = round((time.perf_counter() - t0) * 1000, 2)
        parsed = json.loads(json_resp.text)
        print(f"      [OK] JSON Mode succeeded in {t_elapsed} ms")
        print(f"      - Valid JSON parsed successfully: {parsed}")
    except Exception as exc:
        safe_err = redact_secrets(str(exc))
        print(f"      [FAIL] Structured JSON completion failed: {safe_err}")
        return 1

    # 3. Diagnostic Probe Test
    print(f"\n[4/4] Testing AIService.check_connection() Diagnostic Probe...")
    try:
        # Temporarily wire provider into ai_service for check
        orig_prov = ai_service._provider
        ai_service._provider = provider
        diag = await ai_service.check_connection()
        ai_service._provider = orig_prov

        print(f"      [OK] Diagnostic probe status: {'SUCCESS' if diag.connection_successful else 'FAILED'}")
        print(f"      - Latency: {diag.latency_ms} ms")
        print(f"      - Provider: {diag.provider}")
        print(f"      - Model: {diag.model}")
        print(f"      - Circuit Breaker Open: {diag.circuit_breaker_open}")
        assert diag.connection_successful is True
    except Exception as exc:
        safe_err = redact_secrets(str(exc))
        print(f"      [FAIL] Diagnostic probe failed: {safe_err}")
        return 1

    print("\n" + "=" * 60)
    print("  ALL GROQ REAL-PROVIDER SMOKE TESTS PASSED SUCCESSFULLY!")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    exit_code = asyncio.run(run_smoke_test())
    sys.exit(exit_code)
