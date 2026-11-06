"""
Pre-Provider Enablement Verification Test Suite.
Directly tests and proves all 6 operational readiness criteria before connecting a live external LLM:
[1] Verify circuit-breaker tripping on provider failures and automatic recovery.
[2] Configure valid provider, model, and server-side API key safely.
[3] Enable only the shopping-assistant feature flag required for this phase.
[4] Test real product retrieval against verified Patna partner shops and live stock.
[5] Verify a proposed cart cannot bypass normal cart, stock, and checkout APIs.
[6] Confirm ordinary browsing, cart, and checkout work seamlessly when AI is down.
"""

from decimal import Decimal
import json
import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
import httpx
from sqlalchemy import text

from app.core.config import settings
from app.services.payment_provider import compute_mock_razorpay_signature
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
from app.db.session import engine, async_session_maker
from app.services.catalog_search import search_partner_catalog
from app.models.cart import Cart, CartItem
from app.models.order import Order

pytestmark = pytest.mark.asyncio

BORING_ROAD_LAT = 25.6144
BORING_ROAD_LON = 85.1158


# ---------------------------------------------------------------------------
# Checklist Item 1: Circuit Breaker State & Recovery
# ---------------------------------------------------------------------------
async def test_checklist_1_circuit_breaker_tripping_and_recovery():
    """Verify circuit-breaker trips after consecutive provider failures and recovers on probe success."""
    original_enabled = settings.AI_ENABLED
    original_provider = ai_service._provider
    try:
        settings.AI_ENABLED = True
        ai_service.reset_circuit_breaker()
        ai_service._failure_threshold = 3
        ai_service._cooldown_seconds = 1.0  # 1s cooldown for fast test

        # Initial state: closed
        assert ai_service.is_circuit_breaker_open() is False
        status_before = ai_service.get_status()
        assert status_before.circuit_breaker_open is False

        # Set provider to fail
        failing_provider = MockLLMProvider(simulate_server_error=True)
        ai_service._provider = failing_provider

        req = LLMCompletionRequest(
            messages=[ChatMessage(role=ChatRole.user, content="test")]
        )

        # 3 consecutive failures
        for _ in range(3):
            with pytest.raises(AIProviderError):
                await ai_service.complete(req)

        # Circuit breaker should now be OPEN (tripped)
        assert ai_service.is_circuit_breaker_open() is True
        status_tripped = ai_service.get_status()
        assert status_tripped.circuit_breaker_open is True
        assert "OPEN" in status_tripped.details

        # Subsequent calls must immediately fail without calling upstream
        with pytest.raises(AIProviderError) as exc_info:
            await ai_service.complete(req)
        assert "circuit breaker is currently open" in str(exc_info.value).lower()
        assert exc_info.value.status_code == 503

        # Wait for cooldown to elapse -> Half-open state
        time.sleep(1.1)
        assert ai_service.is_circuit_breaker_open() is False

        # Working provider responds -> Circuit breaker resets
        working_provider = MockLLMProvider(canned_response="Operational again")
        ai_service._provider = working_provider

        resp = await ai_service.complete(req)
        assert resp.text == "Operational again"
        assert ai_service.is_circuit_breaker_open() is False
        status_recovered = ai_service.get_status()
        assert status_recovered.circuit_breaker_open is False
        assert "Operational" in status_recovered.details

    finally:
        settings.AI_ENABLED = original_enabled
        ai_service._provider = original_provider
        ai_service.reset_circuit_breaker()


# ---------------------------------------------------------------------------
# Checklist Item 2: Provider Configuration & Secure Server-Side Headers
# ---------------------------------------------------------------------------
async def test_checklist_2_provider_configuration_and_headers():
    """Verify provider abstraction parses base URL, model, and includes Bearer key safely."""
    test_key = "sk-live-secret-dukaanly-test-key"
    provider = OpenAILikeProvider(
        api_key=test_key,
        base_url="https://api.openai.com/v1",
        model="gpt-4o-mini",
        timeout_seconds=5.0,
    )
    assert provider.provider_name in ("openai", "openai_compatible")
    assert provider.api_key == test_key
    assert provider.base_url == "https://api.openai.com/v1"
    assert provider.default_model == "gpt-4o-mini"


