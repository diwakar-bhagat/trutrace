"""The Experiment Runner.

Runs one prompt version (a Prompt Lab file) with one provider/model
against one dataset split, through the EXISTING pipeline and
verification engine, and persists everything under runs/<run_id>/:

  run.json     the run: prompt snapshot (text, params, profile,
               fingerprint), provider, model, dataset split and case
               ids, the five metrics with counts, cost, and the
               label status that must travel with every score.
  cases.jsonl  one trace record per case, in a Langfuse-shaped
               model: trace id, prompt version, model, input,
               output, per-field evaluations, latency, token usage,
               cost. Langfuse itself is NOT connected (no account, no
               keys); these local records are the trace, and the run
               says so.

Scoring reuses the eval suite's primitives (evals.metrics
field_correct / is_unsupported_claim, app.textutil
span_in_transcript, evals.run_evals PRICES for cost), so there is one
source of truth for correctness. A provider failure stops the run,
the partial record is persisted with the error on it, and nothing is
retried in a loop: the same contract as evals/run_evals.py.

Usage:
  python -m workbench.runner --prompt trutrace@1.0.0 \
      --provider offline --split campaign
  python -m workbench.runner --prompt baseline-naive@1.1.0 \
      --provider openrouter --model openai/gpt-4o-mini --split campaign
"""

import argparse
import json
import os
import time
import uuid
from datetime import datetime, timezone

from app.pipeline import run_pipeline
from app.providers.offline import OfflineProvider
from app.providers.openrouter import OpenRouterProvider
from app.schemas import FIELDS
from app.textutil import span_in_transcript
from evals.metrics import field_correct, is_unsupported_claim
from evals.run_evals import PRICES

from . import prompt_store
from .datasets import LABELS_STATUS, load_split

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RUNS_DIR = os.path.join(ROOT, "runs")

