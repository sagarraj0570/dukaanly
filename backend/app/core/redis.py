import asyncio
import logging
from typing import Optional
from urllib.parse import urlsplit, urlunsplit
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Optional[redis.Redis] = None
_redis_client_loop: Optional[asyncio.AbstractEventLoop] = None


def mask_redis_url(url: str) -> str:
    """Mask credentials in a Redis URL for safe logging and telemetry."""
    if not url:
        return ""
    try:
        parsed = urlsplit(url)
        if parsed.password:
            user = parsed.username or ""
            user_part = f"{user}:***" if user else ":***"
            host = parsed.hostname or ""
            port = f":{parsed.port}" if parsed.port else ""
            netloc = f"{user_part}@{host}{port}"
            return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))
        return url
    except Exception:
        return "redis://***"


async def get_redis_client(decode_responses: bool = True) -> redis.Redis:
    """
    Return a shared async Redis client singleton.
    Safely re-initializes client if running in a new asyncio event loop (e.g. across tests).
    """
    global _redis_client, _redis_client_loop
    try:
        current_loop = asyncio.get_running_loop()
    except RuntimeError:
        current_loop = None

    # If the active loop changed (e.g. pytest-asyncio per-test loop), reset singleton
    if _redis_client is not None and current_loop is not None and _redis_client_loop != current_loop:
        try:
            # Avoid awaiting previous client if its loop is closed
            pass
        except Exception:
            pass
        _redis_client = None
        _redis_client_loop = None

    if _redis_client is None:
        _redis_client = redis.from_url(
            settings.REDIS_URL,
            decode_responses=decode_responses,
            socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT,
            socket_timeout=settings.REDIS_SOCKET_TIMEOUT,
            max_connections=settings.REDIS_MAX_CONNECTIONS,
        )
        _redis_client_loop = current_loop
    return _redis_client


async def close_redis_client() -> None:
    """Close the shared Redis client and reset singleton."""
    global _redis_client, _redis_client_loop
    client = _redis_client
    _redis_client = None
    _redis_client_loop = None
    if client is not None:
        try:
            await client.aclose()
        except Exception as exc:
            logger.debug("Suppressed error closing Redis client: %s", exc)


async def check_redis_connection(timeout: float = 2.0) -> bool:
    """Check if Redis is reachable within a strict timeout, never leaking credentials on failure."""
    try:
        client = await get_redis_client()
        await asyncio.wait_for(client.ping(), timeout=timeout)
        return True
    except asyncio.TimeoutError:
        logger.error(
            "Redis health check timed out after %.1fs for URL '%s'",
            timeout,
            mask_redis_url(settings.REDIS_URL),
        )
        return False
    except Exception as e:
        logger.error(
            "Redis connection failed for URL '%s': %s",
            mask_redis_url(settings.REDIS_URL),
            e.__class__.__name__,
        )
        return False


async def get_redis_status() -> dict:
    """Return sanitized operational metrics for Redis dependency."""
    import time
    t0 = time.perf_counter()
    try:
        is_ok = await check_redis_connection(timeout=2.0)
        latency_ms = round((time.perf_counter() - t0) * 1000, 2) if is_ok else None
        return {
            "connected": is_ok,
            "latency_ms": latency_ms,
            "max_connections": settings.REDIS_MAX_CONNECTIONS,
            "url_masked": mask_redis_url(settings.REDIS_URL),
            "socket_timeout": settings.REDIS_SOCKET_TIMEOUT,
            "connect_timeout": settings.REDIS_SOCKET_CONNECT_TIMEOUT,
        }
    except Exception as exc:
        return {"connected": False, "latency_ms": None, "error": exc.__class__.__name__}
