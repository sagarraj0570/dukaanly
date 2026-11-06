"""
System Test Foundation & Fixture Verification.
"""

import pytest
from sqlalchemy import text
from tests_system.conftest import System
from tests_system.factory import SystemScenario


@pytest.mark.asyncio
async def test_system_helper_interfaces(system: System):
    """Verify System helper provides functional DB and Redis connectivity."""
    rows = await system.execute_query("SELECT 1 AS ready;")
    assert rows[0][0] == 1

    await system.redis.set("systest:ping", "pong", ex=30)
    pong = await system.redis.get("systest:ping")
    assert pong == "pong"


@pytest.mark.asyncio
async def test_scenario_provisioning_and_isolation(system: System, scenario: SystemScenario):
    """Verify scenario factory provisions namespaced customer, shop, products, and riders."""
    # 1. Customer verification
    assert scenario.customer_token is not None
    assert scenario.customer_user["email"].startswith(f"systest-{scenario.run_id}-customer@")

    # 2. Shop verification
    assert scenario.shop["name"].startswith(f"SYSTEST {scenario.run_id}")
    # Verify shop is verified and orderable in DB
    rows = await system.execute_query(
        "SELECT verification_status, is_orderable, is_active FROM shops WHERE id = :sid",
        {"sid": scenario.shop["id"]}
    )
    assert len(rows) == 1
    assert rows[0][0] == "verified"
    assert rows[0][1] is True
    assert rows[0][2] is True

    # 3. Products & Stock verification
    assert len(scenario.products) == 6
    for p in scenario.products:
        inv_rows = await system.execute_query(
            "SELECT stock, version FROM inventory WHERE product_id = :pid",
            {"pid": p["id"]}
        )
        assert len(inv_rows) == 1
        assert inv_rows[0][0] == 5
        assert inv_rows[0][1] == 1

    # 4. Riders verification
    assert len(scenario.riders) == 2
    assert len(scenario.rider_tokens) == 2
    for r in scenario.riders:
        r_rows = await system.execute_query(
            "SELECT is_available FROM rider_profiles WHERE id = :rid",
            {"rid": r["id"]}
        )
        assert len(r_rows) == 1
        assert r_rows[0][0] is True