LANGFUSE_STATUS = {
    "connected": False,
    "status": "not connected",
    "note": (
        "No Langfuse account or keys are configured. Traces are local "
        "records in cases.jsonl, modelled on Langfuse's trace shape "
        "(trace id, prompt version, model, input, output, latency, "
        "token usage, evaluation outcomes)."
    ),
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _percentile(sorted_vals, q):
    if not sorted_vals:
        return None
    idx = min(len(sorted_vals) - 1, int(q * len(sorted_vals)))
    return sorted_vals[idx]


def _slug(text: str) -> str:
    return (
        text.replace("@", "-").replace("/", "-").replace(" ", "-")
    )


def _make_provider(provider_name: str, model, temperature: float):
    if provider_name == "offline":
        return OfflineProvider()
    if provider_name == "openrouter":
        if not model:
            raise ValueError("the openrouter provider needs a model")
        return OpenRouterProvider(model, temperature=temperature)
    raise ValueError(f"unknown provider {provider_name!r}")


def run_experiment(
    prompt_key: str,
    provider_name: str = "offline",
    model: str = None,
    split: str = "campaign",
) -> dict:
    """Execute one experiment and persist it. Returns the run record."""
    prompt_store.load_all()
    record = prompt_store.get_prompt(prompt_key)
    temperature = float(record.get("params", {}).get("temperature", 0))
    provider = _make_provider(provider_name, model, temperature)
    cases = load_split(split)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_tag = _slug(model) if model else "offline"
    run_id = f"{stamp}_{_slug(prompt_key)}_{model_tag}_{split}"
    run_dir = os.path.join(RUNS_DIR, run_id)
    os.makedirs(run_dir, exist_ok=True)

    per_field = {f: {"correct": 0, "total": 0} for f in FIELDS}
    correct_total = 0
    fields_total = 0
    confirmed_fields = 0
    covered = 0
    unsupported = 0
    gold_conflicts = 0
    detected_conflicts = 0
    latencies = []
    prompt_tokens = 0
    completion_tokens = 0
    reported_cost = 0.0
    failures = []
    traces = []
    error = None

    for doc in cases:
        start = time.perf_counter()
        result = run_pipeline(
            doc, provider=provider, prompt_version=prompt_key
        )
        wall_ms = (time.perf_counter() - start) * 1000.0
        if result.provider_used is None:
            error = {"case": doc.id, "message": f"provider failed: {result.error}"}
            traces.append({
                "trace_id": str(uuid.uuid4()),
                "run_id": run_id,
                "case_id": doc.id,
                "taxonomy": doc.taxonomy,
                "timestamp": _now(),
                "prompt_version": prompt_key,
                "provider": provider_name,
                "model": model,
                "status": "error",
                "error": error["message"],
                "latency_ms": round(wall_ms, 2),
                "usage": {},
                "input": {"question": doc.question, "transcript": doc.transcript},
                "output": None,
                "evaluations": None,
            })
            break
        latencies.append(wall_ms)
        usage = result.usage or {}
        prompt_tokens += usage.get("prompt_tokens") or 0
        completion_tokens += usage.get("completion_tokens") or 0
        if usage.get("reported_cost_usd"):
            reported_cost += usage["reported_cost_usd"]

        field_evals = {}
        case_correct = 0
        failed_fields = []
        for name in FIELDS:
            gold = doc.gold[name]
            pred = result.answer.fields[name]
            ok = field_correct(gold, pred)
            per_field[name]["total"] += 1
            fields_total += 1
            if ok:
                per_field[name]["correct"] += 1
                correct_total += 1
                case_correct += 1
            unsup = False
            grounded = None
            if pred.status.value == "confirmed":
                confirmed_fields += 1
                grounded = span_in_transcript(pred.evidence, doc.transcript)
                if grounded:
                    covered += 1
                unsup = is_unsupported_claim(gold, pred)
                if unsup:
                    unsupported += 1
            if gold.status.value == "conflicting":
                gold_conflicts += 1
                if pred.status.value == "conflicting":
                    detected_conflicts += 1
            if not ok:
                failed_fields.append(name)
                failures.append({
                    "case": doc.id, "taxonomy": doc.taxonomy, "field": name,
                })
            field_evals[name] = {
                "gold": gold.model_dump(mode="json"),
                "predicted": pred.model_dump(mode="json"),
                "correct": ok,
                "unsupported_claim": unsup,
                "evidence_grounded": grounded,
            }
        traces.append({
            "trace_id": str(uuid.uuid4()),
            "run_id": run_id,
            "case_id": doc.id,
            "taxonomy": doc.taxonomy,
            "timestamp": _now(),
            "prompt_version": prompt_key,
            "provider": provider_name,
            "model": model,
            "status": "ok",
            "error": None,
            "latency_ms": round(result.latency_ms, 2),
            "wall_latency_ms": round(wall_ms, 2),
            "usage": {
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "reported_cost_usd": usage.get("reported_cost_usd"),
            },
            "provider_used": result.provider_used,
            "fallback_used": result.fallback_used,
            "input": {"question": doc.question, "transcript": doc.transcript},
            "output": {
                "fields": {
                    name: f.model_dump(mode="json")
                    for name, f in result.answer.fields.items()
                }
            },
            "evaluations": {
                "fields": field_evals,
                "correct_fields": case_correct,
                "total_fields": len(FIELDS),
                "failed_fields": failed_fields,
            },
        })

    lat_sorted = sorted(latencies)
    prices = PRICES.get(model) if model else None
    cost = None
    if prices:
        cost = (prompt_tokens * prices[0] + completion_tokens * prices[1]) / 1e6

    run = {
        "run_id": run_id,
        "created_at": _now(),
        "prompt": {
            "key": record["key"],
            "name": record["name"],
            "version": record["version"],
            "parent": record.get("parent"),
            "verification": record["verification"],
            "params": record.get("params", {}),
            "system": record["system"],
            "user": record["user"],
            "fingerprint": prompt_store.prompt_fingerprint(record),
        },
        "provider": provider_name,
        "model": model,
        "dataset": {
            "split": split,
            "cases_total": len(cases),
            "case_ids": [c.id for c in cases],
        },
        "labels_status": LABELS_STATUS,
        "cases_run": len([t for t in traces if t["status"] == "ok"]),
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
        "langfuse": LANGFUSE_STATUS,
    }
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(run, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(run_dir, "cases.jsonl"), "w", encoding="utf-8") as fh:
        for trace in traces:
            fh.write(json.dumps(trace, ensure_ascii=False) + "\n")
    return run


# --------------------------------------------------------------------- read --

def list_runs() -> list:
    if not os.path.isdir(RUNS_DIR):
        return []
    runs = []
    for name in sorted(os.listdir(RUNS_DIR), reverse=True):
        path = os.path.join(RUNS_DIR, name, "run.json")
        if os.path.exists(path):
            with open(path, encoding="utf-8") as fh:
                runs.append(json.load(fh))
    return runs


def get_run(run_id: str) -> dict:
    path = os.path.join(RUNS_DIR, run_id, "run.json")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def get_case_trace(run_id: str, case_id: str) -> dict:
    path = os.path.join(RUNS_DIR, run_id, "cases.jsonl")
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            trace = json.loads(line)
            if trace["case_id"] == case_id:
                return trace
    raise KeyError(f"no case {case_id!r} in run {run_id!r}")


def list_case_summaries(run_id: str) -> list:
    path = os.path.join(RUNS_DIR, run_id, "cases.jsonl")
    out = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            t = json.loads(line)
            ev = t.get("evaluations") or {}
            out.append({
                "case_id": t["case_id"],
                "taxonomy": t["taxonomy"],
                "status": t["status"],
                "correct_fields": ev.get("correct_fields"),
                "total_fields": ev.get("total_fields"),
                "failed_fields": ev.get("failed_fields", []),
                "latency_ms": t.get("latency_ms"),
            })
    return out


def compare_runs(run_id_a: str, run_id_b: str) -> dict:
    """Side-by-side comparison of two runs. Honest only when the two
    runs cover identical inputs; the payload says whether they do."""
    a, b = get_run(run_id_a), get_run(run_id_b)
    complete = (
        a["cases_run"] == a["dataset"]["cases_total"] and not a.get("error")
        and b["cases_run"] == b["dataset"]["cases_total"] and not b.get("error")
    )
    same_inputs = (
        a["dataset"]["split"] == b["dataset"]["split"]
        and a["dataset"]["case_ids"] == b["dataset"]["case_ids"]
        and complete
    )
    per_case = []
    if same_inputs:
        traces_a = {t["case_id"]: t for t in _read_traces(run_id_a)}
        traces_b = {t["case_id"]: t for t in _read_traces(run_id_b)}
        for case_id in a["dataset"]["case_ids"]:
            ta, tb = traces_a.get(case_id), traces_b.get(case_id)
            if not ta or not tb or not ta.get("evaluations") or not tb.get("evaluations"):
                continue
            fields = {}
            for name in FIELDS:
                fa = ta["evaluations"]["fields"][name]
                fb = tb["evaluations"]["fields"][name]
                if fa["correct"] != fb["correct"]:
                    fields[name] = {
                        "a_correct": fa["correct"],
                        "b_correct": fb["correct"],
                    }
            per_case.append({
                "case_id": case_id,
                "a_correct_fields": ta["evaluations"]["correct_fields"],
                "b_correct_fields": tb["evaluations"]["correct_fields"],
                "changed_fields": fields,
            })
    return {
        "a": _run_summary(a),
        "b": _run_summary(b),
        "identical_inputs": same_inputs,
        "per_case": per_case,
        "labels_status": LABELS_STATUS,
    }


def _read_traces(run_id: str) -> list:
    path = os.path.join(RUNS_DIR, run_id, "cases.jsonl")
    with open(path, encoding="utf-8") as fh:
        return [json.loads(line) for line in fh if line.strip()]


def _run_summary(run: dict) -> dict:
    m = run["metrics"]
    return {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "prompt_key": run["prompt"]["key"],
        "provider": run["provider"],
        "model": run["model"],
        "split": run["dataset"]["split"],
        "cases_run": run["cases_run"],
        "error": run["error"],
        "extraction_accuracy": m["extraction_accuracy"],
        "evidence_coverage": m["evidence_coverage"],
        "unsupported_claim_rate": m["unsupported_claim_rate"],
        "contradiction_detection": m["contradiction_detection"],
        "operational_efficiency": m["operational_efficiency"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one TruTrace experiment.")
    parser.add_argument("--prompt", required=True, help="prompt key, e.g. trutrace@1.0.0")
    parser.add_argument("--provider", default="offline",
                        choices=["offline", "openrouter"])
    parser.add_argument("--model", default=None)
    parser.add_argument("--split", default="campaign",
                        choices=["dev", "heldout", "campaign", "all"])
    args = parser.parse_args()
    run = run_experiment(args.prompt, args.provider, args.model, args.split)
    m = run["metrics"]
    ea, uc = m["extraction_accuracy"], m["unsupported_claim_rate"]
    print(f"run {run['run_id']}")
    print(f"  prompt {run['prompt']['key']}  provider {run['provider']}  "
          f"model {run['model'] or '-'}  split {run['dataset']['split']}  "
          f"cases {run['cases_run']}/{run['dataset']['cases_total']}")
    if run["error"]:
        print(f"  RUN STOPPED: {run['error']['message']}")
    print(f"  accuracy {ea['correct']}/{ea['total']} fields, "
          f"unsupported {uc['unsupported']}/{uc['confirmed_fields']} confirmed")
    oe = m["operational_efficiency"]
    if oe["total_tokens"]:
        print(f"  tokens {oe['total_tokens']}, "
              f"cost ${oe['cost_usd_computed']:.6f} computed "
              f"(${oe['cost_usd_reported']:.6f} reported)")
    print(f"  persisted under runs/{run['run_id']}/")
    return 3 if run["error"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
