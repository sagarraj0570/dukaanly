"""
CLI Runner for Dukaanly AI Shopping Assistant Evaluations.

Executes grounded evaluation cases directly against the shopping assistant pipeline
without HTTP overhead, rate-limiting interference, or database side-effects.

Usage:
    python -m evals.assistant.run_eval --provider mock --runs 1
    python -m evals.assistant.run_eval --provider live --runs 3 --max-calls 300
"""

import argparse
import asyncio
from datetime import datetime, timezone
from decimal import Decimal
import json
import logging
from pathlib import Path
import subprocess
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.ai import ai_service, get_llm_provider
from app.core.ai.exceptions import AIError
from app.core.config import settings
from app.db.session import async_session_maker
from app.models.product import Product
from app.models.user import User
from app.schemas.ai import ShoppingAssistantRequest, ShoppingAssistantResponse
from app.services.shopping_assistant import process_shopping_assistant_chat

from evals.assistant.dataset import (
    ResolvedTestCase,
    load_and_resolve_dataset,
)
from evals.assistant.metrics import (
    AggregateEvaluationResult,
    CaseEvaluationResult,
    EvaluatedAssistantResponse,
    EvaluatedProductInfo,
    EvaluatedReturnedItem,
    compute_aggregate_metrics,
    evaluate_case,
    evaluate_resolved_case,
)

logger = logging.getLogger("eval_runner")
logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")

HONESTY_NOTE_MOCK = (
    "HONESTY NOTE: MockLLMProvider is a deterministic rule-based mock. "
    "Mock evaluation results measure the search, retrieval, and validation pipeline ONLY, "
    "NOT live LLM reasoning or prompt quality."
)


def get_git_commit() -> str:
    """Retrieve current short git commit hash, or 'unknown'."""
    try:
        out = subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            stderr=subprocess.DEVNULL,
        )
        return out.decode("utf-8").strip()
    except Exception:
        return "unknown"


async def fetch_db_product_catalog(db: AsyncSession) -> Dict[uuid.UUID, EvaluatedProductInfo]:
    """Load authoritative product catalog snapshot into memory for pure evaluation."""
    stmt = select(Product).options(selectinload(Product.inventory))
    products = (await db.execute(stmt)).scalars().all()
    catalog: Dict[uuid.UUID, EvaluatedProductInfo] = {}
    for p in products:
        stock = p.inventory.stock if p.inventory else 0
        catalog[p.id] = EvaluatedProductInfo(
            product_id=p.id,
            shop_id=p.shop_id,
            name=p.name,
            price=p.price,
            stock=stock,
            is_active=p.is_active,
        )
    return catalog


def format_console_table(agg: AggregateEvaluationResult) -> str:
    """Format aggregate evaluation results into a clean terminal table."""
    header = (
        f"{'Category':<24} | {'N':>3} | {'Prec':>5} | {'Rec':>5} | {'F1':>5} | "
        f"{'QtyAcc':>6} | {'Halluc':>6} | {'Refusal':>7} | {'Exact':>5}"
    )
    divider = "-" * len(header)
    lines = [divider, header, divider]

    for cat_name, cat in sorted(agg.category_breakdown.items()):
        lines.append(
            f"{cat_name:<24} | {cat.n:>3} | {cat.item_precision:>5.2f} | {cat.item_recall:>5.2f} | "
            f"{cat.item_f1:>5.2f} | {cat.quantity_accuracy:>6.2f} | {cat.hallucination_rate:>5.1%} | "
            f"{cat.refusal_accuracy:>6.1%} | {cat.exact_match_rate:>5.1%}"
        )

    lines.append(divider)
    lines.append(
        f"{'OVERALL':<24} | {agg.total_cases:>3} | {agg.item_precision_mean:>5.2f} | {agg.item_recall_mean:>5.2f} | "
        f"{agg.item_f1_mean:>5.2f} | {agg.quantity_accuracy_mean:>6.2f} | {agg.hallucination_rate:>5.1%} | "
        f"{agg.refusal_precision:>6.1%} | {agg.exact_match_rate:>5.1%}"
    )
    lines.append(divider)
    lines.append(
        f"Latency: p50={agg.latency_p50_ms:.1f}ms, p95={agg.latency_p95_ms:.1f}ms, mean={agg.latency_mean_ms:.1f}ms | "
        f"Tokens: prompt={agg.total_prompt_tokens}, comp={agg.total_completion_tokens}, total={agg.total_tokens}"
    )
    lines.append(divider)
    return "\n".join(lines)


