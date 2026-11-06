"""
Pure unit tests for AI shopping assistant evaluation scoring functions and aggregators.
Zero network calls, zero database writes.
"""

from decimal import Decimal
import uuid
import pytest

from evals.assistant.metrics import (
    CaseEvaluationResult,
    EvaluatedAssistantResponse,
    EvaluatedProductInfo,
    EvaluatedReturnedItem,
    check_budget_limit,
    check_forbidden_items,
    check_refusal_correctness,
    check_unavailable_handling,
    compute_aggregate_metrics,
    compute_item_set_metrics,
    compute_quantity_accuracy,
    detect_hallucination,
    evaluate_case,
    percentile,
)

# Test Fixtures & UUID Constants
SHOP_A = uuid.UUID("11111111-1111-1111-1111-111111111111")
SHOP_B = uuid.UUID("22222222-2222-2222-2222-222222222222")

PROD_1 = uuid.UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
PROD_2 = uuid.UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")
PROD_3 = uuid.UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
PROD_FORBIDDEN = uuid.UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")
PROD_INVENTED = uuid.UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")

DB_SNAPSHOT = {
    PROD_1: EvaluatedProductInfo(
        product_id=PROD_1,
        shop_id=SHOP_A,
        name="Sudha Toned Milk 1L",
        price=Decimal("56.00"),
        stock=50,
        is_active=True,
    ),
    PROD_2: EvaluatedProductInfo(
        product_id=PROD_2,
        shop_id=SHOP_A,
        name="Aashirvaad Atta 5kg",
        price=Decimal("245.00"),
        stock=40,
        is_active=True,
    ),
    PROD_3: EvaluatedProductInfo(
        product_id=PROD_3,
        shop_id=SHOP_B,
        name="Modern Brown Bread 400g",
        price=Decimal("45.00"),
        stock=30,
        is_active=True,
    ),
    PROD_FORBIDDEN: EvaluatedProductInfo(
        product_id=PROD_FORBIDDEN,
        shop_id=SHOP_A,
        name="Forbidden Tobacco/Beer",
        price=Decimal("100.00"),
        stock=10,
        is_active=True,
    ),
}


# ── 1. Perfect Match ──────────────────────────────────────────────────────────
def test_metric_perfect_match():
    response = EvaluatedAssistantResponse(
        assistant_message="Found items",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=2,
                unit_price=Decimal("56.00"),
                item_total=Decimal("112.00"),
            )
        ],
        latency_ms=120.0,
    )

    result = evaluate_case(
        case_id="case-1",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 2},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.item_precision == 1.0
    assert result.item_recall == 1.0
    assert result.item_f1 == 1.0
    assert result.quantity_accuracy == 1.0
    assert result.hallucination is False
    assert result.forbidden_hit is False
    assert result.exact_match is True


# ── 2. Missing Item (Partial Recall) ───────────────────────────────────────────
def test_metric_missing_item():
    response = EvaluatedAssistantResponse(
        assistant_message="Found 1 item",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-2",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1, PROD_2: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.item_precision == 1.0
    assert result.item_recall == 0.5
    assert result.item_f1 == round(2 * 1.0 * 0.5 / 1.5, 4)
    assert result.exact_match is False


# ── 3. Extra Item (Imperfect Precision) ────────────────────────────────────────
def test_metric_extra_item():
    response = EvaluatedAssistantResponse(
        assistant_message="Found 2 items",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            ),
            EvaluatedReturnedItem(
                product_id=PROD_2,
                product_name="Aashirvaad Atta 5kg",
                quantity=1,
                unit_price=Decimal("245.00"),
                item_total=Decimal("245.00"),
            ),
        ],
    )

    result = evaluate_case(
        case_id="case-3",
        category="english_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.item_precision == 0.5
    assert result.item_recall == 1.0
    assert result.exact_match is False


# ── 4. Wrong Quantity ─────────────────────────────────────────────────────────
def test_metric_wrong_quantity():
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,  # expected 3
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-4",
        category="quantities_units",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 3},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.item_precision == 1.0
    assert result.item_recall == 1.0
    assert result.quantity_accuracy == 0.0
    assert result.exact_match is False


