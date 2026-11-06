import asyncio
import logging
from typing import AsyncGenerator, Dict, Any
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=settings.DEBUG,
    future=True,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_timeout=settings.DB_POOL_TIMEOUT,
    pool_recycle=settings.DB_POOL_RECYCLE,
    pool_pre_ping=settings.DB_POOL_PRE_PING,
    connect_args={"timeout": settings.DB_CONNECT_TIMEOUT},
)

async_session_maker = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """
    FastAPI dependency that provides an async database session.
    Guarantees clean transaction rollback on exceptions or cancellations,
    and returns connection promptly to the pool.
    """
    async with async_session_maker() as session:
        try:
            yield session
        except Exception:
            try:
                await session.rollback()
            except Exception as rb_err:
                logger.warning("Error during session rollback: %s", rb_err)
            raise


def get_db_pool_status() -> Dict[str, Any]:
    """Returns real-time connection pool utilization metrics for operational diagnostics."""
    try:
        pool = getattr(engine, "sync_engine", engine).pool
        return {
            "size": pool.size(),
            "pool_size": pool.size(),
            "checked_in": pool.checkedin(),
            "checked_out": pool.checkedout(),
            "overflow": pool.overflow(),
            "total_connections": pool.checkedin() + pool.checkedout(),
            "pre_ping": settings.DB_POOL_PRE_PING,
            "recycle_seconds": settings.DB_POOL_RECYCLE,
        }
    except Exception as exc:
        return {"error": str(exc)}


async def check_db_connection(timeout: float = 2.0) -> bool:
    """
    Check if PostgreSQL is reachable within a strict timeout.
    Never hangs indefinitely and never leaks credentials or internal exceptions.
    """
    async def _ping() -> bool:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        return True

    try:
        return await asyncio.wait_for(_ping(), timeout=timeout)
    except asyncio.TimeoutError:
        logger.error("PostgreSQL health check timed out after %.1fs", timeout)
        return False
    except Exception as exc:
        logger.error("PostgreSQL health check failed: %s", exc.__class__.__name__)
        return False


