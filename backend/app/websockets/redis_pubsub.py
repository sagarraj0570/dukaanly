import json
import logging
import asyncio
import redis.asyncio as redis
from app.core.config import settings
from app.websockets.manager import manager

logger = logging.getLogger(__name__)

# Global redis pool
_redis_pool = None

async def get_redis_client() -> redis.Redis:
    global _redis_pool
    if _redis_pool is None:
        _redis_pool = redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_pool

def get_delivery_channel(delivery_id: str) -> str:
    return f"dukaanly:delivery:{delivery_id}"

async def publish_delivery_event(delivery_id: str, event_data: dict):
    """Publish an event to the Redis channel for a specific delivery."""
    try:
        client = await get_redis_client()
        channel = get_delivery_channel(delivery_id)
        await client.publish(channel, json.dumps(event_data))
    except Exception as e:
        logger.error(f"Failed to publish to redis channel {get_delivery_channel(delivery_id)}: {e}")
        # We don't raise here because Redis failure shouldn't fail the PostgreSQL transaction/flow.

async def subscribe_delivery_channel(delivery_id: str, stop_event: asyncio.Event):
    """
    Subscribe to a delivery channel and broadcast messages to the ConnectionManager.
    Runs as a background task until stop_event is set.
    """
    channel = get_delivery_channel(delivery_id)
    try:
        client = await get_redis_client()
        pubsub = client.pubsub()
        await pubsub.subscribe(channel)
        logger.info(f"Subscribed to redis channel: {channel}")
        
        while not stop_event.is_set():
            message = await pubsub.get_message(ignore_subscribe_messages=True, timeout=1.0)
            if message and message["type"] == "message":
                try:
                    data = json.loads(message["data"])
                    await manager.broadcast(delivery_id, data)
                except json.JSONDecodeError:
                    logger.error(f"Invalid JSON received on channel {channel}")
                except Exception as e:
                    logger.error(f"Error broadcasting message from {channel}: {e}")
                    
    except Exception as e:
        logger.error(f"Redis PubSub error on channel {channel}: {e}")
    finally:
        try:
            if 'pubsub' in locals():
                await pubsub.unsubscribe(channel)
                await pubsub.close()
        except Exception:
            pass
        logger.info(f"Unsubscribed from redis channel: {channel}")
