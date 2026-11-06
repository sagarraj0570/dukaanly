"""
Unit and integration tests for dataset loader and resolver.
"""

from pathlib import Path
import pytest
from app.db.session import async_session_maker
from evals.assistant.dataset import (
    AssistantTestCase,
    ExpectedItem,
    load_raw_cases,
    load_and_resolve_dataset,
    resolve_test_case,
)


def test_load_raw_cases_schema_and_distribution():
    cases = load_raw_cases()
    assert len(cases) == 80, f"Expected 80 cases, got {len(cases)}"

    cat_counts = {}
    for c in cases:
        assert isinstance(c, AssistantTestCase)
        assert c.id
        assert c.query
        assert c.shop_ref
        assert c.reviewed is False
        cat_counts[c.category] = cat_counts.get(c.category, 0) + 1

    expected_counts = {
        "hinglish_basic": 15,
        "hindi_script": 10,
        "english_basic": 10,
        "quantities_units": 8,
        "brand_and_size": 8,
        "budget": 8,
        "misspellings_and_slang": 8,
        "unavailable": 8,
        "out_of_scope": 5,
    }
    assert cat_counts == expected_counts


def test_dataset_invalid_category_rejected():
    with pytest.raises(Exception):
        AssistantTestCase(
            id="bad-1",
            category="unsupported_category",
            query="test",
            shop_ref="patna-super-kirana",
        )


@pytest.mark.asyncio
async def test_load_and_resolve_dataset_against_db():
    async with async_session_maker() as session:
        resolved_cases = await load_and_resolve_dataset(session)
        assert len(resolved_cases) == 80

        for rc in resolved_cases:
            assert rc.shop_id is not None
            assert rc.shop_name
            for exp in rc.expected_items:
                assert exp.product_id is not None
                assert exp.product_name
                assert exp.quantity >= 1
                assert exp.unit_price > 0


@pytest.mark.asyncio
async def test_resolve_test_case_fails_on_nonexistent_product():
    async with async_session_maker() as session:
        fake_case = AssistantTestCase(
            id="fake-001",
            category="hinglish_basic",
            query="kuch bhi",
            shop_ref="patna-super-kirana",
            expected_items=[ExpectedItem(product_ref="Nonexistent Imaginary Product 123", quantity=1)],
        )
        with pytest.raises(ValueError, match="DOES NOT EXIST in the database"):
            await resolve_test_case(fake_case, session)


@pytest.mark.asyncio
async def test_resolve_test_case_fails_on_nonexistent_shop():
    async with async_session_maker() as session:
        fake_case = AssistantTestCase(
            id="fake-002",
            category="hinglish_basic",
            query="kuch bhi",
            shop_ref="nonexistent-imaginary-shop",
            expected_items=[],
        )
        with pytest.raises(ValueError, match="no matching Shop exists"):
            await resolve_test_case(fake_case, session)