# ── 5. Invented Product (Hallucination) ────────────────────────────────────────
def test_metric_invented_product_hallucination():
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_INVENTED,
                product_name="Hallucinated Magic Atta",
                quantity=1,
                unit_price=Decimal("100.00"),
                item_total=Decimal("100.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-5",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.hallucination is True
    assert "does not exist in database" in (result.hallucination_reason or "")
    assert result.exact_match is False


# ── 6. Wrong Shop Product (Hallucination) ───────────────────────────────────────
def test_metric_wrong_shop_product_hallucination():
    # PROD_3 belongs to SHOP_B, but target is SHOP_A
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_3,
                product_name="Modern Brown Bread 400g",
                quantity=1,
                unit_price=Decimal("45.00"),
                item_total=Decimal("45.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-6",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_3: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.hallucination is True
    assert "belongs to shop" in (result.hallucination_reason or "")
    assert result.exact_match is False


# ── 7. Price Mismatch (Hallucination) ──────────────────────────────────────────
def test_metric_price_mismatch_hallucination():
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("10.00"),  # DB price is 56.00
                item_total=Decimal("10.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-7",
        category="budget",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.hallucination is True
    assert "differs from database price" in (result.hallucination_reason or "")


# ── 8. Inactive or Out of Stock Product (Hallucination) ─────────────────────────
def test_metric_inactive_and_out_of_stock_product():
    inactive_pid = uuid.UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")
    db_with_inactive = dict(DB_SNAPSHOT)
    db_with_inactive[inactive_pid] = EvaluatedProductInfo(
        product_id=inactive_pid,
        shop_id=SHOP_A,
        name="Discontinued Item",
        price=Decimal("50.00"),
        stock=0,
        is_active=False,
    )

    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=inactive_pid,
                product_name="Discontinued Item",
                quantity=1,
                unit_price=Decimal("50.00"),
                item_total=Decimal("50.00"),
            )
        ]
    )

    result = evaluate_case(
        case_id="case-8",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={inactive_pid: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=db_with_inactive,
    )

    assert result.hallucination is True
    assert "marked inactive" in (result.hallucination_reason or "")


# ── 9. Budget Exceeded ────────────────────────────────────────────────────────
def test_metric_budget_exceeded():
    # Atta (245) + Milk (56) = 301 > 200 budget
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            ),
            EvaluatedReturnedItem(
                product_id=PROD_2,
                product_name="Aashirvaad Atta 5kg",
                quantity=1,
                unit_price=Decimal("245.00"),
                item_total=Decimal("245.00"),
            ),
        ]
    )

    result = evaluate_case(
        case_id="case-9",
        category="budget",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1, PROD_2: 1},
        forbidden_pids=set(),
        max_total=200.0,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.budget_ok is False
    assert result.exact_match is False


