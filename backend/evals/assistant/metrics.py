"""
Evaluation metrics for Dukaanly AI Shopping Assistant.
Pure functions: zero network calls, zero database writes, completely deterministic.
"""

from decimal import Decimal
import math
from typing import Any, Dict, List, Optional, Set, Tuple
import uuid
from pydantic import BaseModel, ConfigDict, Field


class EvaluatedProductInfo(BaseModel):
    """Snapshot of authoritative database product record for evaluation."""
    product_id: uuid.UUID
    shop_id: uuid.UUID
    name: str
    price: Decimal
    stock: int
    is_active: bool = True

    model_config = ConfigDict(from_attributes=True)


class EvaluatedReturnedItem(BaseModel):
    """Proposed cart item returned by assistant."""
    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    item_total: Decimal

    model_config = ConfigDict(from_attributes=True)


class EvaluatedAssistantResponse(BaseModel):
    """Normalized assistant response structure for metric scoring."""
    assistant_message: str = ""
    clarifying_question: Optional[str] = None
    selected_shop_id: Optional[uuid.UUID] = None
    items: List[EvaluatedReturnedItem] = Field(default_factory=list)
    latency_ms: float = 0.0
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CaseEvaluationResult(BaseModel):
    """Detailed evaluation score for a single evaluation test case."""
    case_id: str
    category: str
    item_precision: float
    item_recall: float
    item_f1: float
    quantity_accuracy: float
    hallucination: bool
    hallucination_reason: Optional[str] = None
    forbidden_hit: bool
    budget_ok: bool
    unavailable_handled: bool
    refusal_correct: bool
    exact_match: bool
    latency_ms: float
    prompt_tokens: Optional[int] = None
    completion_tokens: Optional[int] = None
    total_tokens: Optional[int] = None

    model_config = ConfigDict(from_attributes=True)


class CategoryMetrics(BaseModel):
    category: str
    n: int
    item_precision: float
    item_recall: float
    item_f1: float
    quantity_accuracy: float
    exact_match_rate: float
    hallucination_rate: float
    forbidden_hit_rate: float
    budget_ok_rate: float
    unavailable_handled_rate: float
    refusal_accuracy: float


class AggregateEvaluationResult(BaseModel):
    total_cases: int
    item_precision_mean: float
    item_recall_mean: float
    item_f1_mean: float
    quantity_accuracy_mean: float
    exact_match_rate: float
    hallucination_rate: float
    forbidden_hit_rate: float
    budget_ok_rate: float
    unavailable_handled_rate: float
    refusal_precision: float
    refusal_recall: float
    refusal_f1: float
    latency_p50_ms: float
    latency_p90_ms: float
    latency_p95_ms: float
    latency_mean_ms: float
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    category_breakdown: Dict[str, CategoryMetrics]


def compute_item_set_metrics(
    returned_pids: Set[uuid.UUID],
    expected_pids: Set[uuid.UUID],
    expect_refusal: bool = False,
) -> Tuple[float, float, float]:
    """
    Compute set-based precision, recall, and F1 comparing returned product IDs
    against expected product IDs.
    """
    if expect_refusal or len(expected_pids) == 0:
        if len(returned_pids) == 0:
            return 1.0, 1.0, 1.0
        return 0.0, 0.0, 0.0

    if len(returned_pids) == 0:
        return 0.0, 0.0, 0.0

    true_positives = len(returned_pids & expected_pids)
    precision = true_positives / len(returned_pids)
    recall = true_positives / len(expected_pids)

    if precision + recall > 0:
        f1 = (2 * precision * recall) / (precision + recall)
    else:
        f1 = 0.0

    return round(precision, 4), round(recall, 4), round(f1, 4)


def compute_quantity_accuracy(
    returned_items: List[EvaluatedReturnedItem],
    expected_items_map: Dict[uuid.UUID, int],
) -> float:
    """
    Among correctly matched products, compute fraction whose returned quantity
    equals expected quantity.
    """
    returned_map = {item.product_id: item.quantity for item in returned_items}
    matched_pids = set(returned_map.keys()) & set(expected_items_map.keys())

    if len(expected_items_map) == 0:
        return 1.0 if len(returned_items) == 0 else 0.0

    if len(matched_pids) == 0:
        return 0.0

    correct_qty = sum(1 for pid in matched_pids if returned_map[pid] == expected_items_map[pid])
    return round(correct_qty / len(matched_pids), 4)


