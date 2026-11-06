"""
Comprehensive test suite for Dukaanly AI Grounded Shopping Assistant (Phase 2).
Verifies:
1. Authentication requirements.
2. Feature flag enforcement (AI_FEATURE_SHOPPING_ASSISTANT).
3. PostGIS 5 km serviceability and verified/orderable shop filtering.
4. Out-of-stock product rejection.
5. Single-shop cart proposal and cross-shop conflict warnings.
6. Authoritative backend pricing (ignoring LLM math/hallucinations).
7. Resilience against malformed/unparseable LLM output.
8. Customer cart approval execution via the existing cart API.
"""

from decimal import Decimal
import json
import uuid
import pytest
from httpx import AsyncClient
from sqlalchemy import text

from app.core.config import settings
from app.core.ai import ai_service, MockLLMProvider
from app.db.session import engine, async_session_maker
from app.services.catalog_search import search_partner_catalog
from app.models.shop import Shop, ShopVerificationStatus
from app.models.product import Product
from app.models.inventory import Inventory

pytestmark = pytest.mark.asyncio

# Test coordinates centered around Boring Road, Patna
PATNA_BORING_ROAD_LAT = 25.6144
PATNA_BORING_ROAD_LON = 85.1158

# Coordinates ~1.5 km away (within 5 km delivery radius)
PATNA_NEARBY_LAT = 25.6180
PATNA_NEARBY_LON = 85.1250

# Coordinates ~15 km away (outside 5 km delivery radius)
PATNA_FARAWAY_LAT = 25.7200
PATNA_FARAWAY_LON = 85.2500


