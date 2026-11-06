"""
WebSocket endpoint for real-time delivery tracking and rider telematics.

Authentication & Authorization Architecture:
- Authentication: Token-based via query parameter `?token=<JWT>`. The JWT is validated
  against `settings.JWT_SECRET_KEY` using HS256. If the token is missing, expired, or invalid,
  the connection is immediately terminated with WebSocket close code `1008 (WS_1008_POLICY_VIOLATION)`.
- Authorization:
  - Customer: Only the user who placed the associated order (`delivery.order.customer_id == user.id`).
  - Shop Owner: Only the owner of the shop fulfilling the order (`delivery.order.shop.owner_id == user.id`).
  - Rider: Only the rider assigned to the active delivery (`delivery.rider.user_id == user.id`).
  - Admin: System administrators.
  Any connection request by an unassociated party is closed with code `1008`.
- Inbound Frame Hardening:
  - Max frame size: 64 KB (`MAX_WS_FRAME_SIZE_BYTES = 65536`). Exceeding frames close connection with code `1009`.
  - Schema validation: Pydantic models with `extra="forbid"` strictly validate all inbound frames.
  - Protocol versioning: Protocol versions are verified against `SUPPORTED_WS_PROTOCOL_VERSIONS`.
  - Privileged actions: Only the assigned rider can push location updates. The rider identity is
    derived entirely from server-side database state, never from client message fields.
"""
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, or_
from sqlalchemy.orm import joinedload
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from typing import Literal, Optional, Dict, Any
import uuid
import asyncio
import json
import logging
from datetime import datetime, timezone, timedelta

from app.db.session import async_session_maker
from app.core import security
from app.models.user import User
from app.models.delivery import Delivery, DeliveryStatus
from app.models.order import Order
from app.models.shop import Shop
from app.models.rider import RiderProfile
from app.websockets.manager import manager
from app.websockets.redis_pubsub import subscribe_delivery_channel, publish_delivery_event
from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

# Maximum inbound WebSocket frame size in bytes (64 KB)
MAX_WS_FRAME_SIZE_BYTES: int = 64 * 1024

# Supported protocol versions
SUPPORTED_WS_PROTOCOL_VERSIONS = {1}

# Strict inbound message schemas
class WsInboundPing(BaseModel):
    type: Literal["ping"]
    version: Optional[int] = 1

    model_config = ConfigDict(extra="forbid")

class WsInboundLocationUpdate(BaseModel):
    type: Literal["location_update"]
    version: Optional[int] = 1
    latitude: float = Field(..., ge=-90.0, le=90.0, description="Latitude coordinate between -90 and 90")
    longitude: float = Field(..., ge=-180.0, le=180.0, description="Longitude coordinate between -180 and 180")
    client_timestamp: Optional[datetime] = None

    model_config = ConfigDict(extra="forbid")

# Dictionary to track background listener tasks per delivery_id to prevent duplicates
# Key: delivery_id, Value: {"task": task, "stop_event": stop_event, "ref_count": int}
_delivery_listeners: Dict[str, Dict[str, Any]] = {}

async def _get_user_from_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = security.decode_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()
        if not user or not user.is_active:
            return None
        return user
    except Exception:
        return None

async def authorize_delivery_ws(user: User, delivery: Delivery) -> bool:
    """Authorize a user for a specific delivery channel."""
    # Rider: Must be the rider assigned to this delivery
    if user.role.value == "rider":
        if delivery.rider and delivery.rider.user_id == user.id:
            return True
        return False
        
    # Customer: Must be the purchaser of the associated order
    if user.role.value == "customer":
        if delivery.order and delivery.order.customer_id == user.id:
            return True
        return False
        
    # Shop Owner: Must be the owner of the fulfilling shop
    if user.role.value == "shop_owner":
        if delivery.order and delivery.order.shop and delivery.order.shop.owner_id == user.id:
            return True
        return False
        
    # Admin: System administrators
    if user.role.value == "admin":
        return True
        
    return False

def _start_listener_if_needed(delivery_id_str: str) -> None:
    """Ensure a Redis PubSub listener is running for the delivery channel."""
    entry = _delivery_listeners.get(delivery_id_str)
    if entry and not entry["task"].done():
        entry["ref_count"] += 1
    else:
        stop_event = asyncio.Event()
        task = asyncio.create_task(subscribe_delivery_channel(delivery_id_str, stop_event))
        _delivery_listeners[delivery_id_str] = {"task": task, "stop_event": stop_event, "ref_count": 1}

def _stop_listener_if_empty(delivery_id_str: str) -> None:
    """Stop the Redis PubSub listener if no more clients are connected."""
    if delivery_id_str in _delivery_listeners:
        _delivery_listeners[delivery_id_str]["ref_count"] -= 1
        if _delivery_listeners[delivery_id_str]["ref_count"] <= 0:
            entry = _delivery_listeners.pop(delivery_id_str, None)
            if entry:
                entry["stop_event"].set()


