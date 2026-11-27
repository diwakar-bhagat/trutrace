"""The connected gold review flow.

The review page (tools/gold_review.html) used to end in a file: the
reviewer exported gold_labels_v2.json and carried it back by hand.
This module is the receiving end that removes that step:

  POST /api/gold/review   a submitted review export is validated
                          and stored as the current human gold,
                          gold-v2-human-reviewed. In PostgreSQL it
                          lands in eval_gold_submissions (a new row
                          per submission, latest wins); with the
                          file store it lands in gold/ beside the
                          runs. gold-v1-ai-drafted is never
                          overwritten either way.
  GET  /api/gold/review   the current stored submission, payload
                          included, so the review page opens from
                          the persisted state: the fields already
                          reviewed on the backend prefill the tool
                          instead of a fresh page starting at zero.
  GET  /api/gold/status   the current gold version and, once a
                          human review has been submitted, its
                          coverage (fields reviewed of the 224 in
                          the frozen set, per split).
  GET  /api/gold/metrics  the recorded benchmark runs scored
                          against the current gold, computed by
                          evals/gold_metrics.py — the same code the
                          CLI harness runs, not a second metrics
                          implementation. With no human gold stored,
                          the numbers are the AI draft agreement
                          numbers and are labelled as agreement, not
                          correctness. With a partial human review,
                          the metrics are computed over the reviewed
                          fields only and say so: unreviewed fields
                          are excluded, never silently scored
                          against the AI draft under a human label.

The review page keeps localStorage as its working draft and the
file export as a fallback; submission to this backend is the
primary path (see GOLD_REVIEW.md).
"""

import json
import os
from datetime import datetime, timezone

from app.schemas import FIELDS
from evals import gold_metrics
from evals.run_evals import load_cases

from . import pg_store, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GOLD_DIR = os.path.join(ROOT, "gold")
GOLD_FILE_NAME = "gold_labels_v2.json"

HUMAN_VERSION = "gold-v2-human-reviewed"
AI_VERSION = gold_metrics.GOLD_VERSION_AI_DRAFTED
PROTOCOL_STATUSES = ("supported", "uncertain", "unsupported",
                     "contradictory")

# The reviewable set: the 32 frozen transcripts x the 7 fields.
# Campaign cases sit outside it (the review tool walks the 32).
TOTAL_REVIEW_FIELDS = len(load_cases()) * len(FIELDS)

