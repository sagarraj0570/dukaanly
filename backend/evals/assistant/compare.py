"""
Evaluation Comparison Utility for Dukaanly AI Shopping Assistant.

Compares two evaluation result JSON files (e.g. baseline vs candidate, or mock vs live),
computes overall and per-category metric deltas, and flags case-level regressions.

Usage:
    python -m evals.assistant.compare path/to/baseline.json path/to/candidate.json
"""

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Dict, List, Set, Tuple


def load_result_file(path: Path) -> Dict[str, Any]:
    if not path.exists():
        print(f"Error: Result file not found: {path}", file=sys.stderr)
        sys.exit(1)
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def format_delta(v1: float, v2: float, is_pct: bool = False, higher_is_better: bool = True) -> str:
    diff = v2 - v1
    if abs(diff) < 1e-4:
        return " 0.00" if not is_pct else "  0.0%"
    sign = "+" if diff > 0 else ""
    val_str = f"{sign}{diff:.2f}" if not is_pct else f"{sign}{diff*100:.1f}%"
    return f"{val_str:>7}"


def compare_evaluations(path1: Path, path2: Path) -> int:
    data1 = load_result_file(path1)
    data2 = load_result_file(path2)

    meta1 = data1.get("metadata", {})
    meta2 = data2.get("metadata", {})
    agg1 = data1.get("aggregate", {})
    agg2 = data2.get("aggregate", {})

    print("\n" + "=" * 80)
    print(" Dukaanly Assistant Evaluation Comparison")
    print(f" Baseline (A) : {path1.name} [{meta1.get('provider')} / {meta1.get('model')} / {meta1.get('git_commit', 'unknown')}]")
    print(f" Candidate (B): {path2.name} [{meta2.get('provider')} / {meta2.get('model')} / {meta2.get('git_commit', 'unknown')}]")
    print("=" * 80)

    # 1. Overall Summary Comparison
    print("\n--- OVERALL METRICS ---")
    metrics_spec = [
        ("Item Precision", "item_precision_mean", False, True),
        ("Item Recall", "item_recall_mean", False, True),
        ("Item F1", "item_f1_mean", False, True),
        ("Quantity Accuracy", "quantity_accuracy_mean", False, True),
        ("Exact Match Rate", "exact_match_rate", True, True),
        ("Hallucination Rate", "hallucination_rate", True, False),
        ("Forbidden Hit Rate", "forbidden_hit_rate", True, False),
        ("Budget OK Rate", "budget_ok_rate", True, True),
        ("Unavailable Handled", "unavailable_handled_rate", True, True),
        ("Refusal Precision", "refusal_precision", False, True),
        ("Refusal Recall", "refusal_recall", False, True),
        ("Latency p50 (ms)", "latency_p50_ms", False, False),
        ("Latency p95 (ms)", "latency_p95_ms", False, False),
    ]

    header_ov = f"{'Metric':<25} | {'Baseline (A)':>14} | {'Candidate (B)':>14} | {'Delta (B - A)':>14}"
    div_ov = "-" * len(header_ov)
    print(div_ov)
    print(header_ov)
    print(div_ov)

    for label, key, is_pct, hib in metrics_spec:
        v1 = float(agg1.get(key, 0.0))
        v2 = float(agg2.get(key, 0.0))
        v1_str = f"{v1:.2%}" if is_pct else f"{v1:.2f}"
        v2_str = f"{v2:.2%}" if is_pct else f"{v2:.2f}"
        delta_str = format_delta(v1, v2, is_pct=is_pct, higher_is_better=hib)
        print(f"{label:<25} | {v1_str:>14} | {v2_str:>14} | {delta_str:>14}")

    print(div_ov)

    # 2. Per-Category Breakdown Comparison
    cats1 = agg1.get("category_breakdown", {})
    cats2 = agg2.get("category_breakdown", {})
    all_cats = sorted(set(cats1.keys()).union(set(cats2.keys())))

    print("\n--- PER-CATEGORY DELTAS (F1 / Exact Match / Hallucination) ---")
    cat_header = f"{'Category':<22} | {'F1 (A -> B)':>18} | {'Exact (A -> B)':>18} | {'Halluc (A -> B)':>18}"
    cat_div = "-" * len(cat_header)
    print(cat_div)
    print(cat_header)
    print(cat_div)

    for cat in all_cats:
        c1 = cats1.get(cat, {})
        c2 = cats2.get(cat, {})
        f1_1, f1_2 = c1.get("item_f1", 0.0), c2.get("item_f1", 0.0)
        ex1, ex2 = c1.get("exact_match_rate", 0.0), c2.get("exact_match_rate", 0.0)
        hal1, hal2 = c1.get("hallucination_rate", 0.0), c2.get("hallucination_rate", 0.0)

        f1_col = f"{f1_1:.2f} -> {f1_2:.2f} ({f1_2 - f1_1:+.2f})"
        ex_col = f"{ex1:.0%} -> {ex2:.0%} ({(ex2 - ex1)*100:+.0f}%)"
        hal_col = f"{hal1:.0%} -> {hal2:.0%} ({(hal2 - hal1)*100:+.0f}%)"
        print(f"{cat:<22} | {f1_col:>18} | {ex_col:>18} | {hal_col:>18}")

    print(cat_div)

    # 3. Case-level Changes and Regressions
    cases1_map = {c["case_id"]: c for c in data1.get("cases", [])}
    cases2_map = {c["case_id"]: c for c in data2.get("cases", [])}
    common_case_ids = [cid for cid in cases1_map if cid in cases2_map]

    regressions: List[Dict[str, Any]] = []
    improvements: List[Dict[str, Any]] = []

    for cid in common_case_ids:
        c1 = cases1_map[cid]
        c2 = cases2_map[cid]

        # Use primary run (index 0)
        r1 = c1.get("runs", [{}])[0]
        r2 = c2.get("runs", [{}])[0]

        reasons_regressed: List[str] = []
        reasons_improved: List[str] = []

        # Hallucination
        h1 = r1.get("hallucination", False)
        h2 = r2.get("hallucination", False)
        if not h1 and h2:
            reasons_regressed.append(f"New Hallucination ({r2.get('hallucination_reason', 'unknown')})")
        elif h1 and not h2:
            reasons_improved.append("Resolved Hallucination")

        # Exact match
        ex1 = r1.get("exact_match", False)
        ex2 = r2.get("exact_match", False)
        if ex1 and not ex2:
            reasons_regressed.append("Lost Exact Match")
        elif not ex1 and ex2:
            reasons_improved.append("Gained Exact Match")

        # F1 Score
        f1_1 = r1.get("item_f1", 0.0)
        f1_2 = r2.get("item_f1", 0.0)
        if f1_2 < f1_1 - 0.01:
            reasons_regressed.append(f"F1 dropped ({f1_1:.2f} -> {f1_2:.2f})")
        elif f1_2 > f1_1 + 0.01:
            reasons_improved.append(f"F1 improved ({f1_1:.2f} -> {f1_2:.2f})")

        if reasons_regressed:
            regressions.append({
                "id": cid,
                "category": c1.get("category"),
                "query": c1.get("query"),
                "reasons": reasons_regressed,
            })
        if reasons_improved:
            improvements.append({
                "id": cid,
                "category": c1.get("category"),
                "query": c1.get("query"),
                "reasons": reasons_improved,
            })

    print(f"\n--- CASE-LEVEL DELTAS ({len(common_case_ids)} common cases) ---")
    print(f"Improved Cases  : {len(improvements)}")
    print(f"Regressed Cases : {len(regressions)}")

    if regressions:
        print("\n[!] REGRESSIONS FLAGGED:")
        for reg in regressions:
            reasons_txt = ", ".join(reg["reasons"])
            print(f"  - [{reg['id']}] ({reg['category']}) \"{reg['query']}\": {reasons_txt}")

    if improvements:
        print("\n[*] IMPROVEMENTS NOTED:")
        for imp in improvements[:10]:
            reasons_txt = ", ".join(imp["reasons"])
            print(f"  + [{imp['id']}] ({imp['category']}) \"{imp['query']}\": {reasons_txt}")
        if len(improvements) > 10:
            print(f"  ... and {len(improvements) - 10} more improvements.")

    print("\n" + "=" * 80 + "\n")
    return 1 if regressions else 0


def main():
    parser = argparse.ArgumentParser(description="Compare two Dukaanly Assistant evaluation runs")
    parser.add_argument("baseline", type=Path, help="Path to baseline evaluation JSON")
    parser.add_argument("candidate", type=Path, help="Path to candidate evaluation JSON")

    args = parser.parse_args()
    exit_code = compare_evaluations(args.baseline, args.candidate)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
