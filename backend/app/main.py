from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.api.routes import health, auth, shops

def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description="Backend API for Dukaanly Marketplace",
        openapi_url=f"{settings.API_PREFIX}/openapi.json" if settings.DEBUG else None,
        docs_url=f"{settings.API_PREFIX}/docs" if settings.DEBUG else None,
        redoc_url=f"{settings.API_PREFIX}/redoc" if settings.DEBUG else None,
    )

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

    # Register exception handlers
    from app.core.exceptions import global_exception_handler
    app.add_exception_handler(Exception, global_exception_handler)

    return app

app = create_app()
