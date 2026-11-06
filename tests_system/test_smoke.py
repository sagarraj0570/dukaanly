"""
Smoke Test Suite (Marker: smoke, target: <15s).

Verifies core end-to-end viability:
1. Subsystems reachable (Health, Docs, DB, Redis, OSRM).
2. Login succeeds for all three roles (customer, shop_owner, rider).
3. Shop discovery returns the test shop at Patna location.
4. One COD order placed and verified via API and DB.
"""

import uuid
import pytest
import httpx
from sqlalchemy import text
from tests_system.conftest import System
from tests_system.factory import SystemScenario
from tests_system.config import PATNA_LAT, PATNA_LON, API_PREFIX


@pytest.mark.smoke
async def test_smoke_subsystems_reachable(system: System):
    """Asserts that FastAPI, Docs, DB, Redis, and OSRM are reachable."""
    with system.create_client() as client:
        # FastAPI Liveness & Readiness
        res_live = client.get(f"{API_PREFIX}/health/live")
        assert res_live.status_code == 200, f"Health live failed: {res_live.text}"
        assert res_live.json().get("status") == "ok"

        res_ready = client.get(f"{API_PREFIX}/health/ready")
        assert res_ready.status_code == 200, f"Health ready failed: {res_ready.text}"
        assert res_ready.json().get("status") == "ready"

        # OpenAPI Docs
        res_docs = client.get(f"{API_PREFIX}/docs")
        assert res_docs.status_code in (200, 307)

    # Redis reachable
    assert await system.redis.ping() is True

    # Database reachable
    rows = await system.execute_query("SELECT 1;")
    assert len(rows) == 1 and rows[0][0] == 1


@pytest.mark.smoke
async def test_smoke_login_all_roles(system: System, scenario: SystemScenario):
    """Verifies that customer, shop_owner, and rider authentication tokens are valid."""
    with system.create_client() as client:
        # Customer Profile
        r_cust = client.get(f"{API_PREFIX}/auth/me", headers={"Authorization": f"Bearer {scenario.customer_token}"})
        assert r_cust.status_code == 200
        assert r_cust.json()["role"] == "customer"

        # Shop Owner Profile
        r_shop = client.get(f"{API_PREFIX}/auth/me", headers={"Authorization": f"Bearer {scenario.shop_owner_token}"})
        assert r_shop.status_code == 200
        assert r_shop.json()["role"] == "shop_owner"

        # Rider Profile
        r_rider = client.get(f"{API_PREFIX}/riders/me", headers={"Authorization": f"Bearer {scenario.rider_tokens[0]}"})
        assert r_rider.status_code == 200
        assert r_rider.json()["is_available"] is True


@pytest.mark.smoke
async def test_smoke_shop_discovery(system: System, scenario: SystemScenario):
    """Verifies discovery endpoint returns the scenario's active shop in Patna."""
    with system.create_client() as client:
        res = client.get(
            f"{API_PREFIX}/shops",
            params={
                "latitude": PATNA_LAT,
                "longitude": PATNA_LON,
                "radius_meters": 5000,
                "active_only": True,
            },
            headers={"Authorization": f"Bearer {scenario.customer_token}"},
        )
        assert res.status_code == 200
        data = res.json()
        shop_ids = [s["id"] for s in data.get("items", [])]
        assert scenario.shop["id"] in shop_ids, "Scenario shop not found in discovery response"


@pytest.mark.smoke
async def test_smoke_cod_order_placed(system: System, scenario: SystemScenario):
    """Places a single item COD order and asserts state in both API response and DB."""
    product = scenario.products[0]

    with system.create_client() as client:
        headers = {"Authorization": f"Bearer {scenario.customer_token}"}

        # 1. Add item to cart
        r_cart = client.post(
            f"{API_PREFIX}/cart/items",
            json={"product_id": product["id"], "quantity": 1},
            headers=headers,
        )
        assert r_cart.status_code == 200

        # 2. Checkout COD
        r_checkout = client.post(
            f"{API_PREFIX}/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "delivery_address": "Patliputra Colony, Patna, Bihar",
                "delivery_latitude": PATNA_LAT + 0.002,
                "delivery_longitude": PATNA_LON + 0.002,
                "payment_method": "cod",
            },
            headers=headers,
        )
        assert r_checkout.status_code == 201, f"Checkout failed: {r_checkout.text}"
        order = r_checkout.json()
        assert order["status"] in ("pending", "confirmed")
        order_id = order["id"]

    # 3. Direct DB verification
    rows = await system.execute_query(
        "SELECT id, status, total_amount FROM orders WHERE id = :oid",
        {"oid": order_id},
    )
    assert len(rows) == 1
    assert str(rows[0][0]) == order_id
    assert rows[0][1] in ("pending", "confirmed")
    assert float(rows[0][2]) > 0
