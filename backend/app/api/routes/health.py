from fastapi import APIRouter, Response, status
from pydantic import BaseModel
from app.db.session import check_db_connection
from app.core.redis import check_redis_connection

router = APIRouter()

class HealthResponse(BaseModel):
    status: str
    
class ReadinessResponse(BaseModel):
    status: str
    database: bool
    redis: bool

@router.get("/live", response_model=HealthResponse)
async def liveness_check():
    """Verify that the FastAPI process is alive."""
    return {"status": "ok"}

@router.get("/ready", response_model=ReadinessResponse)
async def readiness_check(response: Response):
    """Verify that required infrastructure is reachable."""
    db_ok = await check_db_connection()
    redis_ok = await check_redis_connection()
    
    is_ready = db_ok and redis_ok
    if not is_ready:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        
    return {
        "status": "ready" if is_ready else "unavailable",
        "database": db_ok,
        "redis": redis_ok
    }
