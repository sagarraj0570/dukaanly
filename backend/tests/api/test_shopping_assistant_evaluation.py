"""
Comprehensive Phase 2.5 Shopping Assistant Evaluation Test Matrix.
Evaluates the grounded shopping assistant across 10 critical operational scenarios,
security/privacy constraints, rate limiting, and multi-provider adapter configurations.
"""

import asyncio
from decimal import Decimal
import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.api.routes.ai import ai_user_rate_limiter
from app.core.config import settings
from app.core.ai import (
    ai_service,
    MockLLMProvider,
    OpenAILikeProvider,
    AIDisabledError,
    AIProviderError,
    LLMCompletionRequest,
    ChatMessage,
    ChatRole,
)
from app.core.ai.provider import redact_secrets, get_llm_provider
from app.db.session import async_session_maker
from app.models.inventory import Inventory
from app.models.product import Product
from app.models.shop import Shop, ShopVerificationStatus
from app.services.catalog_search import search_partner_catalog, GROCERY_SYNONYMS

pytestmark = pytest.mark.asyncio

BORING_ROAD_LAT = 25.6144
BORING_ROAD_LON = 85.1158


async def create_authenticated_customer(async_client: AsyncClient, prefix: str = "eval_cust") -> dict:
    """Helper to register and login a test customer."""
    uid = uuid.uuid4().hex[:6]
    email = f"{prefix}_{uid}@example.com"
    phone = f"+91{uuid.uuid4().int % 9000000000 + 1000000000}"
    await async_client.post(
        "/api/v1/auth/register",
        json={"name": "Eval Customer", "email": email, "password": "Password123!", "phone_number": phone},
    )
    login_res = await async_client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": "Password123!"},
    )
    token = login_res.json()["access_token"]
    return {"Authorization": f"Bearer {token}"}


# ---------------------------------------------------------------------------
# Scenario 1: Exact Product Match
# ---------------------------------------------------------------------------
async def test_scenario_1_exact_product_match(async_client: AsyncClient):
    """Customer searches for exact product name; assistant proposes authoritative cart."""
    headers = await create_authenticated_customer(async_client, "exact")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "Milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert len(data["matched_products"]) > 0
        assert data["proposed_cart"] is not None
        assert data["proposed_cart"]["shop_id"] is not None
        assert len(data["proposed_cart"]["items"]) >= 1

        first_item = data["proposed_cart"]["items"][0]
        assert Decimal(str(first_item["unit_price"])) > Decimal("0.00")
        assert first_item["quantity"] >= 1
        assert Decimal(str(data["proposed_cart"]["total_amount"])) >= Decimal(str(first_item["unit_price"]))
    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 2: Hinglish & Grocery Synonym Search (doodh, atta, tel)