async def setup_shopping_assistant_fixtures(async_client: AsyncClient):
    """Create test merchants, verified/unverified shops, products, and customer."""
    owner_email = f"ai_owner_{uuid.uuid4().hex[:6]}@example.com"
    customer_email = f"ai_cust_{uuid.uuid4().hex[:6]}@example.com"
    owner2_email = f"ai_owner2_{uuid.uuid4().hex[:6]}@example.com"

    # Register users
    await async_client.post("/api/v1/auth/register", json={"name": "AI Owner 1", "email": owner_email, "password": "Password123!"})
    await async_client.post("/api/v1/auth/register", json={"name": "AI Owner 2", "email": owner2_email, "password": "Password123!"})
    await async_client.post("/api/v1/auth/register", json={"name": "AI Customer", "email": customer_email, "password": "Password123!"})

    async with engine.connect() as conn:
        await conn.execute(
            text("UPDATE users SET role = 'shop_owner' WHERE email IN (:e1, :e2)"),
            {"e1": owner_email, "e2": owner2_email},
        )
        await conn.commit()

    token_owner1 = (await async_client.post("/api/v1/auth/login", json={"email": owner_email, "password": "Password123!"})).json()["access_token"]
    token_owner2 = (await async_client.post("/api/v1/auth/login", json={"email": owner2_email, "password": "Password123!"})).json()["access_token"]
    token_cust = (await async_client.post("/api/v1/auth/login", json={"email": customer_email, "password": "Password123!"})).json()["access_token"]

    headers_owner1 = {"Authorization": f"Bearer {token_owner1}"}
    headers_owner2 = {"Authorization": f"Bearer {token_owner2}"}

    # Shop 1: Verified Partner in Boring Road (~1.5 km away)
    s1_res = await async_client.post(
        "/api/v1/shops",
        json={
            "name": "Boring Road Mart (Test)",
            "address": "Boring Road, Patna",
            "location": {"latitude": PATNA_NEARBY_LAT, "longitude": PATNA_NEARBY_LON},
        },
        headers=headers_owner1,
    )
    shop1_id = s1_res.json()["id"]

    # Shop 2: Second Verified Partner (~2 km away)
    s2_res = await async_client.post(
        "/api/v1/shops",
        json={
            "name": "Kankarbagh Kirana (Test)",
            "address": "Kankarbagh, Patna",
            "location": {"latitude": 25.5947, "longitude": 85.1588},
        },
        headers=headers_owner2,
    )
    shop2_id = s2_res.json()["id"]

    # Shop 3: Far-away shop (> 5 km)
    s3_res = await async_client.post(
        "/api/v1/shops",
        json={
            "name": "Faraway Store (Test)",
            "address": "Outskirts, Patna",
            "location": {"latitude": PATNA_FARAWAY_LAT, "longitude": PATNA_FARAWAY_LON},
        },
        headers=headers_owner1,
    )
    shop3_id = s3_res.json()["id"]

    # Products for Shop 1
    # 1. Milk (In Stock)
    p_milk_res = await async_client.post(
        f"/api/v1/shops/{shop1_id}/products",
        json={"name": "Amul Fresh Milk 1L", "price": 66.0, "category": "Dairy"},
        headers=headers_owner1,
    )
    p_milk_id = p_milk_res.json()["id"]
    await async_client.patch(
        f"/api/v1/products/{p_milk_id}/inventory",
        json={"stock": 10, "expected_version": 1},
        headers=headers_owner1,
    )

    # 2. Bread (In Stock)
    p_bread_res = await async_client.post(
        f"/api/v1/shops/{shop1_id}/products",
        json={"name": "Harvest Gold White Bread", "price": 45.0, "category": "Bakery"},
        headers=headers_owner1,
    )
    p_bread_id = p_bread_res.json()["id"]
    await async_client.patch(
        f"/api/v1/products/{p_bread_id}/inventory",
        json={"stock": 5, "expected_version": 1},
        headers=headers_owner1,
    )

    # 3. Butter (OUT OF STOCK - stock=0)
    p_butter_res = await async_client.post(
        f"/api/v1/shops/{shop1_id}/products",
        json={"name": "Amul Salted Butter 100g", "price": 58.0, "category": "Dairy"},
        headers=headers_owner1,
    )
    p_butter_id = p_butter_res.json()["id"]
    # Stock remains 0

    # Products for Shop 2
    p_s2_res = await async_client.post(
        f"/api/v1/shops/{shop2_id}/products",
        json={"name": "Aashirvaad Atta 5kg", "price": 240.0, "category": "Groceries"},
        headers=headers_owner2,
    )
    p_s2_id = p_s2_res.json()["id"]
    await async_client.patch(
        f"/api/v1/products/{p_s2_id}/inventory",
        json={"stock": 8, "expected_version": 1},
        headers=headers_owner2,
    )

    # Product for Shop 3 (Faraway)
    p_far_res = await async_client.post(
        f"/api/v1/shops/{shop3_id}/products",
        json={"name": "Faraway Organic Honey", "price": 300.0, "category": "Groceries"},
        headers=headers_owner1,
    )
    p_far_id = p_far_res.json()["id"]
    await async_client.patch(
        f"/api/v1/products/{p_far_id}/inventory",
        json={"stock": 20, "expected_version": 1},
        headers=headers_owner1,
    )

    # Also create an unverified directory shop directly in DB to verify directory exclusion
    async with async_session_maker() as session:
        unverified_shop = Shop(
            name="Unverified Candidate Shop (Test)",
            address="Directory Road, Patna",
            location=f"SRID=4326;POINT({PATNA_NEARBY_LON} {PATNA_NEARBY_LAT})",
            is_active=True,
            is_orderable=False,
            verification_status=ShopVerificationStatus.discovered,
            source="test",
            source_id=f"test:unv:{uuid.uuid4().hex[:8]}",
        )
        session.add(unverified_shop)
        await session.commit()
        await session.refresh(unverified_shop)

        # Add a product to the unverified shop
        unv_prod = Product(
            shop_id=unverified_shop.id,
            name="Unverified Product Item",
            price=Decimal("99.00"),
            is_active=True,
        )
        session.add(unv_prod)
        await session.commit()
        await session.refresh(unv_prod)

        unv_inv = Inventory(product_id=unv_prod.id, stock=50, version=1)
        session.add(unv_inv)
        await session.commit()

    return {
        "token_cust": token_cust,
        "token_owner1": token_owner1,
        "shop1_id": shop1_id,
        "shop2_id": shop2_id,
        "shop3_id": shop3_id,
        "p_milk_id": p_milk_id,
        "p_bread_id": p_bread_id,
        "p_butter_id": p_butter_id,
        "p_s2_id": p_s2_id,
        "p_far_id": p_far_id,
    }


async def test_shopping_assistant_unauthenticated(async_client: AsyncClient):
    """Unauthenticated requests must be rejected with 401."""
    res = await async_client.post(
        "/api/v1/ai/assistant/chat",
        json={
            "message": "Need milk",
            "latitude": PATNA_BORING_ROAD_LAT,
            "longitude": PATNA_BORING_ROAD_LON,
        },
    )
    assert res.status_code == 401


