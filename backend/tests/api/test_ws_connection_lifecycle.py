"""
Automated Test Suite: WebSocket Database Connection Lifecycle & Pool Leak Elimination.

Verifies:
1. 50 concurrent idle WebSocket connections do not exhaust PostgreSQL connection pool.
2. Concurrent REST endpoints remain fast and responsive while 50 WebSockets are held open.
3. PostgreSQL pg_stat_activity exhibits exactly 0 'idle in transaction' sessions from WebSockets.
4. Telematics location updates use dedicated short-lived DB sessions and broadcast over Redis.
5. Sockets disconnect cleanly, tearing down Redis listeners and memory tracking.
6. Handshake rejections (unauthenticated, unauthorized) release DB connections immediately.
"""
import pytest
import asyncio
import uuid
import json
import socket
import subprocess
import sys
import time
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import httpx
import websockets
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.config import settings
from app.core.security import create_access_token
from app.db.session import async_session_maker
from app.models.user import User, UserRole
from app.models.shop import Shop
from app.models.product import Product
from app.models.order import Order, OrderStatus
from app.models.delivery import Delivery, DeliveryStatus
from app.models.rider import RiderProfile
from app.websockets.manager import manager

pytestmark = pytest.mark.asyncio

@pytest.fixture(scope="module")
def ws_test_server():
    """Starts an ephemeral Uvicorn server for live WebSocket lifecycle testing."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        port = s.getsockname()[1]

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app", "--port", str(port)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    started = False
    for _ in range(30):
        try:
            res = httpx.get(f"http://127.0.0.1:{port}/api/v1/health/live")
            if res.status_code == 200:
                started = True
                break
        except Exception:
            pass
        time.sleep(0.3)

    if not started:
        proc.kill()
        pytest.fail("Failed to start live test server for WebSocket lifecycle tests")

    yield f"http://127.0.0.1:{port}", f"ws://127.0.0.1:{port}"
    proc.terminate()
    proc.wait()


async def _create_test_user(role: UserRole) -> tuple[User, str]:
    user_id = uuid.uuid4()
    email = f"wslc_{role.value}_{uuid.uuid4().hex[:8]}@example.com"
    async with async_session_maker() as session:
        user = User(
            id=user_id,
            email=email,
            password_hash="$argon2id$v=19$m=65536,t=3,p=4$fakehashfortesting1234567890",
            name=f"WS {role.value.capitalize()}",
            role=role,
            is_active=True,
        )
        session.add(user)
        await session.commit()
    token = create_access_token(str(user_id), role.value)
    return user, token


async def _create_test_entities():
    """Helper to provision a customer, shop owner, rider, shop, order, and delivery."""
    owner, owner_token = await _create_test_user(UserRole.shop_owner)
    cust, cust_token = await _create_test_user(UserRole.customer)
    rider_user, rider_token = await _create_test_user(UserRole.rider)
    unauthorized_user, unauth_token = await _create_test_user(UserRole.customer)

    async with async_session_maker() as session:
        shop = Shop(
            name=f"WS Lifecycle Shop {uuid.uuid4().hex[:6]}",
            address="123 Test Road",
            location="SRID=4326;POINT(85.1376 25.5941)",
            owner_id=owner.id,
            is_active=True,
            is_orderable=True,
            verification_status="verified",
        )
        session.add(shop)
        await session.flush()

        order = Order(
            customer_id=cust.id,
            shop_id=shop.id,
            status=OrderStatus.confirmed,
            total_amount=Decimal("500.00"),
            idempotency_key=str(uuid.uuid4()),
        )
        session.add(order)
        await session.flush()

        rider_profile = RiderProfile(
            user_id=rider_user.id,
            is_available=True,
            location="SRID=4326;POINT(85.1380 25.5945)",
        )
        session.add(rider_profile)
        await session.flush()

        delivery = Delivery(
            order_id=order.id,
            rider_id=rider_profile.id,
            status=DeliveryStatus.assigned,
            destination_location="SRID=4326;POINT(85.1400 25.5950)",
        )
        session.add(delivery)
        await session.commit()
        await session.refresh(delivery)

    return {
        "cust_id": cust.id,
        "cust_token": cust_token,
        "rider_user_id": rider_user.id,
        "rider_profile_id": rider_profile.id,
        "rider_token": rider_token,
        "unauthorized_token": unauth_token,
        "delivery_id": delivery.id,
    }


async def _get_pg_idle_in_transaction_count() -> int:
    """Queries pg_stat_activity for any sessions in 'idle in transaction' state."""
    direct_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
    async with direct_engine.connect() as conn:
        res = await conn.execute(
            text(
                "SELECT count(*) FROM pg_stat_activity "
                "WHERE datname = :dbname AND state = 'idle in transaction'"
            ),
            {"dbname": settings.POSTGRES_DB},
        )
        count = res.scalar() or 0
    await direct_engine.dispose()
    return count


async def test_50_concurrent_idle_websockets_and_zero_db_leaks(ws_test_server):
    """
    Test Objective:
    Connect 50 concurrent WebSockets to the delivery tracking endpoint.
    With default pool_size=5 (max_overflow=10), this would previously freeze
    and fail at socket 16 due to QueuePool exhaustion.
    Verify all 50 connect, receive initial snapshot, exhibit 0 idle in transaction
    in PostgreSQL, and REST endpoints remain fast.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]
    cust_token = entities["cust_token"]
    ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={cust_token}"

    baseline_idle = await _get_pg_idle_in_transaction_count()

    connections = []
    try:
        # 1. Connect 50 concurrent WebSockets
        num_connections = 50
        connect_tasks = [websockets.connect(ws_url) for _ in range(num_connections)]
        connections = await asyncio.gather(*connect_tasks)
        assert len(connections) == num_connections

        # 2. Verify all received connection.ready
        for ws in connections:
            msg = await asyncio.wait_for(ws.recv(), timeout=5.0)
            data = json.loads(msg)
            assert data["event"] == "connection.ready"
            assert data["delivery_id"] == str(delivery_id)

        # 3. Check PostgreSQL pg_stat_activity: MUST BE ZERO idle in transaction
        current_idle = await _get_pg_idle_in_transaction_count()
        assert current_idle == baseline_idle, (
            f"Expected {baseline_idle} idle in transaction, got {current_idle} while 50 WebSockets connected"
        )

        # 4. Concurrently issue REST requests.
        # Primary acceptance criterion: Connection-pool exhaustion prevention.
        # If connections leaked into 'idle in transaction', this call would stall indefinitely (>5.0s timeout).
        # We use a 2.0s assertion threshold to be stable under CI virtualization and realistic machine load.
        async with httpx.AsyncClient(base_url=http_base, timeout=5.0) as client:
            t0 = time.perf_counter()
            health_res = await client.get("/api/v1/health/ready")
            elapsed = time.perf_counter() - t0
            assert health_res.status_code == 200
            assert elapsed < 2.0, f"REST request took too long ({elapsed:.3f}s) while WebSockets idle"

            # Check shop listing
            shops_res = await client.get("/api/v1/shops")
            assert shops_res.status_code == 200

        # 5. Send ping on all 50 connections and verify pong
        for ws in connections:
            await ws.send(json.dumps({"type": "ping", "version": 1}))
            pong_raw = await asyncio.wait_for(ws.recv(), timeout=3.0)
            pong_msg = json.loads(pong_raw)
            assert pong_msg["event"] == "pong"

    finally:
        # Clean up all 50 connections
        for ws in connections:
            await ws.close()
        await asyncio.sleep(0.5)


