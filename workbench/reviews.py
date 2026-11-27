"""Human review decisions on run fields.

The interactive product's closing loop: the machine verdict is a
proposal, and a person approves it, rejects it, or sends it back for
another look. A decision is recorded per (run, case, field) with an
optional note; a later decision on the same field replaces the
earlier one, so what the store holds is always the current decision
and when it was made.

Reviews work for verify runs (one case, the submitted transcript)
and for benchmark runs (one case per dataset transcript) alike: the
review names the case it belongs to. Persistence follows the one
store rule (workbench/store.py): PostgreSQL (eval_reviews) when
DATABASE_URL is set, a reviews.json beside the run's files
otherwise. No silent fallback either way.
"""

import json
import os
from datetime import datetime, timezone

from . import pg_store, store
from .runner import RUNS_DIR

DECISIONS = ("approve", "reject", "needs_review")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _reviews_path(run_id: str) -> str:
    return os.path.join(RUNS_DIR, run_id, "reviews.json")


def record_review(
    run_id: str, case_id: str, field: str, decision: str, note: str = None
) -> dict:
    """Record (or replace) one field decision. Returns the stored
    review. Raises ValueError for an unknown decision and
    FileNotFoundError for a run that does not exist."""
    if decision not in DECISIONS:
        raise ValueError(
            f"decision must be one of {DECISIONS}, got {decision!r}"
        )
    if store.use_postgres():
        return pg_store.save_review(run_id, case_id, field, decision, note)
    run_dir = os.path.join(RUNS_DIR, run_id)
    if not os.path.exists(os.path.join(run_dir, "run.json")):
        raise FileNotFoundError(f"no run {run_id!r}")
    entry = {
        "run_id": run_id,
        "case_id": case_id,
        "field": field,
        "decision": decision,
        "note": note,
        "created_at": _now(),
    }
    reviews = [
        r for r in list_reviews(run_id)
        if not (r["case_id"] == case_id and r["field"] == field)
    ]
    reviews.append(entry)
    with open(_reviews_path(run_id), "w", encoding="utf-8") as fh:
        json.dump(reviews, fh, indent=2, ensure_ascii=False)
    return entry


def list_reviews(run_id: str) -> list:
    """The current decisions recorded on a run, oldest first. An
    unreviewed run (or a missing reviews file) returns an empty
    list."""
    if store.use_postgres():
        return pg_store.list_reviews(run_id)
    path = _reviews_path(run_id)
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)
