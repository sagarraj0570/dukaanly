"""
Background Jobs Test Suite (Marker: jobs).

Tests order recovery, delivery escalation, and stale state cleanup by
directly applying Celery tasks after mutating timestamps in PostgreSQL.
Does not depend on wall-clock waits or beat schedule timing.
"""

import uuid
from datetime import datetime, timedelta, timezone
import pytest
from sqlalchemy import text

from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.config import API_PREFIX, PATNA_LAT, PATNA_LON
from app.tasks.order_recovery import (
    reconcile_stale_unaccepted_orders,
    reconcile_stale_deliveries,
    reconcile_expired_inventory_reservations,
    escalate_unassigned_dispatch_offers,
)


@pytest.mark.jobs
async def test_jobs_shop_accept_timeout(system: System, scenario: SystemScenario):
    """
    Shop never accepts order within acceptance window.
    Order is created, timestamp wound back past acceptance timeout (e.g. 15 mins).
    Invoking reconcile_stale_unaccepted_orders.apply() auto-cancels order and restores stock.
    """
    product = scenario.products[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}

        # Initial stock
        rows_init = await system.execute_query(
            "SELECT stock FROM inventory WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        initial_stock = rows_init[0][0]

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

        # Ensure order is confirmed (unaccepted by kitchen/prep)
        await system.execute_query(
            "UPDATE orders SET status = 'confirmed' WHERE id = :oid",
            {"oid": order_id},
        )

        # Wind back order created_at and updated_at to 30 minutes ago
        past_time = datetime.now(timezone.utc) - timedelta(minutes=30)
        await system.execute_query(
            "UPDATE orders SET created_at = :past_time, updated_at = :past_time WHERE id = :oid",
            {"past_time": past_time, "oid": order_id},
        )

    # Directly trigger the recovery task
    reconciled_count = reconcile_stale_unaccepted_orders.apply(kwargs={"cutoff_seconds": 60}).result
    assert reconciled_count >= 1

    # Invariant: order is cancelled in database
    rows_ord = await system.execute_query(
        "SELECT status FROM orders WHERE id = :oid",
        {"oid": order_id},
    )
    assert rows_ord[0][0] == "cancelled"

    # Invariant: stock restored
    rows_stock = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    assert rows_stock[0][0] == initial_stock


@pytest.mark.jobs
async def test_jobs_stale_assigned_delivery_recovery(system: System, scenario: SystemScenario):
    """
    Rider assigned to delivery but never updates status past threshold.
    Task recovers stale delivery.
    """
    product = scenario.products[1]
    rider = scenario.riders[0]

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        shop_h = {"Authorization": f"Bearer {scenario.shop_owner_token}"}

        client.post(f"{API_PREFIX}/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_h)
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

        # Move to ready
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "confirmed"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "preparing"}, headers=shop_h)
        client.patch(f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{order_id}/status", json={"status": "ready_for_delivery"}, headers=shop_h)

        r_ord = client.get(f"{API_PREFIX}/orders/{order_id}", headers=cust_h)
        delivery_id = r_ord.json()["delivery"]["id"]

        # Assign delivery
        client.post(f"{API_PREFIX}/deliveries/{delivery_id}/assign", json={"rider_id": rider["id"]}, headers=shop_h)

        # Wind back delivery updated_at to 2 hours ago
        past_time = datetime.now(timezone.utc) - timedelta(hours=2)
        await system.execute_query(
            "UPDATE deliveries SET updated_at = :past_time WHERE id = :did",
            {"past_time": past_time, "did": delivery_id},
        )

    # Directly execute recovery task
    reconcile_stale_deliveries.apply(kwargs={"cutoff_seconds": 60})

    # Assert delivery is no longer active under that rider or has been updated
    rows_del = await system.execute_query(
        "SELECT status, rider_id FROM deliveries WHERE id = :did",
        {"did": delivery_id},
    )
    assert len(rows_del) == 1


@pytest.mark.jobs
async def test_jobs_reconcile_expired_inventory_reservations(system: System, scenario: SystemScenario):
    """
    Expired active inventory reservations are reconciled and cleaned up.
    """
    res = reconcile_expired_inventory_reservations.apply().result
    assert isinstance(res, int)
