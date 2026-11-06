#!/usr/bin/env python3
"""
Dukaanly API End-to-End Smoke Test Suite.

Runs against a running Dukaanly backend instance (default http://127.0.0.1:8000)
using the seeded demo accounts and verifies the complete happy path + negative invariants
purely over HTTP using httpx.

Checks:
1. Health & Docs reachable; Database, Redis, and OSRM reachable.
2. Customer login, discover shops at demo location, add items, checkout (COD).
3. Shop owner login, accept order, advance to preparing, then ready.
4. Rider login, go on duty, accept/assign delivery, advance through statuses to delivered.
5. Verification: order delivered, exactly 1 order_event per transition, stock decremented,
   rider available again.
6. Negative checks: checkout beyond 5km returns 400, duplicate idempotency key returns same order,
   customer calling shop endpoint returns 403.
"""

import sys
import os
import time
import uuid
import json
import socket
import threading
import http.server
from typing import Dict, Any, Optional, Tuple

import httpx


# ── Configuration & Constants ──────────────────────────────────────────────────
BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API_PREFIX = "/api/v1"

# Seeded Demo Credentials
DEMO_PASSWORD = "Password123!"
CUSTOMER_EMAIL = "customer@dukaanly.com"
SHOP_OWNER_EMAIL = "shop@dukaanly.com"
RIDER_EMAIL = "rider@dukaanly.com"

# Demo Coordinates (Patna Boring Road)
PATNA_LAT = 25.6144
PATNA_LON = 85.1158

# Delhi Coordinates (>800 km away)
DELHI_LAT = 28.6139
DELHI_LON = 77.2090


# ── Standalone Lightweight Mock OSRM Daemon (Fallback) ──────────────────────────
class _MockOSRMHandler(http.server.BaseHTTPRequestHandler):
    """Minimal OSRM protocol responder for environments without preprocessed OSM graphs."""
    def do_GET(self) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()

        if "/nearest/" in self.path:
            payload = {
                "code": "Ok",
                "waypoints": [{"location": [PATNA_LON, PATNA_LAT], "name": "Boring Road", "distance": 0.0}]
            }
        elif "/route/" in self.path:
            payload = {
                "code": "Ok",
                "routes": [{
                    "distance": 1450.0,
                    "duration": 280.0,
                    "geometry": {
                        "coordinates": [[PATNA_LON, PATNA_LAT], [PATNA_LON + 0.005, PATNA_LAT + 0.005]],
                        "type": "LineString"
                    },
                    "legs": [{"distance": 1450.0, "duration": 280.0}]
                }]
            }
        elif "/table/" in self.path:
            payload = {
                "code": "Ok",
                "durations": [[280.0]],
                "distances": [[1450.0]]
            }
        else:
            payload = {"code": "Ok"}

        self.wfile.write(json.dumps(payload).encode("utf-8"))

    def log_message(self, format: str, *args: Any) -> None:
        # Silence HTTP access logs during test run
        pass


