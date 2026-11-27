"""Load runs over the campaign pipeline.

Three sizes, two kinds of run, labelled as what they are:

- n=10 and n=100: REAL sequential calls through the OpenRouter helper
  against the live provider (gpt-4o-mini), current configuration.
  Throughput, error rate, latency and cost are measured from the run.
- n=1000: SIMULATED. The real pipeline code runs in-process against
  the deterministic offline provider; no network calls are made. What
  is mocked is provider behaviour: per-call latency is the rule
  engine's in-process time, not a live model's.

Results are written to evals/results/load_<n>_<provider>.json. Only
measured numbers are recorded; a run that errors records the error.

Run: python scripts/load_test.py --n 10|100|1000
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from evals.run_evals import PRICES, load_case_dir  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT_DIR = os.path.join(ROOT, "evals", "results")


def percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    return sorted_vals[min(len(sorted_vals) - 1, int(q * len(sorted_vals)))]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--n", type=int, required=True)
    parser.add_argument("--provider", default=None,
                        help="default: openrouter for n<=100, offline for n=1000")
    parser.add_argument("--model", default="openai/gpt-4o-mini")
    args = parser.parse_args()

    provider = args.provider or ("offline" if args.n > 100 else "openrouter")
    simulated = provider == "offline"
    docs = load_case_dir(os.path.join(ROOT, "datasets", "campaign"))
    batch = [docs[i % len(docs)] for i in range(args.n)]

    latencies = []
    errors = 0
    prompt_tokens = 0
    completion_tokens = 0
    reported_cost = 0.0
    start = time.perf_counter()
    for doc in batch:
        t0 = time.perf_counter()
        result = run_pipeline(
            doc, provider_name=provider,
            prompt_version="trutrace-1.0.0",
            model=args.model if provider == "openrouter" else None,
        )
        latencies.append((time.perf_counter() - t0) * 1000.0)
        if result.provider_used is None:
            errors += 1
        usage = result.usage or {}
        prompt_tokens += usage.get("prompt_tokens") or 0
        completion_tokens += usage.get("completion_tokens") or 0
        reported_cost += usage.get("reported_cost_usd") or 0.0
    wall_s = time.perf_counter() - start

    prices = PRICES.get(args.model) if provider == "openrouter" else None
    computed_cost = None
    if prices:
        computed_cost = (prompt_tokens * prices[0]
                         + completion_tokens * prices[1]) / 1e6
    lat_sorted = sorted(latencies)
    record = {
        "n": args.n,
        "provider": provider,
        "model": args.model if provider == "openrouter" else None,
        "configuration": "trutrace-1.0.0",
        "mode": "simulated" if simulated else "real",
        "mocked": (
            "Provider behaviour: the deterministic offline rule "
            "provider ran in-process; no network calls were made and "
            "per-call latency is rule-engine time, not a live model's."
            if simulated else None
        ),
        "wall_time_s": round(wall_s, 2),
        "throughput_transcripts_per_s": round(args.n / wall_s, 3) if wall_s else None,
        "errors": errors,
        "error_rate": round(errors / args.n, 4) if args.n else None,
        "latency_ms": {
            "mean": round(sum(latencies) / len(latencies), 2) if latencies else None,
            "p50": round(percentile(lat_sorted, 0.5), 2) if latencies else None,
            "p95": round(percentile(lat_sorted, 0.95), 2) if latencies else None,
        },
        "total_tokens": (prompt_tokens + completion_tokens) or None,
        "cost_usd_computed": round(computed_cost, 6) if computed_cost is not None else None,
        "cost_usd_reported": round(reported_cost, 6) if reported_cost else None,
        "cost_per_transcript_usd": (
            round(computed_cost / args.n, 6)
            if computed_cost is not None else None
        ),
    }
    out = os.path.join(OUT_DIR, f"load_{args.n}_{provider}.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    print(json.dumps(record, indent=1))
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
