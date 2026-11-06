"""
Stage 9: Production Reliability, Observability & Operational Resilience Tests.

Validates:
1. Liveness vs. Readiness endpoints with strict bounded timeouts and failure injection.
2. PostgreSQL connection pool resilience, pool metrics, and safe session rollback/cleanup on error.
3. Redis resilience, bounded timeouts, health check latency, and sliding window rate limiter fallback.
4. Celery worker reliability, late ACKs, prefetch limit, soft time limit handling, and DB error retries.
5. JSON structured logging, context-propagated request/correlation IDs, and sensitive field redaction.
6. Centralized sanitized error handling preventing stack trace or internal SQL/credential leakage.
7. Graceful WebSocket shutdown with RFC 6455 1001 Going Away close codes and listener task cleanup.
8. Operational diagnostics endpoint (/api/v1/health/diagnostics) with strict admin RBAC and comprehensive metrics.
"""
import asyncio
import json
import logging
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, OperationalError, IntegrityError

from app.api.dependencies import require_role
from app.core.celery_app import celery_app, get_celery_status
from app.core.config import settings
from app.core.exceptions import (
    database_exception_handler,
    global_exception_handler,
    redis_exception_handler,
)
from app.core.logging_config import (
    StructuredJsonFormatter,
    set_correlation_id,
    set_request_id,
    sanitize_sensitive_data,
)
from app.core.redis import check_redis_connection, get_redis_client, get_redis_status
from app.db.session import (
    async_session_maker,
    check_db_connection,
    engine,
    get_db,
    get_db_pool_status,
)
from app.models.user import User, UserRole
from app.tasks.delivery_eta import reconcile_active_deliveries_eta
from app.websockets.manager import ConnectionManager, manager
from celery.exceptions import SoftTimeLimitExceeded
from fastapi import HTTPException, Request, Response, status

pytestmark = pytest.mark.asyncio


# ==============================================================================
# Helper to create an authenticated user with a specific role
# ==============================================================================
async def _create_user_with_role(async_client: AsyncClient, role: UserRole, prefix: str) -> dict:
    uid = uuid.uuid4().hex[:8]
    email = f"{prefix}_{uid}@example.com"
    password = "PassWord123"

    reg_resp = await async_client.post(
        "/api/v1/auth/register",
        json={"name": f"User {role.value}", "email": email, "password": password},
    )
    assert reg_resp.status_code == 201

    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET role = :r WHERE email = :e"),
            {"r": role.value, "e": email},
        )
        await conn.commit()

    login_resp = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    return {"email": email, "token": token, "role": role.value}


# ==============================================================================
# 1. LIVENESS VS. READINESS ENDPOINTS
# ==============================================================================
async def test_liveness_endpoint_always_succeeds_without_dependencies(async_client: AsyncClient):
    """Liveness probe must return 200 even if database and Redis are completely down."""
    with patch("app.api.routes.health.check_db_connection", new_callable=AsyncMock) as mock_db, \
         patch("app.api.routes.health.check_redis_connection", new_callable=AsyncMock) as mock_redis:
        mock_db.return_value = False
        mock_redis.return_value = False

        resp = await async_client.get("/api/v1/health/live")
        assert resp.status_code == 200
        data = resp.json()
        assert data == {"status": "ok"}
        # Proves liveness does NOT call or block on DB or Redis
        mock_db.assert_not_called()
        mock_redis.assert_not_called()


async def test_readiness_endpoint_all_healthy(async_client: AsyncClient):
    """Readiness probe returns 200 when all core dependencies (DB, Redis, Config) are healthy."""
    resp = await async_client.get("/api/v1/health/ready")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ready"
    assert data["database"] is True
    assert data["redis"] is True
    assert data["configuration"] is True


async def test_readiness_endpoint_fails_when_db_down(async_client: AsyncClient):
    """Readiness probe returns 503 and marks database False when DB connection fails."""
    with patch("app.api.routes.health.check_db_connection", new_callable=AsyncMock) as mock_db:
        mock_db.return_value = False

        resp = await async_client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["database"] is False


async def test_readiness_endpoint_fails_when_redis_down(async_client: AsyncClient):
    """Readiness probe returns 503 and marks redis False when Redis connection fails."""
    with patch("app.api.routes.health.check_redis_connection", new_callable=AsyncMock) as mock_redis:
        mock_redis.return_value = False

        resp = await async_client.get("/api/v1/health/ready")
        assert resp.status_code == 503
        data = resp.json()
        assert data["status"] == "unavailable"
        assert data["redis"] is False


