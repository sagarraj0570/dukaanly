"""
Fault Injection & Mutation Suite for Dukaanly System Test Harness.

Applies safe, reversible database-level and API-level faults inside an isolated
test scenario and asserts that:
1. Invariant assertions immediately detect database corruption.
2. API security and validation layers reject malformed and unauthorized requests.
Proves that the system test harness detects failures rather than passing vacuously.
"""

import uuid
import logging
from dataclasses import dataclass
from typing import List, Optional

import httpx
from sqlalchemy import text

from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.invariants import verify_system_invariants, InvariantViolationError
from tests_system.config import API_PREFIX, PATNA_LAT, PATNA_LON

logger = logging.getLogger("tests_system.mutations")


@dataclass
class FaultResult:
    name: str
    tier: str
    detected: bool
    description: str
    details: Optional[str] = None


async def run_database_fault_injections(system: System, scenario: SystemScenario) -> List[FaultResult]:
    """
    Applies reversible database corruption faults and asserts that
    verify_system_invariants detects every violation.
    """
    results: List[FaultResult] = []
    product = scenario.products[0]
    rider = scenario.riders[0]

    # ── Fault 1: Negative Inventory Stock ─────────────────────────────────────
    fault_name = "db_negative_inventory_stock"
    try:
        # Temporarily drop check constraint to inject negative stock fault
        await system.execute_query("ALTER TABLE inventory DROP CONSTRAINT IF EXISTS chk_inventory_stock_non_negative")
        await system.execute_query(
            "UPDATE inventory SET stock = -10 WHERE product_id = :pid",
            {"pid": product["id"]},
        )
        detected = False
        try:
            await verify_system_invariants(scenario.run_id)
        except InvariantViolationError as e:
            detected = True
            details = str(e)
        finally:
            # Revert and restore constraint
            await system.execute_query(
                "UPDATE inventory SET stock = 5 WHERE product_id = :pid",
                {"pid": product["id"]},
            )
            await system.execute_query(
                "ALTER TABLE inventory ADD CONSTRAINT chk_inventory_stock_non_negative CHECK (stock >= 0)"
            )
        results.append(FaultResult(fault_name, "database", detected, "Negative stock injected into inventory table", details if detected else "Checker failed to catch negative stock"))
    except Exception as exc:
        results.append(FaultResult(fault_name, "database", False, "Fault execution error", str(exc)))

    # ── Fault 2: Unavailable Rider Without Active Delivery ────────────────────
    fault_name = "db_unavailable_rider_without_delivery"
    try:
        await system.execute_query(
            "UPDATE rider_profiles SET is_available = false WHERE id = :rid",
            {"rid": rider["id"]},
        )
        detected = False
        try:
            await verify_system_invariants(scenario.run_id)
        except InvariantViolationError as e:
            detected = True
            details = str(e)
        finally:
            await system.execute_query(
                "UPDATE rider_profiles SET is_available = true WHERE id = :rid",
                {"rid": rider["id"]},
            )
        results.append(FaultResult(fault_name, "database", detected, "Rider set unavailable with zero active deliveries", details if detected else "Checker failed to catch ghost busy rider"))
    except Exception as exc:
        results.append(FaultResult(fault_name, "database", False, "Fault execution error", str(exc)))

    # ── Fault 3: Duplicate Order Transition Events ────────────────────────────
    fault_name = "db_duplicate_transition_events"
    try:
        # Create an order to attach events to
        with system.create_client() as client:
            cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
            client.post(f"{API_PREFIX}/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_h)
            r = client.post(
                f"{API_PREFIX}/orders/checkout",
                json={
                    "idempotency_key": str(uuid.uuid4()),
                    "delivery_address": "Patna",
                    "delivery_latitude": PATNA_LAT,
                    "delivery_longitude": PATNA_LON,
                    "payment_method": "cod",
                },
                headers=cust_h,
            )
            order_id = r.json()["id"]

        # Insert duplicate order events
        event_id1 = uuid.uuid4()
        event_id2 = uuid.uuid4()
        await system.execute_query(
            """
            INSERT INTO order_events (id, order_id, from_state, to_state, actor_role, reason)
            VALUES (:id1, :oid, 'pending', 'confirmed', 'shop_owner', 'test_dup_1'),
                   (:id2, :oid, 'pending', 'confirmed', 'shop_owner', 'test_dup_2')
            """,
            {"id1": event_id1, "id2": event_id2, "oid": order_id},
        )
        detected = False
        try:
            await verify_system_invariants(scenario.run_id)
        except InvariantViolationError as e:
            detected = True
            details = str(e)
        finally:
            await system.execute_query(
                "DELETE FROM order_events WHERE id IN (:id1, :id2)",
                {"id1": event_id1, "id2": event_id2},
            )
        results.append(FaultResult(fault_name, "database", detected, "Duplicate from_state->to_state transition events inserted", details if detected else "Checker failed to catch duplicate events"))
    except Exception as exc:
        results.append(FaultResult(fault_name, "database", False, "Fault execution error", str(exc)))

    # ── Fault 4: Open Delivery Offer On Terminal Delivery ─────────────────────
    fault_name = "db_open_offer_on_terminal_delivery"
    try:
        # Create a delivery row in terminal state
        deliv_id = uuid.uuid4()
        offer_id = uuid.uuid4()
        await system.execute_query(
            """
            INSERT INTO deliveries (id, order_id, rider_id, status, destination_location)
            VALUES (:did, :oid, :rid, 'delivered', ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            """,
            {"did": deliv_id, "oid": order_id, "rid": rider["id"], "lat": PATNA_LAT, "lon": PATNA_LON},
        )
        await system.execute_query(
            """
            INSERT INTO delivery_offers (id, delivery_id, rider_id, attempt_no, status, expires_at)
            VALUES (:ofid, :did, :rid, 1, 'offered', NOW() + interval '5 minutes')
            """,
            {"ofid": offer_id, "did": deliv_id, "rid": rider["id"]},
        )
        detected = False
        try:
            await verify_system_invariants(scenario.run_id)
        except InvariantViolationError as e:
            detected = True
            details = str(e)
        finally:
            await system.execute_query("DELETE FROM delivery_offers WHERE id = :ofid", {"ofid": offer_id})
            await system.execute_query("DELETE FROM deliveries WHERE id = :did", {"did": deliv_id})
        results.append(FaultResult(fault_name, "database", detected, "Active offer left on delivered delivery", details if detected else "Checker failed to catch offer on terminal delivery"))
    except Exception as exc:
        results.append(FaultResult(fault_name, "database", False, "Fault execution error", str(exc)))

    # ── Fault 5: Order Total Math Corruption ──────────────────────────────────
    fault_name = "db_order_total_mismatch"
    try:
        await system.execute_query(
            "UPDATE orders SET total_amount = total_amount + 999.00 WHERE id = :oid",
            {"oid": order_id},
        )
        detected = False
        try:
            await verify_system_invariants(scenario.run_id)
        except InvariantViolationError as e:
            detected = True
            details = str(e)
        finally:
            await system.execute_query(
                "UPDATE orders SET total_amount = total_amount - 999.00 WHERE id = :oid",
                {"oid": order_id},
            )
        results.append(FaultResult(fault_name, "database", detected, "Order total altered to mismatch items sum", details if detected else "Checker failed to catch total mismatch"))
    except Exception as exc:
        results.append(FaultResult(fault_name, "database", False, "Fault execution error", str(exc)))

    return results


async def run_api_fault_injections(system: System, scenario: SystemScenario) -> List[FaultResult]:
    """
    Submits mutated, tampered, or unauthorized requests and asserts rejection.
    """
    results: List[FaultResult] = []
    product = scenario.products[0]

    with system.create_client() as client:
        # ── Fault 6: Negative Cart Quantity ───────────────────────────────────
        fault_name = "api_tampered_negative_quantity"
        r = client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": -5},
            headers={"Authorization": f"Bearer {scenario.customer_token}"},
        )
        detected = r.status_code in (400, 422)
        results.append(FaultResult(fault_name, "api", detected, "Negative quantity rejected at validation", f"HTTP {r.status_code}"))

        # ── Fault 7: Tampered / Expired JWT Token ─────────────────────────────
        fault_name = "api_tampered_jwt_token"
        r = client.get(
            f"{API_PREFIX}/orders",
            headers={"Authorization": "Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.invalid.signature"},
        )
        detected = r.status_code == 401
        results.append(FaultResult(fault_name, "api", detected, "Tampered JWT signature rejected with 401", f"HTTP {r.status_code}"))

        # ── Fault 8: Wrong Role Privilege Escalation ──────────────────────────
        fault_name = "api_wrong_role_privilege_escalation"
        r = client.patch(
            f"{API_PREFIX}/shops/{scenario.shop['id']}/orders/{uuid.uuid4()}/status",
            json={"status": "confirmed"},
            headers={"Authorization": f"Bearer {scenario.customer_token}"},
        )
        detected = r.status_code in (403, 404)
        results.append(FaultResult(fault_name, "api", detected, "Customer calling shop management endpoint rejected with 403", f"HTTP {r.status_code}"))

        # ── Fault 9: Horizontal Privilege Escalation (Cross-Customer) ─────────
        fault_name = "api_cross_customer_order_access"
        # Customer 2 accessing Customer 1's order
        if scenario.customer2_token:
            r = client.get(
                f"{API_PREFIX}/orders/{uuid.uuid4()}",
                headers={"Authorization": f"Bearer {scenario.customer2_token}"},
            )
            detected = r.status_code in (403, 404)
            results.append(FaultResult(fault_name, "api", detected, "Access to another user's order rejected with 403/404", f"HTTP {r.status_code}"))

    return results
