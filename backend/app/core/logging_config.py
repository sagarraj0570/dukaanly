"""
Structured Logging & Correlation System for Dukaanly (Stage 9).

Provides:
- JSON-compatible structured log formatting for production observability.
- ContextVar-based request ID and correlation ID propagation.
- Automatic sanitization of sensitive security fields (passwords, tokens, secrets).
- Correlation across HTTP requests, background Celery tasks, and WebSocket sessions.
"""

from contextvars import ContextVar
from datetime import datetime, timezone
import json
import logging
import re
import sys
from typing import Any, Dict, Optional

from app.core.config import settings

# Request-scoped context variables
request_id_ctx_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
correlation_id_ctx_var: ContextVar[Optional[str]] = ContextVar("correlation_id", default=None)
task_id_ctx_var: ContextVar[Optional[str]] = ContextVar("task_id", default=None)


def get_request_id() -> Optional[str]:
    """Retrieve current request ID from context."""
    return request_id_ctx_var.get()


def set_request_id(req_id: Optional[str]) -> None:
    """Store request ID in context."""
    request_id_ctx_var.set(req_id)


def get_correlation_id() -> Optional[str]:
    """Retrieve current correlation ID from context."""
    return correlation_id_ctx_var.get()


def set_correlation_id(corr_id: Optional[str]) -> None:
    """Store correlation ID in context."""
    correlation_id_ctx_var.set(corr_id)


def get_task_id() -> Optional[str]:
    """Retrieve current Celery task ID from context."""
    return task_id_ctx_var.get()


def set_task_id(t_id: Optional[str]) -> None:
    """Store Celery task ID in context."""
    task_id_ctx_var.set(t_id)


# Sensitive fields regex and set for automated sanitization
SENSITIVE_KEYS = {
    "password", "password_hash", "access_token", "refresh_token", "token",
    "jwt", "secret", "jwt_secret_key", "key_secret", "webhook_secret",
    "authorization", "api_key", "credit_card", "card_number", "cvv", "pan"
}

SENSITIVE_PATTERN = re.compile(
    r"(?i)(password|token|secret|authorization|bearer\s+[a-zA-Z0-9_\-\.]+)=([^\s&]+)"
)


def sanitize_sensitive_data(obj: Any) -> Any:
    """Recursively redacts passwords, tokens, and cryptographic secrets from log payloads."""
    if isinstance(obj, dict):
        sanitized = {}
        for k, v in obj.items():
            if str(k).lower() in SENSITIVE_KEYS:
                sanitized[k] = "[REDACTED]"
            elif isinstance(v, (dict, list)):
                sanitized[k] = sanitize_sensitive_data(v)
            elif isinstance(v, str) and ("bearer " in v.lower() or "secret" in v.lower()):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = v
        return sanitized
    elif isinstance(obj, list):
        return [sanitize_sensitive_data(item) for item in obj]
    elif isinstance(obj, str):
        return SENSITIVE_PATTERN.sub(r"\1=[REDACTED]", obj)
    return obj


class StructuredJsonFormatter(logging.Formatter):
    """
    JSON-compatible log formatter emitting production-grade structured telemetry.
    Strictly sanitizes sensitive data and propagates request and correlation IDs.
    """

    def format(self, record: logging.LogRecord) -> str:
        log_entry: Dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "service": "dukaanly-api",
            "environment": settings.APP_ENV,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # Context-derived correlation metadata
        req_id = getattr(record, "request_id", None) or get_request_id()
        if req_id:
            log_entry["request_id"] = req_id

        corr_id = getattr(record, "correlation_id", None) or get_correlation_id()
        if corr_id:
            log_entry["correlation_id"] = corr_id

        t_id = getattr(record, "task_id", None) or get_task_id()
        if t_id:
            log_entry["task_id"] = t_id

        # HTTP telemetry metadata if populated by middleware
        for attr in ("http_method", "route", "status_code", "duration_ms", "client_ip", "order_id", "delivery_id"):
            val = getattr(record, attr, None)
            if val is not None:
                log_entry[attr] = val

        # Handle exception information
        if record.exc_info:
            log_entry["exception"] = {
                "type": record.exc_info[0].__name__ if record.exc_info[0] else "UnknownException",
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info) if settings.DEBUG else "[REDACTED_IN_PRODUCTION]",
            }

        # Extra context passed via extra={...}
        if hasattr(record, "extra_data") and isinstance(record.extra_data, dict):
            log_entry["data"] = sanitize_sensitive_data(record.extra_data)

        # Sanitize entire log object
        sanitized_entry = sanitize_sensitive_data(log_entry)
        return json.dumps(sanitized_entry, default=str)


def setup_logging(log_format: Optional[str] = None) -> None:
    """
    Initializes application logging with structured JSON formatting or human-readable text.
    """
    format_type = (log_format or settings.LOG_FORMAT).lower()
    root_logger = logging.getLogger()
    
    # Configure root log level
    log_level = logging.DEBUG if settings.DEBUG else logging.INFO
    root_logger.setLevel(log_level)

    # Clear existing handlers to prevent duplicate output
    for handler in list(root_logger.handlers):
        root_logger.removeHandler(handler)

    handler = logging.StreamHandler(sys.stdout)
    if format_type == "json":
        handler.setFormatter(StructuredJsonFormatter())
    else:
        text_fmt = "%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
        handler.setFormatter(logging.Formatter(text_fmt))

    root_logger.addHandler(handler)

    # Suppress overly chatty external libraries
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    logging.getLogger("passlib").setLevel(logging.ERROR)