async def test_readiness_timeout_bounded():
    """Health check helpers must enforce strict bounded timeouts and not hang indefinitely."""
    # Test DB check timeout with near-zero timeout against slow simulation
    async def slow_ping():
        await asyncio.sleep(0.5)
        return True

    with patch("asyncio.wait_for", side_effect=asyncio.TimeoutError):
        db_ok = await check_db_connection(timeout=0.01)
        assert db_ok is False

    # Test Redis check timeout
    fake_client = MagicMock()
    fake_client.ping = AsyncMock(side_effect=asyncio.TimeoutError)
    with patch("app.core.redis.get_redis_client", return_value=fake_client):
        redis_ok = await check_redis_connection(timeout=0.01)
        assert redis_ok is False


# ==============================================================================
# 2. POSTGRESQL CONNECTION POOL RESILIENCE & SESSION CLEANUP
# ==============================================================================
async def test_database_connection_pool_metrics():
    """Pool status helper must return accurate metrics without throwing exceptions."""
    pool_status = get_db_pool_status()
    assert "pool_size" in pool_status
    assert "checked_in" in pool_status
    assert "checked_out" in pool_status
    assert "overflow" in pool_status
    assert "total_connections" in pool_status

    assert pool_status["pool_size"] == settings.DB_POOL_SIZE
    assert pool_status["checked_out"] >= 0
    assert pool_status["checked_in"] >= 0


async def test_database_session_cleanup_and_rollback_on_error():
    """Verify that get_db() rolls back transactions and always closes sessions on error or cancellation."""
    session_generator = get_db()
    session = await anext(session_generator)

    # Spy on rollback and close
    with patch.object(session, "rollback", wraps=session.rollback) as spy_rollback, \
         patch.object(session, "close", wraps=session.close) as spy_close:
        try:
            # Simulate an unhandled exception thrown in route handler
            await session_generator.athrow(RuntimeError("Simulated unhandled route failure"))
        except RuntimeError:
            pass

        assert spy_rollback.called, "Database session MUST be rolled back on error"
        assert spy_close.called, "Database session MUST be closed in finally block"


async def test_database_session_cleanup_on_success():
    """Verify that get_db() closes cleanly on normal route completion."""
    session_generator = get_db()
    session = await anext(session_generator)

    with patch.object(session, "close", wraps=session.close) as spy_close:
        try:
            await anext(session_generator)
        except StopAsyncIteration:
            pass

        assert spy_close.called, "Database session MUST close on exit"


# ==============================================================================
# 3. REDIS RESILIENCE & STATUS REPORTING
# ==============================================================================
async def test_redis_status_reporting():
    """Redis status helper returns real-time connection telemetry and latency."""
    status = await get_redis_status()
    assert status["connected"] is True
    assert "latency_ms" in status
    assert status["latency_ms"] is not None
    assert status["latency_ms"] >= 0.0
    assert status["max_connections"] == settings.REDIS_MAX_CONNECTIONS


async def test_redis_status_reporting_failure():
    """Redis status helper safely captures and returns disconnected status when Redis fails."""
    fake_client = MagicMock()
    fake_client.ping = AsyncMock(side_effect=ConnectionError("Connection refused by test mock"))
    with patch("app.core.redis.get_redis_client", return_value=fake_client):
        status = await get_redis_status()
        assert status["connected"] is False
        assert status["latency_ms"] is None


# ==============================================================================
# 4. CELERY WORKER & BEAT RELIABILITY CONFIGURATION
# ==============================================================================
async def test_celery_reliability_configuration():
    """Verify Celery is configured for production resilience."""
    conf = celery_app.conf
    assert conf.task_acks_late is True, "task_acks_late MUST be True to prevent task loss on worker crash"
    assert conf.task_reject_on_worker_lost is True, "task_reject_on_worker_lost MUST be True"
    assert conf.worker_prefetch_multiplier == 1, "worker_prefetch_multiplier MUST be 1 for fair dispatch"
    assert conf.task_soft_time_limit == 240, "task_soft_time_limit MUST be configured"
    assert conf.broker_connection_retry_on_startup is True

    # Telemetry report
    status = get_celery_status()
    assert status["task_acks_late"] is True
    assert status["worker_prefetch_multiplier"] == 1
    assert status["broker_url_configured"] is True
    # Password must not be exposed in celery status
    assert "password" not in status.get("broker_transport", "").lower()


async def test_celery_task_retry_configuration():
    """Verify Celery task delivery ETA retries on database operational errors and handles soft limits."""
    assert issubclass(OperationalError, reconcile_active_deliveries_eta.autoretry_for)
    assert issubclass(DBAPIError, reconcile_active_deliveries_eta.autoretry_for)
    assert reconcile_active_deliveries_eta.retry_backoff is True
    assert reconcile_active_deliveries_eta.max_retries == 3