# ---------------------------------------------------------------------------
async def test_scenario_2_hinglish_and_synonym_search(async_client: AsyncClient):
    """Customer queries using Hindi/Hinglish terms; catalog search expands synonyms and finds items."""
    headers = await create_authenticated_customer(async_client, "hinglish")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Test doodh -> milk expansion
        res_doodh = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "1 packet doodh chahiye", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res_doodh.status_code == 200
        data_doodh = res_doodh.json()
        assert len(data_doodh["matched_products"]) > 0
        assert any("milk" in p["product_name"].lower() for p in data_doodh["matched_products"])

        # Test atta -> flour expansion directly in catalog search
        async with async_session_maker() as session:
            atta_items = await search_partner_catalog(
                db=session,
                latitude=BORING_ROAD_LAT,
                longitude=BORING_ROAD_LON,
                query="atta",
            )
            assert len(atta_items) > 0, "Synonym 'atta' should match wheat flour items"

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 3: Budget Limit Constraint
# ---------------------------------------------------------------------------
async def test_scenario_3_budget_limit_constraint(async_client: AsyncClient):
    """Customer specifies a budget constraint; proposal enforces total amount cap."""
    headers = await create_authenticated_customer(async_client, "budget")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Query with explicit budget limit: under 100
        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "Milk under 100", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        if data["proposed_cart"]:
            total = float(data["proposed_cart"]["total_amount"])
            assert total <= 100.0, f"Proposed total {total} exceeded stated budget cap of 100.0"

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 4: Out-of-Stock Item Handling
# ---------------------------------------------------------------------------
async def test_scenario_4_out_of_stock_items_excluded(async_client: AsyncClient):
    """Out-of-stock items (stock=0) are NEVER returned in recommendations or proposed carts."""
    headers = await create_authenticated_customer(async_client, "stock")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()
    oos_prod_id = None

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        async with async_session_maker() as session:
            # Create a temporary zero-stock product in a verified shop
            verified_shop = (
                await session.execute(
                    text("SELECT id FROM shops WHERE is_active=true AND is_orderable=true AND verification_status='verified' LIMIT 1")
                )
            ).scalar_one()

            oos_prod_id = uuid.uuid4()
            await session.execute(
                text(
                    "INSERT INTO products (id, shop_id, name, description, price, category, is_active, created_at, updated_at) "
                    "VALUES (:id, :shop_id, 'ZeroStockWidgetXyz', 'Out of stock description', 99.00, 'TestCat', true, NOW(), NOW())"
                ),
                {"id": oos_prod_id, "shop_id": verified_shop},
            )
            await session.execute(
                text(
                    "INSERT INTO inventory (id, product_id, stock, version, created_at, updated_at) "
                    "VALUES (:id, :prod_id, 0, 1, NOW(), NOW())"
                ),
                {"id": uuid.uuid4(), "prod_id": oos_prod_id},
            )
            await session.commit()

            # Search catalog directly
            search_items = await search_partner_catalog(
                db=session,
                latitude=BORING_ROAD_LAT,
                longitude=BORING_ROAD_LON,
                query="ZeroStockWidgetXyz",
            )
            assert len(search_items) == 0, "Zero-stock product must NOT be returned in catalog search"

        # Search via assistant
        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "ZeroStockWidgetXyz", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert not any(str(p["product_id"]) == str(oos_prod_id) for p in data["matched_products"])
        if data["proposed_cart"]:
            assert not any(str(item["product_id"]) == str(oos_prod_id) for item in data["proposed_cart"]["items"])

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop
        if oos_prod_id is not None:
            try:
                async with async_session_maker() as session:
                    await session.execute(text("DELETE FROM inventory WHERE product_id = :pid"), {"pid": str(oos_prod_id)})
                    await session.execute(text("DELETE FROM cart_items WHERE product_id = :pid"), {"pid": str(oos_prod_id)})
                    await session.execute(text("DELETE FROM products WHERE id = :pid"), {"pid": str(oos_prod_id)})
                    await session.commit()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Scenario 5: Multi-Shop Ranking & Single-Shop Cart Invariant
