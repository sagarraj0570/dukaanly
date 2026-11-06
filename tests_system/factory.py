"""
System Test Scenario Factory.

Builds isolated, namespaced test fixtures using Dukaanly's real HTTP endpoints
wherever possible, utilizing direct database operations strictly where the public API
does not permit self-service actions (e.g., merchant verification status, direct initial stock).
"""

import uuid
from typing import Dict, Any, List, Optional
import httpx
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

from tests_system.config import (
    API_PREFIX,
    PATNA_LAT,
    PATNA_LON,
    ASYNC_DB_URL,
    make_email,
    make_shop_name,
    make_phone,
)

DEFAULT_TEST_PASSWORD = "Password123!"

# 6 Structured test products with known prices and stock
PRESET_PRODUCTS = [
    {"name": "Organic Chakki Atta 5kg", "category": "groceries", "price": "220.00", "stock": 5, "unit": "5kg"},
    {"name": "Pure Cow Ghee 500ml", "category": "dairy", "price": "340.00", "stock": 5, "unit": "500ml"},
    {"name": "Basmati Rice 1kg", "category": "groceries", "price": "115.00", "stock": 5, "unit": "1kg"},
    {"name": "Refined Sunflower Oil 1L", "category": "groceries", "price": "145.00", "stock": 5, "unit": "1L"},
    {"name": "Tata Tea Premium 250g", "category": "beverages", "price": "95.00", "stock": 5, "unit": "250g"},
    {"name": "Parle-G Biscuit 250g", "category": "snacks", "price": "25.00", "stock": 5, "unit": "250g"},
]


class SystemScenario:
    """Represents a fully provisioned, isolated namespaced system test scenario."""

    def __init__(self, run_id: str):
        self.run_id = run_id
        self.customer_user: Dict[str, Any] = {}
        self.customer_token: str = ""
        self.customer2_user: Optional[Dict[str, Any]] = None
        self.customer2_token: Optional[str] = None
        self.shop_owner_user: Dict[str, Any] = {}
        self.shop_owner_token: str = ""
        self.shop: Dict[str, Any] = {}
        self.products: List[Dict[str, Any]] = []
        self.riders: List[Dict[str, Any]] = []
        self.rider_tokens: List[str] = []


async def reset_auth_rate_limits():
    """Resets auth IP rate limits in Redis so back-to-back test provisioning never hits 429."""
    try:
        import redis.asyncio as aioredis
        from tests_system.config import REDIS_URL
        r = aioredis.from_url(REDIS_URL, decode_responses=True)
        keys = await r.keys("rl:auth_*")
        if keys:
            await r.delete(*keys)
        await r.aclose()
    except Exception:
        pass


