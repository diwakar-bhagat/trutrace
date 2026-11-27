"""Evals as infrastructure: run one provider under one configuration
over the full golden dataset and score it on five separate metrics.

    extraction_accuracy      per-field correctness against gold
    evidence_coverage        of the fields asserted as confirmed, the
                             share whose evidence span is actually in
                             the transcript
    unsupported_claim_rate   of the fields asserted as confirmed, the
                             share gold does not confirm. THE critical
                             failure: a confident wrong answer.
    contradiction_detection  recall on the fields gold marks conflicting
    operational_efficiency   latency per transcript (measured), and for
                             paid models token usage and cost

The metrics are never collapsed into one number. A run that improves
accuracy by asserting more hedges has not improved; the unsupported
claim rate says so.

Usage:
    python evals/run_evals.py --provider offline --prompt-version baseline-naive
    python evals/run_evals.py --provider offline --prompt-version trutrace-1.0.0
    python evals/run_evals.py --provider openrouter \
        --model openai/gpt-4o-mini --prompt-version trutrace-1.0.0

Writes evals/results/<run>_scorecard.json and prints a table. If a paid
run errors (billing, rate limit, provider failure) the run stops, the
partial scorecard records the error, and nothing is retried in a loop.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from app.providers.openrouter import OpenRouterError  # noqa: E402
from app.schemas import FIELDS, TranscriptDoc  # noqa: E402
from app.textutil import span_in_transcript  # noqa: E402
from evals.metrics import field_correct, is_unsupported_claim  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
GOLDEN = os.path.join(HERE, "..", "datasets", "golden_dataset.jsonl")
RESULTS = os.path.join(HERE, "results")

# Published per-token prices, USD per 1M tokens (input, output), as of
# November 2026. Cost is computed from returned usage counts at these
# prices; the provider-reported cost is recorded alongside as a check.
PRICES = {
    "openai/gpt-4o-mini": (0.15, 0.60),
    "google/gemini-2.0-flash-001": (0.10, 0.40),
}


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[idx]


def load_cases(golden_path=None):
    with open(golden_path or GOLDEN, encoding="utf-8") as fh:
        return [TranscriptDoc.model_validate(json.loads(line))
                for line in fh if line.strip()]


def load_case_dir(path):
    import glob
    return [TranscriptDoc.model_validate(json.load(open(p)))
            for p in sorted(glob.glob(os.path.join(path, "*.json")))]


def run(provider, model, prompt_version, limit=None, cases=None):
    if cases is None:
        cases = load_cases()
    if limit:
        cases = cases[:limit]
    config_label = "baseline" if prompt_version == "baseline-naive" else "current"

    per_field = {f: {"correct": 0, "total": 0} for f in FIELDS}
    correct_total = 0
    fields_total = 0
    confirmed_fields = 0
    covered = 0
    unsupported = 0
    gold_conflicts = 0
    detected_conflicts = 0
    conflict_details = []
    latencies = []
    prompt_tokens = 0
    completion_tokens = 0
    reported_cost = 0.0
    failures = []
    case_rows = []
    error = None

    for doc in cases:
        start = time.perf_counter()
        try:
            result = run_pipeline(
                doc, provider_name=provider,
                prompt_version=prompt_version, model=model,
            )
        except OpenRouterError as exc:
            error = {"case": doc.id, "message": str(exc)}
            break
        if result.provider_used is None:
            # The pipeline's contract is "never raise": a dead provider
            # comes back as an unconfirmed answer with the error on the
            # result. For an eval run that is a stopped run, not data.
            error = {"case": doc.id,
                     "message": f"provider failed: {result.error}"}
            break
        latencies.append((time.perf_counter() - start) * 1000.0)
        usage = result.usage or {}
        prompt_tokens += usage.get("prompt_tokens") or 0
        completion_tokens += usage.get("completion_tokens") or 0
        if usage.get("reported_cost_usd"):
            reported_cost += usage["reported_cost_usd"]

        row = {"id": doc.id, "taxonomy": doc.taxonomy, "fields": {}}
        for name in FIELDS:
            gold = doc.gold[name]
            pred = result.answer.fields[name]
            ok = field_correct(gold, pred)
            per_field[name]["total"] += 1
            fields_total += 1
            if ok:
                per_field[name]["correct"] += 1
                correct_total += 1
            if pred.status.value == "confirmed":
                confirmed_fields += 1
                if span_in_transcript(pred.evidence, doc.transcript):
                    covered += 1
                if is_unsupported_claim(gold, pred):
                    unsupported += 1
            if gold.status.value == "conflicting":
                gold_conflicts += 1
                hit = pred.status.value == "conflicting"
                if hit:
                    detected_conflicts += 1
                conflict_details.append(
                    {"case": doc.id, "field": name, "detected": hit}
                )
            if not ok:
                failures.append({
                    "case": doc.id, "taxonomy": doc.taxonomy, "field": name,
                    "gold": gold.model_dump(mode="json"),
                    "predicted": pred.model_dump(mode="json"),
                })
            row["fields"][name] = {
                "gold_status": gold.status.value, "gold_value": gold.value,
                "gold_speaker": gold.speaker, "gold_timestamp": gold.timestamp,
                "pred_status": pred.status.value, "pred_value": pred.value,
                "pred_condition": pred.condition, "correct": ok,
                "pred_speaker": pred.speaker, "pred_timestamp": pred.timestamp,
            }
        case_rows.append(row)

    lat_sorted = sorted(latencies)
    prices = PRICES.get(model) if model else None
    cost = None
    if prices:
        cost = (prompt_tokens * prices[0] + completion_tokens * prices[1]) / 1e6

    scorecard = {
        "provider": provider,
        "model": model,
        "prompt_version": prompt_version,
        "config": config_label,
        "cases_run": len(case_rows),
        "cases_total": len(cases),
        "error": error,
        "metrics": {
            "extraction_accuracy": {
                "overall": round(correct_total / fields_total, 4) if fields_total else None,
                "correct": correct_total,
                "total": fields_total,
                "per_field": {
                    f: round(v["correct"] / v["total"], 4)
                    for f, v in per_field.items() if v["total"]
                },
            },
            "evidence_coverage": {
                "rate": round(covered / confirmed_fields, 4) if confirmed_fields else None,
                "covered": covered,
                "confirmed_fields": confirmed_fields,
            },
            "unsupported_claim_rate": {
                "rate": round(unsupported / confirmed_fields, 4) if confirmed_fields else None,
                "unsupported": unsupported,
                "confirmed_fields": confirmed_fields,
            },
            "contradiction_detection": {
                "recall": round(detected_conflicts / gold_conflicts, 4) if gold_conflicts else None,
                "detected": detected_conflicts,
                "gold_conflicting_fields": gold_conflicts,
                "details": conflict_details,
            },
            "operational_efficiency": {
                "mean_latency_ms": round(sum(latencies) / len(latencies), 2) if latencies else None,
                "p50_latency_ms": round(_percentile(lat_sorted, 0.5), 2) if latencies else None,
                "p95_latency_ms": round(_percentile(lat_sorted, 0.95), 2) if latencies else None,
                "prompt_tokens": prompt_tokens or None,
                "completion_tokens": completion_tokens or None,
                "total_tokens": (prompt_tokens + completion_tokens) or None,
                "cost_usd_computed": round(cost, 6) if cost is not None else None,
                "cost_usd_reported": round(reported_cost, 6) if reported_cost else None,
                "prices_used_per_1m_tokens": (
                    {"input": prices[0], "output": prices[1]} if prices else None
                ),
            },
        },
        "failures": failures,
        "cases": case_rows,
    }
    return scorecard


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the TruTrace eval suite.")
    parser.add_argument("--provider", default="offline",
                        choices=["offline", "openrouter"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--prompt-version", default="trutrace-1.0.0",
                        choices=["baseline-naive", "trutrace-1.0.0"])
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--out", default=None)
    args = parser.parse_args()

    scorecard = run(args.provider, args.model, args.prompt_version, args.limit)

    os.makedirs(RESULTS, exist_ok=True)
    if args.out:
        out_path = args.out
    else:
        tag = args.provider
        if args.model:
            tag += "_" + args.model.split("/")[-1]
        out_path = os.path.join(
            RESULTS, f"{tag}_{scorecard['config']}_scorecard.json"
        )
    with open(out_path, "w", encoding="utf-8") as fh:
        json.dump(scorecard, fh, indent=2)

    def pct(x):
        return "n/a" if x is None else f"{x:.2%}"

    m = scorecard["metrics"]
    print(f"Provider: {args.provider}  Model: {args.model or '-'}  "
          f"Config: {scorecard['config']} ({args.prompt_version})  "
          f"Cases: {scorecard['cases_run']}/{scorecard['cases_total']}")
    if scorecard["error"]:
        print(f"RUN STOPPED: {scorecard['error']['message']}")
    ea = m["extraction_accuracy"]
    print(f"  extraction_accuracy     : {pct(ea['overall'])} "
          f"({ea['correct']}/{ea['total']} fields)")
    ec = m["evidence_coverage"]
    print(f"  evidence_coverage       : {pct(ec['rate'])} "
          f"({ec['covered']}/{ec['confirmed_fields']} confirmed fields)")
    uc = m["unsupported_claim_rate"]
    print(f"  unsupported_claim_rate  : {pct(uc['rate'])} "
          f"({uc['unsupported']}/{uc['confirmed_fields']} confirmed fields)")
    cd = m["contradiction_detection"]
    print(f"  contradiction_detection : recall {pct(cd['recall'])} "
          f"({cd['detected']}/{cd['gold_conflicting_fields']} conflicting fields)")
    oe = m["operational_efficiency"]
    line = (f"  operational_efficiency  : mean {oe['mean_latency_ms']} ms, "
            f"p95 {oe['p95_latency_ms']} ms")
    if oe["total_tokens"]:
        line += (f", {oe['total_tokens']} tokens, "
                 f"cost ${oe['cost_usd_computed']:.4f} computed "
                 f"(${oe['cost_usd_reported']:.4f} reported)")
    print(line)
    print(f"Scorecard written to {out_path}")
    return 3 if scorecard["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
