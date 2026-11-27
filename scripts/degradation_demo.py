"""Degradation demo: kill a provider mid run and watch the batch.

Scenario A: six campaign calls. The primary provider is a real
gpt-4o-mini wrapped in a KillAfterProvider set to die after 3 calls.
The remaining calls fall back to the offline provider. The batch
completes: partial results preserved, nothing invented.

Scenario B: primary and fallback both dead from the start. Every call
comes back with all fields unconfirmed and the failure recorded. No
exception escapes, no answer is fabricated.

The provider deaths are simulated by the killswitch wrappers in
app/providers/killswitch.py (the same stubs the automated tests in
tests/test_degradation.py use). The fallback and unconfirmed paths are
the pipeline's own code path. Output is recorded to
reports/degradation_record.json.

Run: python scripts/degradation_demo.py [--offline-primary]
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_batch  # noqa: E402
from app.providers.killswitch import DeadProvider, KillAfterProvider  # noqa: E402
from app.providers.offline import OfflineProvider  # noqa: E402
from app.providers.openrouter import OpenRouterProvider  # noqa: E402
from evals.run_evals import load_case_dir  # noqa: E402

ROOT = os.path.join(os.path.dirname(__file__), "..")
OUT = os.path.join(ROOT, "reports", "degradation_record.json")


def describe(results, summary):
    rows = []
    for r in results:
        rows.append({
            "provider_used": r.provider_used,
            "fallback_used": r.fallback_used,
            "confirmed_fields": len(r.answer.confirmed_values()),
            "error": r.error,
        })
    return {"summary": summary, "per_transcript": rows}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--offline-primary", action="store_true",
                        help="use the offline provider as primary "
                             "(for keyless runs); the recorded run "
                             "used gpt-4o-mini")
    args = parser.parse_args()

    docs = load_case_dir(os.path.join(ROOT, "datasets", "campaign"))[:6]

    if args.offline_primary:
        primary = KillAfterProvider(OfflineProvider(), kill_after=3)
        primary_desc = "offline provider wrapped in KillAfterProvider(3)"
    else:
        primary = KillAfterProvider(
            OpenRouterProvider("openai/gpt-4o-mini"), kill_after=3)
        primary_desc = "gpt-4o-mini via OpenRouter, wrapped in KillAfterProvider(3)"
    results_a, summary_a = run_batch(
        docs, primary, prompt_version="trutrace-1.0.0",
        fallback_provider=OfflineProvider(),
        provider_label="primary", fallback_label="offline-fallback",
    )
    scenario_a = describe(results_a, summary_a)
    scenario_a["setup"] = (
        f"primary: {primary_desc}; fallback: offline provider; "
        "6 campaign transcripts, current configuration"
    )

    results_b, summary_b = run_batch(
        docs, DeadProvider("primary down (simulated)"),
        prompt_version="trutrace-1.0.0",
        fallback_provider=DeadProvider("fallback down (simulated)"),
        provider_label="primary", fallback_label="offline-fallback",
    )
    scenario_b = describe(results_b, summary_b)
    scenario_b["setup"] = (
        "primary: DeadProvider; fallback: DeadProvider; "
        "6 campaign transcripts, current configuration"
    )

    record = {
        "note": (
            "Provider deaths are simulated by the killswitch wrappers; "
            "the fallback and unconfirmed behaviour is the pipeline's own "
            "pipeline code path (app/pipeline.py run_batch). The same "
            "scenarios are covered by automated tests in "
            "tests/test_degradation.py."
        ),
        "scenario_a_killed_mid_run": scenario_a,
        "scenario_b_all_providers_down": scenario_b,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=1)
    print(json.dumps({"scenario_a": summary_a, "scenario_b": summary_b},
                     indent=1))
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