async def create_system_scenario(
    client: httpx.Client,
    run_id: str,
    create_second_customer: bool = False,
) -> SystemScenario:
    """
    Provisions a fresh scenario:
    - 1 customer (+ optional 2nd customer) via API register & login
    - 1 shop owner via API register & login
    - 1 shop in Patna Boring Road via API, verified & enabled via direct DB update
    - 6 products with prices and 5 units stock each (DB inventory initialization)
    - 2 riders near shop via API register, profile create, availability True, location set
    """
    await reset_auth_rate_limits()
    scenario = SystemScenario(run_id)

    # ── 1. Create Customer 1 ──────────────────────────────────────────────────
    c1_email = make_email("customer", run_id)
    c1_phone = make_phone(1, run_id)
    r_reg = client.post(f"{API_PREFIX}/auth/register", json={
        "name": f"Customer One {run_id}",
        "email": c1_email,
        "password": DEFAULT_TEST_PASSWORD,
        "phone_number": c1_phone,
        "role": "customer",
    })
    if r_reg.status_code not in (200, 201):
        raise RuntimeError(f"Customer registration failed: {r_reg.status_code} - {r_reg.text}")
    scenario.customer_user = r_reg.json()

    r_log = client.post(f"{API_PREFIX}/auth/login", json={
        "email": c1_email,
        "password": DEFAULT_TEST_PASSWORD,
    })
    scenario.customer_token = r_log.json()["access_token"]

    # ── 1b. Create Optional Customer 2 ─────────────────────────────────────────
    if create_second_customer:
        c2_email = make_email("customer2", run_id)
        c2_phone = make_phone(2, run_id)
        r_c2 = client.post(f"{API_PREFIX}/auth/register", json={
            "name": f"Customer Two {run_id}",
            "email": c2_email,
            "password": DEFAULT_TEST_PASSWORD,
            "phone_number": c2_phone,
            "role": "customer",
        })
        scenario.customer2_user = r_c2.json()
        r_log2 = client.post(f"{API_PREFIX}/auth/login", json={
            "email": c2_email,
            "password": DEFAULT_TEST_PASSWORD,
        })
        scenario.customer2_token = r_log2.json()["access_token"]

    # ── 2. Create Shop Owner & Shop ───────────────────────────────────────────
    so_email = make_email("owner", run_id)
    so_phone = make_phone(3, run_id)
    r_so = client.post(f"{API_PREFIX}/auth/register", json={
        "name": f"Shop Owner {run_id}",
        "email": so_email,
        "password": DEFAULT_TEST_PASSWORD,
        "phone_number": so_phone,
    })
    scenario.shop_owner_user = r_so.json()

    # Direct DB Update: Elevate registered user to shop_owner role
    # REASON: The public registration API deliberately forces role='customer' to prevent
    # privilege escalation attacks via API payloads.
    engine = create_async_engine(ASYNC_DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as session:
        await session.execute(
            text("UPDATE users SET role = 'shop_owner' WHERE email = :email"),
            {"email": so_email}
        )
        await session.commit()

    r_so_log = client.post(f"{API_PREFIX}/auth/login", json={
        "email": so_email,
        "password": DEFAULT_TEST_PASSWORD,
    })
    so_token = r_so_log.json()["access_token"]
    scenario.shop_owner_token = so_token

    # Create Shop via API
    shop_name = make_shop_name("SuperStore", run_id)
    r_shop = client.post(
        f"{API_PREFIX}/shops",
        json={
            "name": shop_name,
            "description": f"Dedicated system test grocery store for run {run_id}",
            "address": "Boring Road Crossing, Patna, Bihar 800001",
            "location": {
                "latitude": PATNA_LAT,
                "longitude": PATNA_LON,
            },
        },
        headers={"Authorization": f"Bearer {so_token}"},
    )
    if r_shop.status_code != 201:
        raise RuntimeError(f"Shop creation failed: {r_shop.status_code} - {r_shop.text}")
    scenario.shop = r_shop.json()
    shop_id = scenario.shop["id"]

    # Direct DB Update 1: Self-service shop verification & activation
    # REASON: The public API does not allow regular shop owners to mark their own store as
    # 'verified' (which requires admin intervention in production).
    engine = create_async_engine(ASYNC_DB_URL, echo=False)
    session_maker = async_sessionmaker(engine, expire_on_commit=False, autoflush=False)
    async with session_maker() as session:
        await session.execute(
            text("""
                UPDATE shops
                SET verification_status = 'verified',
                    is_orderable = true,
                    is_active = true
                WHERE id = :sid
            """),
            {"sid": shop_id}
        )
        await session.commit()

    # ── 3. Create 6 Products with Inventory ────────────────────────────────────
    created_products = []
    for prod_spec in PRESET_PRODUCTS:
        # Create product via API
        r_p = client.post(
            f"{API_PREFIX}/shops/{shop_id}/products",
            json={
                "name": f"{prod_spec['name']} ({run_id})",
                "price": prod_spec["price"],
                "category": prod_spec["category"],
                "description": f"Test product {prod_spec['name']}",
            },
            headers={"Authorization": f"Bearer {so_token}"},
        )
        if r_p.status_code != 201:
            raise RuntimeError(f"Product creation failed: {r_p.status_code} - {r_p.text}")
        p_data = r_p.json()
        pid = p_data["id"]

        # Direct DB Insert 2: Initial inventory stock level & version
        # REASON: Initial product creation sets stock to 0; this initializes known test units (5).
        async with session_maker() as session:
            await session.execute(
                text("""
                    INSERT INTO inventory (id, product_id, stock, version, created_at, updated_at)
                    VALUES (:iid, :pid, :stock, 1, NOW(), NOW())
                    ON CONFLICT (product_id)
                    DO UPDATE SET stock = :stock, version = 1, updated_at = NOW()
                """),
                {"iid": str(uuid.uuid4()), "pid": pid, "stock": prod_spec["stock"]}
            )
            await session.commit()

        p_data["initial_stock"] = prod_spec["stock"]
        created_products.append(p_data)

    scenario.products = created_products

    # ── 4. Create 2 Riders ────────────────────────────────────────────────────
    rider_tokens = []
    rider_profiles = []
    for r_idx in (1, 2):
        r_email = make_email(f"rider{r_idx}", run_id)
        r_phone = make_phone(10 + r_idx, run_id)

        # Register Rider via API
        r_reg_rider = client.post(f"{API_PREFIX}/auth/register", json={
            "name": f"Rider {r_idx} ({run_id})",
            "email": r_email,
            "password": DEFAULT_TEST_PASSWORD,
            "phone_number": r_phone,
        })
        if r_reg_rider.status_code not in (200, 201):
            raise RuntimeError(f"Rider {r_idx} registration failed: {r_reg_rider.status_code}")

        # Direct DB Update: Elevate registered user to rider role
        # REASON: Public registration forces role='customer' to prevent privilege escalation.
        async with session_maker() as session:
            await session.execute(
                text("UPDATE users SET role = 'rider' WHERE email = :email"),
                {"email": r_email}
            )
            await session.commit()

        # Login Rider
        r_rlog = client.post(f"{API_PREFIX}/auth/login", json={
            "email": r_email,
            "password": DEFAULT_TEST_PASSWORD,
        })
        r_token = r_rlog.json()["access_token"]
        r_headers = {"Authorization": f"Bearer {r_token}"}

        # Create Rider Profile via API
        r_prof = client.post(f"{API_PREFIX}/riders/profile", headers=r_headers)
        if r_prof.status_code not in (200, 201):
            # Profile might already be auto-created; fetch via /me
            r_prof = client.get(f"{API_PREFIX}/riders/me", headers=r_headers)

        profile_data = r_prof.json()

        # Set Availability to True via API
        client.patch(f"{API_PREFIX}/riders/me/availability", json={"is_available": True}, headers=r_headers)

        # Set Location near shop (~200m offset) via API
        offset = 0.0015 * r_idx
        client.patch(
            f"{API_PREFIX}/riders/me/location",
            json={"latitude": PATNA_LAT + offset, "longitude": PATNA_LON + offset},
            headers=r_headers,
        )

        rider_tokens.append(r_token)
        rider_profiles.append(profile_data)

    scenario.riders = rider_profiles
    scenario.rider_tokens = rider_tokens

    await engine.dispose()
    return scenario