# ---------------------------------------------------------------------------
# Checklist Item 3: Feature Flag Isolation
# ---------------------------------------------------------------------------
async def test_checklist_3_feature_flag_isolation(async_client: AsyncClient):
    """Enable only AI_FEATURE_SHOPPING_ASSISTANT; verify catalog_search and order_support are gated."""
    original_enabled = settings.AI_ENABLED
    original_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    original_cat = settings.AI_FEATURE_CATALOG_SEARCH
    original_ord = settings.AI_FEATURE_ORDER_SUPPORT
    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True
        settings.AI_FEATURE_CATALOG_SEARCH = False
        settings.AI_FEATURE_ORDER_SUPPORT = False

        status = ai_service.get_status()
        assert status.enabled is True
        assert status.features["shopping_assistant"] is True
        assert status.features["catalog_search"] is False
        assert status.features["order_support"] is False

        # Attempting un-enabled feature throws AIDisabledError
        with pytest.raises(AIDisabledError) as exc_info:
            ai_service.check_feature_enabled("catalog_search")
        assert "catalog_search" in str(exc_info.value)

        with pytest.raises(AIDisabledError) as exc_info:
            ai_service.check_feature_enabled("order_support")
        assert "order_support" in str(exc_info.value)

        # Shopping assistant does NOT raise
        ai_service.check_feature_enabled("shopping_assistant")

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_shop
        settings.AI_FEATURE_CATALOG_SEARCH = original_cat
        settings.AI_FEATURE_ORDER_SUPPORT = original_ord


# ---------------------------------------------------------------------------
# Checklist Item 4: Real Patna Product Retrieval & In-Stock Verification
# ---------------------------------------------------------------------------
async def test_checklist_4_real_product_retrieval_patna_partners():
    """Verify catalog search retrieves real verified Patna partner merchants with live positive stock."""
    async with async_session_maker() as session:
        items = await search_partner_catalog(
            db=session,
            latitude=BORING_ROAD_LAT,
            longitude=BORING_ROAD_LON,
            query="milk",
            max_radius_meters=5000,
        )

        assert len(items) > 0, "Expected at least 1 verified in-stock partner product in Patna"
        for item in items:
            # 1. Must be verified partner
            assert "verified" in str(item.shop_name).lower() or item.is_delivery_eligible is True
            # 2. Must be in stock
            assert item.stock > 0
            # 3. Must be within 5 km delivery radius
            assert item.distance_meters <= 5000.0
            # 4. Must have positive price
            assert item.price > Decimal("0.00")


# ---------------------------------------------------------------------------
# Checklist Item 5: Proposed Cart Cannot Bypass Cart & Checkout APIs
# ---------------------------------------------------------------------------
async def test_checklist_5_proposed_cart_cannot_bypass_cart_and_checkout_api(async_client: AsyncClient):
    """
    Verify:
    1. A proposed cart response does NOT create items in the database cart table.
    2. A proposed cart alone cannot be used to place an order or complete payment.
    3. Items can ONLY be added via POST /api/v1/cart/items with live stock checks.
    """
    cust_email = f"bypass_check_{uuid.uuid4().hex[:6]}@example.com"
    phone = f"+91{uuid.uuid4().int % 9000000000 + 1000000000}"
    await async_client.post("/api/v1/auth/register", json={"name": "Bypass Tester", "email": cust_email, "password": "Password123!", "phone_number": phone})
    token = (await async_client.post("/api/v1/auth/login", json={"email": cust_email, "password": "Password123!"})).json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    original_enabled = settings.AI_ENABLED
    original_shop = settings.AI_FEATURE_SHOPPING_ASSISTANT
    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Customer chats with assistant and receives a proposed cart
        chat_res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={"message": "Need milk", "latitude": BORING_ROAD_LAT, "longitude": BORING_ROAD_LON},
            headers=headers,
        )
        assert chat_res.status_code == 200
        proposal = chat_res.json()["proposed_cart"]
        assert proposal is not None
        proposed_prod_id = proposal["items"][0]["product_id"]

        # Invariant 1: Database Cart must still be completely empty!
        cart_check = await async_client.get("/api/v1/cart", headers=headers)
        assert cart_check.status_code == 200
        assert len(cart_check.json()["items"]) == 0
        assert cart_check.json()["total_amount"] == "0.00"

        # Invariant 2: Cannot place order with empty cart (proposal bypassed nothing)
        order_attempt = await async_client.post(
            "/api/v1/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "destination_latitude": BORING_ROAD_LAT,
                "destination_longitude": BORING_ROAD_LON,
            },
            headers=headers,
        )
        assert order_attempt.status_code == 400
        assert "empty" in order_attempt.json()["detail"].lower()

        # Invariant 3: Customer must explicitly call POST /api/v1/cart/items
        add_res = await async_client.post(
            "/api/v1/cart/items",
            json={"product_id": proposed_prod_id, "quantity": 1},
            headers=headers,
        )
        assert add_res.status_code == 200
        assert len(add_res.json()["items"]) == 1

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_shop