async def test_rider_location_updates_use_short_lived_sessions(ws_test_server):
    """
    Test Objective:
    Assigned rider connects and sends location updates.
    Customer socket observes real-time broadcast.
    PostgreSQL reflects updated coordinates.
    Transactions do not remain idle in PostgreSQL.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]
    rider_profile_id = entities["rider_profile_id"]
    cust_token = entities["cust_token"]
    rider_token = entities["rider_token"]

    cust_ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={cust_token}"
    rider_ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={rider_token}"

    async with websockets.connect(cust_ws_url) as cust_ws, \
               websockets.connect(rider_ws_url) as rider_ws:

        # Consume snapshots
        await cust_ws.recv()
        await rider_ws.recv()

        # Rider pushes location update
        new_lat = 25.5980
        new_lng = 85.1420
        loc_payload = {
            "type": "location_update",
            "version": 1,
            "latitude": new_lat,
            "longitude": new_lng,
        }
        await rider_ws.send(json.dumps(loc_payload))

        # Customer must receive delivery.location_updated
        broadcast_raw = await asyncio.wait_for(cust_ws.recv(), timeout=5.0)
        broadcast = json.loads(broadcast_raw)
        assert broadcast["event"] == "delivery.location_updated"
        assert broadcast["data"]["latitude"] == new_lat
        assert broadcast["data"]["longitude"] == new_lng

        # Verify DB is persisted
        async with async_session_maker() as session:
            res = await session.execute(
                select(RiderProfile).where(RiderProfile.id == rider_profile_id)
            )
            profile = res.scalar_one()
            from geoalchemy2.shape import to_shape
            pt = to_shape(profile.location)
            assert abs(pt.y - new_lat) < 1e-4
            assert abs(pt.x - new_lng) < 1e-4
            await session.rollback()

        # Brief wait to allow background ETA task to finish execution
        await asyncio.sleep(0.5)

        # Zero idle in transaction
        idle_count = await _get_pg_idle_in_transaction_count()
        assert idle_count == 0


async def test_clean_disconnect_and_reconnect_lifecycle(ws_test_server):
    """
    Test Objective:
    Verify that upon WebSocket disconnect, connections and Redis listeners
    are torn down cleanly without lingering memory leaks or database sessions.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]
    cust_token = entities["cust_token"]
    ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={cust_token}"

    # Connect client 1
    ws1 = await websockets.connect(ws_url)
    await ws1.recv()  # connection.ready

    # Disconnect client 1
    await ws1.close()
    await asyncio.sleep(0.3)

    # Reconnect client 2
    ws2 = await websockets.connect(ws_url)
    snap = json.loads(await ws2.recv())
    assert snap["event"] == "connection.ready"
    await ws2.close()
    await asyncio.sleep(0.3)

    # Verify no open transactions
    assert await _get_pg_idle_in_transaction_count() == 0


