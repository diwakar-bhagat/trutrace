"""Final evaluation runs, per the frozen protocol in datasets/SPLIT.md.

Each configuration (provider x baseline/current) is run N times over
the eval set; the summary reports every metric as counts with
denominators per run plus the spread across runs. Nothing is tuned
here: this script only measures.

Usage:
  python -m evals.run_final --set heldout --runs 3
  python -m evals.run_final --set campaign --runs 3
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from evals.run_evals import load_case_dir, load_cases, run as eval_run  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
RESULTS = os.path.join(HERE, "results")
ROOT = os.path.join(HERE, "..")

CONFIGS = ["baseline-naive", "trutrace-1.0.0"]
PROVIDERS = [
    ("offline", None, "offline"),
    ("openrouter", "openai/gpt-4o-mini", "gpt-4o-mini"),
]


def cases_for(set_name):
    if set_name == "heldout":
        with open(os.path.join(ROOT, "datasets", "split.json")) as fh:
            ids = set(json.load(fh)["heldout"])
        return [c for c in load_cases() if c.id in ids]
    if set_name == "campaign":
        return load_case_dir(os.path.join(ROOT, "datasets", "campaign"))
    raise ValueError(set_name)


def proof_stats(scorecard):
    """Speaker/timestamp proof accuracy over the scorecard's rows:
    for gold-confirmed fields that carry gold proof, did the predicted
    field's derived proof match?"""
    total = 0
    matched = 0
    for row in scorecard["cases"]:
        for f in row["fields"].values():
            if f["gold_status"] == "confirmed" and f["gold_timestamp"]:
                total += 1
                if (f["pred_speaker"] == f["gold_speaker"]
                        and f["pred_timestamp"] == f["gold_timestamp"]):
                    matched += 1
    return {"matched": matched, "total": total}


def spread(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return {"mean": None, "min": None, "max": None}
    return {
        "mean": round(sum(vals) / len(vals), 4),
        "min": min(vals),
        "max": max(vals),
    }


def aggregate(set_name, tag, config_label, runs):
    m = [r["metrics"] for r in runs]
    agg = {
        "set": set_name,
        "provider_tag": tag,
        "config": config_label,
        "runs": len(runs),
        "cases_per_run": runs[0]["cases_total"] if runs else 0,
        "errors": [r["error"] for r in runs if r.get("error")],
        "extraction_accuracy": {
            "per_run": [
                f"{x['extraction_accuracy']['correct']} of "
                f"{x['extraction_accuracy']['total']}"
                for x in m
            ],
            "rate": spread([x["extraction_accuracy"]["overall"] for x in m]),
        },
        "evidence_coverage": {
            "per_run": [
                f"{x['evidence_coverage']['covered']} of "
                f"{x['evidence_coverage']['confirmed_fields']}"
                for x in m
            ],
            "rate": spread([x["evidence_coverage"]["rate"] for x in m]),
        },
        "unsupported_claim_rate": {
            "per_run": [
                f"{x['unsupported_claim_rate']['unsupported']} of "
                f"{x['unsupported_claim_rate']['confirmed_fields']}"
                for x in m
            ],
            "rate": spread([x["unsupported_claim_rate"]["rate"] for x in m]),
        },
        "contradiction_detection": {
            "per_run": [
                f"{x['contradiction_detection']['detected']} of "
                f"{x['contradiction_detection']['gold_conflicting_fields']}"
                for x in m
            ],
            "recall": spread([x["contradiction_detection"]["recall"] for x in m]),
        },
        "operational_efficiency": {
            "mean_latency_ms": spread(
                [x["operational_efficiency"]["mean_latency_ms"] for x in m]),
            "p50_latency_ms": spread(
                [x["operational_efficiency"]["p50_latency_ms"] for x in m]),
            "p95_latency_ms": spread(
                [x["operational_efficiency"]["p95_latency_ms"] for x in m]),
            "cost_usd_per_run": [
                x["operational_efficiency"]["cost_usd_computed"] for x in m
            ],
            "total_tokens_per_run": [
                x["operational_efficiency"]["total_tokens"] for x in m
            ],
        },
        "proof_accuracy": proof_stats(runs[0]) if runs else None,
    }
    return agg


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", required=True, choices=["heldout", "campaign"])
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--providers", default="offline,gpt-4o-mini",
                        help="comma list of provider tags to run")
    args = parser.parse_args()

    cases = cases_for(args.set)
    print(f"{args.set}: {len(cases)} cases x {args.runs} runs")
    summary = {"set": args.set, "runs_per_config": args.runs, "cells": []}
    for provider_name, model, tag in PROVIDERS:
        if tag not in args.providers.split(","):
            continue
        for version in CONFIGS:
            label = "baseline" if version == "baseline-naive" else "current"
            runs = []
            for i in range(1, args.runs + 1):
                sc = eval_run(provider_name, model, version, cases=cases)
                path = os.path.join(
                    RESULTS,
                    f"final_{args.set}_{tag}_{label}_run{i}.json",
                )
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(sc, fh, indent=1)
                runs.append(sc)
                ea = sc["metrics"]["extraction_accuracy"]
                uc = sc["metrics"]["unsupported_claim_rate"]
                print(f"  {tag} {label} run{i}: "
                      f"accuracy {ea['correct']}/{ea['total']}, "
                      f"unsupported {uc['unsupported']}/{uc['confirmed_fields']}"
                      + (f", ERROR {sc['error']['message']}" if sc["error"] else ""))
            summary["cells"].append(aggregate(args.set, tag, label, runs))
    out = os.path.join(RESULTS, f"final_{args.set}_summary.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, indent=1)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
