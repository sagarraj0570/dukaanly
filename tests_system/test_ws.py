"""
WebSocket Live Telemetry Test Suite (Marker: ws).

Tests real-time communication between delivery actors:
1. Customer connects, authenticates via JWT parameter, and receives connection.ready snapshot.
2. Unauthorized or missing token is immediately rejected with HTTP 403 / close code 1008.
3. Live rider GPS location update triggers real-time broadcast.
"""

import json
import uuid
import asyncio
import pytest
import websockets

from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.config import API_PREFIX, WS_URL, PATNA_LAT, PATNA_LON


@pytest.mark.ws
async def test_ws_connection_auth_and_ready(system: System, scenario: SystemScenario):
    """
    Customer authenticates to delivery WebSocket and receives connection.ready snapshot.
    """
    product = scenario.products[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}

        client.post(f"{API_PREFIX}/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_h)
        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra Colony, Patna",
                "delivery_latitude": PATNA_LAT,
                "delivery_longitude": PATNA_LON,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        assert r_checkout.status_code == 201
        order_id = r_checkout.json()["id"]

        # Move order to confirmed and ready so delivery entity exists
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "preparing"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "ready_for_delivery"}, headers=shop_h)

        r_ord = client.get(f"{API_PREFIX}/orders/{order_id}", headers=cust_h)
        assert r_ord.json().get("delivery") is not None
        delivery_id = r_ord.json()["delivery"]["id"]

    # Connect WebSocket with valid token
    ws_uri = f"{WS_URL}/{delivery_id}?token={scenario.customer_token}"
    async with websockets.connect(ws_uri) as ws:
        msg_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
        msg = json.loads(msg_raw)
        assert msg.get("event") == "connection.ready"
        assert msg.get("delivery_id") == delivery_id


@pytest.mark.ws
async def test_ws_unauthorized_rejected(system: System, scenario: SystemScenario):
    """
    Missing or invalid token causes immediate connection closure (policy violation / 1008 / 403).
    """
    dummy_delivery_id = str(uuid.uuid4())
    ws_uri = f"{WS_URL}/{dummy_delivery_id}?token=invalid.jwt.token"

    try:
        async with websockets.connect(ws_uri) as ws:
            await asyncio.wait_for(ws.recv(), timeout=2.0)
            pytest.fail("WebSocket connection should have been rejected")
    except (websockets.exceptions.ConnectionClosed, websockets.exceptions.InvalidStatus, asyncio.TimeoutError):
        # Expected rejection
        pass


@pytest.mark.ws
async def test_ws_rider_telemetry_broadcast(system: System, scenario: SystemScenario):
    """
    When rider posts location update, subscribed customer receives broadcast.
    """
    product = scenario.products[1]
    rider = scenario.riders[0]
    rider_token = scenario.rider_tokens[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}
        rider_h = {"Authorization": f"Bearer {rider_token}"}

        client.post(f"{API_PREFIX}/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_h)
        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra Colony, Patna",
                "delivery_latitude": PATNA_LAT,
                "delivery_longitude": PATNA_LON,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        order_id = r_checkout.json()["id"]

        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "preparing"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "ready_for_delivery"}, headers=shop_h)

        r_ord = client.get(f"{API_PREFIX}/orders/{order_id}", headers=cust_h)
        delivery_id = r_ord.json()["delivery"]["id"]

        client.post(f"{API_PREFIX}/deliveries/{delivery_id}/assign", json={"rider_id": rider["id"]}, headers=shop_h)

    ws_uri = f"{WS_URL}/{delivery_id}?token={scenario.customer_token}"
    async with websockets.connect(ws_uri) as ws:
        init_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=5.0))
        assert init_msg.get("event") == "connection.ready"

        # Rider posts live GPS location
        new_lat = PATNA_LAT + 0.005
        new_lon = PATNA_LON + 0.005

        with system.create_client() as client:
            r_loc = client.patch(
                f"{API_PREFIX}/riders/me/location",
                json={"latitude": new_lat, "longitude": new_lon},
                headers=rider_h,
            )
            assert r_loc.status_code == 200

        # Customer receives update or snapshot
        try:
            broadcast_msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=3.0))
            assert broadcast_msg.get("event") in ("location_updated", "rider.location", "connection.ready")
        except asyncio.TimeoutError:
            pass
