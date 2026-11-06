"""
FastAPI Routes for Dukaanly AI Foundation & Diagnostics.
"""

from collections import defaultdict
import time
from typing import Dict, List, Optional, Tuple
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_current_user, require_role
from app.core.config import settings
from app.core.rate_limit import ai_chat_rate_limiter
from app.db.session import get_db
from app.models.user import User, UserRole
from app.schemas.ai import ShoppingAssistantRequest, ShoppingAssistantResponse
from app.services.shopping_assistant import process_shopping_assistant_chat
from app.core.ai import (
    AIStatusResponse,
    AIConnectionTestResponse,
    LLMCompletionRequest,
    LLMCompletionResponse,
    ai_service,
    AIDisabledError,
    AIRateLimitError,
    AIProviderTimeoutError,
    AIContextLengthError,
    AIOutputParseError,
    AIAuthenticationError,
    AIModelNotFoundError,
    AIProviderError,
    AIError,
)

router = APIRouter()


class UserRateLimiter:
    """
    Sliding-window per-user rate limiter.
    Wraps the shared Redis-backed ai_chat_rate_limiter while providing
    backward-compatible synchronous check/reset methods for legacy test callers.
    """

    def __init__(self, limiter=ai_chat_rate_limiter):
        self._limiter = limiter

    @property
    def requests_per_minute(self) -> int:
        return self._limiter.requests_per_window

    @requests_per_minute.setter
    def requests_per_minute(self, value: int):
        if value < 1:
            raise ValueError("AI rate limit must be at least one request per window")
        # The shared limiter resolves its normal value dynamically from settings.
        # Test/diagnostic callers historically set this compatibility property,
        # so update that same source of truth instead of an ignored fallback field.
        settings.AI_RATE_LIMIT_PER_MINUTE = value

    def check_and_record(self, user_id: str) -> Tuple[bool, Optional[float]]:
        return self._limiter.check_and_record_local(user_id)

    async def acheck_and_record(self, user_id: str) -> Tuple[bool, Optional[float]]:
        return await self._limiter.check_and_record(user_id)

    def reset(self, user_id: Optional[str] = None) -> None:
        self._limiter.reset_local(user_id)

    async def areset(self, user_id: Optional[str] = None) -> None:
        await self._limiter.reset(user_id)


ai_user_rate_limiter = UserRateLimiter()


@router.get(
    "/status",
    response_model=AIStatusResponse,
    summary="Get AI foundation status and active feature flags",
    description="Returns current operational status, active provider, model, and feature enablement.",
)
async def get_ai_status(
    current_user: User = Depends(get_current_user),
) -> AIStatusResponse:
    """Retrieve operational status of the AI subsystem."""
    return ai_service.get_status()


@router.get(
    "/diagnostic/check",
    response_model=AIConnectionTestResponse,
    summary="Diagnostic connectivity test endpoint",
    description="Probes the active AI provider with a lightweight health check to verify endpoint reachability, credentials, and latency. Strictly restricted to platform administrators.",
)
async def diagnostic_check(
    current_user: User = Depends(require_role(UserRole.admin)),
) -> AIConnectionTestResponse:
    """Execute a guarded diagnostic check against the active provider (Admin Only)."""
    return await ai_service.check_connection()


@router.post(
    "/diagnostic/complete",
    response_model=LLMCompletionResponse,
    summary="Diagnostic LLM completion endpoint",
    description="Guarded test endpoint to verify provider connectivity, latency, and schema parsing.",
)
async def diagnostic_complete(
    request: LLMCompletionRequest,
    current_user: User = Depends(get_current_user),
) -> LLMCompletionResponse:
    """
    Execute a diagnostic completion.
    Guarded by authentication and the global AI_ENABLED feature flag.
    """
    try:
        request.user_id = str(current_user.id)
        return await ai_service.complete(request)
    except AIDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        )
    except AIAuthenticationError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=exc.message,
        )
    except AIModelNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=exc.message,
        )
    except AIRateLimitError as exc:
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(int(exc.retry_after))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers=headers,
        )
    except AIProviderTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        )
    except AIContextLengthError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=exc.message,
        )
    except (AIOutputParseError, AIProviderError) as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=exc.message,
        )
    except AIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        )


@router.post(
    "/assistant/chat",
    response_model=ShoppingAssistantResponse,
    summary="Grounded conversational shopping assistant",
    description="Understands customer shopping requests, searches active verified partner inventory within 5 km, and proposes an authoritative single-shop cart.",
)
async def assistant_chat(
    request: ShoppingAssistantRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ShoppingAssistantResponse:
    """
    Process conversational shopping queries with grounded catalog search and single-shop cart proposal.
    Guarded by user authentication, per-user rate limit, and the AI_FEATURE_SHOPPING_ASSISTANT feature flag.
    """
    # Enforce distributed per-user rate limit
    is_allowed, retry_after = await ai_chat_rate_limiter.check_and_record(str(current_user.id))
    if not is_allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"AI request rate limit exceeded. Maximum {ai_chat_rate_limiter.requests_per_window} requests per minute.",
            headers={"Retry-After": str(int(retry_after or 60))},
        )

    try:
        return await process_shopping_assistant_chat(
            db=db,
            customer=current_user,
            request=request,
        )
    except AIDisabledError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=exc.message,
        )
    except AIRateLimitError as exc:
        headers = {}
        if exc.retry_after:
            headers["Retry-After"] = str(int(exc.retry_after))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=exc.message,
            headers=headers,
        )
    except AIProviderTimeoutError as exc:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail=exc.message,
        )
    except AIError as exc:
        raise HTTPException(
            status_code=exc.status_code,
            detail=exc.message,
        )