def detect_hallucination(
    returned_items: List[EvaluatedReturnedItem],
    target_shop_id: uuid.UUID,
    db_products_map: Dict[uuid.UUID, EvaluatedProductInfo],
) -> Tuple[bool, Optional[str]]:
    """
    Check if ANY returned product ID:
    - Does not exist in the database
    - Does not belong to the target shop
    - Is inactive in the database
    - Is out of stock (stock < 1)
    - Returns a price differing from database price
    """
    for item in returned_items:
        db_prod = db_products_map.get(item.product_id)
        if not db_prod:
            return True, f"Product ID '{item.product_id}' ({item.product_name}) does not exist in database"

        if db_prod.shop_id != target_shop_id:
            return True, (
                f"Product '{db_prod.name}' belongs to shop '{db_prod.shop_id}', "
                f"not target shop '{target_shop_id}'"
            )

        if not db_prod.is_active:
            return True, f"Product '{db_prod.name}' is marked inactive (is_active=False) in database"

        if db_prod.stock < 1:
            return True, f"Product '{db_prod.name}' is out of stock in database (stock={db_prod.stock})"

        if item.unit_price != db_prod.price:
            return True, (
                f"Product '{db_prod.name}' returned unit price ₹{item.unit_price} "
                f"differs from database price ₹{db_prod.price}"
            )

    return False, None


def check_forbidden_items(
    returned_pids: Set[uuid.UUID],
    forbidden_pids: Set[uuid.UUID],
) -> bool:
    """True if ANY forbidden product appears in the returned cart."""
    return len(returned_pids & forbidden_pids) > 0


def check_budget_limit(
    returned_items: List[EvaluatedReturnedItem],
    max_total: Optional[float],
    db_products_map: Dict[uuid.UUID, EvaluatedProductInfo],
) -> bool:
    """
    True if max_total is None OR computed total (using DATABASE prices) <= max_total.
    """
    if max_total is None:
        return True

    computed_total = Decimal("0.00")
    for item in returned_items:
        db_prod = db_products_map.get(item.product_id)
        price = db_prod.price if db_prod else item.unit_price
        computed_total += price * item.quantity

    return float(computed_total) <= max_total


def check_unavailable_handling(
    expect_unavailable: List[str],
    assistant_message: str,
    clarifying_question: Optional[str] = None,
) -> bool:
    """
    True if every expect_unavailable item is reported as unavailable
    in the assistant text message or clarifying question.
    """
    if not expect_unavailable:
        return True

    text = f"{assistant_message} {clarifying_question or ''}".lower()
    negative_signals = [
        "not available",
        "unavailable",
        "out of stock",
        "not in stock",
        "don't have",
        "do not have",
        "nahi hai",
        "nahi mila",
        "upalabdh nahi",
        "could not find",
        "couldn't find",
        "not found",
    ]

    has_negative_signal = any(sig in text for sig in negative_signals)
    if not has_negative_signal:
        return False

    for item in expect_unavailable:
        tokens = [t.lower() for t in item.split() if len(t) > 2]
        # At least one meaningful token of the unavailable item must be mentioned
        if tokens and not any(t in text for t in tokens):
            return False

    return True


def check_refusal_correctness(
    expect_refusal: bool,
    returned_items: List[EvaluatedReturnedItem],
    assistant_message: str,
) -> bool:
    """
    For expect_refusal=True: True if declined and returned no items.
    For expect_refusal=False: True if not wrongly declined.
    """
    if expect_refusal:
        return len(returned_items) == 0

    # Normal case: if items returned, refusal wasn't triggered
    if len(returned_items) > 0:
        return True

    # If 0 items returned on an in-scope request, check if it wrongly refused
    refusal_keywords = ["cannot assist", "cannot help", "inappropriate", "policy", "cannot fulfill", "refuse"]
    is_hard_refusal = any(kw in assistant_message.lower() for kw in refusal_keywords)
    return not is_hard_refusal