async def test_shopping_assistant_feature_flag_disabled(async_client: AsyncClient):
    """When shopping assistant feature flag is disabled, returns 503."""
    fixtures = await setup_shopping_assistant_fixtures(async_client)
    headers = {"Authorization": f"Bearer {fixtures['token_cust']}"}

    original_enabled = settings.AI_ENABLED
    original_feature = settings.AI_FEATURE_SHOPPING_ASSISTANT
    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = False

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={
                "message": "Need milk and bread",
                "latitude": PATNA_BORING_ROAD_LAT,
                "longitude": PATNA_BORING_ROAD_LON,
            },
            headers=headers,
        )
        assert res.status_code == 503
        assert "disabled" in res.json()["detail"].lower()
    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_feature


async def test_catalog_search_filters_serviceability_and_stock(async_client: AsyncClient):
    """Verify PostGIS serviceability, stock > 0, and verified-only filtering."""
    fixtures = await setup_shopping_assistant_fixtures(async_client)

    async with async_session_maker() as session:
        # Search from Boring Road
        results = await search_partner_catalog(
            db=session,
            latitude=PATNA_BORING_ROAD_LAT,
            longitude=PATNA_BORING_ROAD_LON,
            query=None,
            shop_id=fixtures["shop1_id"],
            max_results=50,
            max_radius_meters=5000,
        )

        result_names = [item.product_name for item in results]
        result_shop_ids = [str(item.shop_id) for item in results]

        # 1. Milk and Bread from Shop 1 are within ~1.5 km and in stock -> MUST be present
        assert "Amul Fresh Milk 1L" in result_names
        assert "Harvest Gold White Bread" in result_names

        # 2. Butter has stock=0 -> MUST BE EXCLUDED
        assert "Amul Salted Butter 100g" not in result_names

        # 3. Shop 3 is > 5 km away -> MUST BE EXCLUDED by PostGIS ST_DWithin
        assert "Faraway Organic Honey" not in result_names
        assert str(fixtures["shop3_id"]) not in result_shop_ids

        # 4. Unverified directory shop product -> MUST BE EXCLUDED
        assert "Unverified Product Item" not in result_names

        # 5. Distances are populated and all <= 5000 meters
        for item in results:
            assert item.distance_meters <= 5000.0
            assert item.is_delivery_eligible is True
            assert item.stock > 0


