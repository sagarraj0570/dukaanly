"""
LLM Provider Abstraction and Concrete Adapters for Dukaanly.
"""

from abc import ABC, abstractmethod
import asyncio
import json
import logging
import os
import re
import time
from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.core.ai.exceptions import (
    AIConfigurationError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIContextLengthError,
    AIOutputParseError,
    AIAuthenticationError,
    AIModelNotFoundError,
)
from app.core.ai.schemas import (
    ChatMessage,
    LLMCompletionRequest,
    LLMCompletionResponse,
    TokenUsage,
)

logger = logging.getLogger(__name__)

# Approximate pricing per 1M tokens for cost tracking estimates (e.g. gpt-4o-mini tier)
ESTIMATED_INPUT_PRICE_PER_1M_USD = 0.15
ESTIMATED_OUTPUT_PRICE_PER_1M_USD = 0.60

# Model-specific pricing tiers (USD per 1M tokens)
MODEL_TOKEN_PRICING: Dict[str, Dict[str, float]] = {
    # Groq Production Models
    "llama-3.3-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-70b-versatile": {"input": 0.59, "output": 0.79},
    "llama-3.1-8b-instant": {"input": 0.05, "output": 0.08},
    "mixtral-8x7b-32768": {"input": 0.24, "output": 0.24},
    "openai/gpt-oss-120b": {"input": 0.59, "output": 0.79},
    # OpenAI Models
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    # Default fallback baseline
    "default": {
        "input": ESTIMATED_INPUT_PRICE_PER_1M_USD,
        "output": ESTIMATED_OUTPUT_PRICE_PER_1M_USD,
    },
}

