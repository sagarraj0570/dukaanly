import logging
from fastapi import Request
from fastapi.responses import JSONResponse
from app.core.config import settings

logger = logging.getLogger(__name__)

async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled server error for {request.method} {request.url}: {exc}", exc_info=settings.DEBUG)
    
    content = {"detail": "Internal server error"}
    if settings.DEBUG:
        content["debug"] = str(exc)
        
    return JSONResponse(
        status_code=500,
        content=content,
    )
