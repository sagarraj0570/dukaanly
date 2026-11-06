"""
Custom exception hierarchy for the Dukaanly AI subsystem.
"""

class AIError(Exception):
    """Base exception for all AI subsystem errors."""
    def __init__(self, message: str, status_code: int = 500, detail: str | None = None):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.detail = detail or message


class AIConfigurationError(AIError):
    """Raised when an AI provider or feature is misconfigured."""
    def __init__(self, message: str):
        super().__init__(message, status_code=500)


class AIDisabledError(AIError):
    """Raised when AI subsystem or specific AI feature is disabled via feature flags."""
    def __init__(self, message: str = "AI capabilities are currently disabled on this platform."):
        super().__init__(message, status_code=503)


class AIProviderError(AIError):
    """Raised when upstream LLM provider returns an error."""
    def __init__(self, message: str, status_code: int = 502, provider: str = "unknown"):
        super().__init__(f"AI provider '{provider}' failed: {message}", status_code=status_code)
        self.provider = provider


class AIProviderTimeoutError(AIProviderError):
    """Raised when an upstream LLM request times out."""
    def __init__(self, timeout_seconds: float, provider: str = "unknown"):
        super().__init__(
            f"Request timed out after {timeout_seconds} seconds",
            status_code=504,
            provider=provider
        )
        self.timeout_seconds = timeout_seconds


class AIRateLimitError(AIProviderError):
    """Raised when an upstream provider or local rate limit is exceeded."""
    def __init__(self, retry_after: float | None = None, provider: str = "unknown"):
        msg = "Rate limit exceeded"
        if retry_after:
            msg += f". Retry after {retry_after} seconds."
        super().__init__(msg, status_code=429, provider=provider)
        self.retry_after = retry_after


class AIContextLengthError(AIError):
    """Raised when token count exceeds configured maximum allowed tokens."""
    def __init__(self, message: str = "Input context exceeds maximum token limits."):
        super().__init__(message, status_code=400)


class AIOutputParseError(AIError):
    """Raised when the LLM outputs malformed JSON or unparseable structured content."""
    def __init__(self, message: str, raw_output: str | None = None):
        super().__init__(message, status_code=502)
        self.raw_output = raw_output


class AIAuthenticationError(AIProviderError):
    """Raised when upstream LLM provider rejects authentication credentials (HTTP 401/403)."""
    def __init__(self, message: str = "Invalid or expired provider credentials.", provider: str = "unknown"):
        super().__init__(message, status_code=401, provider=provider)


class AIModelNotFoundError(AIProviderError):
    """Raised when requested model ID does not exist on upstream provider (HTTP 404)."""
    def __init__(self, model_name: str, provider: str = "unknown"):
        super().__init__(f"Requested model '{model_name}' was not found on provider.", status_code=404, provider=provider)