async def test_handshake_rejections_release_db_immediately(ws_test_server):
    """
    Test Objective:
    Verify invalid token and unauthorized user attempts close with 1008
    and leave 0 open DB connections or transactions.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]
    unauth_token = entities["unauthorized_token"]

    # 1. Missing token
    try:
        async with websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}"):
            pytest.fail("Should have been rejected")
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatus) as exc:
        if isinstance(exc, websockets.exceptions.ConnectionClosedError):
            assert exc.code == 1008

    # 2. Unauthorized token
    try:
        async with websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={unauth_token}"):
            pytest.fail("Should have been rejected")
    except (websockets.exceptions.ConnectionClosedError, websockets.exceptions.InvalidStatus) as exc:
        if isinstance(exc, websockets.exceptions.ConnectionClosedError):
            assert exc.code == 1008

    # Verify 0 idle in transaction
    assert await _get_pg_idle_in_transaction_count() == 0


async def test_simultaneous_location_updates_concurrency_guard(ws_test_server):
    """
    Test Objective:
    Simulate simultaneous/out-of-order GPS updates from the rider.
    Ensure that older/stale coordinates cannot overwrite newer coordinates
    in PostgreSQL or broadcast to connected clients.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]
    rider_profile_id = entities["rider_profile_id"]
    cust_token = entities["cust_token"]
    rider_token = entities["rider_token"]

    cust_ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={cust_token}"
    rider_ws_url = f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token={rider_token}"

    async with websockets.connect(cust_ws_url) as cust_ws, \
               websockets.connect(rider_ws_url) as rider_ws:

        await cust_ws.recv()  # connection.ready
        await rider_ws.recv() # connection.ready

        now = datetime.now(timezone.utc)
        t_newer = now
        t_stale = now - timedelta(seconds=15)

        # 1. Send newer update first (T_newer)
        newer_lat, newer_lng = 25.6100, 85.1500
        await rider_ws.send(json.dumps({
            "type": "location_update",
            "version": 1,
            "latitude": newer_lat,
            "longitude": newer_lng,
            "client_timestamp": t_newer.isoformat(),
        }))

        # Customer receives newer location broadcast
        b1_raw = await asyncio.wait_for(cust_ws.recv(), timeout=5.0)
        b1 = json.loads(b1_raw)
        assert b1["event"] == "delivery.location_updated"
        assert b1["data"]["latitude"] == newer_lat

        # 2. Send stale update (T_stale < T_newer) with different coordinates
        stale_lat, stale_lng = 25.5000, 85.1000
        await rider_ws.send(json.dumps({
            "type": "location_update",
            "version": 1,
            "latitude": stale_lat,
            "longitude": stale_lng,
            "client_timestamp": t_stale.isoformat(),
        }))

        # Verify customer does NOT receive stale broadcast (timeout confirms no broadcast)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(cust_ws.recv(), timeout=1.0)

        # 3. Verify PostgreSQL database retains newer coordinates
        async with async_session_maker() as session:
            res = await session.execute(
                select(RiderProfile).where(RiderProfile.id == rider_profile_id)
            )
            profile = res.scalar_one()
            from geoalchemy2.shape import to_shape
            pt = to_shape(profile.location)
            assert abs(pt.y - newer_lat) < 1e-4, f"DB coordinates were overwritten by stale update! y={pt.y}"
            assert abs(pt.x - newer_lng) < 1e-4
            await session.rollback()

        # Zero idle in transaction
        assert await _get_pg_idle_in_transaction_count() == 0


async def test_handshake_cancellation_and_error_releases_session(ws_test_server):
    """
    Test Objective:
    Verify that if connection is abruptly aborted or cancelled during handshake,
    the context manager and finally block guarantee session closure with 0 open transactions.
    """
    http_base, ws_base = ws_test_server
    entities = await _create_test_entities()
    delivery_id = entities["delivery_id"]

    # Rapid connect and immediate close before handshake completes
    for _ in range(5):
        try:
            ws = await websockets.connect(f"{ws_base}/api/v1/ws/deliveries/{delivery_id}?token=invalid_token")
            await ws.close()
        except Exception:
            pass

    await asyncio.sleep(0.3)
    assert await _get_pg_idle_in_transaction_count() == 0