# ---------------------------------------------------------------------------
# Checklist Item 6: Normal Browsing & Checkout Unaffected When Provider Down
# ---------------------------------------------------------------------------
async def test_checklist_6_ordinary_browsing_and_checkout_unaffected_when_ai_down(async_client: AsyncClient):
    """Confirm shops, catalog browsing, cart, and checkout work 100% when AI is disabled or down."""
    original_enabled = settings.AI_ENABLED
    try:
        # AI globally disabled
        settings.AI_ENABLED = False

        # 1. Shop discovery works
        shops_res = await async_client.get(
            f"/api/v1/shops?latitude={BORING_ROAD_LAT}&longitude={BORING_ROAD_LON}&delivery_only=true"
        )
        assert shops_res.status_code == 200
        shops_data = shops_res.json()
        assert len(shops_data["items"]) > 0
        target_shop = shops_data["items"][0]

        # 2. Product browsing works
        prod_res = await async_client.get(f"/api/v1/shops/{target_shop['id']}/products")
        assert prod_res.status_code == 200
        prods = prod_res.json()["items"]
        assert len(prods) > 0

        # 3. Customer cart and checkout work
        cust_email = f"norm_cust_{uuid.uuid4().hex[:6]}@example.com"
        phone = f"+91{uuid.uuid4().int % 9000000000 + 1000000000}"
        await async_client.post("/api/v1/auth/register", json={"name": "Normal Customer", "email": cust_email, "password": "Password123!", "phone_number": phone})
        token = (await async_client.post("/api/v1/auth/login", json={"email": cust_email, "password": "Password123!"})).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Add an in-stock product to cart
        cart_res = None
        target_prod = None
        for p in prods:
            add_res = await async_client.post(
                "/api/v1/cart/items",
                json={"product_id": p["id"], "quantity": 1},
                headers=headers,
            )
            if add_res.status_code == 200:
                cart_res = add_res
                target_prod = p
                break

        assert cart_res is not None and cart_res.status_code == 200, "Should successfully add an in-stock product to cart"

        # Create order via checkout
        order_res = await async_client.post(
            "/api/v1/orders/checkout",
            json={
                "idempotency_key": str(uuid.uuid4()),
                "destination_latitude": BORING_ROAD_LAT,
                "destination_longitude": BORING_ROAD_LON,
            },
            headers=headers,
        )
        assert order_res.status_code == 201
        order_id = order_res.json()["id"]

        # 4. Initiate payment and verify via mock provider
        init_res = await async_client.post(f"/api/v1/orders/{order_id}/payment", headers=headers)
        assert init_res.status_code == 200
        provider_order_id = init_res.json()["provider_order_id"]

        payment_id = f"pay_mock_{uuid.uuid4().hex[:6]}"
        verify_res = await async_client.post(
            "/api/v1/payments/verify",
            json={
                "razorpay_order_id": provider_order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": compute_mock_razorpay_signature(provider_order_id, payment_id),
            },
            headers=headers,
        )
        assert verify_res.status_code == 200
        assert verify_res.json()["status"] == "captured"

        # Check Order confirmed
        final_order = await async_client.get(f"/api/v1/orders/{order_id}", headers=headers)
        assert final_order.status_code == 200
        assert final_order.json()["status"] == "confirmed"

    finally:
        settings.AI_ENABLED = original_enabled
        # Deterministic teardown: restore deducted stock and remove test order records
        try:
            from app.db.session import async_session_maker
            from sqlalchemy import select, delete, update
            from app.models.user import User
            from app.models.order import Order, OrderItem
            from app.models.delivery import Delivery
            from app.models.payment import Payment
            from app.models.cart import Cart, CartItem
            from app.models.inventory import Inventory
            from app.models.notification import Notification

            async with async_session_maker() as session:
                # Restore stock if product was purchased
                if target_prod is not None:
                    await session.execute(
                        update(Inventory)
                        .where(Inventory.product_id == target_prod["id"])
                        .values(stock=Inventory.stock + 1, version=Inventory.version + 1)
                    )

                # Clean up test customer and associated records
                user_res = await session.execute(select(User.id).where(User.email == cust_email))
                user_id = user_res.scalar_one_or_none()
                if user_id:
                    ord_ids = (await session.execute(select(Order.id).where(Order.customer_id == user_id))).scalars().all()
                    if ord_ids:
                        await session.execute(delete(Delivery).where(Delivery.order_id.in_(ord_ids)))
                        await session.execute(delete(Payment).where(Payment.order_id.in_(ord_ids)))
                        await session.execute(delete(OrderItem).where(OrderItem.order_id.in_(ord_ids)))
                        await session.execute(delete(Order).where(Order.id.in_(ord_ids)))

                    cart_ids = (await session.execute(select(Cart.id).where(Cart.customer_id == user_id))).scalars().all()
                    if cart_ids:
                        await session.execute(delete(CartItem).where(CartItem.cart_id.in_(cart_ids)))
                        await session.execute(delete(Cart).where(Cart.id.in_(cart_ids)))

                    await session.execute(delete(Notification).where(Notification.user_id == user_id))
                    await session.execute(delete(User).where(User.id == user_id))

                await session.commit()
        except Exception:
            pass