async def run_single_eval_call(
    db: AsyncSession,
    customer: User,
    case: ResolvedTestCase,
    provider_name: str,
    db_products: Dict[uuid.UUID, EvaluatedProductInfo],
    captured_tokens: Dict[str, Optional[int]],
) -> Tuple[ShoppingAssistantResponse, CaseEvaluationResult]:
    """Execute a single end-to-end assistant call and evaluate its output."""
    # Standard Boring Road, Patna coordinates within ~500m of all partner shops
    lat, lng = 25.6150, 85.1160
    req = ShoppingAssistantRequest(
        message=case.query,
        latitude=lat,
        longitude=lng,
    )

    response = await process_shopping_assistant_chat(
        db=db,
        customer=customer,
        request=req,
    )

    # Convert ShoppingAssistantResponse to EvaluatedAssistantResponse
    items: List[EvaluatedReturnedItem] = []
    selected_shop_id = None
    if response.proposed_cart:
        selected_shop_id = response.proposed_cart.shop_id
        for item in response.proposed_cart.items:
            items.append(
                EvaluatedReturnedItem(
                    product_id=item.product_id,
                    product_name=item.product_name,
                    quantity=item.quantity,
                    unit_price=item.unit_price,
                    item_total=item.item_total,
                )
            )

    eval_resp = EvaluatedAssistantResponse(
        assistant_message=response.assistant_message,
        clarifying_question=response.clarifying_question,
        selected_shop_id=selected_shop_id,
        items=items,
        latency_ms=response.latency_ms,
        prompt_tokens=captured_tokens.get("prompt_tokens"),
        completion_tokens=captured_tokens.get("completion_tokens"),
        total_tokens=captured_tokens.get("total_tokens"),
    )

    case_eval = evaluate_resolved_case(case, eval_resp, db_products)
    return response, case_eval


