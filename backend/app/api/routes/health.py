import time
from typing import Optional, Dict, Any
from fastapi import APIRouter, Response, Request, Depends, status
from pydantic import BaseModel, ConfigDict
from app.db.session import check_db_connection, get_db_pool_status
from app.core.redis import check_redis_connection, get_redis_status
from app.core.celery_app import get_celery_status
from app.websockets.manager import manager
from app.core.config import settings
from app.models.user import User, UserRole
from app.api.dependencies import require_role

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    
class ReadinessResponse(BaseModel):
    status: str
    database: bool
    redis: bool
    configuration: bool = True

    model_config = ConfigDict(extra="ignore")

class RoutingHealthResponse(BaseModel):
    status: str
    provider: str
    base_url: str
    details: str

@router.get("/live", response_model=HealthResponse)
async def liveness_check():
    """Verify that the FastAPI process is alive and responsive."""
    return {"status": "ok"}

@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response):
    """
    Verify that mandatory dependencies (PostgreSQL, Redis, Core Config) are ready.
    Bounded by strict timeouts; never hangs and never exposes credentials.
    """
    db_ok = await check_db_connection(timeout=2.5)
    redis_ok = await check_redis_connection(timeout=2.5)
    config_ok = bool(settings.JWT_SECRET_KEY and settings.database_url)
    
    is_ready = db_ok and redis_ok and config_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return {
        "status": "ready" if is_ready else "unavailable",
        "database": db_ok,
        "redis": redis_ok,
        "configuration": config_ok,
    }

@router.get("/routing", response_model=RoutingHealthResponse)
async def routing_health_check(response: Response):
    """Verify routing infrastructure health without exposing sensitive credentials."""
    from app.services.osrm import osrm_service
    health_info = await osrm_service.check_routing_health()
    if health_info.get("status") != "healthy":
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return health_info

@router.get("/diagnostics")
async def operational_diagnostics(
    request: Request,
    current_user: User = Depends(require_role(UserRole.admin)),
) -> Dict[str, Any]:
    """
    Lightweight operational diagnostics endpoint (Stage 9).
    Strictly RBAC-restricted to administrators; zero PII and zero secret leakage.
    Provides real-time database pool metrics, Redis status, Celery telemetry, and WebSocket counts.
    """
    started_at = getattr(request.app.state, "started_at", None)
    uptime_seconds = round(time.time() - started_at, 2) if started_at else 0.0

    return {
        "status": "healthy",
        "app_name": settings.APP_NAME,
        "app_version": settings.APP_VERSION,
        "environment": settings.APP_ENV,
        "uptime_seconds": uptime_seconds,
        "database": {
            "status": "connected" if await check_db_connection(timeout=3.0) else "disconnected",
            "pool": get_db_pool_status(),
        },
        "redis": await get_redis_status(),
        "celery": get_celery_status(),
        "websockets": {
            "active_connections": manager.get_total_connections(),
            "active_deliveries_tracked": len(manager.get_active_delivery_ids()),
        },
    }