def evaluate_case(
    case_id: str,
    category: str,
    target_shop_id: uuid.UUID,
    expected_items_map: Dict[uuid.UUID, int],
    forbidden_pids: Set[uuid.UUID],
    max_total: Optional[float],
    expect_unavailable: List[str],
    expect_refusal: bool,
    response: EvaluatedAssistantResponse,
    db_products_map: Dict[uuid.UUID, EvaluatedProductInfo],
) -> CaseEvaluationResult:
    """
    Evaluate a single assistant response against ground-truth case specifications.
    Pure function: no network, no DB.
    """
    returned_pids = {item.product_id for item in response.items}
    expected_pids = set(expected_items_map.keys())

    # 1. Item precision, recall, F1
    precision, recall, f1 = compute_item_set_metrics(
        returned_pids=returned_pids,
        expected_pids=expected_pids,
        expect_refusal=expect_refusal,
    )

    # 2. Quantity accuracy
    qty_acc = compute_quantity_accuracy(
        returned_items=response.items,
        expected_items_map=expected_items_map,
    )

    # 3. Hallucination check
    hallucinated, hall_reason = detect_hallucination(
        returned_items=response.items,
        target_shop_id=target_shop_id,
        db_products_map=db_products_map,
    )

    # 4. Forbidden items check
    forb_hit = check_forbidden_items(
        returned_pids=returned_pids,
        forbidden_pids=forbidden_pids,
    )

    # 5. Budget constraint check
    budget_ok = check_budget_limit(
        returned_items=response.items,
        max_total=max_total,
        db_products_map=db_products_map,
    )

    # 6. Unavailable items handling
    unavail_handled = check_unavailable_handling(
        expect_unavailable=expect_unavailable,
        assistant_message=response.assistant_message,
        clarifying_question=response.clarifying_question,
    )

    # 7. Refusal correctness
    refusal_ok = check_refusal_correctness(
        expect_refusal=expect_refusal,
        returned_items=response.items,
        assistant_message=response.assistant_message,
    )

    # 8. Exact match: exact items & quantities match, no forbidden, no hallucination, budget ok
    exact_match = (
        not hallucinated
        and not forb_hit
        and budget_ok
        and unavail_handled
        and refusal_ok
        and (precision == 1.0 and recall == 1.0 and qty_acc == 1.0)
    )

    return CaseEvaluationResult(
        case_id=case_id,
        category=category,
        item_precision=precision,
        item_recall=recall,
        item_f1=f1,
        quantity_accuracy=qty_acc,
        hallucination=hallucinated,
        hallucination_reason=hall_reason,
        forbidden_hit=forb_hit,
        budget_ok=budget_ok,
        unavailable_handled=unavail_handled,
        refusal_correct=refusal_ok,
        exact_match=exact_match,
        latency_ms=response.latency_ms,
        prompt_tokens=response.prompt_tokens,
        completion_tokens=response.completion_tokens,
        total_tokens=response.total_tokens,
    )


def evaluate_resolved_case(
    case: Any,
    response: EvaluatedAssistantResponse,
    db_products_map: Dict[uuid.UUID, EvaluatedProductInfo],
) -> CaseEvaluationResult:
    """Convenience wrapper for evaluate_case using a ResolvedTestCase object."""
    expected_items_map = {item.product_id: item.quantity for item in case.expected_items}
    forbidden_pids = set(case.forbidden_product_ids)
    return evaluate_case(
        case_id=case.id,
        category=case.category,
        target_shop_id=case.shop_id,
        expected_items_map=expected_items_map,
        forbidden_pids=forbidden_pids,
        max_total=case.max_total,
        expect_unavailable=case.expect_unavailable,
        expect_refusal=case.expect_refusal,
        response=response,
        db_products_map=db_products_map,
    )


def percentile(data: List[float], p: float) -> float:
    """Calculate the p-th percentile of a list of floats (0 <= p <= 100)."""
    if not data:
        return 0.0
    sorted_data = sorted(data)
    idx = (len(sorted_data) - 1) * (p / 100.0)
    floor_idx = math.floor(idx)
    ceil_idx = math.ceil(idx)
    if floor_idx == ceil_idx:
        return round(sorted_data[int(idx)], 2)
    fraction = idx - floor_idx
    val = sorted_data[floor_idx] + fraction * (sorted_data[ceil_idx] - sorted_data[floor_idx])
    return round(val, 2)