async def main_async(args: argparse.Namespace) -> int:
    timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    provider_choice = args.provider.lower()
    commit_hash = get_git_commit()

    runs = 1 if provider_choice == "mock" else args.runs

    print("\n" + "=" * 70)
    print(f" Dukaanly Shopping Assistant Evaluation Harness")
    print(f" Provider: {provider_choice.upper()} | Runs: {runs} | Commit: {commit_hash}")
    if provider_choice == "mock":
        print(f" {HONESTY_NOTE_MOCK}")
    print("=" * 70 + "\n")

    # Configure AI Service for Evaluation
    settings.AI_ENABLED = True
    ai_service.reset_circuit_breaker()
    if provider_choice == "mock":
        ai_service._provider = get_llm_provider("mock")
    else:
        ai_service._provider = get_llm_provider()

    # Intercept tokens for telemetry
    captured_tokens: Dict[str, Optional[int]] = {
        "prompt_tokens": None,
        "completion_tokens": None,
        "total_tokens": None,
    }
    original_complete = ai_service.complete

    async def complete_spy(request: Any, feature_name: str = "shopping_assistant"):
        nonlocal captured_tokens
        resp = await original_complete(request, feature_name)
        if resp and resp.usage:
            captured_tokens["prompt_tokens"] = resp.usage.prompt_tokens
            captured_tokens["completion_tokens"] = resp.usage.completion_tokens
            captured_tokens["total_tokens"] = resp.usage.total_tokens
        else:
            captured_tokens["prompt_tokens"] = None
            captured_tokens["completion_tokens"] = None
            captured_tokens["total_tokens"] = None
        return resp

    ai_service.complete = complete_spy

    async with async_session_maker() as db:
        try:
            # 1. Fetch demo customer
            cust_res = await db.execute(
                select(User).where(User.email == "customer@dukaanly.com")
            )
            customer = cust_res.scalar_one_or_none()
            if not customer:
                raise RuntimeError(
                    "Demo customer 'customer@dukaanly.com' not found. "
                    "Please run 'python -m app.db.seed_demo' first."
                )

            # 2. Authoritative products snapshot
            db_products = await fetch_db_product_catalog(db)

            # 3. Load & resolve evaluation cases
            cases = await load_and_resolve_dataset(db)
            if args.category != "all":
                cases = [c for c in cases if c.category == args.category]

            if args.limit and args.limit > 0:
                cases = cases[: args.limit]

            total_cases = len(cases)
            estimated_calls = total_cases * runs

            print(f"Loaded {total_cases} test cases (Category: {args.category})")
            print(f"Planned calls: {estimated_calls} (Max limit: {args.max_calls})")

            if estimated_calls > args.max_calls:
                raise ValueError(
                    f"Planned calls ({estimated_calls}) exceeds --max-calls ({args.max_calls}). "
                    f"Adjust --limit or increase --max-calls."
                )

            evaluated_runs: List[CaseEvaluationResult] = []
            detailed_case_logs: List[Dict[str, Any]] = []

            total_calls_executed = 0
            start_time_all = time.time()

            for i, case in enumerate(cases, 1):
                case_run_evals: List[CaseEvaluationResult] = []
                last_raw_resp: Optional[ShoppingAssistantResponse] = None

                for run_idx in range(runs):
                    if ai_service.is_circuit_breaker_open():
                        print(f"\n[ALERT] AI Circuit Breaker TRIPPED at case {case.id} run {run_idx+1}. Stopping early.")
                        break

                    # Exponential backoff retry for live provider errors
                    max_retries = 3 if provider_choice == "live" else 1
                    retry_delay = 1.0

                    resp = None
                    case_eval = None
                    for attempt in range(max_retries):
                        try:
                            if provider_choice == "live" and run_idx > 0:
                                await asyncio.sleep(0.5)

                            resp, case_eval = await run_single_eval_call(
                                db=db,
                                customer=customer,
                                case=case,
                                provider_name=provider_choice,
                                db_products=db_products,
                                captured_tokens=captured_tokens,
                            )
                            total_calls_executed += 1
                            break
                        except Exception as exc:
                            if attempt == max_retries - 1:
                                logger.error("Case %s run %d failed after %d retries: %s", case.id, run_idx, max_retries, exc)
                                raise
                            await asyncio.sleep(retry_delay)
                            retry_delay *= 2.0

                    if resp and case_eval:
                        last_raw_resp = resp
                        case_run_evals.append(case_eval)
                        evaluated_runs.append(case_eval)

                # Format detailed log entry for the case
                if case_run_evals:
                    primary_eval = case_run_evals[0]
                    detailed_case_logs.append({
                        "case_id": case.id,
                        "category": case.category,
                        "query": case.query,
                        "expected_items": [
                            {"product_name": item.product_name, "quantity": item.quantity}
                            for item in case.expected_items
                        ],
                        "expect_refusal": case.expect_refusal,
                        "expect_unavailable": case.expect_unavailable,
                        "runs": [r.model_dump() for r in case_run_evals],
                        "raw_response": last_raw_resp.model_dump() if last_raw_resp else None,
                    })

                print(
                    f"\rProgress: [{i}/{total_cases}] cases processed "
                    f"({total_calls_executed}/{estimated_calls} calls)",
                    end="",
                    flush=True,
                )

            total_duration = time.time() - start_time_all
            print(f"\nCompleted {total_calls_executed} calls in {total_duration:.2f}s.\n")

            # Compute aggregate metrics across all runs
            agg = compute_aggregate_metrics(evaluated_runs)
            print(format_console_table(agg))

            # Prepare full JSON output
            results_dir = Path(args.out).parent if args.out else Path(__file__).parent / "results"
            results_dir.mkdir(parents=True, exist_ok=True)
            out_path = Path(args.out) if args.out else results_dir / f"{timestamp_str}-{provider_choice}.json"

            output_payload = {
                "metadata": {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "provider": provider_choice,
                    "model": getattr(ai_service.provider, "model", "mock-rule-engine"),
                    "git_commit": commit_hash,
                    "runs_per_case": runs,
                    "total_cases": total_cases,
                    "total_calls": total_calls_executed,
                    "duration_seconds": round(total_duration, 2),
                    "honesty_note": HONESTY_NOTE_MOCK if provider_choice == "mock" else None,
                },
                "aggregate": agg.model_dump(),
                "cases": detailed_case_logs,
            }

            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(output_payload, f, indent=2, default=str)

            print(f"\nSaved full evaluation results to: {out_path}\n")

            # Check CI exit condition
            if args.fail_on_hallucination and agg.hallucination_rate > 0.0:
                print(f"[FAIL] Hallucination detected (rate: {agg.hallucination_rate:.1%}) with --fail-on-hallucination enabled.")
                return 1

            return 0

        finally:
            ai_service.complete = original_complete
            await db.rollback()


def main():
    parser = argparse.ArgumentParser(description="Dukaanly AI Shopping Assistant Evaluation Runner")
    parser.add_argument("--provider", choices=["mock", "live"], default="mock", help="AI provider to evaluate")
    parser.add_argument("--runs", type=int, default=1, help="Runs per test case (default: 1 for mock, 3 for live)")
    parser.add_argument("--category", default="all", help="Specific category to run or 'all'")
    parser.add_argument("--limit", type=int, default=None, help="Maximum number of test cases to run")
    parser.add_argument("--max-calls", type=int, default=300, help="Hard ceiling on total LLM calls")
    parser.add_argument("--out", type=str, default=None, help="Output JSON filepath")
    parser.add_argument("--fail-on-hallucination", action="store_true", help="Exit non-zero if any hallucination is found")

    args = parser.parse_args()
    if args.provider == "live" and args.runs == 1:
        args.runs = 3

    exit_code = asyncio.run(main_async(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
