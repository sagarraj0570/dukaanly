import logging
import redis.asyncio as redis
from app.core.config import settings

logger = logging.getLogger(__name__)

async def check_redis_connection() -> bool:
    """Check if Redis is reachable."""
    try:
        # Create a client for the health check
        client = redis.from_url(settings.REDIS_URL)
        await client.ping()
        await client.aclose()
        return True
    except Exception as e:
        logger.error(f"Redis connection failed: {e}")
        return False
