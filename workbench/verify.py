"""The interactive verification path (POST /api/verify).

The benchmark path extracts an answer from a transcript and verifies
the extraction. This path starts one step later: a visitor supplies a
transcript AND the flat JSON an AI (theirs, anyone's) already
extracted from it, and TruTrace verifies the claims in that JSON
against the transcript. TruTrace does not extract in this path: the
values being judged are the visitor's, never the pipeline's own.

How the judgement is made, with no parallel checker: the existing
provider machinery reads the transcript once to build the evidence
layer the verification engine consumes (evidence spans, price and
timing candidates, availability signals — exactly what it builds for
a benchmark extraction), then the EXISTING verification engine
(app/verification/engine.py, the full trutrace-1.0.0 configuration)
judges that layer, and each verdict is mapped onto the visitor's
claimed value for the field.

Verification is relative to an ask, exactly as in the benchmark:
the engine checks a price against the product it was quoted for, so
the request may carry the same context a benchmark case carries
(the product and the buyer's question, both optional). With no
context the engine stays conservative — a price quoted with
qualifiers it cannot tie to any ask is demoted by its
product-mismatch rule rather than confirmed. The context used is
stored on the run with the rest of the input.

  engine confirmed, same value   -> supported
  engine uncertain, same value   -> uncertain (the call hedges it)
  engine conflicting             -> contradictory
  anything else                  -> unsupported (a different value
                                    established, only a different
                                    value suggested, or nothing in
                                    the call supports the claim)

Value comparison reuses evals/metrics.values_equal (plus a numeric
coercion for a price claimed as a string), the same normalisation
the benchmark scores with.

A verify run persists through the same store as benchmark runs
(PostgreSQL when DATABASE_URL is set, files otherwise), marked
kind="verify" so the two never mix: benchmark run lists skip verify
runs, and a verify record states plainly that the input carries no
gold labels — each field is verified against the submitted
transcript itself, not against an annotation.

Guards live here and in the server (the endpoint is public and the
OpenRouter path spends real money): a transcript size cap, the
model restricted to openai/gpt-4o-mini or the offline provider, and
a per-client rate limit in workbench/server.py.
"""

import json
import os
import uuid
from datetime import datetime, timezone

from app.config import get_config
from app.context_builder import build_context
from app.schemas import FIELDS, TranscriptDoc
from app.verification.engine import verify as engine_verify
from evals.metrics import values_equal

from . import pg_store, store
from .runner import LANGFUSE_STATUS, RUNS_DIR, _make_provider

# The extraction prompt and full verification configuration the
# evidence layer is built with: the legacy code-defined harness.
VERIFY_PROMPT_VERSION = "trutrace-1.0.0"
# The registered Prompt Lab key for the same harness; eval_runs
# references it so a verify run's configuration stays exact.
VERIFY_PROMPT_KEY = "trutrace@1.0.0"

CASE_ID = "submission"
MAX_TRANSCRIPT_CHARS = 12000
ALLOWED_MODEL = "openai/gpt-4o-mini"

LABELS_STATUS = (
    "User-submitted input: the transcript and the candidate JSON "
    "were supplied by the caller and carry no gold labels. Each "
    "field is verified against the submitted transcript itself, "
    "not against an annotation."
)

