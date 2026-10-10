from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import joinedload
import uuid
import asyncio
import json
from datetime import datetime, timezone

from app.db.session import get_db
from app.core import security
from app.models.user import User
from app.models.delivery import Delivery
from app.models.order import Order
from app.models.shop import Shop
from app.models.rider import RiderProfile
from app.websockets.manager import manager
from app.websockets.redis_pubsub import subscribe_delivery_channel
from app.services.rider import update_rider_location
from app.core.config import settings

router = APIRouter()

# Dictionary to track background listener tasks per delivery_id to prevent duplicates
# Key: delivery_id, Value: (task, stop_event, ref_count)
_delivery_listeners = {}

async def _get_user_from_token(token: str, db: AsyncSession) -> User | None:
    try:
        payload = security.decode_token(token)
        user_id_str = payload.get("sub")
        if not user_id_str:
            return None
        user_id = uuid.UUID(user_id_str)
        stmt = select(User).where(User.id == user_id)
        result = await db.execute(stmt)
        return result.scalar_one_or_none()
    except Exception:
        return None

async def authorize_delivery_ws(user: User, delivery: Delivery) -> bool:
    """Authorize a user for a specific delivery."""
    # Rider
    if user.role.value == "rider":
        if delivery.rider and delivery.rider.user_id == user.id:
            return True
        return False
        
    # Customer
    if user.role.value == "customer":
        if delivery.order.customer_id == user.id:
            return True
        return False
        
    # Shop Owner
    if user.role.value == "shop_owner":
        if delivery.order.shop.owner_id == user.id:
            return True
        return False
        
    # Admin
    if user.role.value == "admin":
        return True
        
    return False

def _start_listener_if_needed(delivery_id_str: str):
    """Ensure a Redis PubSub listener is running for the delivery channel."""
    if delivery_id_str not in _delivery_listeners:
        stop_event = asyncio.Event()
        task = asyncio.create_task(subscribe_delivery_channel(delivery_id_str, stop_event))
        _delivery_listeners[delivery_id_str] = {"task": task, "stop_event": stop_event, "ref_count": 1}
    else:
        _delivery_listeners[delivery_id_str]["ref_count"] += 1

def _stop_listener_if_empty(delivery_id_str: str):
    """Stop the Redis PubSub listener if no more clients are connected."""
    if delivery_id_str in _delivery_listeners:
        _delivery_listeners[delivery_id_str]["ref_count"] -= 1
        if _delivery_listeners[delivery_id_str]["ref_count"] <= 0:
            _delivery_listeners[delivery_id_str]["stop_event"].set()
            # The task will exit on its own
            del _delivery_listeners[delivery_id_str]

@router.websocket("/{delivery_id}")
async def delivery_websocket(
    websocket: WebSocket,
    delivery_id: uuid.UUID,
    token: str = Query(None),
    db: AsyncSession = Depends(get_db)
):
    # 1. Authenticate
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Missing token")
        return
        
    user = await _get_user_from_token(token, db)
    if not user:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Invalid or expired token")
        return

    # 2. Load delivery and relationships for authorization
    stmt = (
        select(Delivery)
        .options(
            joinedload(Delivery.order).joinedload(Order.shop),
            joinedload(Delivery.rider)
        )
        .where(Delivery.id == delivery_id)
    )
    result = await db.execute(stmt)
    delivery = result.scalar_one_or_none()
    
    if not delivery:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Delivery not found")
        return

    # 3. Authorize
    is_authorized = await authorize_delivery_ws(user, delivery)
    if not is_authorized:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
        return

    # 4. Connect
    delivery_id_str = str(delivery_id)
    await manager.connect(websocket, delivery_id_str)
    _start_listener_if_needed(delivery_id_str)
    
    # 5. Send connection.ready snapshot
    try:
        from geoalchemy2.shape import to_shape
        rider_loc = None
        if delivery.rider and delivery.rider.location:
            point = to_shape(delivery.rider.location)
            rider_loc = {
                "latitude": point.y,
                "longitude": point.x,
                "updated_at": delivery.rider.location_updated_at.isoformat() if delivery.rider.location_updated_at else None
            }
            
        snapshot = {
            "event": "connection.ready",
            "version": 1,
            "delivery_id": delivery_id_str,
            "data": {
                "delivery_status": delivery.status.value,
                "rider_id": str(delivery.rider_id) if delivery.rider_id else None,
                "rider_location": rider_loc
            }
        }
        await websocket.send_json(snapshot)
    except Exception:
        pass # Ignore failure to send initial snapshot if connection dropped immediately
        
    # 6. Message Loop
    # Keep track of last update for throttling
    last_update_time = None
    min_interval = getattr(settings, "RIDER_LOCATION_MIN_UPDATE_INTERVAL_SECONDS", 5)

    try:
        while True:
            text_data = await websocket.receive_text()
            try:
                message = json.loads(text_data)
            except json.JSONDecodeError:
                await websocket.send_json({"event": "error", "message": "Invalid JSON"})
                continue
                
            msg_type = message.get("type")
            
            if msg_type == "ping":
                await websocket.send_json({"event": "pong", "version": 1})
                
            elif msg_type == "location_update":
                # Only the assigned rider can send location updates
                if user.role.value != "rider" or not delivery.rider or delivery.rider.user_id != user.id:
                    await websocket.send_json({"event": "error", "message": "Only the assigned rider can update location"})
                    continue
                    
                lat = message.get("latitude")
                lng = message.get("longitude")
                
                if lat is None or lng is None:
                    await websocket.send_json({"event": "error", "message": "Missing latitude or longitude"})
                    continue
                    
                try:
                    lat = float(lat)
                    lng = float(lng)
                except ValueError:
                    await websocket.send_json({"event": "error", "message": "Invalid coordinates"})
                    continue
                    
                if not (-90 <= lat <= 90) or not (-180 <= lng <= 180):
                    await websocket.send_json({"event": "error", "message": "Coordinates out of bounds"})
                    continue
                
                # Throttling
                now = datetime.now(timezone.utc)
                if last_update_time and (now - last_update_time).total_seconds() < min_interval:
                    # Ignore throttled updates
                    continue
                
                # Update DB
                # Note: We need a fresh DB session or at least execute on the existing one.
                # Since websocket lifecycle holds this db session, let's use it carefully.
                from sqlalchemy import func
                point_wkt = f"SRID=4326;POINT({lng} {lat})"
                delivery.rider.location = point_wkt
                delivery.rider.location_updated_at = func.now()
                
                try:
                    await db.commit()
                    last_update_time = now
                    
                    # Publish event to Redis
                    from app.websockets.redis_pubsub import publish_delivery_event
                    await publish_delivery_event(delivery_id_str, {
                        "event": "delivery.location_updated",
                        "version": 1,
                        "delivery_id": delivery_id_str,
                        "rider_id": str(delivery.rider_id),
                        "timestamp": now.isoformat(),
                        "data": {
                            "latitude": lat,
                            "longitude": lng
                        }
                    })
                except Exception as e:
                    await db.rollback()
                    await websocket.send_json({"event": "error", "message": "Failed to persist location"})
            else:
                await websocket.send_json({"event": "error", "message": "Unknown message type"})
                
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket, delivery_id_str)
        _stop_listener_if_empty(delivery_id_str)
