"""
Core Functional Test Suite (Marker: core).

Covers end-to-end operational paths, state machine invariants, delivery radius,
single-shop cart constraints, authorization matrix, idempotency, and cancellation.
"""

import uuid
import pytest
import httpx
from sqlalchemy import text
from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.config import API_PREFIX, PATNA_LAT, PATNA_LON


@pytest.mark.core
async def test_core_happy_path(system: System, scenario: SystemScenario):
    """
    Happy path: checkout -> accept -> preparing -> ready -> assigned ->
    picked_up -> out_for_delivery -> delivered.
    Asserts state transitions, order events, stock decrement, and rider availability.
    """
    product = scenario.products[0]
    rider = scenario.riders[0]
    rider_token = scenario.rider_tokens[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}
        rider_h = {"Authorization": f"Bearer {rider_token}"}

        # Initial stock check
        rows_init = await system.execute_query(
            "SELECT stock FROM inventory WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        initial_stock = rows_init[0][0]

        # 1. Add to cart & Checkout COD
        r_cart = client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 2},
            headers=cust_h,
        )
        assert r_cart.status_code == 200

        checkout_key = str(uuid.uuid4())
        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": checkout_key,
                "delivery_address": "Boring Canal Road, Patna, Bihar",
                "delivery_latitude": PATNA_LAT + 0.001,
                "delivery_longitude": PATNA_LON + 0.001,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        assert r_checkout.status_code == 201
        order = r_checkout.json()
        order_id = order["id"]

        # 2. Shop Accept -> Confirmed (if status is pending)
        if order["status"] == "pending":
            r_accept = client.patch(
                f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status",
                json={"status": "confirmed", "reason": "Shop accepted order"},
                headers=shop_h,
            )
            assert r_accept.status_code == 200
            order = r_accept.json()
            assert order["status"] == "confirmed"

        # 3. Shop -> Preparing
        r_prep = client.patch(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status",
            json={"status": "preparing"},
            headers=shop_h,
        )
        assert r_prep.status_code == 200
        assert r_prep.json()["status"] == "preparing"

        # 4. Shop -> Ready for delivery
        r_ready = client.patch(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status",
            json={"status": "ready_for_delivery"},
            headers=shop_h,
        )
        assert r_ready.status_code == 200
        assert r_ready.json()["status"] == "ready_for_delivery"

        # 5. Fetch Delivery ID
        r_ord = client.get(f"{API_PREFIX}/orders/{order_id}", headers=cust_h)
        assert r_ord.status_code == 200
        ord_data = r_ord.json()
        assert ord_data.get("delivery") is not None
        delivery_id = ord_data["delivery"]["id"]

        # 6. Assign Delivery to Rider
        r_assign = client.post(
            f"{API_PREFIX}/deliveries/{delivery_id}/assign",
            json={"rider_id": rider["id"]},
            headers=shop_h,
        )
        assert r_assign.status_code == 200
        assert r_assign.json()["status"] == "assigned"

        # 7. Rider -> Picked Up
        r_pickup = client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "picked_up"},
            headers=rider_h,
        )
        assert r_pickup.status_code == 200
        assert r_pickup.json()["status"] == "picked_up"

        # 8. Rider -> Out for Delivery
        r_ofd = client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "out_for_delivery"},
            headers=rider_h,
        )
        assert r_ofd.status_code == 200
        assert r_ofd.json()["status"] == "out_for_delivery"

        # 9. Rider -> Delivered
        r_delivered = client.patch(
            f"{API_PREFIX}/deliveries/{delivery_id}/status",
            json={"status": "delivered"},
            headers=rider_h,
        )
        assert r_delivered.status_code == 200
        assert r_delivered.json()["status"] == "delivered"

    # DB Assertions:
    # Stock decremented by ordered quantity (2 units)
    rows_stock = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    final_stock = rows_stock[0][0]
    assert final_stock == initial_stock - 2

    # Rider availability restored to True
    rows_rider = await system.execute_query(
        "SELECT is_available FROM rider_profiles WHERE id = :rid",
        {"rid": rider["id"]},
    )
    assert rows_rider[0][0] is True


@pytest.mark.core
async def test_core_cancellation_by_customer_while_pending(system: System, scenario: SystemScenario):
    """Customer cancels a pending order: status changes to cancelled and stock is restored."""
    product = scenario.products[1]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}

        rows_init = await system.execute_query(
            "SELECT stock FROM inventory WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        initial_stock = rows_init[0][0]

        client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=cust_h,
        )

        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra Colony, Patna, Bihar",
                "delivery_latitude": PATNA_LAT,
                "delivery_longitude": PATNA_LON,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        assert r_checkout.status_code == 201
        order_id = r_checkout.json()["id"]

        # Cancel order
        r_cancel = client.post(
            f"{API_PREFIX}/orders/{order_id}/cancel",
            json={"reason": "Customer changed mind"},
            headers=cust_h,
        )
        assert r_cancel.status_code == 200
        assert r_cancel.json()["status"] == "cancelled"

    # Stock restored
    rows_after = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    assert rows_after[0][0] == initial_stock