async def test_celery_task_soft_time_limit_handled():
    """Verify tasks catch SoftTimeLimitExceeded and return fallback count 0 rather than crashing unhandled."""
    with patch("app.tasks.delivery_eta._reconcile_active_deliveries_eta_async", side_effect=SoftTimeLimitExceeded):
        res = reconcile_active_deliveries_eta()
        assert res == 0


# ==============================================================================
# 5. REQUEST CORRELATION & STRUCTURED JSON LOGGING
# ==============================================================================
async def test_request_id_injected_when_missing(async_client: AsyncClient):
    """When client sends no X-Request-ID, middleware must generate and return a valid UUID hex."""
    resp = await async_client.get("/api/v1/health/ready")
    req_id = resp.headers.get("x-request-id")
    assert req_id is not None
    # Validate it is a valid UUID hex
    parsed_uuid = uuid.UUID(req_id)
    assert parsed_uuid.hex == req_id


async def test_request_id_preserved_when_provided(async_client: AsyncClient):
    """When client provides X-Request-ID, middleware preserves and echoes it."""
    custom_id = "custom-req-trace-4242"
    resp = await async_client.get("/api/v1/health/ready", headers={"X-Request-ID": custom_id})
    assert resp.headers.get("x-request-id") == custom_id


async def test_correlation_id_propagated(async_client: AsyncClient):
    """When client provides X-Correlation-ID, middleware preserves and echoes it."""
    corr_id = "corr-upstream-8888"
    resp = await async_client.get("/api/v1/health/ready", headers={"X-Correlation-ID": corr_id})
    assert resp.headers.get("x-correlation-id") == corr_id


async def test_sensitive_data_sanitization():
    """Ensure passwords, tokens, and authorization headers are never logged in plaintext."""
    sensitive_dict = {
        "email": "user@dukaanly.com",
        "password": "SuperSecretPassword123",
        "access_token": "eyJhbGciOi...",
        "credit_card": "4111222233334444",
        "nested": {
            "api_key": "sk-secret-key-123",
            "normal_field": "visible_value",
        },
    }
    sanitized = sanitize_sensitive_data(sensitive_dict)
    assert sanitized["email"] == "user@dukaanly.com"
    assert sanitized["password"] == "[REDACTED]"
    assert sanitized["access_token"] == "[REDACTED]"
    assert sanitized["credit_card"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["normal_field"] == "visible_value"


async def test_structured_json_formatter():
    """Ensure StructuredJsonFormatter outputs valid JSON containing correlation context."""
    formatter = StructuredJsonFormatter()
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=10,
        msg="Test event message with sensitive field",
        args=(),
        exc_info=None,
    )

    set_request_id("req-test-1111")
    set_correlation_id("corr-test-2222")

    formatted = formatter.format(record)
    parsed = json.loads(formatted)

    assert parsed["logger"] == "test_logger"
    assert parsed["level"] == "INFO"
    assert parsed["message"] == "Test event message with sensitive field"
    assert parsed["request_id"] == "req-test-1111"
    assert parsed["correlation_id"] == "corr-test-2222"
    assert "timestamp" in parsed


# ==============================================================================
# 6. CENTRALIZED SANITIZED EXCEPTION HANDLING
# ==============================================================================
async def test_global_exception_handler_sanitizes_500():
    """Unhandled exceptions must return sanitized 500 without leaking stack traces or filenames."""
    req = MagicMock(spec=Request)
    req.method = "POST"
    req.url.path = "/api/v1/orders"
    req.state.request_id = "req-sanitized-500"

    set_request_id("req-sanitized-500")

    exc = RuntimeError("Database password leaked in trace: secret_pass_123")
    resp = await global_exception_handler(req, exc)

    assert resp.status_code == status.HTTP_500_INTERNAL_SERVER_ERROR
    content = json.loads(resp.body.decode())

    assert content["detail"] == "Internal server error"
    assert content["request_id"] == "req-sanitized-500"
    assert "secret_pass_123" not in str(content)
    assert "RuntimeError" not in str(content)


async def test_database_exception_handler_sanitizes_operational_error():
    """Database exceptions must return 503 or sanitized 500 without leaking raw SQL queries."""
    req = MagicMock(spec=Request)
    req.method = "POST"
    req.url.path = "/api/v1/checkout"
    req.state.request_id = "req-db-err"

    set_request_id("req-db-err")

    raw_sql = "SELECT * FROM users WHERE password_hash = 'secret'"
    db_exc = OperationalError(statement=raw_sql, params={}, orig=Exception("Connection lost"))
    resp = await database_exception_handler(req, db_exc)

    assert resp.status_code in (status.HTTP_503_SERVICE_UNAVAILABLE, status.HTTP_500_INTERNAL_SERVER_ERROR)
    content = json.loads(resp.body.decode())

    assert "password_hash" not in str(content)
    assert "SELECT *" not in str(content)
    assert content["request_id"] == "req-db-err"


