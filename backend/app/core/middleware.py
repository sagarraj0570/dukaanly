"""
Request Correlation & Observability Middleware for Dukaanly (Stage 9).

Responsibilities:
- Inbound extraction and fallback generation of unique Request ID and Correlation ID.
- Propagation across async ContextVars for structured logging.
- Outbound header injection (X-Request-ID, X-Correlation-ID).
- Latency measurement and structured HTTP access logging.
"""

import time
import uuid
import logging
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import Response

from app.core.logging_config import set_request_id, set_correlation_id, get_request_id, get_correlation_id

logger = logging.getLogger("app.access")

# High-frequency endpoints to suppress from INFO-level access logging
SILENT_PATHS = {"/api/v1/health/live"}


class RequestCorrelationMiddleware(BaseHTTPMiddleware):
    """
    Middleware that establishes and propagates end-to-end request correlation identifiers.
    """

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # 1. Extract or generate Request ID
        incoming_req_id = request.headers.get("X-Request-ID")
        request_id = incoming_req_id if (incoming_req_id and len(incoming_req_id) <= 64) else uuid.uuid4().hex

        # 2. Extract or inherit Correlation ID
        incoming_corr_id = request.headers.get("X-Correlation-ID")
        correlation_id = incoming_corr_id if (incoming_corr_id and len(incoming_corr_id) <= 64) else request_id

        # 3. Store in ContextVars for this request context
        set_request_id(request_id)
        set_correlation_id(correlation_id)

        # Store in request state for downstream handlers
        request.state.request_id = request_id
        request.state.correlation_id = correlation_id

        start_time = time.perf_counter()
        status_code = 500

        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            duration_ms = round((time.perf_counter() - start_time) * 1000, 2)
            logger.error(
                f"Request failed: {request.method} {request.url.path} ({duration_ms}ms) - {exc}",
                exc_info=True,
                extra={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "http_method": request.method,
                    "route": request.url.path,
                    "status_code": 500,
                    "duration_ms": duration_ms,
                },
            )
            raise exc

        duration_ms = round((time.perf_counter() - start_time) * 1000, 2)

        # 4. Inject correlation headers in response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = correlation_id

        # 5. Emit structured access log
        path = request.url.path
        if path not in SILENT_PATHS:
            log_level = logging.INFO
            if status_code >= 500:
                log_level = logging.ERROR
            elif status_code >= 400:
                log_level = logging.WARNING

            logger.log(
                log_level,
                f"{request.method} {path} {status_code} ({duration_ms}ms)",
                extra={
                    "request_id": request_id,
                    "correlation_id": correlation_id,
                    "http_method": request.method,
                    "route": path,
                    "status_code": status_code,
                    "duration_ms": duration_ms,
                    "client_ip": request.client.host if request.client else "unknown",
                },
            )

        return response
