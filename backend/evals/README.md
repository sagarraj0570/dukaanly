# Dukaanly AI Shopping Assistant Evaluation Harness

An offline, reproducible evaluation framework for measuring shopping assistant accuracy, hallucination rates, quantity compliance, and out-of-scope refusals across grounded Hindi, Hinglish, and English grocery queries.

---

## 1. Quickstart

### Run Mock Evaluation (Fast, Offline, Deterministic)
Runs all 80 evaluation cases against the deterministic rule-based mock provider and PostgreSQL catalog:
```bash
python -m evals.assistant.run_eval --provider mock --out evals/assistant/results/baseline-mock.json
```

> [!IMPORTANT]
> **Honesty Note**: `MockLLMProvider` is a deterministic, rule-based mock. Mock evaluation results measure Dukaanly's **search, retrieval, and validation pipeline ONLY**, NOT live LLM reasoning, conversational subtlety, or model quality. Never present mock scores as AI model benchmark numbers.

### Run Live Evaluation (Requires API Key & Model Quota)
Runs each case 3 times to account for model output variability:
```bash
python -m evals.assistant.run_eval --provider live --runs 3 --max-calls 300 --out evals/assistant/results/live-eval.json
```

> [!WARNING]
> **Cost & Quota Warning**: Running 80 cases with `--runs 3` performs up to 240 LLM calls. Always check `--max-calls` (default 300) before starting. Never run live evaluations inside CI pipelines.

---

## 2. Generating Reports and Comparisons

### Generate Markdown Baseline Report
Produces `docs/evals/assistant_eval.md`:
```bash
python -m evals.assistant.report evals/assistant/results/baseline-mock.json --out ../docs/evals/assistant_eval.md
```

### Compare Two Evaluation Runs
Compares two result files, computes metric deltas, and flags regressions:
```bash
python -m evals.assistant.compare evals/assistant/results/baseline-mock.json evals/assistant/results/candidate-run.json
```

---

## 3. Reviewing Ground-Truth Labels (`REVIEW.csv`)

All 80 baseline cases were curated to match seeded demo catalog items and are initially flagged as:
```csv
reviewed: false
```
in `backend/evals/assistant/REVIEW.csv`.

To verify labels:
1. Open `backend/evals/assistant/REVIEW.csv`.
2. Inspect `query`, `target_shop_id`, and `expected_items_summary`.
3. Set `reviewed` to `true` after verifying that the expected items and quantities reflect accurate customer intent.

---

## 4. Adding New Test Cases

Append new cases to `backend/evals/assistant/cases.jsonl`:
```json
{
  "id": "hinglish-016",
  "category": "hinglish_basic",
  "query": "1kg aashirvaad atta chahiye",
  "shop_ref": "demo:shop:patna-super-kirana",
  "expected_items": [
    {"product_ref": "Aashirvaad Superior MP Shudh Chakki Atta 5kg", "quantity": 1}
  ],
  "forbidden_items": [],
  "max_total": null,
  "expect_unavailable": [],
  "expect_refusal": false,
  "reviewed": false,
  "notes": "Variant fallback test"
}
```

Rules for new cases:
- `shop_ref` must match a seeded demo shop (`demo:shop:patna-super-kirana`, `demo:shop:patna-city-medicos`, or `demo:shop:pataliputra-bakery`).
- `product_ref` must match an active product `name` in that shop.
- Category must be one of the 9 validated categories.

---

## 5. Automated CI Checks

To verify zero hallucinations on the pipeline during automated CI:
```bash
python -m evals.assistant.run_eval --provider mock --fail-on-hallucination
```
Exits with code `1` if any proposed product ID does not exist in the database, belongs to the wrong shop, or has an altered price.