# ==============================================================================
# 7. WEBSOCKET MANAGER GRACEFUL SHUTDOWN
# ==============================================================================
async def test_websocket_manager_graceful_shutdown():
    """Verify close_all cleanly disconnects active WebSockets with 1001 status code."""
    ws_mgr = ConnectionManager()

    # Create mock WebSocket instances
    mock_ws_rider = AsyncMock()
    mock_ws_cust = AsyncMock()

    await ws_mgr.connect(mock_ws_rider, delivery_id="delivery-1")
    await ws_mgr.connect(mock_ws_cust, delivery_id="delivery-2")

    assert ws_mgr.get_total_connections() == 2

    # Invoke graceful shutdown
    await ws_mgr.close_all(code=1001, reason="Server shutting down")

    # Both connections must be closed with 1001
    mock_ws_rider.close.assert_awaited_once_with(code=1001, reason="Server shutting down")
    mock_ws_cust.close.assert_awaited_once_with(code=1001, reason="Server shutting down")

    # Connection pools must now be empty
    assert ws_mgr.get_total_connections() == 0


# ==============================================================================
# 8. OPERATIONAL DIAGNOSTICS ENDPOINT (RBAC & TELEMETRY)
# ==============================================================================
async def test_diagnostics_unauthenticated_returns_401(async_client: AsyncClient):
    """Unauthenticated requests to /diagnostics must be rejected with 401."""
    resp = await async_client.get("/api/v1/health/diagnostics")
    assert resp.status_code == status.HTTP_401_UNAUTHORIZED


async def test_diagnostics_customer_forbidden_returns_403(async_client: AsyncClient):
    """Customer role requesting /diagnostics must be rejected with 403."""
    user_info = await _create_user_with_role(async_client, UserRole.customer, "diag_cust")
    resp = await async_client.get(
        "/api/v1/health/diagnostics",
        headers={"Authorization": f"Bearer {user_info['token']}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "admin role" in resp.json()["detail"].lower()


async def test_diagnostics_shop_owner_forbidden_returns_403(async_client: AsyncClient):
    """Shop owner role requesting /diagnostics must be rejected with 403."""
    user_info = await _create_user_with_role(async_client, UserRole.shop_owner, "diag_shop")
    resp = await async_client.get(
        "/api/v1/health/diagnostics",
        headers={"Authorization": f"Bearer {user_info['token']}"},
    )
    assert resp.status_code == status.HTTP_403_FORBIDDEN
    assert "admin role" in resp.json()["detail"].lower()


async def test_diagnostics_admin_success(async_client: AsyncClient):
    """Admin role requesting /diagnostics receives full operational telemetry without secrets."""
    admin_info = await _create_user_with_role(async_client, UserRole.admin, "diag_admin")
    resp = await async_client.get(
        "/api/v1/health/diagnostics",
        headers={"Authorization": f"Bearer {admin_info['token']}"},
    )
    assert resp.status_code == status.HTTP_200_OK
    data = resp.json()

    assert data["status"] == "healthy"
    assert data["app_name"] == settings.APP_NAME
    assert data["app_version"] == settings.APP_VERSION
    assert data["environment"] == settings.APP_ENV
    assert isinstance(data["uptime_seconds"], (int, float))

    # Verify database telemetry
    assert "database" in data
    assert data["database"]["status"] == "connected"
    assert "pool" in data["database"]
    assert data["database"]["pool"]["pool_size"] == settings.DB_POOL_SIZE

    # Verify Redis telemetry
    assert "redis" in data
    assert data["redis"]["connected"] is True
    assert data["redis"]["latency_ms"] is not None

    # Verify Celery telemetry
    assert "celery" in data
    assert data["celery"]["task_acks_late"] is True
    assert data["celery"]["worker_prefetch_multiplier"] == 1

    # Verify WebSocket telemetry
    assert "websockets" in data
    assert "active_connections" in data["websockets"]
    assert "active_deliveries_tracked" in data["websockets"]

    # Invariant: Zero credentials or secret keys exposed
    payload_str = json.dumps(data)
    assert "secret" not in payload_str.lower()
    assert "password" not in payload_str.lower()
    assert "jwt" not in payload_str.lower()