# The product vocabulary, mapped from the engine's own statuses.
STATUS_MAP = {
    "confirmed": "supported",
    "uncertain": "uncertain",
    "unconfirmed": "unsupported",
    "conflicting": "contradictory",
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def resolve_profile(profile) -> tuple:
    """Resolve the request's fields profile to (name, field list).

    The default ("campaign") is the campaign field set: the seven
    fields in app.schemas.FIELDS, the set the engine already knows.
    A list selects a subset of those fields. Anything else is a
    client error, raised as ValueError.
    """
    if profile is None or profile == "campaign":
        return "campaign", list(FIELDS)
    if isinstance(profile, list):
        if not profile:
            raise ValueError("the fields profile may not be empty")
        unknown = [f for f in profile if f not in FIELDS]
        if unknown:
            raise ValueError(
                f"unknown field(s) in the profile: {unknown}; "
                f"choose from {FIELDS}"
            )
        return "custom", [f for f in FIELDS if f in profile]
    raise ValueError(
        "profile must be \"campaign\" or a list of field names "
        f"from {FIELDS}"
    )


def resolve_provider(provider_name, model) -> tuple:
    """Validate the provider/model pair for a verify run. The model
    is restricted because the endpoint is public: openai/gpt-4o-mini
    via OpenRouter, or the offline provider. Anything else raises
    ValueError before any provider is constructed."""
    if provider_name == "offline":
        if model is not None:
            raise ValueError(
                "the offline provider takes no model; omit it or "
                "use provider \"openrouter\""
            )
        return "offline", None
    if provider_name == "openrouter":
        model = model or ALLOWED_MODEL
        if model != ALLOWED_MODEL:
            raise ValueError(
                f"only {ALLOWED_MODEL} is available for verification "
                f"runs, got {model!r}"
            )
        return "openrouter", model
    raise ValueError(
        f"unknown provider {provider_name!r}; "
        "choose \"openrouter\" or \"offline\""
    )


def _is_scalar(value) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _claimed_equal(claimed, verified) -> bool:
    """Does the verified value match what the visitor claimed? The
    benchmark's normalisation first; then a numeric coercion so a
    price claimed as \"35\" matches a verified 35. Booleans never
    coerce (True is not 1 here)."""
    if values_equal(claimed, verified):
        return True
    if isinstance(claimed, bool) or isinstance(verified, bool):
        return False
    try:
        return float(claimed) == float(verified)
    except (TypeError, ValueError):
        return False


def _verdict(name, claimed_present, claimed, vf) -> dict:
    """Map one engine verdict (a VerifiedField) onto the visitor's
    claimed value for the field, in the product vocabulary."""
    entry = {
        "claimed_value": claimed if claimed_present else None,
        "value": claimed if claimed_present else None,
        "verified_value": vf.value,
        "status": None,
        "engine_status": vf.status.value,
        "evidence": vf.evidence,
        "reason": None,
        "condition": vf.condition,
        "candidates": vf.candidates,
        "speaker": vf.speaker,
        "timestamp": vf.timestamp,
    }
    if not claimed_present:
        entry["status"] = "unsupported"
        entry["reason"] = (
            "the submitted extraction does not provide this field"
        )
        return entry
    if not _is_scalar(claimed):
        entry["status"] = "unsupported"
        entry["reason"] = (
            "the submitted value is not a flat scalar; only flat "
            "values can be verified"
        )
        return entry
    engine_status = vf.status.value
    if engine_status == "conflicting":
        entry["status"] = "contradictory"
        entry["reason"] = vf.reason
    elif engine_status == "confirmed" and _claimed_equal(claimed, vf.value):
        entry["status"] = "supported"
        entry["reason"] = vf.reason
    elif engine_status == "uncertain" and _claimed_equal(claimed, vf.value):
        entry["status"] = "uncertain"
        entry["reason"] = vf.reason
    else:
        entry["status"] = "unsupported"
        if engine_status == "confirmed":
            entry["reason"] = (
                f"the call establishes a different value "
                f"({vf.value!r}); the claimed value is not supported"
            )
        elif engine_status == "uncertain":
            entry["reason"] = (
                f"the call only suggests a different value "
                f"({vf.value!r}), and hedged at that; the claimed "
                "value is not supported"
            )
        else:
            entry["reason"] = vf.reason or (
                "no supporting span in the transcript"
            )
    return entry


def run_verify(
    transcript: str,
    candidate: dict,
    profile=None,
    provider_name: str = "openrouter",
    model: str = None,
    product: str = "",
    question: str = "",
) -> dict:
    """Verify one submitted extraction against its transcript and
    persist the run. Returns the verify run record.

    Raises ValueError for client errors (oversized transcript, bad
    profile, restricted model, unknown provider) and lets the
    provider's ProviderError propagate for provider failures.
    """
    if not isinstance(transcript, str) or not transcript.strip():
        raise ValueError("a transcript is required")
    if len(transcript) > MAX_TRANSCRIPT_CHARS:
        raise ValueError(
            f"transcript is {len(transcript)} characters; the limit "
            f"is {MAX_TRANSCRIPT_CHARS}"
        )
    if not isinstance(candidate, dict):
        raise ValueError("candidate must be a flat JSON object")
    profile_name, fields = resolve_profile(profile)
    provider_name, model = resolve_provider(provider_name, model)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    model_tag = model.replace("/", "-") if model else "offline"
    run_id = f"{stamp}_verify_{model_tag}_{uuid.uuid4().hex[:6]}"

    doc = TranscriptDoc(
        id=f"verify-{uuid.uuid4().hex[:8]}",
        business_name="",
        business_type="",
        product=product or "",
        question=question or "",
        requested_fields=fields,
        taxonomy="user_submitted",
        transcript=transcript,
        gold={},
    )
    context = build_context(doc)
    provider = _make_provider(provider_name, model, 0.0)
    result = provider.extract(context, transcript, VERIFY_PROMPT_VERSION)
    answer = engine_verify(
        result.raw, context, transcript, get_config(VERIFY_PROMPT_VERSION)
    )

    verdicts = {}
    for name in fields:
        claimed_present = name in candidate and candidate[name] is not None
        verdicts[name] = _verdict(
            name, claimed_present, candidate.get(name), answer.fields[name]
        )
    unverified = {}
    for key, value in candidate.items():
        if key in verdicts:
            continue
        if key in FIELDS:
            reason = "not part of the selected verification profile"
        else:
            reason = "the engine has no checks for this field"
        unverified[key] = {"claimed_value": value, "reason": reason}

    summary = {
        "supported": 0, "uncertain": 0,
        "unsupported": 0, "contradictory": 0,
        "total": len(fields),
    }
    for entry in verdicts.values():
        summary[entry["status"]] += 1

    usage = {
        "prompt_tokens": (result.usage or {}).get("prompt_tokens"),
        "completion_tokens": (result.usage or {}).get("completion_tokens"),
        "total_tokens": (result.usage or {}).get("total_tokens"),
        "reported_cost_usd": (result.usage or {}).get("reported_cost_usd"),
    }
    record = {
        "run_id": run_id,
        "kind": "verify",
        "created_at": _now(),
        "provider": provider_name,
        "model": model,
        "prompt_version": VERIFY_PROMPT_VERSION,
        "profile": {"name": profile_name, "fields": fields},
        "input": {
            "transcript": transcript,
            "candidate": candidate,
            "product": doc.product,
            "question": doc.question,
        },
        "fields": verdicts,
        "unverified": unverified,
        "summary": summary,
        "labels_status": LABELS_STATUS,
        "usage": usage,
        "latency_ms": round(result.latency_ms, 2),
        "langfuse": LANGFUSE_STATUS,
        "error": None,
    }
    trace = {
        "trace_id": str(uuid.uuid4()),
        "run_id": run_id,
        "case_id": CASE_ID,
        "kind": "verify",
        "taxonomy": "user_submitted",
        "timestamp": record["created_at"],
        "prompt_version": VERIFY_PROMPT_VERSION,
        "provider": provider_name,
        "model": model,
        "status": "ok",
        "error": None,
        "latency_ms": record["latency_ms"],
        "usage": usage,
        "provider_used": provider_name,
        "fallback_used": False,
        "input": {
            "question": doc.question,
            "transcript": transcript,
            "candidate": candidate,
        },
        "raw_response": result.raw_text,
        "raw_extraction": result.raw.model_dump(mode="json"),
        "output": {"fields": verdicts},
        "evaluations": None,
    }
    save_verify_run(record, trace)
    return record


# ------------------------------------------------------------ persistence --

def save_verify_run(record: dict, trace: dict) -> None:
    """Persist one verify run through the active store, in the same
    places benchmark runs live, marked kind="verify"."""
    if store.use_postgres():
        pg_store.save_verify_run(record, trace)
        return
    run_dir = os.path.join(RUNS_DIR, record["run_id"])
    os.makedirs(run_dir, exist_ok=True)
    with open(os.path.join(run_dir, "run.json"), "w", encoding="utf-8") as fh:
        json.dump(record, fh, indent=2, ensure_ascii=False)
    with open(os.path.join(run_dir, "cases.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(trace, ensure_ascii=False) + "\n")


def get_verify_run(run_id: str) -> dict:
    """Read back a verify run by id (either store). Raises
    FileNotFoundError for a missing run or a benchmark run id."""
    from .runner import get_run

    record = get_run(run_id)
    if record.get("kind") != "verify":
        raise FileNotFoundError(f"no verify run {run_id!r}")
    return record