SECRET_PATTERNS = [
    re.compile(r"Bearer\s+([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(r"([A-Za-z0-9_\-]{0,8}(?:key|secret|token|auth)[A-Za-z0-9_\-]*\s*[:=]\s*[\"']?)([A-Za-z0-9_\-\.]{8,})", re.IGNORECASE),
    re.compile(r"(sk-[A-Za-z0-9_\-]{16,})", re.IGNORECASE),
    re.compile(r"(gsk_[A-Za-z0-9_\-]{16,})", re.IGNORECASE),
]


def redact_secrets(text: str) -> str:
    """Mask sensitive tokens, API keys, and authorization headers from logs and error messages."""
    if not text:
        return text
    # Replace Bearer tokens: 'Bearer xyz' -> 'Bearer ***REDACTED***'
    text = re.sub(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", r"\1***REDACTED***", text, flags=re.IGNORECASE)
    # Replace sk- tokens: 'sk-proj-xyz' -> '***REDACTED***'
    text = re.sub(r"sk-[A-Za-z0-9_\-]{16,}", r"***REDACTED***", text, flags=re.IGNORECASE)
    # Replace gsk_ tokens: 'gsk_xyz' -> '***REDACTED***'
    text = re.sub(r"gsk_[A-Za-z0-9_\-]{16,}", r"***REDACTED***", text, flags=re.IGNORECASE)
    # Replace key/secret/token assignments: 'key="xyz"' -> 'key="***REDACTED***"'
    text = re.sub(
        r"([A-Za-z0-9_\-]{0,8}(?:key|secret|token|auth)[A-Za-z0-9_\-]*\s*[:=]\s*[\"']?)[A-Za-z0-9_\-\.]{8,}([\"']?)",
        r"\1***REDACTED***\2",
        text,
        flags=re.IGNORECASE,
    )
    return text


mask_sensitive_data = redact_secrets


def estimate_token_cost(
    prompt_tokens: int,
    completion_tokens: int,
    model: Optional[str] = None,
) -> float:
    """
    Calculate an approximate dollar cost for token usage.
    Uses model-specific pricing tier if model is specified and recognized,
    falling back to standard baseline tier ($0.15/M in, $0.60/M out).
    """
    tier = MODEL_TOKEN_PRICING.get(model or "", MODEL_TOKEN_PRICING["default"])
    input_cost = (prompt_tokens / 1_000_000) * tier["input"]
    output_cost = (completion_tokens / 1_000_000) * tier["output"]
    return round(input_cost + output_cost, 6)


SUPPORTED_PROVIDERS: Dict[str, Dict[str, Any]] = {
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "default_model": "gpt-4o-mini",
        "env_keys": ["OPENAI_API_KEY", "AI_API_KEY"],
        "extra_headers": {},
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "default_model": "openai/gpt-oss-120b",
        "env_keys": ["GROQ_API_KEY", "AI_API_KEY"],
        "extra_headers": {},
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "default_model": "openai/gpt-4o-mini",
        "env_keys": ["OPENROUTER_API_KEY", "AI_API_KEY"],
        "extra_headers": {
            "HTTP-Referer": "https://dukaanly.local",
            "X-Title": "Dukaanly Hyperlocal Marketplace",
        },
    },
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai",
        "default_model": "gemini-1.5-flash",
        "env_keys": ["GEMINI_API_KEY", "AI_API_KEY"],
        "extra_headers": {},
    },
    "openai_compatible": {
        "base_url": settings.AI_BASE_URL,
        "default_model": settings.AI_MODEL,
        "env_keys": ["AI_API_KEY"],
        "extra_headers": {},
    },
}


class BaseLLMProvider(ABC):
    """Abstract interface for all Dukaanly LLM providers."""

    @abstractmethod
    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        """Execute a chat completion request and return a normalized response."""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """The identifier string of this provider."""
        pass


class MockLLMProvider(BaseLLMProvider):
    """
    Deterministic in-memory mock provider for testing and zero-cost local development.
    Supports injecting custom canned responses, budget simulation, or triggering simulated failures.
    """

    def __init__(
        self,
        canned_response: Optional[str] = None,
        simulate_timeout: bool = False,
        simulate_rate_limit: bool = False,
        simulate_server_error: bool = False,
        simulate_malformed_json: bool = False,
        latency_seconds: float = 0.0,
    ):
        self.canned_response = canned_response
        self.simulate_timeout = simulate_timeout
        self.simulate_rate_limit = simulate_rate_limit
        self.simulate_server_error = simulate_server_error
        self.simulate_malformed_json = simulate_malformed_json
        self.latency_seconds = latency_seconds

    @property
    def provider_name(self) -> str:
        return "mock"

    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        start_time = time.perf_counter()

        if self.latency_seconds > 0:
            await asyncio.sleep(self.latency_seconds)

        if self.simulate_timeout:
            raise AIProviderTimeoutError(timeout_seconds=request.max_tokens or 10.0, provider=self.provider_name)

        if self.simulate_rate_limit:
            raise AIRateLimitError(retry_after=5.0, provider=self.provider_name)

        if self.simulate_server_error:
            raise AIProviderError("Simulated upstream provider outage", status_code=502, provider=self.provider_name)

        if self.simulate_malformed_json and request.response_format and request.response_format.get("type") == "json_object":
            raise AIOutputParseError("Malformed JSON response from mock provider", raw_output="{\"unclosed_json: ")

        # Default deterministic reply based on user message
        last_user_msg = next(
            (m.content for m in reversed(request.messages) if m.role == "user"),
            "Hello from Dukaanly AI Mock Provider",
        )

        if self.canned_response is not None:
            text = self.canned_response
        elif request.response_format and request.response_format.get("type") == "json_object":
            candidate_marker = "CATALOG_CANDIDATES:"
            prompt_text = " ".join(m.content for m in request.messages)
            if candidate_marker in prompt_text:
                try:
                    candidates_part = prompt_text.split(candidate_marker)[1].split("CUSTOMER_REQUEST:")[0].strip()
                    candidates = json.loads(candidates_part)
                    if candidates and isinstance(candidates, list) and len(candidates) > 0:
                        # Extract user request keywords to rank candidates by relevance
                        req_match = re.search(r"CUSTOMER_REQUEST:\s*(.*?)(?:\n\s*[A-Z_]+:|$)", prompt_text, re.DOTALL)
                        customer_text = (req_match.group(1) if req_match else last_user_msg).lower()
                        user_tokens = set(re.findall(r"[\w\u0900-\u097F]+", customer_text))
                        from app.services.catalog_search import GROCERY_SYNONYMS, COMMON_STOP_WORDS
                        content_user_tokens = {t for t in user_tokens if t not in COMMON_STOP_WORDS or t in GROCERY_SYNONYMS}
                        active_user_tokens = content_user_tokens if content_user_tokens else user_tokens
                        expanded_user_tokens = set(active_user_tokens)
                        for t in active_user_tokens:
                            if t in GROCERY_SYNONYMS:
                                expanded_user_tokens.update(GROCERY_SYNONYMS[t])

                        def cand_score(cand: Dict[str, Any]) -> int:
                            name_tokens = set(re.findall(r"[\w\u0900-\u097F]+", cand.get("name", "").lower()))
                            other_tokens = set(re.findall(
                                r"[\w\u0900-\u097F]+",
                                f"{cand.get('description', '')} {cand.get('category', '')}".lower(),
                            ))
                            return len(expanded_user_tokens.intersection(name_tokens)) * 3 + len(expanded_user_tokens.intersection(other_tokens))

                        # Sort candidates so the most relevant items come first
                        sorted_candidates = sorted(candidates, key=cand_score, reverse=True)

                        # Check budget limit if present in prompt
                        budget_limit = None
                        budget_match = re.search(r"BUDGET_CONSTRAINT:\s*Max\s*₹?(\d+(?:\.\d+)?)", prompt_text, re.IGNORECASE)
                        if not budget_match:
                            budget_match = re.search(r"(?:under|below|less\s+than)\s*₹?(\d+(?:\.\d+)?)", prompt_text, re.IGNORECASE)
                        if budget_match:
                            budget_limit = float(budget_match.group(1))

                        # Build proposed items from selected candidates (respecting single shop & budget)
                        target_shop_id = sorted_candidates[0].get("shop_id")
                        shop_candidates = [c for c in sorted_candidates if c.get("shop_id") == target_shop_id]

                        proposed_items = []
                        total_cost = 0.0

                        # Detect if multi-product request
                        multi_product = any(sep in prompt_text.lower() for sep in [",", " and ", " aur ", " also ", " with ", " + ", "&", " और "])

                        if multi_product:
                            # Extract distinct sub-queries to pick distinct items
                            sub_parts = [s.strip() for s in re.split(r",|\sand\s|\saur\s|\salso\s|\swith\s|\s\+\s|&|\sऔर\s", customer_text) if s.strip()]
                            if len(sub_parts) > 1:
                                selected_product_ids = set()
                                for sub in sub_parts:
                                    sub_tokens = set(re.findall(r"[\w\u0900-\u097F]+", sub))
                                    sub_content = {t for t in sub_tokens if t not in COMMON_STOP_WORDS or t in GROCERY_SYNONYMS}
                                    active_sub = sub_content if sub_content else sub_tokens
                                    expanded_sub = set(active_sub)
                                    for t in active_sub:
                                        if t in GROCERY_SYNONYMS:
                                            expanded_sub.update(GROCERY_SYNONYMS[t])

                                    def sub_cand_score(cand: Dict[str, Any]) -> int:
                                        name_tokens = set(re.findall(r"[\w\u0900-\u097F]+", cand.get("name", "").lower()))
                                        other_tokens = set(re.findall(r"[\w\u0900-\u097F]+", f"{cand.get('description', '')} {cand.get('category', '')}".lower()))
                                        return len(expanded_sub.intersection(name_tokens)) * 3 + len(expanded_sub.intersection(other_tokens))

                                    matching = [c for c in shop_candidates if c.get("product_id") not in selected_product_ids and sub_cand_score(c) > 0]
                                    if matching:
                                        best_match = max(matching, key=sub_cand_score)
                                        item_price = float(best_match.get("price", 0))
                                        if budget_limit is None or (total_cost + item_price) <= budget_limit:
                                            proposed_items.append({
                                                "product_id": best_match.get("product_id"),
                                                "quantity": 1,
                                            })
                                            total_cost += item_price
                                            selected_product_ids.add(best_match.get("product_id"))
                                    if len(proposed_items) >= 5:
                                        break

                        if not proposed_items:
                            for c in shop_candidates:
                                item_price = float(c.get("price", 0))
                                if budget_limit is not None and (total_cost + item_price) > budget_limit:
                                    continue
                                proposed_items.append({
                                    "product_id": c.get("product_id"),
                                    "quantity": 1,
                                })
                                total_cost += item_price
                                if not multi_product and len(proposed_items) >= 1:
                                    break
                                if len(proposed_items) >= 5:
                                    break

                        if not proposed_items and shop_candidates:
                            proposed_items = [{"product_id": shop_candidates[0].get("product_id"), "quantity": 1}]

                        first_cand = shop_candidates[0]
                        item_names = ", ".join(c.get("name", "") for c in shop_candidates[:len(proposed_items)])
                        text = json.dumps({
                            "assistant_message": f"I found {item_names or first_cand.get('name', 'items')} from {first_cand.get('shop_name', 'your nearby partner shop')}. Here is a proposed cart.",
                            "clarifying_question": None,
                            "selected_shop_id": target_shop_id,
                            "proposed_items": proposed_items,
                        })
                    else:
                        text = json.dumps({
                            "assistant_message": "No matching products were found in stock near your location.",
                            "clarifying_question": None,
                            "selected_shop_id": None,
                            "proposed_items": [],
                        })
                except Exception:
                    text = json.dumps({
                        "message": f"Processed query: {last_user_msg}",
                        "status": "success",
                        "recommendations": [],
                    })
            else:
                text = json.dumps({
                    "message": f"Processed query: {last_user_msg}",
                    "status": "success",
                    "recommendations": [],
                })
        else:
            text = f"Mock response for query: {last_user_msg}"

        # Rough token approximation (4 characters per token heuristic)
        prompt_chars = sum(len(m.content) for m in request.messages)
        prompt_tokens = max(1, prompt_chars // 4)
        completion_tokens = max(1, len(text) // 4)
        total_tokens = prompt_tokens + completion_tokens

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return LLMCompletionResponse(
            model=request.model or "mock-model",
            provider=self.provider_name,
            text=text,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimate_token_cost(
                    prompt_tokens, completion_tokens, request.model or "mock-model"
                ),
            ),
            latency_ms=latency_ms,
            finish_reason="stop",
        )


class OpenAILikeProvider(BaseLLMProvider):
    """
    HTTP adapter for standard OpenAI-compatible completions endpoints.
    Compatible with OpenAI, Groq, OpenRouter, Google Gemini, Ollama, and vLLM.
    Guarantees bounded concurrency, token bounds, timeout handling, and zero secret leakage.
    """

    def __init__(
        self,
        provider_type: str = "openai_compatible",
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
        max_concurrent_requests: Optional[int] = None,
    ):
        self._provider_type = provider_type.lower()
        cfg = SUPPORTED_PROVIDERS.get(self._provider_type, SUPPORTED_PROVIDERS["openai_compatible"])

        # Resolve API key from param, provider-specific settings, env_keys fallback, or settings.AI_API_KEY
        resolved_key = api_key
        if not resolved_key and self._provider_type == "groq":
            resolved_key = getattr(settings, "GROQ_API_KEY", None)
        if not resolved_key:
            for env_name in cfg.get("env_keys", []):
                val = getattr(settings, env_name, None) or os.getenv(env_name)
                if val and str(val).strip():
                    resolved_key = str(val).strip()
                    break
        if not resolved_key:
            resolved_key = settings.AI_API_KEY

        self.api_key = resolved_key

        # Resolve base URL and default model
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif self._provider_type == "groq":
            if settings.AI_BASE_URL and "groq.com" in settings.AI_BASE_URL:
                self.base_url = settings.AI_BASE_URL.rstrip("/")
            else:
                self.base_url = cfg["base_url"].rstrip("/")
        elif self._provider_type == "openai_compatible":
            self.base_url = settings.AI_BASE_URL.rstrip("/")
        else:
            self.base_url = cfg["base_url"].rstrip("/")

        if model:
            self.default_model = model
        elif self._provider_type == "groq":
            if settings.AI_MODEL and settings.AI_MODEL != "gpt-4o-mini":
                self.default_model = settings.AI_MODEL
            else:
                self.default_model = cfg["default_model"]
        elif self._provider_type == "openai_compatible":
            self.default_model = settings.AI_MODEL
        else:
            self.default_model = cfg["default_model"]

        self.timeout_seconds = timeout_seconds or settings.AI_REQUEST_TIMEOUT_SECONDS
        self.extra_headers = cfg.get("extra_headers", {})

        # Bounded concurrency semaphore
        max_concurrency = max_concurrent_requests or getattr(settings, "AI_MAX_CONCURRENT_REQUESTS", 5)
        self._semaphore = asyncio.Semaphore(max_concurrency)

        if not self.api_key and settings.AI_PROVIDER != "mock":
            logger.warning(
                "OpenAILikeProvider (%s) initialized without API key. Requests will fail if key is required.",
                self._provider_type,
            )

    @property
    def provider_name(self) -> str:
        if self._provider_type in ("openai", "openai_compatible"):
            return "openai_compatible"
        return self._provider_type

    async def complete(self, request: LLMCompletionRequest) -> LLMCompletionResponse:
        start_time = time.perf_counter()
        target_model = request.model or self.default_model
        
        # Guard against duplicated path components in base_url
        cleaned_base = self.base_url.rstrip("/")
        if cleaned_base.endswith("/chat/completions"):
            endpoint = cleaned_base
        else:
            endpoint = f"{cleaned_base}/chat/completions"

        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Dukaanly-AI/0.1.0",
        }
        if self.extra_headers:
            headers.update(self.extra_headers)

        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: Dict[str, Any] = {
            "model": target_model,
            "messages": [
                {"role": m.role.value, "content": m.content, **({"name": m.name} if m.name else {})}
                for m in request.messages
            ],
            "temperature": request.temperature if request.temperature is not None else settings.AI_TEMPERATURE,
            "max_tokens": request.max_tokens if request.max_tokens is not None else settings.AI_MAX_TOKENS,
        }

        if request.response_format:
            payload["response_format"] = request.response_format

        if request.stop:
            payload["stop"] = request.stop

        async with self._semaphore:
            try:
                async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                    response = await client.post(endpoint, json=payload, headers=headers)

                    if response.status_code in (401, 403):
                        safe_text = redact_secrets(response.text[:300])
                        raise AIAuthenticationError(
                            message=f"Authentication failed (HTTP {response.status_code}): {safe_text}",
                            provider=self.provider_name,
                        )

                    if response.status_code == 404:
                        safe_text = redact_secrets(response.text[:300])
                        raise AIModelNotFoundError(
                            model_name=target_model,
                            provider=self.provider_name,
                        )

                    if response.status_code == 429:
                        retry_after_header = response.headers.get("retry-after")
                        retry_after = (
                            float(retry_after_header)
                            if retry_after_header and retry_after_header.isdigit()
                            else None
                        )
                        raise AIRateLimitError(retry_after=retry_after, provider=self.provider_name)

                    if response.status_code in (400, 413) and "context_length" in response.text.lower():
                        raise AIContextLengthError(redact_secrets(response.text[:300]))

                    if 400 <= response.status_code < 500:
                        safe_text = redact_secrets(response.text[:300])
                        raise AIProviderError(
                            f"Provider client error (HTTP {response.status_code}): {safe_text}",
                            status_code=response.status_code,
                            provider=self.provider_name,
                        )

                    if response.status_code != 200:
                        safe_text = redact_secrets(response.text[:300])
                        raise AIProviderError(
                            f"Upstream returned HTTP {response.status_code}: {safe_text}",
                            status_code=502,
                            provider=self.provider_name,
                        )

                    data = response.json()

            except httpx.TimeoutException:
                raise AIProviderTimeoutError(timeout_seconds=self.timeout_seconds, provider=self.provider_name)
            except httpx.RequestError as exc:
                safe_err = redact_secrets(str(exc))
                raise AIProviderError(
                    f"Network error connecting to provider: {safe_err}",
                    status_code=502,
                    provider=self.provider_name,
                )

        # Parse upstream response
        try:
            choice = data["choices"][0]
            message_text = choice["message"]["content"]
            finish_reason = choice.get("finish_reason", "stop")
            raw_usage = data.get("usage", {})
            prompt_tokens = raw_usage.get("prompt_tokens", 0)
            completion_tokens = raw_usage.get("completion_tokens", 0)
            total_tokens = raw_usage.get("total_tokens", prompt_tokens + completion_tokens)
        except (KeyError, IndexError, TypeError) as exc:
            safe_data = redact_secrets(str(data)[:500])
            raise AIOutputParseError(f"Malformed response payload from provider: {exc}", raw_output=safe_data)

        # Validate JSON if json_object format was requested
        if request.response_format and request.response_format.get("type") == "json_object":
            try:
                json.loads(message_text)
            except json.JSONDecodeError as exc:
                safe_raw = redact_secrets(message_text[:500])
                raise AIOutputParseError(
                    f"Expected valid JSON object but received unparseable text: {exc}",
                    raw_output=safe_raw,
                )

        latency_ms = round((time.perf_counter() - start_time) * 1000, 2)

        return LLMCompletionResponse(
            id=data.get("id", f"ai-{int(start_time)}"),
            model=data.get("model", target_model),
            provider=self.provider_name,
            text=message_text,
            usage=TokenUsage(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
                total_tokens=total_tokens,
                estimated_cost_usd=estimate_token_cost(
                    prompt_tokens, completion_tokens, target_model
                ),
            ),
            latency_ms=latency_ms,
            finish_reason=finish_reason,
        )


def get_llm_provider(provider_type: Optional[str] = None) -> BaseLLMProvider:
    """
    Factory function returning the configured LLM provider instance.
    Supports: "mock", "openai", "groq", "openrouter", "gemini", "openai_compatible".
    """
    active_type = (provider_type or settings.AI_PROVIDER).lower()

    if active_type == "mock":
        return MockLLMProvider()
    elif active_type in SUPPORTED_PROVIDERS:
        return OpenAILikeProvider(provider_type=active_type)
    else:
        raise AIConfigurationError(
            f"Unsupported AI provider '{active_type}'. Allowed: 'mock', 'openai', 'groq', 'openrouter', 'gemini', 'openai_compatible'."
        )
