from contextlib import asynccontextmanager
import logging
from pathlib import Path
import time
from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import Response
from sqlalchemy.exc import SQLAlchemyError
from redis.exceptions import RedisError

from app.core.config import settings
from app.core.logging_config import setup_logging
from app.core.middleware import RequestCorrelationMiddleware
from app.core.exceptions import (
    http_exception_handler,
    validation_exception_handler,
    database_exception_handler,
    redis_exception_handler,
    global_exception_handler,
)
from app.api.routes import health, auth, shops, products, cart, orders, payments, riders, deliveries, discovery, ai

logger = logging.getLogger("app.lifecycle")


class CachedStaticFiles(StaticFiles):
    """StaticFiles subclass that serves media assets with immutable caching headers."""
    def file_response(self, *args, **kwargs) -> Response:
        response = super().file_response(*args, **kwargs)
        response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. Application startup
    setup_logging()
    app.state.started_at = time.time()
    logger.info("Dukaanly application starting up (environment: %s)", settings.APP_ENV)

    # Pre-flight readiness verification
    from app.db.session import check_db_connection, engine
    from app.core.redis import check_redis_connection, close_redis_client
    from app.services.osrm import close_osrm_http_client
    from app.api.routes.ws_deliveries import close_all_delivery_ws_and_listeners

    db_ready = await check_db_connection(timeout=3.0)
    redis_ready = await check_redis_connection(timeout=3.0)
    logger.info("Startup dependency check: database=%s, redis=%s", db_ready, redis_ready)

    yield

    # 2. Graceful shutdown: bounded clean teardown of network & stateful resources
    logger.info("Dukaanly application shutting down gracefully...")
    try:
        await close_all_delivery_ws_and_listeners()
    except Exception as exc:
        logger.warning("Error closing WebSocket listeners on shutdown: %s", exc)

    try:
        await close_osrm_http_client()
    except Exception as exc:
        logger.warning("Error closing OSRM client on shutdown: %s", exc)

    try:
        await close_redis_client()
    except Exception as exc:
        logger.warning("Error closing Redis client on shutdown: %s", exc)

    try:
        await engine.dispose()
    except Exception as exc:
        logger.warning("Error disposing database engine on shutdown: %s", exc)

    logger.info("Graceful shutdown complete.")


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend API for Dukaanly Marketplace",
        openapi_url=f"{settings.API_PREFIX}/openapi.json" if settings.DEBUG else None,
        docs_url=f"{settings.API_PREFIX}/docs" if settings.DEBUG else None,
        redoc_url=f"{settings.API_PREFIX}/redoc" if settings.DEBUG else None,
        lifespan=lifespan,
    )

    # Correlation & Observability Middleware (registered first so it wraps all downstream handlers)
    app.add_middleware(RequestCorrelationMiddleware)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Register routers
    app.include_router(health.router, prefix=f"{settings.API_PREFIX}/health", tags=["Health"])
    app.include_router(auth.router, prefix=f"{settings.API_PREFIX}/auth", tags=["Auth"])
    app.include_router(shops.router, prefix=f"{settings.API_PREFIX}/shops", tags=["Shops"])
    app.include_router(discovery.router, prefix=f"{settings.API_PREFIX}/discovery", tags=["Discovery"])
    app.include_router(products.router, prefix=f"{settings.API_PREFIX}/products", tags=["Products"])
    app.include_router(cart.router, prefix=f"{settings.API_PREFIX}/cart", tags=["Cart"])
    app.include_router(orders.router, prefix=f"{settings.API_PREFIX}/orders", tags=["Orders"])
    app.include_router(payments.router, prefix=f"{settings.API_PREFIX}", tags=["Payments"])
    app.include_router(riders.router, prefix=f"{settings.API_PREFIX}/riders", tags=["Riders"])
    app.include_router(deliveries.router, prefix=f"{settings.API_PREFIX}/deliveries", tags=["Deliveries"])
    app.include_router(ai.router, prefix=f"{settings.API_PREFIX}/ai", tags=["AI"])
    
    from app.api.routes import ws_deliveries
    app.include_router(ws_deliveries.router, prefix=f"{settings.API_PREFIX}/ws/deliveries", tags=["WebSocket Deliveries"])

    # Register centralized exception handlers
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(SQLAlchemyError, database_exception_handler)
    app.add_exception_handler(RedisError, redis_exception_handler)
    app.add_exception_handler(Exception, global_exception_handler)

    # Static media files with immutable caching
    media_dir = (Path(__file__).resolve().parent.parent / "data" / "media").resolve()
    media_dir.mkdir(parents=True, exist_ok=True)
    (media_dir / "products").mkdir(parents=True, exist_ok=True)
    app.mount("/static/media", CachedStaticFiles(directory=str(media_dir)), name="media")

    return app

app = create_app()
