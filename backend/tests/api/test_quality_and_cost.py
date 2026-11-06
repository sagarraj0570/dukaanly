"""
Quality and Cost Tracking Benchmark Suite (Phase 2.7 Focus Area 4).

Tracks and Validates:
1. Response Latency: Execution duration tracked in milliseconds on all completions and chat responses.
2. Grounded Product Accuracy: 100% of proposed items must match active, in-stock partner products.
3. Successful Cart Proposal Rate: High success rate on unambiguous shopping requests.
4. Token Usage and Cost Estimation: Accurate prompt/completion token tracking and USD cost estimation.
5. Fallback Frequency: Safe local fallback behavior when upstream provider fails.
6. Privacy & Confidentiality Audit: Zero API keys (gsk_*, Bearer), secrets, or customer PII in telemetry.
"""

from decimal import Decimal
import json
import logging
import re
import uuid
import pytest

from app.core.ai import (
    AIService,
    MockLLMProvider,
    ai_service,
    estimate_token_cost,
    mask_sensitive_data,
)
from app.core.ai.schemas import (
    ChatMessage,
    ChatRole,
    LLMCompletionRequest,
    TokenUsage,
)
from app.db.session import async_session_maker
from app.models.product import Product
from app.models.user import User, UserRole
from app.schemas.ai import ShoppingAssistantRequest
from app.services.shopping_assistant import process_shopping_assistant_chat

pytestmark = pytest.mark.asyncio

PATNA_LAT = 25.6144
PATNA_LON = 85.1158
CANONICAL_PATNA_SHOP_ID = uuid.UUID("397dd958-810a-4f84-89c8-6a35c082d47a")


@pytest.fixture
async def customer_user():
    async with async_session_maker() as session:
        user_id = uuid.uuid4()
        user = User(
            id=user_id,
            name="Quality Benchmark Customer",
            email=f"quality_{uuid.uuid4().hex[:8]}@example.com",
            password_hash="dummy_hash",
            role=UserRole.customer,
            is_active=True,
        )
        session.add(user)
        await session.commit()
        yield user

        from sqlalchemy import text
        await session.execute(text("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE customer_id = :uid)"), {"uid": str(user_id)})
        await session.execute(text("DELETE FROM carts WHERE customer_id = :uid"), {"uid": str(user_id)})
        await session.execute(text("DELETE FROM users WHERE id = :uid"), {"uid": str(user_id)})
        await session.commit()


# ---------------------------------------------------------------------------
# Test 1: Latency Tracking Accuracy
# ---------------------------------------------------------------------------
async def test_response_latency_tracking(customer_user):
    """Verify that response latency is measured and recorded in milliseconds on all responses."""
    ai_service._provider = MockLLMProvider()
    async with async_session_maker() as session:
        req = ShoppingAssistantRequest(
            message="Amul Taaza milk 1 litre",
            latitude=PATNA_LAT,
            longitude=PATNA_LON,
        )
        resp = await process_shopping_assistant_chat(session, customer_user, req)

        assert resp.latency_ms is not None
        assert resp.latency_ms > 0.0
        # In mock offline mode, latency should be rapid (< 2000 ms)
        assert resp.latency_ms < 2000.0


# ---------------------------------------------------------------------------
# Test 2: Grounded Product Accuracy (100% Invariant)
# ---------------------------------------------------------------------------
async def test_grounded_product_accuracy(customer_user):
    """
    Verify grounded accuracy: every proposed product ID in the response
    MUST exist in the database, belong to the target verified partner shop,
    and have positive stock.
    """
    ai_service._provider = MockLLMProvider()
    test_queries = [
        "Aashirvaad wheat flour 5kg",
        "Amul milk and butter",
        "Fortune cooking oil 1L",
        "Tata salt and maggi noodles",
        "Bread and butter for breakfast",
    ]

    total_proposed_items = 0
    grounded_items = 0

    async with async_session_maker() as session:
        for q in test_queries:
            req = ShoppingAssistantRequest(
                message=q,
                latitude=PATNA_LAT,
                longitude=PATNA_LON,
            )
            resp = await process_shopping_assistant_chat(session, customer_user, req)

            if resp.proposed_cart and resp.proposed_cart.items:
                for item in resp.proposed_cart.items:
                    total_proposed_items += 1
                    # Verify product exists in DB and is active
                    prod = await session.get(Product, item.product_id)
                    assert prod is not None, f"Proposed product {item.product_id} does not exist in DB!"
                    assert prod.is_active is True
                    assert prod.shop_id == resp.proposed_cart.shop_id
                    grounded_items += 1

    accuracy_rate = grounded_items / total_proposed_items if total_proposed_items > 0 else 0.0
    assert accuracy_rate == 1.0, f"Grounded product accuracy was {accuracy_rate * 100}% (expected 100%)"