# ---------------------------------------------------------------------------
async def test_scenario_5_single_shop_invariant_enforced(async_client: AsyncClient):
    """Proposal strictly enforces that ALL proposed items originate from the single selected shop."""
    headers = await create_authenticated_customer(async_client, "single_shop")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "groceries essentials", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        if data["proposed_cart"]:
            target_shop = data["proposed_cart"]["shop_id"]
            assert target_shop is not None

            # Verify against database that every proposed product belongs to target_shop
            async with async_session_maker() as session:
                for item in data["proposed_cart"]["items"]:
                    prod = await session.get(Product, uuid.UUID(item["product_id"]))
                    assert prod is not None
                    assert str(prod.shop_id) == str(target_shop), (
                        f"Single-shop invariant violation: Product {prod.id} belongs to {prod.shop_id}, "
                        f"not cart target shop {target_shop}"
                    )

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 6: Boundary Cases & Zero Coordinates
# ---------------------------------------------------------------------------
async def test_scenario_6_boundary_cases_and_zero_coordinates(async_client: AsyncClient):
    """Null Island (0.0, 0.0) coordinates are rejected with a helpful map prompt."""
    headers = await create_authenticated_customer(async_client, "zero_coord")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Send (0.0, 0.0)
        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "Need milk", "latitude": 0.0, "longitude": 0.0},
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["proposed_cart"] is None
        assert data["matched_products"] == []
        assert "delivery address" in data["assistant_message"].lower() or "map" in data["assistant_message"].lower()

        # Send blank/control char message -> Pydantic validation error HTTP 422
        bad_msg_res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "   \n\t  ", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert bad_msg_res.status_code == 422

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 7: Cross-Shop Cart Replacement Warning
# ---------------------------------------------------------------------------
async def test_scenario_7_cross_shop_cart_replacement_warning(async_client: AsyncClient):
    """If customer cart contains items from Shop A and proposal selects Shop B, warning is flagged."""
    headers = await create_authenticated_customer(async_client, "cross_shop")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        async with async_session_maker() as session:
            # Find two different verified shops with products
            shops = (
                await session.execute(
                    text(
                        "SELECT s.id, p.id AS prod_id FROM shops s "
                        "JOIN products p ON s.id = p.shop_id "
                        "JOIN inventory i ON p.id = i.product_id "
                        "WHERE s.is_active=true AND s.is_orderable=true AND s.verification_status='verified' AND i.stock > 0 "
                        "LIMIT 10"
                    )
                )
            ).all()

        assert len(shops) >= 2, "Expected at least 2 products from verified shops"
        shop_a_id, prod_a_id = shops[0]
        # Find product from distinct shop
        diff_shop = next((s for s in shops if str(s[0]) != str(shop_a_id)), None)

        if diff_shop:
            shop_b_id, prod_b_id = diff_shop

            # 1. Add Shop A item to current cart
            add_res = await async_client.post(
                "/api/v1/cart/items",
                json={"product_id": str(prod_a_id), "quantity": 1},
                headers=headers,
            )
            assert add_res.status_code == 200

            # 2. Ask assistant specifically for Shop B's product
            chat_res = await async_client.post(
                "/api/v1/ai/assistant/chat",
                json={
                    "message": "Give me this item",
                    "latitude": BORING_ROAD_LAT,
                    "longitude": BORING_ROAD_LON,
                    "shop_id": str(shop_b_id),
                },
                headers=headers,
            )
            assert chat_res.status_code == 200
            data = chat_res.json()
            if data["proposed_cart"] and str(data["proposed_cart"]["shop_id"]) == str(shop_b_id):
                assert data["proposed_cart"]["has_different_shop_in_current_cart"] is True
                assert data["proposed_cart"]["warning_message"] is not None
                assert "replace" in data["proposed_cart"]["warning_message"].lower()

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 8: Malformed LLM Response Fallback
# ---------------------------------------------------------------------------
async def test_scenario_8_malformed_llm_response_fallback(async_client: AsyncClient):
    """When upstream LLM returns malformed JSON, system recovers with grounded deterministic fallback."""
    headers = await create_authenticated_customer(async_client, "malformed")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    orig_provider = ai_service._provider
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Inject malformed JSON mock provider
        ai_service._provider = MockLLMProvider(simulate_malformed_json=True)

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200, "Malformed LLM response must NOT crash with 500"
        data = res.json()
        assert len(data["matched_products"]) > 0
        assert data["proposed_cart"] is not None
        assert "recommended cart" in data["assistant_message"].lower() or "matching" in data["assistant_message"].lower()

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop
        ai_service._provider = orig_provider


# ---------------------------------------------------------------------------
# Scenario 9: Inventory Change Between Proposal and Cart Addition
# ---------------------------------------------------------------------------
async def test_scenario_9_inventory_change_between_proposal_and_cart(async_client: AsyncClient):
    """If stock drops between assistant proposal and cart addition, cart API rejects overselling."""
    headers = await create_authenticated_customer(async_client, "midturn")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200
        proposal = res.json()["proposed_cart"]
        assert proposal is not None
        prod_id = proposal["items"][0]["product_id"]

        # Simulate sudden out-of-stock event in the database
        async with async_session_maker() as session:
            await session.execute(
                text("UPDATE inventory SET stock = 0 WHERE product_id = :pid"),
                {"pid": uuid.UUID(prod_id)},
            )
            await session.commit()

        # Customer attempts to add the now out-of-stock item to cart
        add_res = await async_client.post(
            "/api/v1/cart/items",
            json={"product_id": prod_id, "quantity": 1},
            headers=headers,
        )
        assert add_res.status_code == 400
        assert "out of stock" in add_res.json()["detail"].lower() or "stock" in add_res.json()["detail"].lower()

        # Restore stock for future tests
        async with async_session_maker() as session:
            await session.execute(
                text("UPDATE inventory SET stock = 20 WHERE product_id = :pid"),
                {"pid": uuid.UUID(prod_id)},
            )
            await session.commit()

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop


# ---------------------------------------------------------------------------
# Scenario 10: Provider Outage & Circuit Breaker Graceful Degradation
# ---------------------------------------------------------------------------
async def test_scenario_10_provider_outage_circuit_breaker_and_core_isolation(async_client: AsyncClient):
    """When provider is down or circuit breaker trips, core browsing, cart, and checkout remain fully functional."""
    headers = await create_authenticated_customer(async_client, "outage")
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    orig_provider = ai_service._provider
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # 1. Trip circuit breaker with failing provider
        failing_provider = MockLLMProvider(simulate_server_error=True)
        ai_service._provider = failing_provider
        ai_service._failure_threshold = 3
        ai_service._cooldown_seconds = 10.0

        req = LLMCompletionRequest(messages=[ChatMessage(role=ChatRole.user, content="test")])
        for _ in range(3):
            try:
                await ai_service.complete(req)
            except Exception:
                pass

        assert ai_service.is_circuit_breaker_open() is True

        # 2. Verify AI chat endpoint handles open circuit breaker gracefully with grounded fallback
        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert res.status_code == 200, "Shopping assistant should provide grounded fallback even during provider outage"
        assert len(res.json()["matched_products"]) > 0

        # 3. Core browsing must be completely unaffected
        shops_res = await async_client.get(f"/api/v1/shops?latitude={BORING_ROAD_LAT}&longitude={BORING_ROAD_LON}")
        assert shops_res.status_code == 200

        # 4. Core cart operations must work
        cart_res = await async_client.get("/api/v1/cart", headers=headers)
        assert cart_res.status_code == 200

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop
        ai_service._provider = orig_provider
        ai_service.reset_circuit_breaker()


# ---------------------------------------------------------------------------
# Security & Rate Limiting Verification
# ---------------------------------------------------------------------------
async def test_security_auth_required_and_per_user_rate_limiting(async_client: AsyncClient):
    """AI endpoints require authentication and enforce sliding-window per-user rate limits."""
    orig_enabled = settings.AI_ENABLED
    orig_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    ai_user_rate_limiter.reset()

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # 1. Unauthenticated request must return 401
        unauth_res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
        )
        assert unauth_res.status_code == 401

        # 2. Per-user rate limiting: set limit to 3 for fast test
        headers = await create_authenticated_customer(async_client, "ratelimit")
        ai_user_rate_limiter.requests_per_minute = 3

        for i in range(3):
            ok_res = await async_client.post(
                "/api/v1/ai/assistant/chat",
                json={"message": f"milk query {i}", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
                headers=headers,
            )
            assert ok_res.status_code == 200

        # 4th request within 1 minute must return HTTP 429 Too Many Requests
        rate_limited_res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "milk query 4", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert rate_limited_res.status_code == 429
        assert "Retry-After" in rate_limited_res.headers
        assert "rate limit exceeded" in rate_limited_res.json()["detail"].lower()

    finally:
        settings.AI_ENABLED = orig_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = orig_shop
        ai_user_rate_limiter.requests_per_minute = settings.AI_RATE_LIMIT_PER_MINUTE
        ai_user_rate_limiter.reset()


# ---------------------------------------------------------------------------
# Provider Verification & Secret Redaction
# ---------------------------------------------------------------------------
async def test_provider_verification_and_secret_redaction():
    """Verify supported provider adapters, bounded concurrency, and zero secret leakage in logs/traces."""
    # 1. Check all supported provider types construct cleanly
    for ptype in ("openai", "groq", "openrouter", "gemini", "mock", "openai_compatible"):
        provider = get_llm_provider(ptype)
        assert provider is not None
        assert provider.provider_name in (ptype, "openai_compatible")

    # 2. Secret Redaction tests
    raw_leak = "Error calling https://api.openai.com: Bearer sk-proj-1234567890abcdef12345678 failed"
    redacted = redact_secrets(raw_leak)
    assert "sk-proj-1234567890abcdef12345678" not in redacted
    assert "***REDACTED***" in redacted

    gsk_leak = "Groq auth failed for gsk_998877665544332211aabbccdd with 401"
    gsk_redacted = redact_secrets(gsk_leak)
    assert "gsk_998877665544332211aabbccdd" not in gsk_redacted
    assert "***REDACTED***" in gsk_redacted

    # 3. Concurrency Semaphore verification
    openai_prov = OpenAILikeProvider(provider_type="openai", max_concurrent_requests=5)
    assert isinstance(openai_prov._semaphore, asyncio.Semaphore)
    assert openai_prov._semaphore._value == 5
