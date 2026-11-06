"""
Centralized Error Handling & Exception Translation for Dukaanly (Stage 9).

Enforces:
- Consistent JSON error response payloads with request correlation IDs.
- Secure sanitization preventing leakage of stack traces, SQL strings, or credentials.
- Appropriate HTTP status preservation (400, 401, 403, 404, 409, 422, 429, 500, 503).
- Structured logging of server errors and unhandled exceptions.
"""

import logging
from typing import Any, Dict, Optional
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError, OperationalError, DBAPIError
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging_config import get_request_id

logger = logging.getLogger(__name__)


def _extract_request_id(request: Request) -> Optional[str]:
    state = getattr(request, "state", None)
    req_id = getattr(state, "request_id", None) if state else None
    if isinstance(req_id, str) and req_id:
        return req_id
    ctx_id = get_request_id()
    if isinstance(ctx_id, str) and ctx_id:
        return ctx_id
    return None


def _build_error_payload(detail: Any, request_id: str | None) -> Dict[str, Any]:
    """Helper to assemble a consistent error payload containing the correlation request_id."""
    payload: Dict[str, Any] = {
        "detail": detail,
    }
    if request_id:
        payload["request_id"] = request_id
    return payload


async def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    """Handles standard HTTPExceptions, preserving status codes and headers with request ID."""
    req_id = _extract_request_id(request)
    headers = dict(exc.headers) if exc.headers else {}
    if req_id:
        headers["X-Request-ID"] = req_id

    content = _build_error_payload(exc.detail, req_id)
    return JSONResponse(
        status_code=exc.status_code,
        content=content,
        headers=headers,
    )


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    """Handles Pydantic request validation errors, returning structured 422 with correlation context."""
    req_id = _extract_request_id(request)
    headers = {"X-Request-ID": req_id} if req_id else {}

    # Format errors cleanly
    clean_errors = []
    for err in exc.errors():
        clean_errors.append({
            "loc": err.get("loc", []),
            "msg": err.get("msg", ""),
            "type": err.get("type", ""),
        })

    logger.warning(
        f"Validation error for {request.method} {request.url.path}: {len(clean_errors)} field errors",
        extra={"request_id": req_id, "route": request.url.path, "errors": clean_errors},
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=_build_error_payload(clean_errors, req_id),
        headers=headers,
    )


async def database_exception_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    """
    Handles database errors (e.g. connection drops, pool exhaustion, statement timeouts).
    Never exposes internal table names, SQL queries, or connection strings to clients.
    """
    req_id = _extract_request_id(request)
    headers = {"X-Request-ID": req_id} if req_id else {}

    is_connectivity = isinstance(exc, (OperationalError, DBAPIError))
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE if is_connectivity else status.HTTP_500_INTERNAL_SERVER_ERROR

    logger.error(
        f"Database failure on {request.method} {request.url.path}: {exc.__class__.__name__}",
        exc_info=True,
        extra={"request_id": req_id, "route": request.url.path, "db_error_type": exc.__class__.__name__},
    )

    detail = "Database service temporarily unavailable" if is_connectivity else "Database operation failed"
    content = _build_error_payload(detail, req_id)
    if settings.DEBUG and settings.APP_ENV != "production":
        content["debug"] = str(exc)

    return JSONResponse(
        status_code=status_code,
        content=content,
        headers=headers,
    )


async def redis_exception_handler(request: Request, exc: RedisError) -> JSONResponse:
    """Handles Redis errors gracefully, returning controlled HTTP 503."""
    req_id = _extract_request_id(request)
    headers = {"X-Request-ID": req_id} if req_id else {}

    logger.error(
        f"Redis cache/broker error on {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"request_id": req_id, "route": request.url.path},
    )

    content = _build_error_payload("Cache or messaging service temporarily unavailable", req_id)
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=content,
        headers=headers,
    )


async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Fallback handler for unhandled exceptions, returning sanitized 500 with correlation context."""
    req_id = _extract_request_id(request)
    headers = {"X-Request-ID": req_id} if req_id else {}

    logger.error(
        f"Unhandled server error for {request.method} {request.url.path}: {exc}",
        exc_info=True,
        extra={"request_id": req_id, "route": request.url.path},
    )

    content = _build_error_payload("Internal server error", req_id)
    if settings.DEBUG and settings.APP_ENV != "production":
        content["debug"] = str(exc)

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=content,
        headers=headers,
    )