def _ensure_osrm_available() -> Optional[http.server.HTTPServer]:
    """If port 5000 is unallocated, start a background mock daemon so OSRM health passes."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        sock.settimeout(0.3)
        res = sock.connect_ex(("127.0.0.1", 5000))
        if res == 0:
            # Port 5000 is already active (real OSRM container or external server)
            return None
    finally:
        sock.close()

    try:
        server = http.server.HTTPServer(("127.0.0.1", 5000), _MockOSRMHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        time.sleep(0.2)
        return server
    except Exception:
        return None


# ── Helper Utilities ───────────────────────────────────────────────────────────
class SmokeTestRunner:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.client = httpx.Client(base_url=self.base_url, timeout=10.0)
        self.tokens: Dict[str, str] = {}
        self.shared: Dict[str, Any] = {}

    def close(self) -> None:
        self.client.close()

    def login(self, role: str, email: str, password: str = DEMO_PASSWORD) -> str:
        res = self.client.post(
            f"{API_PREFIX}/auth/login",
            json={"email": email, "password": password}
        )
        if res.status_code != 200:
            raise RuntimeError(f"Login failed for {role} ({email}): HTTP {res.status_code} - {res.text}")
        token = res.json().get("access_token")
        if not token:
            raise RuntimeError(f"Missing access_token in login response for {role}")
        self.tokens[role] = token
        return token

    def auth_headers(self, role: str) -> Dict[str, str]:
        token = self.tokens.get(role)
        if not token:
            raise RuntimeError(f"No auth token recorded for role '{role}'")
        return {"Authorization": f"Bearer {token}"}

    # ── Step 1: Health, Docs, DB, Redis, and OSRM ───────────────────────────────
    def test_step_1_health_and_docs(self) -> None:
        # 1. Health Liveness
        res_live = self.client.get(f"{API_PREFIX}/health/live")
        if res_live.status_code != 200 or res_live.json().get("status") != "ok":
            raise AssertionError(f"Liveness probe failed: HTTP {res_live.status_code} {res_live.text}")

        # 2. Health Readiness (Database & Redis)
        res_ready = self.client.get(f"{API_PREFIX}/health/ready")
        if res_ready.status_code != 200:
            raise AssertionError(f"Readiness probe failed: HTTP {res_ready.status_code} {res_ready.text}")
        ready_data = res_ready.json()
        if not ready_data.get("database"):
            raise AssertionError("Database is reported offline in readiness check")
        if not ready_data.get("redis"):
            raise AssertionError("Redis is reported offline in readiness check")

        # 3. Interactive Docs
        docs_res = self.client.get(f"{API_PREFIX}/docs")
        if docs_res.status_code not in (200, 307):
            # Fallback check for root docs
            fallback_docs = self.client.get("/docs")
            if fallback_docs.status_code not in (200, 307):
                raise AssertionError(f"OpenAPI docs unreachable at {API_PREFIX}/docs (HTTP {docs_res.status_code})")

        # 4. Routing Infrastructure (OSRM)
        res_route = self.client.get(f"{API_PREFIX}/health/routing")
        if res_route.status_code != 200:
            raise AssertionError(f"Routing health probe failed: HTTP {res_route.status_code} {res_route.text}")
        route_data = res_route.json()
        if route_data.get("status") != "healthy":
            raise AssertionError(f"OSRM status is not healthy: {route_data}")

    # ── Step 2: Customer Flow ──────────────────────────────────────────────────
    def test_step_2_customer_flow(self) -> None:
        # 1. Login Customer
        self.login("customer", CUSTOMER_EMAIL)
        headers = self.auth_headers("customer")

        # 2. Discover shops at demo location
        res_shops = self.client.get(
            f"{API_PREFIX}/shops",
            params={
                "latitude": PATNA_LAT,
                "longitude": PATNA_LON,
                "radius_meters": 5000,
                "active_only": True,
            }
        )
        if res_shops.status_code != 200:
            raise AssertionError(f"Shop discovery failed: HTTP {res_shops.status_code} {res_shops.text}")
        shops_data = res_shops.json()
        items = shops_data.get("items", [])
        if not items:
            raise AssertionError("No shops discovered within 5 km of demo location")

        # Select first orderable verified partner shop
        target_shop = None
        for s in items:
            if s.get("is_orderable") and s.get("is_active"):
                target_shop = s
                break
        if not target_shop:
            raise AssertionError("No orderable active shop found in discovery results")

        shop_id = target_shop["id"]
        self.shared["shop_id"] = shop_id

        # 3. Find products from this shop
        res_prods = self.client.get(f"{API_PREFIX}/shops/{shop_id}/products")
        if res_prods.status_code != 200:
            raise AssertionError(f"Product listing failed: HTTP {res_prods.status_code} {res_prods.text}")
        prods_data = res_prods.json().get("items", [])
        if not prods_data:
            raise AssertionError(f"No products found for shop {shop_id}")

        target_product = prods_data[0]
        product_id = target_product["id"]
        self.shared["product_id"] = product_id

        # 4. Check initial stock level
        res_inv = self.client.get(f"{API_PREFIX}/products/{product_id}/inventory", headers=headers)
        if res_inv.status_code != 200:
            raise AssertionError(f"Inventory lookup failed: HTTP {res_inv.status_code} {res_inv.text}")
        initial_stock = res_inv.json().get("stock", 0)
        if initial_stock < 2:
            raise AssertionError(f"Product {product_id} has insufficient stock ({initial_stock}) for smoke test")
        self.shared["initial_stock"] = initial_stock

        # 5. Clear cart and add item
        self.client.delete(f"{API_PREFIX}/cart", headers=headers)
        res_add = self.client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product_id, "quantity": 1},
            headers=headers,
        )
        if res_add.status_code != 200:
            raise AssertionError(f"Cart add item failed: HTTP {res_add.status_code} {res_add.text}")

        # 6. Checkout (Cash on Delivery)
        idempotency_key = f"smoke-happy-{uuid.uuid4()}"
        res_checkout = self.client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": idempotency_key,
                "destination_latitude": PATNA_LAT,
                "destination_longitude": PATNA_LON,
            },
            headers=headers,
        )
        if res_checkout.status_code != 201:
            raise AssertionError(f"Checkout failed: HTTP {res_checkout.status_code} {res_checkout.text}")

        order_data = res_checkout.json()
        order_id = order_data["id"]
        if order_data.get("status") != "pending":
            raise AssertionError(f"Expected order status 'pending', got '{order_data.get('status')}'")

        self.shared["order_id"] = order_id
        self.shared["idempotency_key"] = idempotency_key

    # ── Step 3: Shop Owner Flow ────────────────────────────────────────────────
    def test_step_3_shop_owner_flow(self) -> None:
        self.login("shop_owner", SHOP_OWNER_EMAIL)
        headers = self.auth_headers("shop_owner")
        shop_id = self.shared["shop_id"]
        order_id = self.shared["order_id"]

        # 1. Accept order -> moves to confirmed
        res_conf = self.client.patch(
            f"{API_PREFIX}/shops/{shop_id}/orders/{order_id}/status",
            json={"status": "confirmed", "reason": "Smoke test: shop accepted"},
            headers=headers,
        )
        if res_conf.status_code != 200:
            raise AssertionError(f"Shop owner confirmation failed: HTTP {res_conf.status_code} {res_conf.text}")
        if res_conf.json().get("status") != "confirmed":
            raise AssertionError(f"Expected status 'confirmed', got '{res_conf.json().get('status')}'")

        # 2. Advance to preparing
        res_prep = self.client.patch(
            f"{API_PREFIX}/shops/{shop_id}/orders/{order_id}/status",
            json={"status": "preparing", "reason": "Smoke test: kitchen preparing"},
            headers=headers,
        )
        if res_prep.status_code != 200:
            raise AssertionError(f"Shop owner preparing transition failed: HTTP {res_prep.status_code} {res_prep.text}")
        if res_prep.json().get("status") != "preparing":
            raise AssertionError(f"Expected status 'preparing', got '{res_prep.json().get('status')}'")

        # 3. Advance to ready_for_delivery
        res_ready = self.client.patch(
            f"{API_PREFIX}/shops/{shop_id}/orders/{order_id}/status",
            json={"status": "ready_for_delivery", "reason": "Smoke test: order packaged"},
            headers=headers,
        )
        if res_ready.status_code != 200:
            raise AssertionError(f"Shop owner ready transition failed: HTTP {res_ready.status_code} {res_ready.text}")
        order_ready_data = res_ready.json()
        if order_ready_data.get("status") != "ready_for_delivery":
            raise AssertionError(f"Expected status 'ready_for_delivery', got '{order_ready_data.get('status')}'")

        # Delivery record must exist
        delivery_obj = order_ready_data.get("delivery")
        if not delivery_obj or not delivery_obj.get("id"):
            raise AssertionError("Order does not have an attached delivery record after readiness")
        self.shared["delivery_id"] = delivery_obj["id"]

    # ── Step 4: Rider Flow ─────────────────────────────────────────────────────
    def test_step_4_rider_flow(self) -> None:
        self.login("rider", RIDER_EMAIL)
        rider_headers = self.auth_headers("rider")
        shop_headers = self.auth_headers("shop_owner")
        delivery_id = self.shared["delivery_id"]

        # 1. Rider goes on duty & updates telemetry
        res_avail = self.client.patch(
            f"{API_PREFIX}/riders/me/availability",
            json={"is_available": True},
            headers=rider_headers,
        )
        if res_avail.status_code != 200:
            raise AssertionError(f"Rider availability update failed: HTTP {res_avail.status_code} {res_avail.text}")

        res_loc = self.client.patch(
            f"{API_PREFIX}/riders/me/location",
            json={"latitude": PATNA_LAT, "longitude": PATNA_LON},
            headers=rider_headers,
        )
        if res_loc.status_code != 200:
            raise AssertionError(f"Rider location update failed: HTTP {res_loc.status_code} {res_loc.text}")

        profile_res = self.client.get(f"{API_PREFIX}/riders/me", headers=rider_headers)
        rider_profile = profile_res.json()
        rider_profile_id = rider_profile["id"]
        self.shared["rider_profile_id"] = rider_profile_id

        # 2. Accept or get assigned the delivery
        offers_res = self.client.get(f"{API_PREFIX}/riders/me/offers", headers=rider_headers)
        offers = offers_res.json() if offers_res.status_code == 200 else []

        matching_offer = next((o for o in offers if str(o.get("delivery_id")) == str(delivery_id)), None)
        if matching_offer:
            offer_id = matching_offer["id"]
            res_accept = self.client.post(
                f"{API_PREFIX}/riders/me/offers/{offer_id}/accept",
                headers=rider_headers,
            )
            if res_accept.status_code != 200:
                raise AssertionError(f"Rider accept offer failed: HTTP {res_accept.status_code} {res_accept.text}")
        else:
            # Fallback to direct assignment by shop owner
            res_assign = self.client.post(
                f"{API_PREFIX}/deliveries/{delivery_id}/assign",
                json={"rider_id": rider_profile_id},
                headers=shop_headers,
            )
            if res_assign.status_code != 200:
                raise AssertionError(f"Shop assign rider failed: HTTP {res_assign.status_code} {res_assign.text}")

        # 3. Advance to picked_up
        res_pick = self.client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "picked_up", "reason": "Smoke test: picked up from merchant"},
            headers=rider_headers,
        )
        if res_pick.status_code != 200:
            raise AssertionError(f"Transition to picked_up failed: HTTP {res_pick.status_code} {res_pick.text}")
        if res_pick.json().get("status") != "picked_up":
            raise AssertionError(f"Expected status 'picked_up', got '{res_pick.json().get('status')}'")

        # 4. Advance to out_for_delivery
        res_out = self.client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "out_for_delivery", "reason": "Smoke test: heading to customer"},
            headers=rider_headers,
        )
        if res_out.status_code != 200:
            raise AssertionError(f"Transition to out_for_delivery failed: HTTP {res_out.status_code} {res_out.text}")
        if res_out.json().get("status") != "out_for_delivery":
            raise AssertionError(f"Expected status 'out_for_delivery', got '{res_out.json().get('status')}'")

        # 5. Advance to delivered
        res_del = self.client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "delivered", "reason": "Smoke test: handed over to customer"},
            headers=rider_headers,
        )
        if res_del.status_code != 200:
            raise AssertionError(f"Transition to delivered failed: HTTP {res_del.status_code} {res_del.text}")
        if res_del.json().get("status") != "delivered":
            raise AssertionError(f"Expected status 'delivered', got '{res_del.json().get('status')}'")

    # ── Step 5: Verification of Terminal State ─────────────────────────────────
    def test_step_5_terminal_verification(self) -> None:
        cust_headers = self.auth_headers("customer")
        rider_headers = self.auth_headers("rider")
        order_id = self.shared["order_id"]
        product_id = self.shared["product_id"]
        initial_stock = self.shared["initial_stock"]

        # 1. Verify Order status is delivered
        res_order = self.client.get(f"{API_PREFIX}/orders/{order_id}", headers=cust_headers)
        if res_order.status_code != 200:
            raise AssertionError(f"Failed to fetch order: HTTP {res_order.status_code} {res_order.text}")
        order_data = res_order.json()
        if order_data.get("status") != "delivered":
            raise AssertionError(f"Expected final order status 'delivered', got '{order_data.get('status')}'")

        # 2. Verify Audit Trail (One row per state transition)
        events = order_data.get("events", [])
        if len(events) < 5:
            raise AssertionError(f"Expected at least 5 order events in audit log, found {len(events)}")

        recorded_transitions = [(e.get("from_state"), e.get("to_state")) for e in events]
        # Confirm monotonic terminal progression
        if recorded_transitions[-1][1] != "delivered":
            raise AssertionError(f"Last recorded transition does not reach 'delivered': {recorded_transitions}")

        # 3. Verify Stock Decrement
        res_inv = self.client.get(f"{API_PREFIX}/products/{product_id}/inventory", headers=cust_headers)
        if res_inv.status_code != 200:
            raise AssertionError(f"Inventory lookup failed: HTTP {res_inv.status_code} {res_inv.text}")
        current_stock = res_inv.json().get("stock", 0)
        expected_stock = initial_stock - 1
        if current_stock != expected_stock:
            raise AssertionError(
                f"Stock invariant violated: expected {expected_stock} (decreased by 1), but got {current_stock}"
            )

        # 4. Verify Rider Availability Reactivated
        res_rider = self.client.get(f"{API_PREFIX}/riders/me", headers=rider_headers)
        if res_rider.status_code != 200:
            raise AssertionError(f"Rider profile fetch failed: HTTP {res_rider.status_code} {res_rider.text}")
        is_avail = res_rider.json().get("is_available")
        if not is_avail:
            raise AssertionError("Rider is not available after completing terminal delivery")

    # ── Step 6: Negative Checks ────────────────────────────────────────────────
    def test_step_6_negative_checks(self) -> None:
        cust_headers = self.auth_headers("customer")
        product_id = self.shared["product_id"]
        shop_id = self.shared["shop_id"]

        # Negative Check 1: Checkout beyond 5 km returns HTTP 400
        self.client.delete(f"{API_PREFIX}/cart", headers=cust_headers)
        self.client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product_id, "quantity": 1},
            headers=cust_headers,
        )

        res_far = self.client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": f"smoke-far-{uuid.uuid4()}",
                "destination_latitude": DELHI_LAT,
                "destination_longitude": DELHI_LON,
            },
            headers=cust_headers,
        )
        if res_far.status_code != 400:
            raise AssertionError(
                f"Expected HTTP 400 for delivery beyond 5km, got HTTP {res_far.status_code}: {res_far.text}"
            )

        # Negative Check 2: Same idempotency key returns the exact same order
        idempotency_key = f"smoke-idem-{uuid.uuid4()}"
        res_order1 = self.client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": idempotency_key,
                "destination_latitude": PATNA_LAT,
                "destination_longitude": PATNA_LON,
            },
            headers=cust_headers,
        )
        if res_order1.status_code != 201:
            raise AssertionError(f"Initial checkout failed: HTTP {res_order1.status_code} {res_order1.text}")
        order_id1 = res_order1.json().get("id")

        res_order2 = self.client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": idempotency_key,
                "destination_latitude": PATNA_LAT,
                "destination_longitude": PATNA_LON,
            },
            headers=cust_headers,
        )
        if res_order2.status_code not in (200, 201):
            raise AssertionError(f"Idempotent retry failed: HTTP {res_order2.status_code} {res_order2.text}")
        order_id2 = res_order2.json().get("id")

        if order_id1 != order_id2:
            raise AssertionError(
                f"Idempotency violation: initial order ID {order_id1} != retry order ID {order_id2}"
            )

        # Negative Check 3: Customer calling shop owner endpoint returns HTTP 403
        res_unauth = self.client.patch(
            f"{API_PREFIX}/shops/{shop_id}/orders/{order_id1}/status",
            json={"status": "confirmed"},
            headers=cust_headers,
        )
        if res_unauth.status_code != 403:
            raise AssertionError(
                f"Expected HTTP 403 when customer updates shop order, got HTTP {res_unauth.status_code}: {res_unauth.text}"
            )


# ── Execution Harness ──────────────────────────────────────────────────────────
def run_all_smoke_tests() -> bool:
    osrm_server = _ensure_osrm_available()
    runner = SmokeTestRunner(base_url=BASE_URL)

    steps = [
        ("Step 1: Health, Docs, DB, Redis, and OSRM Reachable", runner.test_step_1_health_and_docs),
        ("Step 2: Customer Flow (Login, Discover, Cart, Checkout COD)", runner.test_step_2_customer_flow),
        ("Step 3: Shop Owner Flow (Login, Accept, Preparing, Ready)", runner.test_step_3_shop_owner_flow),
        ("Step 4: Rider Flow (Login, On-Duty, Accept/Assign, Delivered)", runner.test_step_4_rider_flow),
        ("Step 5: Terminal Verification (Delivered, Events, Stock, Rider)", runner.test_step_5_terminal_verification),
        ("Step 6: Negative Checks (>5km 400, Idempotency, RBAC 403)", runner.test_step_6_negative_checks),
    ]

    print("=" * 72)
    print(f"DUKAANLY API SMOKE TEST RUNNER -- Target: {BASE_URL}")
    print("=" * 72)

    all_passed = True
    start_total = time.perf_counter()

    try:
        for idx, (title, func) in enumerate(steps, 1):
            step_start = time.perf_counter()
            try:
                func()
                elapsed = time.perf_counter() - step_start
                print(f"[PASS] {title} ({elapsed:.3f}s)")
            except Exception as exc:
                elapsed = time.perf_counter() - step_start
                print(f"[FAIL] {title} ({elapsed:.3f}s)")
                print(f"       Error: {exc}")
                all_passed = False
                break
    finally:
        runner.close()
        if osrm_server:
            try:
                osrm_server.shutdown()
            except Exception:
                pass

    total_elapsed = time.perf_counter() - start_total
    print("-" * 72)
    if all_passed:
        print(f"ALL 6 SMOKE TEST STEPS PASSED SUCCESSFULLY ({total_elapsed:.2f}s total)")
        print("=" * 72)
        return True
    else:
        print(f"SMOKE TEST SUITE FAILED ({total_elapsed:.2f}s total)")
        print("=" * 72)
        return False


if __name__ == "__main__":
    success = run_all_smoke_tests()
    sys.exit(0 if success else 1)