async def test_shopping_assistant_end_to_end_cart_proposal(async_client: AsyncClient):
    """Test full shopping assistant chat returning grounded matched products and valid cart proposal."""
    fixtures = await setup_shopping_assistant_fixtures(async_client)
    headers = {"Authorization": f"Bearer {fixtures['token_cust']}"}

    original_enabled = settings.AI_ENABLED
    original_feature = settings.AI_FEATURE_SHOPPING_ASSISTANT
    original_provider = ai_service._provider

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True
        ai_service._provider = MockLLMProvider()

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={
                "message": "I need milk for breakfast",
                "latitude": PATNA_BORING_ROAD_LAT,
                "longitude": PATNA_BORING_ROAD_LON,
                "shop_id": fixtures["shop1_id"],
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()

        # Check assistant message
        assert len(data["assistant_message"]) > 0
        assert len(data["matched_products"]) > 0

        # Check matched products contain authoritative fields
        first_match = data["matched_products"][0]
        assert "Amul Fresh Milk 1L" in [p["product_name"] for p in data["matched_products"]]
        assert first_match["is_delivery_eligible"] is True
        assert first_match["distance_meters"] <= 5000.0

        # Check proposed cart
        proposed_cart = data["proposed_cart"]
        assert proposed_cart is not None
        assert proposed_cart["shop_id"] == fixtures["shop1_id"]
        assert len(proposed_cart["items"]) >= 1

        proposed_item = proposed_cart["items"][0]
        assert proposed_item["product_id"] == fixtures["p_milk_id"]
        assert proposed_item["quantity"] == 1
        assert Decimal(str(proposed_item["unit_price"])) == Decimal("66.00")
        assert Decimal(str(proposed_cart["total_amount"])) >= Decimal("66.00")

        # Now verify customer can take proposed item and invoke standard cart API
        cart_add_res = await async_client.post(
            "/api/v1/cart/items",
            json={"product_id": proposed_item["product_id"], "quantity": proposed_item["quantity"]},
            headers=headers,
        )
        assert cart_add_res.status_code == 200
        cart_data = cart_add_res.json()
        assert cart_data["shop_id"] == fixtures["shop1_id"]
        assert len(cart_data["items"]) == 1

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_feature
        ai_service._provider = original_provider


async def test_shopping_assistant_cross_shop_cart_warning(async_client: AsyncClient):
    """When customer has items from Shop A, proposing Shop B must set has_different_shop_in_current_cart."""
    fixtures = await setup_shopping_assistant_fixtures(async_client)
    headers = {"Authorization": f"Bearer {fixtures['token_cust']}"}

    original_enabled = settings.AI_ENABLED
    original_feature = settings.AI_FEATURE_SHOPPING_ASSISTANT
    original_provider = ai_service._provider

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # Pre-populate customer's cart with an item from Shop 2 (Atta)
        await async_client.post(
            "/api/v1/cart/items",
            json={"product_id": fixtures["p_s2_id"], "quantity": 1},
            headers=headers,
        )

        # Custom canned response proposing Shop 1 items
        canned = json.dumps({
            "assistant_message": "Here is milk from Boring Road Mart.",
            "clarifying_question": None,
            "selected_shop_id": fixtures["shop1_id"],
            "proposed_items": [{"product_id": fixtures["p_milk_id"], "quantity": 1}],
        })
        ai_service._provider = MockLLMProvider(canned_response=canned)

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={
                "message": "Need milk",
                "latitude": PATNA_BORING_ROAD_LAT,
                "longitude": PATNA_BORING_ROAD_LON,
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        proposed = data["proposed_cart"]
        assert proposed is not None
        assert proposed["has_different_shop_in_current_cart"] is True
        assert "different shop" in proposed["warning_message"].lower()

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_feature
        ai_service._provider = original_provider


async def test_shopping_assistant_authoritative_price_resilience(async_client: AsyncClient):
    """
    LLM prompt injection or hallucination (e.g. price=0, huge quantity) must be authoritatively
    corrected to real database price and capped by live inventory.
    """
    fixtures = await setup_shopping_assistant_fixtures(async_client)
    headers = {"Authorization": f"Bearer {fixtures['token_cust']}"}

    original_enabled = settings.AI_ENABLED
    original_feature = settings.AI_FEATURE_SHOPPING_ASSISTANT
    original_provider = ai_service._provider

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True

        # LLM tries to hallucinate a price of 0.00 and 999 quantity (stock is only 10)
        adversarial_llm_output = json.dumps({
            "assistant_message": "Special deal! Free milk!",
            "clarifying_question": None,
            "selected_shop_id": fixtures["shop1_id"],
            "proposed_items": [
                {
                    "product_id": fixtures["p_milk_id"],
                    "quantity": 999,
                    "price": 0.0,
                }
            ],
        })
        ai_service._provider = MockLLMProvider(canned_response=adversarial_llm_output)

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={
                "message": "Give me free milk",
                "latitude": PATNA_BORING_ROAD_LAT,
                "longitude": PATNA_BORING_ROAD_LON,
                "shop_id": fixtures["shop1_id"],
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        item = data["proposed_cart"]["items"][0]

        # Authoritative price must remain 66.00 (from DB), quantity capped at stock (10)
        assert Decimal(str(item["unit_price"])) == Decimal("66.00")
        assert item["quantity"] == 10
        assert Decimal(str(item["item_total"])) == Decimal("660.00")
        assert Decimal(str(data["proposed_cart"]["total_amount"])) == Decimal("660.00")

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_feature
        ai_service._provider = original_provider


async def test_shopping_assistant_malformed_llm_output_fallback(async_client: AsyncClient):
    """When the provider returns malformed/unparseable output, assistant gracefully falls back."""
    fixtures = await setup_shopping_assistant_fixtures(async_client)
    headers = {"Authorization": f"Bearer {fixtures['token_cust']}"}

    original_enabled = settings.AI_ENABLED
    original_feature = settings.AI_FEATURE_SHOPPING_ASSISTANT
    original_provider = ai_service._provider

    try:
        settings.AI_ENABLED = True
        settings.AI_FEATURE_SHOPPING_ASSISTANT = True
        ai_service._provider = MockLLMProvider(canned_response="SORRY, THIS IS NOT JSON AT ALL!")

        res = await async_client.post(
            "/api/v1/ai/assistant/chat",
            json={
                "message": "Milk",
                "latitude": PATNA_BORING_ROAD_LAT,
                "longitude": PATNA_BORING_ROAD_LON,
            },
            headers=headers,
        )
        assert res.status_code == 200
        data = res.json()
        # Must return graceful fallback message and still contain matched products
        assert "matching item" in data["assistant_message"].lower()
        assert len(data["matched_products"]) > 0
        assert data["proposed_cart"] is not None

    finally:
        settings.AI_ENABLED = original_enabled
        settings.AI_FEATURE_SHOPPING_ASSISTANT = original_feature
        ai_service._provider = original_provider