AI_AGREEMENT_NOTE = (
    "No human reviewed gold has been submitted. These numbers are "
    "scored against gold-v1-ai-drafted and measure AGREEMENT WITH "
    "AI DRAFTED LABELS, not validated correctness: the labels were "
    "drafted by an AI coding agent and are pending human review."
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _gold_file() -> str:
    return os.path.join(GOLD_DIR, GOLD_FILE_NAME)


# ---------------------------------------------------------------- coverage --

def coverage_of(payload: dict) -> dict:
    """Review coverage of one export payload: fields reviewed of
    the fields the payload carries, overall and per split. A field
    counts as reviewed when the reviewer recorded a human status
    for it."""
    per_split = {}
    reviewed = 0
    carried = 0
    for case in (payload.get("cases") or {}).values():
        split = case.get("split") or "unknown"
        fields = case.get("fields") or {}
        done = sum(
            1 for entry in fields.values()
            if entry.get("reviewed") and entry.get("human_status")
        )
        bucket = per_split.setdefault(split, {"reviewed": 0, "total": 0})
        bucket["reviewed"] += done
        bucket["total"] += len(fields)
        reviewed += done
        carried += len(fields)
    total = payload.get("fields_total") or carried or TOTAL_REVIEW_FIELDS
    return {
        "fields_reviewed": reviewed,
        "fields_total": total,
        "per_split": per_split,
    }


# -------------------------------------------------------------- submission --

def validate_payload(payload) -> None:
    """Raise ValueError unless the payload is a review export in
    the shape tools/gold_review.html produces."""
    if not isinstance(payload, dict):
        raise ValueError("the review payload must be a JSON object")
    version = payload.get("dataset_version")
    if version != HUMAN_VERSION:
        raise ValueError(
            f"dataset_version must be {HUMAN_VERSION!r}, "
            f"got {version!r}"
        )
    cases = payload.get("cases")
    if not isinstance(cases, dict) or not cases:
        raise ValueError("the review payload carries no cases")
    for case_id, case in cases.items():
        if not isinstance(case, dict):
            raise ValueError(f"case {case_id!r} is not an object")
        for name, entry in (case.get("fields") or {}).items():
            if not isinstance(entry, dict):
                raise ValueError(
                    f"case {case_id} field {name}: not an object"
                )
            if entry.get("reviewed") and (
                entry.get("human_status") not in PROTOCOL_STATUSES
            ):
                raise ValueError(
                    f"case {case_id} field {name}: human_status "
                    f"must be one of {list(PROTOCOL_STATUSES)} when "
                    "the field is marked reviewed"
                )


def _status_of(record: dict) -> dict:
    coverage = coverage_of(record["payload"])
    return {
        "gold_version": HUMAN_VERSION,
        "reviewer": record.get("reviewer"),
        "submitted_at": record["submitted_at"],
        "fields_reviewed": coverage["fields_reviewed"],
        "fields_total": coverage["fields_total"],
        "per_split": coverage["per_split"],
        "complete": coverage["fields_reviewed"] >= coverage["fields_total"],
    }


def submit_review(payload: dict) -> dict:
    """Validate and store one review export. Returns the recorded
    status (version, coverage, timestamp). The stored payload is
    the new current human gold; gold-v1-ai-drafted is untouched."""
    validate_payload(payload)
    submitted_at = _now()
    if store.use_postgres():
        record = pg_store.save_gold_submission(payload, submitted_at)
    else:
        os.makedirs(GOLD_DIR, exist_ok=True)
        record = {
            "version": HUMAN_VERSION,
            "reviewer": payload.get("reviewer"),
            "submitted_at": submitted_at,
            "payload": payload,
        }
        tmp = _gold_file() + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
        os.replace(tmp, _gold_file())
    return _status_of(record)


def current_submission() -> dict:
    """The current human gold submission record ({version,
    reviewer, submitted_at, payload}), or None when no human review
    has been submitted yet."""
    if store.use_postgres():
        return pg_store.latest_gold_submission()
    path = _gold_file()
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def current_submission_view() -> dict | None:
    """The current human gold submission as the review page seeds
    from it: the recorded status (version, reviewer, coverage) plus
    the stored payload itself, in the export shape the page
    produces. None when no human review has been submitted yet.
    Reading it changes nothing; the stored gold is only ever
    replaced by a new POST /api/gold/review submission."""
    record = current_submission()
    if record is None:
        return None
    return _status_of(record) | {"payload": record["payload"]}


def gold_status() -> dict:
    """The current gold state for the API: the AI drafted version
    until a human review lands, then the human version with its
    coverage."""
    record = current_submission()
    if record is None:
        return {
            "gold_version": AI_VERSION,
            "labels_status": (
                "AI drafted, pending human review: scores are "
                "measured against unreviewed labels, not validated "
                "ground truth"
            ),
            "human_review": None,
            "fields_reviewed": 0,
            "fields_total": TOTAL_REVIEW_FIELDS,
        }
    status = _status_of(record)
    return {
        "gold_version": HUMAN_VERSION,
        "labels_status": (
            f"Human reviewed gold ({HUMAN_VERSION}) submitted "
            f"{status['submitted_at']}: {status['fields_reviewed']} "
            f"of {status['fields_total']} fields reviewed. "
            "Unreviewed fields keep the AI drafted label."
        ),
        "human_review": status,
        "fields_reviewed": status["fields_reviewed"],
        "fields_total": status["fields_total"],
    }


# ----------------------------------------------------------------- metrics --

def gold_metrics_report() -> dict:
    """Score the recorded benchmark runs against the current gold,
    using evals/gold_metrics.py unchanged.

    No human gold stored: every recorded field is scored against
    gold-v1-ai-drafted and the report is labelled agreement, not
    correctness. Human gold stored: only the fields the reviewer
    actually decided are scored (the AI drafted remainder is
    excluded, not relabelled), and the report says so.
    """
    book = gold_metrics.load_gold()
    record = current_submission()
    human = False
    if record is not None:
        book.overlay_export_data(record["payload"])
        human = book.reviewed_fields > 0
    rows = gold_metrics.load_rows(gold_metrics.default_result_paths(), book)
    if human:
        reviewed = book.reviewed_keys()
        rows = [
            r for r in rows
            if (r["case_id"], r["field"]) in reviewed
        ]
        coverage = coverage_of(record["payload"])
        if coverage["fields_reviewed"] >= coverage["fields_total"]:
            note = (
                f"Gold version: {HUMAN_VERSION}, covering all "
                f"{coverage['fields_total']} fields. These metrics "
                "are computed over the full human reviewed set."
            )
            scope = "all_fields"
        else:
            note = (
                f"Gold version: {HUMAN_VERSION}, covering "
                f"{coverage['fields_reviewed']} of "
                f"{coverage['fields_total']} fields. These metrics "
                "are computed over the reviewed fields only; "
                "unreviewed fields are excluded, not scored against "
                "the AI drafted labels under a human label."
            )
            scope = "reviewed_fields_only"
        fields_reviewed = coverage["fields_reviewed"]
        fields_total = coverage["fields_total"]
    else:
        note = AI_AGREEMENT_NOTE
        scope = "all_fields"
        fields_reviewed = 0
        fields_total = TOTAL_REVIEW_FIELDS
    by_config = {}
    for row in rows:
        by_config.setdefault(row["config"], []).append(row)
    return {
        "gold_version": book.version if human else AI_VERSION,
        "provenance": book.provenance,
        "scope": scope,
        "note": note,
        "fields_reviewed": fields_reviewed,
        "fields_total": fields_total,
        "configurations": {
            label: gold_metrics.compute_metrics(config_rows)
            for label, config_rows in sorted(by_config.items())
        },
    }
