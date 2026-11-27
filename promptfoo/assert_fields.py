"""Promptfoo assertion: field-level scoring by the existing eval rules.

Correctness comes from evals/metrics.py (field_correct,
is_unsupported_claim) — the same functions the benchmark and the
Experiment Runner use. Promptfoo contributes the matrix and the
report; it does not get its own opinion about what is correct.

Score is the share of the case's 7 fields that are correct; a case
passes only when every field is correct, the strict definition the
metrics module encodes. Gold labels are AI drafted and pending human
review, and the reason string says so on every case.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.schemas import VerifiedField  # noqa: E402
from evals.metrics import field_correct, is_unsupported_claim  # noqa: E402
from workbench.datasets import load_split  # noqa: E402

_CASES = {}


def _case(case_id):
    if not _CASES:
        for doc in load_split("campaign"):
            _CASES[doc.id] = doc
    return _CASES[case_id]


def get_assert(output, context):
    vars_ = (context or {}).get("vars", {})
    doc = _case(vars_["case_id"])
    predicted = json.loads(output)
    correct = 0
    unsupported = 0
    total = 0
    for name, gold in doc.gold.items():
        p = predicted.get(name) or {}
        field = VerifiedField(
            value=p.get("value"),
            status=p.get("status") or "unconfirmed",
            condition=p.get("condition"),
        )
        total += 1
        if field_correct(gold, field):
            correct += 1
        if is_unsupported_claim(gold, field):
            unsupported += 1
    score = correct / total if total else 0
    return {
        "pass": correct == total,
        "score": score,
        "reason": (
            f"{correct}/{total} fields correct, {unsupported} unsupported "
            "claims (gold labels AI drafted, pending human review)"
        ),
        "namedScores": {
            "field_accuracy": score,
            "unsupported_claims": float(unsupported),
        },
    }