async def close_all_delivery_ws_and_listeners() -> None:
    """
    Cancels and cleanly awaits all active Redis PubSub listener tasks
    and disconnects all WebSockets during graceful shutdown.
    """
    # 1. Close all active WebSocket connections
    await manager.close_all(code=1001, reason="Server shutting down")

    # 2. Stop and await all background Redis PubSub listener tasks
    tasks_to_await = []
    for d_id, entry in list(_delivery_listeners.items()):
        entry["stop_event"].set()
        task = entry["task"]
        if not task.done():
            task.cancel()
            tasks_to_await.append(task)
    _delivery_listeners.clear()

    if tasks_to_await:
        await asyncio.gather(*tasks_to_await, return_exceptions=True)
    logger.info("Cleaned up all delivery WebSocket listeners during shutdown")

@router.websocket("/{delivery_id}")
async def delivery_websocket(
    websocket: WebSocket,
    delivery_id: uuid.UUID,
    token: str = Query(None),
):
    # 1. Early token validation
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return

    delivery_id_str = str(delivery_id)

    # 2. Authentication, Authorization & Snapshot Data Retrieval (Short-Lived Session)
    try:
        async with async_session_maker() as auth_db:
            try:
                user = await _get_user_from_token(token, auth_db)
                if not user:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
                    return

                stmt = (
                    select(Delivery)
                    .options(
                        joinedload(Delivery.order).joinedload(Order.shop),
                        joinedload(Delivery.rider)
                    )
                    .where(Delivery.id == delivery_id)
                )
                result = await auth_db.execute(stmt)
                delivery = result.scalar_one_or_none()
                
                if not delivery:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Delivery not found")
                    return

                is_authorized = await authorize_delivery_ws(user, delivery)
                if not is_authorized:
                    await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
                    return

                # Extract scalar values into local variables to avoid session detachment issues
                user_id = user.id
                user_role = user.role.value
                rider_id_str = str(delivery.rider_id) if delivery.rider_id else None
                
                is_assigned_rider = (
                    user_role == "rider"
                    and delivery.rider is not None
                    and delivery.rider.user_id == user_id
                )
                assigned_rider_profile_id = delivery.rider.id if delivery.rider else None

                rider_loc = None
                if delivery.rider and delivery.rider.location:
                    try:
                        from geoalchemy2.shape import to_shape
                        point = to_shape(delivery.rider.location)
                        rider_loc = {
                            "latitude": point.y,
                            "longitude": point.x,
                            "updated_at": delivery.rider.location_updated_at.isoformat() if delivery.rider.location_updated_at else None
                        }
                    except Exception as e:
                        logger.error(f"Error converting rider location to shape: {e}")

                eta_data = None
                if delivery.eta_calculated_at:
                    eta_data = {
                        "earliest_at": delivery.eta_earliest_at.isoformat() if delivery.eta_earliest_at else None,
                        "latest_at": delivery.eta_latest_at.isoformat() if delivery.eta_latest_at else None,
                        "remaining_seconds": delivery.eta_remaining_seconds or 0,
                        "source": delivery.eta_source or "unavailable",
                        "calculated_at": delivery.eta_calculated_at.isoformat() if delivery.eta_calculated_at else None,
                        "delay_reason": delivery.eta_delay_reason,
                    }

                snapshot = {
                    "event": "connection.ready",
                    "version": 1,
                    "delivery_id": delivery_id_str,
                    "data": {
                        "delivery_status": delivery.status.value,
                        "rider_id": rider_id_str,
                        "rider_location": rider_loc,
                        "eta": eta_data,
                    }
                }
            finally:
                # Guarantees that the read transaction is terminated on every exit path:
                # normal completion, early return (auth rejection), exception, or cancellation
                await auth_db.rollback()
    except Exception as e:
        logger.error(f"Database error during WebSocket connection handshake for delivery {delivery_id_str}: {e}", exc_info=True)
        await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Handshake database error")
        return

    # Database session is fully released and closed before accepting and entering loop
    await manager.connect(websocket, delivery_id_str)
    _start_listener_if_needed(delivery_id_str)

    last_update_time = None
    min_interval = getattr(settings, "RIDER_LOCATION_MIN_UPDATE_INTERVAL_SECONDS", 1.0)

    try:
        # Deliver initial connection snapshot
        try:
            await websocket.send_json(snapshot)
        except Exception as e:
            logger.debug(f"Failed to send connection.ready snapshot: {e}")

        while True:
            text_data = await websocket.receive_text()
            
            # Enforce frame size limit
            raw_bytes = text_data.encode("utf-8")
            if len(raw_bytes) > MAX_WS_FRAME_SIZE_BYTES:
                logger.warning(f"Frame size {len(raw_bytes)} bytes exceeded {MAX_WS_FRAME_SIZE_BYTES} bytes limit")
                await websocket.close(code=status.WS_1009_MESSAGE_TOO_BIG, reason="Message size exceeds limit")
                break

            # Parse JSON
            try:
                message = json.loads(text_data)
            except (json.JSONDecodeError, UnicodeDecodeError):
                await websocket.send_json({"event": "error", "message": "Invalid JSON format"})
                continue
                
            if not isinstance(message, dict):
                await websocket.send_json({"event": "error", "message": "Message payload must be a JSON object"})
                continue

            # Validate protocol version
            client_version = message.get("version", 1)
            if client_version not in SUPPORTED_WS_PROTOCOL_VERSIONS:
                await websocket.send_json({
                    "event": "error",
                    "message": f"Unsupported protocol version {client_version}"
                })
                continue

            msg_type = message.get("type")
            
            if msg_type == "ping":
                try:
                    WsInboundPing.model_validate(message)
                except ValidationError as val_err:
                    await websocket.send_json({
                        "event": "error",
                        "message": "Invalid ping payload",
                        "errors": [{"loc": err["loc"], "msg": err["msg"]} for err in val_err.errors()]
                    })
                    continue
                await websocket.send_json({"event": "pong", "version": 1})
                
            elif msg_type == "location_update":
                # Only assigned rider can send location updates
                if user_role != "rider" or not is_assigned_rider or not assigned_rider_profile_id:
                    await websocket.send_json({"event": "error", "message": "Only the assigned rider can update location"})
                    continue

                try:
                    loc_payload = WsInboundLocationUpdate.model_validate(message)
                except ValidationError as val_err:
                    await websocket.send_json({
                        "event": "error",
                        "message": "Invalid location update payload",
                        "errors": [{"loc": err["loc"], "msg": err["msg"]} for err in val_err.errors()]
                    })
                    continue

                lat = loc_payload.latitude
                lng = loc_payload.longitude
                
                # Determine effective timestamp for monotonic GPS ordering
                now = datetime.now(timezone.utc)
                if loc_payload.client_timestamp and loc_payload.client_timestamp <= now + timedelta(seconds=10):
                    effective_ts = loc_payload.client_timestamp
                else:
                    effective_ts = now

                # Rate-limiting / Throttling
                if last_update_time and (effective_ts - last_update_time).total_seconds() < min_interval:
                    continue
                
                point_wkt = f"SRID=4326;POINT({lng} {lat})"
                current_delivery_status = None
                
                try:
                    # Short-lived session for location persistence with concurrency guard
                    async with async_session_maker() as loc_db:
                        rider_update_stmt = (
                            update(RiderProfile)
                            .where(
                                RiderProfile.id == assigned_rider_profile_id,
                                or_(
                                    RiderProfile.location_updated_at.is_(None),
                                    RiderProfile.location_updated_at <= effective_ts,
                                )
                            )
                            .values(
                                location=point_wkt,
                                location_updated_at=effective_ts
                            )
                        )
                        update_result = await loc_db.execute(rider_update_stmt)
                        
                        # Concurrency check: If rowcount == 0, a newer GPS update was already committed;
                        # drop stale update to prevent overwriting newer coordinates.
                        if update_result.rowcount == 0:
                            logger.info(f"Skipping stale location update for rider {assigned_rider_profile_id} (timestamp: {effective_ts})")
                            await loc_db.rollback()
                            continue

                        deliv_stmt = select(Delivery.status).where(Delivery.id == delivery_id)
                        deliv_res = await loc_db.execute(deliv_stmt)
                        current_delivery_status = deliv_res.scalar_one_or_none()
                        
                        await loc_db.commit()
                        
                    last_update_time = effective_ts
                    
                    # Publish event to Redis PubSub
                    await publish_delivery_event(delivery_id_str, {
                        "event": "delivery.location_updated",
                        "version": 1,
                        "delivery_id": delivery_id_str,
                        "rider_id": rider_id_str,
                        "timestamp": effective_ts.isoformat(),
                        "data": {
                            "latitude": lat,
                            "longitude": lng
                        }
                    })

                    # Trigger throttled movement-based ETA refresh if in active delivery
                    if current_delivery_status in [DeliveryStatus.assigned, DeliveryStatus.picked_up, DeliveryStatus.out_for_delivery]:
                        from app.services.delivery_eta import eta_service

                        async def _bg_refresh_eta(target_delivery_id: uuid.UUID):
                            try:
                                async with async_session_maker() as bg_session:
                                    await eta_service.update_and_persist_delivery_eta(
                                        bg_session, target_delivery_id, update_reason="movement_reroute"
                                    )
                                    await bg_session.commit()
                            except Exception as err:
                                logger.debug(f"Background movement ETA refresh skipped: {err}")

                        asyncio.create_task(_bg_refresh_eta(delivery_id))
                except Exception as e:
                    logger.error(f"Failed to persist rider location: {e}", exc_info=True)
                    await websocket.send_json({"event": "error", "message": "Failed to persist location"})
            else:
                await websocket.send_json({"event": "error", "message": f"Unknown message type '{msg_type}'"})
                
    except WebSocketDisconnect:
        logger.debug(f"WebSocket client disconnected for delivery {delivery_id_str}")
    except Exception as e:
        logger.error(f"Unexpected WebSocket error on delivery {delivery_id_str}: {e}", exc_info=True)
    finally:
        manager.disconnect(websocket, delivery_id_str)
        _stop_listener_if_empty(delivery_id_str)