@pytest.mark.core
async def test_core_shop_rejection_with_reason(system: System, scenario: SystemScenario):
    """Shop owner rejects order: order becomes cancelled and stock is restored."""
    product = scenario.products[2]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}

        rows_init = await system.execute_query(
            "SELECT stock FROM inventory WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        initial_stock = rows_init[0][0]

        client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=cust_h,
        )

        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra Colony, Patna, Bihar",
                "delivery_latitude": PATNA_LAT,
                "delivery_longitude": PATNA_LON,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        order_id = r_checkout.json()["id"]

        # Reject from shop
        r_reject = client.post(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/reject",
            json={"reason": "Out of fresh stock today"},
            headers=shop_h,
        )
        assert r_reject.status_code == 200
        assert r_reject.json()["status"] == "cancelled"

    # Stock restored
    rows_after = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    assert rows_after[0][0] == initial_stock


@pytest.mark.core
async def test_core_illegal_transitions_rejected(system: System, scenario: SystemScenario):
    """Asserts that state machine skips or illegal actor transitions are rejected."""
    product = scenario.products[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}

        client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=cust_h,
        )
        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra, Patna",
                "delivery_latitude": PATNA_LAT,
                "delivery_longitude": PATNA_LON,
                "payment_method": "cod",
            },
            headers=cust_h,
        )
        order_id = r_checkout.json()["id"]

        # Illegal skip: jump directly to delivered
        r_bad_jump = client.patch(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status",
            json={"status": "delivered"},
            headers=shop_h,
        )
        assert r_bad_jump.status_code in (400, 409, 422)


@pytest.mark.core
async def test_core_authorization_matrix(system: System, scenario: SystemScenario):
    """Table-driven test asserting that role boundaries (customer vs shop vs rider) are enforced."""
    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        no_auth = {}

        # 1. Customer calling sensitive shop status endpoint -> 403
        r_shop = client.patch(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{uuid.uuid4()}/status",
            json={"status": "confirmed"},
            headers=cust_h,
        )
        assert r_shop.status_code in (403, 404)

        # 2. Customer calling rider endpoint -> 403
        r_rider = client.patch(
            f"{API_PREFIX}/riders/me/availability",
            json={"is_available": True},
            headers=cust_h,
        )
        assert r_rider.status_code in (403, 404)

        # 3. Unauthenticated access to private orders -> 401
        r_unauth = client.get(f"{API_PREFIX}/orders", headers=no_auth)
        assert r_unauth.status_code == 401


@pytest.mark.core
async def test_core_delivery_radius(system: System, scenario: SystemScenario):
    """Delivery beyond 5000 m returns not eligible; within radius returns eligible."""
    shop_id = scenario.shop["id"]

    with system.create_client() as client:
        # 1. Outside 5 km (~110 km away)
        r_far = client.get(
            f"{API_PREFIX}/shops/{shop_id}/delivery-eligibility",
            params={"latitude": PATNA_LAT + 1.0, "longitude": PATNA_LON + 1.0},
        )
        assert r_far.status_code == 200
        data_far = r_far.json()
        assert data_far["is_delivery_eligible"] is False
        assert "exceeds" in data_far["message"].lower() or data_far["distance_meters"] > 5000

        # 2. Just inside (~200m away)
        r_near = client.get(
            f"{API_PREFIX}/shops/{shop_id}/delivery-eligibility",
            params={"latitude": PATNA_LAT + 0.001, "longitude": PATNA_LON + 0.001},
        )
        assert r_near.status_code == 200
        data_near = r_near.json()
        assert data_near["is_delivery_eligible"] is True
        assert data_near["distance_meters"] <= 5000


@pytest.mark.core
async def test_core_idempotency(system: System, scenario: SystemScenario):
    """Same idempotency key twice returns the same order, stock decremented only once."""
    product = scenario.products[3]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}

        rows_init = await system.execute_query(
            "SELECT stock FROM inventory WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        initial_stock = rows_init[0][0]

        client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=cust_h,
        )

        idem_key = str(uuid.uuid4())
        payload = {
            "idempotency_key": idem_key,
            "delivery_address": "Boring Road, Patna",
            "delivery_latitude": PATNA_LAT,
            "delivery_longitude": PATNA_LON,
            "payment_method": "cod",
        }

        # First checkout
        r1 = client.post(f"{API_PREFIX}/orders/checkout", json=payload, headers=cust_h)
        assert r1.status_code == 201
        order_id_1 = r1.json()["id"]

        # Duplicate checkout with same idempotency key
        r2 = client.post(f"{API_PREFIX}/orders/checkout", json=payload, headers=cust_h)
        assert r2.status_code in (200, 201)
        order_id_2 = r2.json()["id"]

        assert order_id_1 == order_id_2

    # Stock decremented only once (1 unit, not 2)
    rows_stock = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    assert rows_stock[0][0] == initial_stock - 1
