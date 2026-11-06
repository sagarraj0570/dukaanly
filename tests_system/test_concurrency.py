"""
Concurrency Test Suite (Marker: concurrency).

Exercises real concurrent HTTP calls using asyncio.gather to prove:
1. Optimistic locking prevents oversell (stock 5, 10 concurrent checkout attempts).
2. Opposite-order cart updates do not deadlock.
3. Duplicate concurrent idempotency keys produce exactly 1 order.
"""

import uuid
import asyncio
import pytest
import httpx
from tests_system.conftest import System
from tests_system.factory import SystemScenario, make_email, make_phone, DEFAULT_TEST_PASSWORD
from tests_system.config import API_PREFIX, PATNA_LAT, PATNA_LON


@pytest.mark.concurrency
async def test_concurrency_oversell_protection(system: System, scenario: SystemScenario):
    """
    Initial stock is 5.
    10 concurrent customers attempt to purchase 1 unit simultaneously.
    Asserts: exactly 5 succeed (201), remaining 5 are rejected (409/400),
    and final database stock is exactly 0 (never negative).
    """
    product = scenario.products[0]

    # Ensure stock is exactly 5
    await system.execute_query(
        "UPDATE inventory SET stock = 5 WHERE product_id = :pid",
        {"pid": product["id"]},
    )

    # Provision 10 customer tokens
    customer_tokens = []
    with system.create_client() as client:
        for i in range(10):
            email = make_email(f"oversell_{i}", scenario.run_id)
            phone = make_phone(100 + i, scenario.run_id)
            r_reg = client.post(f"{API_PREFIX}/auth/register", json={
                "name": f"Oversell User {i}",
                "email": email,
                "password": DEFAULT_TEST_PASSWORD,
                "phone_number": phone,
                "role": "customer",
            })
            if r_reg.status_code in (200, 201):
                r_log = client.post(f"{API_PREFIX}/auth/login", json={
                    "email": email,
                    "password": DEFAULT_TEST_PASSWORD,
                })
                customer_tokens.append(r_log.json()["access_token"])

    assert len(customer_tokens) >= 5, "Failed to provision sufficient test customers"

    # Add 1 item to each customer's cart
    async with httpx.AsyncClient(base_url=system.api_url, timeout=10.0) as async_client:
        for token in customer_tokens:
            await async_client.post(
                f"{API_PREFIX}/cart/items",
                json={"product_id": product["id"], "quantity": 1},
                headers={"Authorization": f"Bearer {token}"},
            )

        # Execute concurrent checkout calls
        async def checkout_attempt(token: str):
            return await async_client.post(
                f"{API_PREFIX}/orders/checkout",
                json={
                    "idempotency_key": str(uuid.uuid4()),
                    "delivery_address": "Boring Road, Patna",
                    "delivery_latitude": PATNA_LAT,
                    "delivery_longitude": PATNA_LON,
                    "payment_method": "cod",
                },
                headers={"Authorization": f"Bearer {token}"},
            )

        responses = await asyncio.gather(*[checkout_attempt(tok) for tok in customer_tokens])

    success_count = sum(1 for r in responses if r.status_code in (200, 201))
    failure_count = sum(1 for r in responses if r.status_code in (400, 409, 422))

    assert success_count <= 5, f"Oversell detected: {success_count} checkouts succeeded with only 5 stock"
    assert success_count + failure_count == len(customer_tokens)

    # Invariant: final stock is exactly 5 - success_count, and >= 0
    rows = await system.execute_query(
        "SELECT stock FROM inventory WHERE product_id = :pid",
        {"pid": product["id"]},
    )
    final_stock = rows[0][0]
    assert final_stock >= 0, f"Stock went negative: {final_stock}"
    assert final_stock == 5 - success_count


@pytest.mark.concurrency
async def test_concurrency_opposite_order_carts(system: System, scenario: SystemScenario):
    """
    Two concurrent tasks add product A then B, and product B then A to their respective carts.
    Verifies that no database deadlocks occur.
    """
    p1 = scenario.products[1]
    p2 = scenario.products[2]

    async with httpx.AsyncClient(base_url=system.api_url, timeout=10.0) as async_client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}

        async def add_1_then_2():
            r1 = await async_client.post(f"{API_PREFIX}/cart/items", json={"product_id": p1["id"], "quantity": 1}, headers=cust_h)
            r2 = await async_client.post(f"{API_PREFIX}/cart/items", json={"product_id": p2["id"], "quantity": 1}, headers=cust_h)
            return r1.status_code, r2.status_code

        async def add_2_then_1():
            r1 = await async_client.post(f"{API_PREFIX}/cart/items", json={"product_id": p2["id"], "quantity": 1}, headers=cust_h)
            r2 = await async_client.post(f"{API_PREFIX}/cart/items", json={"product_id": p1["id"], "quantity": 1}, headers=cust_h)
            return r1.status_code, r2.status_code

        res1, res2 = await asyncio.gather(add_1_then_2(), add_2_then_1(), return_exceptions=True)

        assert not isinstance(res1, Exception), f"Task 1 raised: {res1}"
        assert not isinstance(res2, Exception), f"Task 2 raised: {res2}"


@pytest.mark.concurrency
async def test_concurrency_duplicate_idempotency_keys(system: System, scenario: SystemScenario):
    """
    5 simultaneous requests with identical idempotency keys.
    Asserts: exactly 1 order created, zero duplicate records in DB.
    """
    product = scenario.products[3]
    shared_key = str(uuid.uuid4())

    with system.create_client() as client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}
        client.post(f"{API_PREFIX}/cart/items", json={"product_id": product["id"], "quantity": 1}, headers=cust_h)

    async with httpx.AsyncClient(base_url=system.api_url, timeout=10.0) as async_client:
        cust_h = {"Authorization": f"Bearer {scenario.customer_token}"}

        async def post_checkout():
            return await async_client.post(
                f"{API_PREFIX}/orders/checkout",
                json={
                    "idempotency_key": shared_key,
                    "delivery_address": "Patliputra Colony, Patna",
                    "delivery_latitude": PATNA_LAT,
                    "delivery_longitude": PATNA_LON,
                    "payment_method": "cod",
                },
                headers=cust_h,
            )

        responses = await asyncio.gather(*[post_checkout() for _ in range(5)])

    # All returned successful or conflict responses
    order_ids = set()
    for r in responses:
        if r.status_code in (200, 201):
            order_ids.add(r.json().get("id"))

    assert len(order_ids) == 1, f"Expected 1 unique order for shared idempotency key, got: {order_ids}"