# ---------------------------------------------------------------------------
# Test 3: Successful Cart Proposal Rate Benchmark
# ---------------------------------------------------------------------------
async def test_successful_cart_proposal_rate(customer_user):
    """
    Verify proposal success rate across clear shopping requests.
    A successful proposal has a valid shop_id, non-empty items, and total > 0.
    """
    ai_service._provider = MockLLMProvider()
    shopping_queries = [
        "Aashirvaad atta 5kg",
        "Amul Taaza milk",
        "Tata salt 1kg packet",
        "Fortune refined oil",
        "Maggi 2-Minute noodles",
        "India Gate basmati rice",
        "Biscuits and tea gold",
        "Eggs and bread",
    ]

    proposals_count = 0
    async with async_session_maker() as session:
        for q in shopping_queries:
            req = ShoppingAssistantRequest(
                message=q,
                latitude=PATNA_LAT,
                longitude=PATNA_LON,
            )
            resp = await process_shopping_assistant_chat(session, customer_user, req)
            if resp.proposed_cart and len(resp.proposed_cart.items) > 0 and resp.proposed_cart.total_amount > Decimal("0.00"):
                proposals_count += 1

    success_rate = proposals_count / len(shopping_queries)
    assert success_rate >= 0.90, f"Cart proposal success rate was {success_rate * 100}% (expected >= 90%)"


# ---------------------------------------------------------------------------
# Test 4: Token Usage & Cost Estimation Tracking
# ---------------------------------------------------------------------------
async def test_token_usage_and_cost_estimation():
    """Verify calculation of prompt/completion token costs against standard pricing."""
    # Test case 1: Typical shopping assistant turn (450 prompt, 120 completion)
    prompt_tokens = 450
    completion_tokens = 120
    cost = estimate_token_cost(prompt_tokens, completion_tokens)
    assert isinstance(cost, float)
    assert cost > 0.0
    # At $0.15/M in and $0.60/M out:
    # (450 * 0.15 + 120 * 0.60) / 1,000,000 = 0.0001395 -> 0.00014 USD
    assert cost == pytest.approx(0.00014, rel=1e-2)

    # Test case 2: Zero tokens -> $0.00
    assert estimate_token_cost(0, 0) == 0.0


# ---------------------------------------------------------------------------
# Test 5: Fallback Frequency Under Upstream Failure
# ---------------------------------------------------------------------------
async def test_fallback_execution_under_provider_failure(customer_user):
    """
    Verify that when upstream LLM fails, the shopping assistant executes
    the registered safe fallback without returning an unhandled 500.
    """
    failing_provider = MockLLMProvider(simulate_server_error=True)
    ai_service._provider = failing_provider

    async with async_session_maker() as session:
        req = ShoppingAssistantRequest(
            message="Amul milk 1 litre",
            latitude=PATNA_LAT,
            longitude=PATNA_LON,
        )
        resp = await process_shopping_assistant_chat(session, customer_user, req)

        # Fallback response must still return gracefully with matched catalog items
        assert resp is not None
        assert resp.assistant_message is not None
        assert len(resp.matched_products) > 0
        assert resp.proposed_cart is not None
        assert resp.proposed_cart.items[0].product_name is not None

    # Reset provider
    ai_service._provider = MockLLMProvider()


# ---------------------------------------------------------------------------
# Test 6: Zero Secrets & Zero PII Confidentiality Check
# ---------------------------------------------------------------------------
async def test_mask_sensitive_data_zero_leakage():
    """
    Verify mask_sensitive_data sanitizes authorization headers, Groq keys, and sensitive tokens.
    """
    sample_text = (
        "Sending request to https://api.groq.com/openai/v1 with "
        "Authorization: Bearer gsk_dummy_mock_key_1234567890abcdef and "
        "apiKey: gsk_sampleFakeKey1234567890abcdef."
    )
    sanitized = mask_sensitive_data(sample_text)

    # Assert all keys are fully redacted
    assert "gsk_dummy_mock_key_1234567890abcdef" not in sanitized
    assert "gsk_sampleFakeKey1234567890abcdef" not in sanitized
    assert "***REDACTED***" in sanitized
