"""
AI Service Orchestrator for Dukaanly.
Coordinates provider calls, retries, feature flags, telemetry, and safe fallbacks.
"""

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine, Dict, Optional

from app.core.config import settings
from app.core.ai.exceptions import (
    AIDisabledError,
    AIError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIAuthenticationError,
    AIModelNotFoundError,
)
from app.core.ai.provider import BaseLLMProvider, OpenAILikeProvider, get_llm_provider
from app.core.ai.schemas import (
    AIStatusResponse,
    AIConnectionTestResponse,
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
    LLMCompletionResponse,
)

logger = logging.getLogger(__name__)


class AIService:
    """
    Central orchestration service for all Dukaanly AI interactions.
    Guarantees strict feature flag compliance, bounded retries, dynamic circuit breaker, and privacy-conscious telemetry.
    """

    def __init__(
        self,
        provider: Optional[BaseLLMProvider] = None,
        failure_threshold: int = 3,
        cooldown_seconds: float = 30.0,
    ):
        self._provider = provider
        self._consecutive_failures: int = 0
        self._failure_threshold: int = failure_threshold
        self._last_failure_time: float = 0.0
        self._cooldown_seconds: float = cooldown_seconds
        self._last_diagnostic_time: float = 0.0
        self._last_diagnostic_result: Optional[AIConnectionTestResponse] = None
        self._diagnostic_cooldown_seconds: float = 30.0

    @property
    def provider(self) -> BaseLLMProvider:
        if self._provider is None:
            self._provider = get_llm_provider()
        return self._provider

    def is_circuit_breaker_open(self) -> bool:
        """
        Check if circuit breaker is open (tripped).
        Open if globally disabled or if consecutive failures exceed threshold during cooldown.
        Recovers to half-open when cooldown expires.
        """
        if not settings.AI_ENABLED:
            return True
        if self._consecutive_failures >= self._failure_threshold:
            time_since_failure = time.time() - self._last_failure_time
            if time_since_failure < self._cooldown_seconds:
                return True
            # Cooldown passed -> Half-open state allowing next probe attempt
            logger.info("AI circuit breaker entered HALF-OPEN state after cooldown (probe allowed)")
            return False
        return False

    def record_success(self) -> None:
        """Reset consecutive failures upon successful completion."""
        if self._consecutive_failures > 0:
            logger.info("AI provider recovered successfully. Circuit breaker reset.")
        self._consecutive_failures = 0
        self._last_failure_time = 0.0

    def record_failure(self) -> None:
        """Record a failure event and update circuit breaker state."""
        self._consecutive_failures += 1
        self._last_failure_time = time.time()
        if self._consecutive_failures >= self._failure_threshold:
            logger.error(
                "AI circuit breaker TRIPPED [consecutive_failures=%d, threshold=%d, cooldown=%.1fs]",
                self._consecutive_failures,
                self._failure_threshold,
                self._cooldown_seconds,
            )

    def reset_circuit_breaker(self) -> None:
        """Explicitly reset circuit breaker state."""
        self._consecutive_failures = 0
        self._last_failure_time = 0.0

    def reset_diagnostic_cache(self) -> None:
        """Explicitly invalidate diagnostic probe cache for testing."""
        self._last_diagnostic_time = 0.0
        self._last_diagnostic_result = None

    def check_feature_enabled(self, feature_name: Optional[str] = None) -> None:
        """
        Verify that AI is globally enabled and the specific feature flag is active.
        Raises AIDisabledError if either flag is disabled.
        """
        if not settings.AI_ENABLED:
            raise AIDisabledError("AI subsystem is globally disabled on this deployment.")

        if feature_name:
            flag_attr = f"AI_FEATURE_{feature_name.upper()}"
            is_feature_active = getattr(settings, flag_attr, False)
            if not is_feature_active:
                raise AIDisabledError(f"AI feature '{feature_name}' is currently disabled.")

    async def complete(
        self,
        request: LLMCompletionRequest,
        feature_name: Optional[str] = None,
        fallback_fn: Optional[Callable[[], Coroutine[Any, Any, LLMCompletionResponse]]] = None,
    ) -> LLMCompletionResponse:
        """
        Execute an LLM completion with feature flag checks, circuit breaker inspection,
        bounded retries, and structured fallbacks.
        """
        self.check_feature_enabled(feature_name)

        # Check circuit breaker before attempting upstream call
        if self.is_circuit_breaker_open() and settings.AI_ENABLED:
            logger.warning("AI circuit breaker is currently OPEN. Bypassing upstream call.")
            if fallback_fn is not None:
                return await fallback_fn()
            raise AIProviderError(
                "AI circuit breaker is currently open due to consecutive upstream failures. Please retry shortly.",
                status_code=503,
            )

        max_retries = max(0, settings.AI_MAX_RETRIES)
        backoff_base = settings.AI_RETRY_BACKOFF_SECONDS
        last_exception: Optional[Exception] = None

        for attempt in range(max_retries + 1):
            try:
                start_time = time.perf_counter()
                response = await self.provider.complete(request)
                
                # Success -> reset circuit breaker
                self.record_success()

                # Telemetry & privacy-safe logging (no PII, no message bodies in prod logs)
                logger.info(
                    "AI completion succeeded [provider=%s, model=%s, tokens=%d, latency=%.2fms, attempt=%d]",
                    response.provider,
                    response.model,
                    response.usage.total_tokens,
                    response.latency_ms,
                    attempt + 1,
                )
                return response

            except (AIAuthenticationError, AIModelNotFoundError) as exc:
                self.record_failure()
                logger.error(
                    "AI non-retryable error [provider=%s, status=%d, error=%s]",
                    self.provider.provider_name,
                    exc.status_code,
                    str(exc),
                )
                raise exc

            except AIProviderError as exc:
                if exc.status_code in (400, 401, 403, 404, 413, 422):
                    self.record_failure()
                    logger.error(
                        "AI client error HTTP %d (non-retryable) [provider=%s, error=%s]",
                        exc.status_code,
                        self.provider.provider_name,
                        str(exc),
                    )
                    raise exc

                last_exception = exc
                logger.warning(
                    "AI provider transient error on attempt %d/%d [provider=%s, error=%s]",
                    attempt + 1,
                    max_retries + 1,
                    self.provider.provider_name,
                    str(exc),
                )
                
                if attempt < max_retries:
                    # Exponential backoff: 0.5s, 1.0s, etc.
                    delay = backoff_base * (2 ** attempt)
                    if isinstance(exc, AIRateLimitError) and exc.retry_after:
                        delay = max(delay, exc.retry_after)
                    await asyncio.sleep(delay)
                else:
                    break

            except AIError:
                # Configuration or validation errors are terminal and should not be retried
                raise

        # Record failure for circuit breaker tracking
        self.record_failure()

        # If all retries exhausted, check for fallback
        if fallback_fn is not None:
            logger.warning("All AI provider attempts failed. Executing registered safe fallback.")
            try:
                return await fallback_fn()
            except Exception as fb_exc:
                logger.error("AI safe fallback execution failed: %s", fb_exc)

        if last_exception:
            raise last_exception
        raise AIProviderError("AI completion failed after maximum retry attempts.")

    def get_status(self) -> AIStatusResponse:
        """Get the current operational health and feature configuration of the AI foundation."""
        features = {
            "shopping_assistant": settings.AI_FEATURE_SHOPPING_ASSISTANT,
            "catalog_search": settings.AI_FEATURE_CATALOG_SEARCH,
            "order_support": settings.AI_FEATURE_ORDER_SUPPORT,
        }
        
        is_open = self.is_circuit_breaker_open()
        if not settings.AI_ENABLED:
            detail_msg = "Disabled globally (kill-switch active)"
        elif is_open:
            detail_msg = f"Circuit breaker OPEN ({self._consecutive_failures} failures recorded, cooldown in effect)"
        elif settings.AI_PROVIDER == "mock":
            detail_msg = "Operational (Mock provider active)"
        else:
            detail_msg = f"Operational ({settings.AI_PROVIDER} upstream active)"

        api_key_configured = False
        active_endpoint = None

        if settings.AI_PROVIDER == "mock":
            api_key_configured = True
            active_endpoint = "in-memory://mock"
        else:
            try:
                prov = self.provider
                if isinstance(prov, OpenAILikeProvider):
                    api_key_configured = bool(prov.api_key)
                    active_endpoint = prov.base_url
                else:
                    api_key_configured = bool(settings.AI_API_KEY)
                    active_endpoint = settings.AI_BASE_URL
            except Exception:
                api_key_configured = False

        return AIStatusResponse(
            enabled=settings.AI_ENABLED,
            provider=settings.AI_PROVIDER,
            model=settings.AI_MODEL,
            features=features,
            circuit_breaker_open=is_open,
            details=detail_msg,
            api_key_configured=api_key_configured,
            active_endpoint=active_endpoint,
        )

    async def check_connection(self, force: bool = False) -> AIConnectionTestResponse:
        """
        Lightweight diagnostic probe to test provider connectivity, authentication, and round-trip latency.
        Strictly sanitizes all errors, enforces a 3.0s bounded timeout, and throttles rapid calls
        via cooldown caching to protect against excessive provider costs.
        """
        now = time.time()
        if not force and self._last_diagnostic_result is not None:
            if (now - self._last_diagnostic_time) < self._diagnostic_cooldown_seconds:
                logger.info(
                    "Returning cached AI diagnostic probe result (cooldown active, remaining: %.1fs)",
                    self._diagnostic_cooldown_seconds - (now - self._last_diagnostic_time),
                )
                res = self._last_diagnostic_result.model_copy()
                res.circuit_breaker_open = self.is_circuit_breaker_open()
                res.cached = True
                return res

        provider_name = self.provider.provider_name
        model_name = getattr(self.provider, "default_model", settings.AI_MODEL)

        api_key_configured = False
        if provider_name == "mock":
            api_key_configured = True
        elif isinstance(self.provider, OpenAILikeProvider):
            api_key_configured = bool(self.provider.api_key)
        else:
            api_key_configured = bool(settings.AI_API_KEY)

        if not settings.AI_ENABLED:
            res = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=0.0,
                error_category="disabled",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = res
            return res

        if not api_key_configured and provider_name != "mock":
            res = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=False,
                connection_successful=False,
                latency_ms=0.0,
                error_category="missing_api_key",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = res
            return res

        probe_request = LLMCompletionRequest(
            messages=[ChatMessage(role=ChatRole.user, content="ping")],
            max_tokens=3,
            temperature=0.0,
        )

        start_time = time.perf_counter()
        try:
            # Enforce strict 3.0-second timeout ceiling to prevent long-lived hanging requests
            resp = await asyncio.wait_for(
                self.provider.complete(probe_request),
                timeout=3.0,
            )
            latency_ms = resp.latency_ms or round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=resp.model or model_name,
                api_key_configured=True,
                connection_successful=True,
                latency_ms=latency_ms,
                error_category=None,
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except asyncio.TimeoutError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="timeout",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except AIAuthenticationError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="authentication_failed",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except AIModelNotFoundError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="model_not_found",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except AIRateLimitError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="rate_limited",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except AIProviderTimeoutError:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="timeout",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result
        except Exception:
            latency_ms = round((time.perf_counter() - start_time) * 1000, 2)
            result = AIConnectionTestResponse(
                provider=provider_name,
                model=model_name,
                api_key_configured=api_key_configured,
                connection_successful=False,
                latency_ms=latency_ms,
                error_category="upstream_error",
                circuit_breaker_open=self.is_circuit_breaker_open(),
                cached=False,
            )
            self._last_diagnostic_time = time.time()
            self._last_diagnostic_result = result
            return result


# Global singleton instance
ai_service = AIService()