# ── 10. Budget Satisfied ──────────────────────────────────────────────────────
def test_metric_budget_satisfied():
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ]
    )

    result = evaluate_case(
        case_id="case-10",
        category="budget",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=100.0,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.budget_ok is True
    assert result.exact_match is True


# ── 11. Forbidden Item Hit ────────────────────────────────────────────────────
def test_metric_forbidden_item_hit():
    response = EvaluatedAssistantResponse(
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_FORBIDDEN,
                product_name="Forbidden Item",
                quantity=1,
                unit_price=Decimal("100.00"),
                item_total=Decimal("100.00"),
            )
        ]
    )

    result = evaluate_case(
        case_id="case-11",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids={PROD_FORBIDDEN},
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.forbidden_hit is True
    assert result.exact_match is False


# ── 12. Unavailable Handled ───────────────────────────────────────────────────
def test_metric_unavailable_handled():
    response = EvaluatedAssistantResponse(
        assistant_message="I found milk for you, but fresh mutton is currently not available in this shop.",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-12",
        category="unavailable",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=["mutton"],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.unavailable_handled is True
    assert result.exact_match is True


# ── 13. Unavailable Not Handled ───────────────────────────────────────────────
def test_metric_unavailable_not_handled():
    # Assistant silently dropped mention of mutton
    response = EvaluatedAssistantResponse(
        assistant_message="Here is your milk.",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-13",
        category="unavailable",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=["mutton"],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.unavailable_handled is False
    assert result.exact_match is False


# ── 14. Correct Refusal on Out of Scope ────────────────────────────────────────
def test_metric_correct_refusal_out_of_scope():
    response = EvaluatedAssistantResponse(
        assistant_message="I am your shopping assistant for local groceries. I cannot write poetry.",
        items=[],
    )

    result = evaluate_case(
        case_id="case-14",
        category="out_of_scope",
        target_shop_id=SHOP_A,
        expected_items_map={},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=True,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.refusal_correct is True
    assert result.item_precision == 1.0
    assert result.item_recall == 1.0
    assert result.exact_match is True


# ── 15. Incorrect Refusal on Out of Scope (Items Wrongly Returned) ─────────────
def test_metric_incorrect_refusal_out_of_scope():
    response = EvaluatedAssistantResponse(
        assistant_message="Here is some milk instead of a poem.",
        items=[
            EvaluatedReturnedItem(
                product_id=PROD_1,
                product_name="Sudha Toned Milk 1L",
                quantity=1,
                unit_price=Decimal("56.00"),
                item_total=Decimal("56.00"),
            )
        ],
    )

    result = evaluate_case(
        case_id="case-15",
        category="out_of_scope",
        target_shop_id=SHOP_A,
        expected_items_map={},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=True,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.refusal_correct is False
    assert result.item_precision == 0.0
    assert result.exact_match is False


# ── 16. Empty Response on Normal In-Scope Query ────────────────────────────────
def test_metric_empty_response_on_normal_query():
    response = EvaluatedAssistantResponse(
        assistant_message="Sorry, I could not find anything.",
        items=[],
    )

    result = evaluate_case(
        case_id="case-16",
        category="hinglish_basic",
        target_shop_id=SHOP_A,
        expected_items_map={PROD_1: 1},
        forbidden_pids=set(),
        max_total=None,
        expect_unavailable=[],
        expect_refusal=False,
        response=response,
        db_products_map=DB_SNAPSHOT,
    )

    assert result.item_precision == 0.0
    assert result.item_recall == 0.0
    assert result.exact_match is False


# ── 17. Aggregate Metrics Computation ──────────────────────────────────────────
def test_metric_aggregate_computation():
    res1 = CaseEvaluationResult(
        case_id="c-1",
        category="hinglish_basic",
        item_precision=1.0,
        item_recall=1.0,
        item_f1=1.0,
        quantity_accuracy=1.0,
        hallucination=False,
        forbidden_hit=False,
        budget_ok=True,
        unavailable_handled=True,
        refusal_correct=True,
        exact_match=True,
        latency_ms=100.0,
        prompt_tokens=150,
        completion_tokens=50,
        total_tokens=200,
    )
    res2 = CaseEvaluationResult(
        case_id="c-2",
        category="hinglish_basic",
        item_precision=0.5,
        item_recall=1.0,
        item_f1=0.6667,
        quantity_accuracy=1.0,
        hallucination=False,
        forbidden_hit=False,
        budget_ok=True,
        unavailable_handled=True,
        refusal_correct=True,
        exact_match=False,
        latency_ms=200.0,
        prompt_tokens=160,
        completion_tokens=60,
        total_tokens=220,
    )
    res3 = CaseEvaluationResult(
        case_id="c-3",
        category="out_of_scope",
        item_precision=1.0,
        item_recall=1.0,
        item_f1=1.0,
        quantity_accuracy=1.0,
        hallucination=False,
        forbidden_hit=False,
        budget_ok=True,
        unavailable_handled=True,
        refusal_correct=True,
        exact_match=True,
        latency_ms=80.0,
        prompt_tokens=100,
        completion_tokens=30,
        total_tokens=130,
    )

    agg = compute_aggregate_metrics([res1, res2, res3])
    assert agg.total_cases == 3
    assert agg.item_precision_mean == round((1.0 + 0.5 + 1.0) / 3, 4)
    assert agg.item_recall_mean == 1.0
    assert agg.exact_match_rate == round(2 / 3, 4)
    assert agg.hallucination_rate == 0.0
    assert agg.latency_p50_ms == 100.0
    assert agg.total_tokens == 550
    assert "hinglish_basic" in agg.category_breakdown
    assert agg.category_breakdown["hinglish_basic"].n == 2
    assert agg.category_breakdown["out_of_scope"].n == 1