def compute_aggregate_metrics(results: List[CaseEvaluationResult]) -> AggregateEvaluationResult:
    """
    Aggregate evaluation results across all cases:
    - Overall & per-category means
    - Hallucination rate
    - Refusal precision/recall/F1
    - Exact match rate
    - Latency percentiles (p50, p90, p95)
    - Token sums
    Always includes count (n) for every number.
    """
    total = len(results)
    if total == 0:
        return AggregateEvaluationResult(
            total_cases=0,
            item_precision_mean=0.0,
            item_recall_mean=0.0,
            item_f1_mean=0.0,
            quantity_accuracy_mean=0.0,
            exact_match_rate=0.0,
            hallucination_rate=0.0,
            forbidden_hit_rate=0.0,
            budget_ok_rate=0.0,
            unavailable_handled_rate=0.0,
            refusal_precision=0.0,
            refusal_recall=0.0,
            refusal_f1=0.0,
            latency_p50_ms=0.0,
            latency_p90_ms=0.0,
            latency_p95_ms=0.0,
            latency_mean_ms=0.0,
            total_prompt_tokens=0,
            total_completion_tokens=0,
            total_tokens=0,
            category_breakdown={},
        )

    # Group by category
    cat_groups: Dict[str, List[CaseEvaluationResult]] = {}
    for r in results:
        cat_groups.setdefault(r.category, []).append(r)

    category_breakdown: Dict[str, CategoryMetrics] = {}
    for cat_name, cat_results in cat_groups.items():
        cn = len(cat_results)
        category_breakdown[cat_name] = CategoryMetrics(
            category=cat_name,
            n=cn,
            item_precision=round(sum(r.item_precision for r in cat_results) / cn, 4),
            item_recall=round(sum(r.item_recall for r in cat_results) / cn, 4),
            item_f1=round(sum(r.item_f1 for r in cat_results) / cn, 4),
            quantity_accuracy=round(sum(r.quantity_accuracy for r in cat_results) / cn, 4),
            exact_match_rate=round(sum(1 for r in cat_results if r.exact_match) / cn, 4),
            hallucination_rate=round(sum(1 for r in cat_results if r.hallucination) / cn, 4),
            forbidden_hit_rate=round(sum(1 for r in cat_results if r.forbidden_hit) / cn, 4),
            budget_ok_rate=round(sum(1 for r in cat_results if r.budget_ok) / cn, 4),
            unavailable_handled_rate=round(sum(1 for r in cat_results if r.unavailable_handled) / cn, 4),
            refusal_accuracy=round(sum(1 for r in cat_results if r.refusal_correct) / cn, 4),
        )

    # Refusal metrics
    out_of_scope_cases = [r for r in results if r.category == "out_of_scope"]
    refused_cases = [r for r in results if r.item_precision == 1.0 and r.item_recall == 1.0 and r.refusal_correct and r.category == "out_of_scope"]
    
    true_refusals = len(refused_cases)
    total_expected_refusals = len(out_of_scope_cases)
    total_assistant_refusals = sum(1 for r in results if r.refusal_correct and r.category == "out_of_scope")

    refusal_prec = (true_refusals / total_assistant_refusals) if total_assistant_refusals > 0 else 1.0
    refusal_rec = (true_refusals / total_expected_refusals) if total_expected_refusals > 0 else 1.0
    refusal_f1 = (2 * refusal_prec * refusal_rec / (refusal_prec + refusal_rec)) if (refusal_prec + refusal_rec) > 0 else 0.0

    latencies = [r.latency_ms for r in results]
    prompt_tokens = sum(r.prompt_tokens or 0 for r in results)
    completion_tokens = sum(r.completion_tokens or 0 for r in results)
    total_toks = sum(r.total_tokens or 0 for r in results)

    return AggregateEvaluationResult(
        total_cases=total,
        item_precision_mean=round(sum(r.item_precision for r in results) / total, 4),
        item_recall_mean=round(sum(r.item_recall for r in results) / total, 4),
        item_f1_mean=round(sum(r.item_f1 for r in results) / total, 4),
        quantity_accuracy_mean=round(sum(r.quantity_accuracy for r in results) / total, 4),
        exact_match_rate=round(sum(1 for r in results if r.exact_match) / total, 4),
        hallucination_rate=round(sum(1 for r in results if r.hallucination) / total, 4),
        forbidden_hit_rate=round(sum(1 for r in results if r.forbidden_hit) / total, 4),
        budget_ok_rate=round(sum(1 for r in results if r.budget_ok) / total, 4),
        unavailable_handled_rate=round(sum(1 for r in results if r.unavailable_handled) / total, 4),
        refusal_precision=round(refusal_prec, 4),
        refusal_recall=round(refusal_rec, 4),
        refusal_f1=round(refusal_f1, 4),
        latency_p50_ms=percentile(latencies, 50),
        latency_p90_ms=percentile(latencies, 90),
        latency_p95_ms=percentile(latencies, 95),
        latency_mean_ms=round(sum(latencies) / total, 2),
        total_prompt_tokens=prompt_tokens,
        total_completion_tokens=completion_tokens,
        total_tokens=total_toks,
        category_breakdown=category_breakdown,
    )
