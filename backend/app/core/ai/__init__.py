"""
Dukaanly AI Core Module.
Provides lightweight LLM abstractions, schemas, providers, and orchestration service.
"""

from app.core.ai.exceptions import (
    AIError,
    AIConfigurationError,
    AIDisabledError,
    AIProviderError,
    AIProviderTimeoutError,
    AIRateLimitError,
    AIContextLengthError,
    AIOutputParseError,
    AIAuthenticationError,
    AIModelNotFoundError,
)
from app.core.ai.schemas import (
    ChatRole,
    ChatMessage,
    TokenUsage,
    LLMCompletionRequest,
    LLMCompletionResponse,
    AIStatusResponse,
    AIConnectionTestResponse,
)
from app.core.ai.provider import (
    BaseLLMProvider,
    MockLLMProvider,
    OpenAILikeProvider,
    get_llm_provider,
    estimate_token_cost,
    mask_sensitive_data,
)
from app.core.ai.service import AIService, ai_service

__all__ = [
    "AIError",
    "AIConfigurationError",
    "AIDisabledError",
    "AIProviderError",
    "AIProviderTimeoutError",
    "AIRateLimitError",
    "AIContextLengthError",
    "AIOutputParseError",
    "AIAuthenticationError",
    "AIModelNotFoundError",
    "ChatRole",
    "ChatMessage",
    "TokenUsage",
    "LLMCompletionRequest",
    "LLMCompletionResponse",
    "AIStatusResponse",
    "AIConnectionTestResponse",
    "BaseLLMProvider",
    "MockLLMProvider",
    "OpenAILikeProvider",
    "get_llm_provider",
    "estimate_token_cost",
    "mask_sensitive_data",
    "AIService",
    "ai_service",
]
