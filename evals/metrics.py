"""Scoring primitives for the eval suite.

The five metrics are computed separately and never averaged into one
score (see evals/run_evals.py). This module holds the per-field
correctness rules they share:

- gold confirmed:   correct iff predicted confirmed, same value, and the
                    condition matches (same condition tokens, either may
                    be the more specific phrasing).
- gold unconfirmed: correct iff predicted unconfirmed with no value.
                    The call never established it; anything asserted is
                    wrong by construction.
- gold uncertain:   correct iff predicted uncertain or unconfirmed.
                    Asserting it as confirmed is exactly the failure
                    this project exists to catch.
- gold conflicting: correct iff predicted conflicting.
"""

import re


def norm_value(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        return " ".join(v.lower().split())
    return v


def values_equal(a, b) -> bool:
    return norm_value(a) == norm_value(b)


def _cond_tokens(cond):
    if not cond:
        return set()
    return set(re.findall(r"[a-z0-9]+", str(cond).lower()))


def condition_match(gold_cond, pred_cond) -> bool:
    g, p = _cond_tokens(gold_cond), _cond_tokens(pred_cond)
    if not g and not p:
        return True
    if not g or not p:
        return False
    return g <= p or p <= g


def field_correct(gold, pred) -> bool:
    """gold and pred are objects with .value, .status, .condition."""
    gs, ps = gold.status.value, pred.status.value
    if gs == "confirmed":
        return (
            ps == "confirmed"
            and values_equal(gold.value, pred.value)
            and condition_match(gold.condition, pred.condition)
        )
    if gs == "unconfirmed":
        return ps == "unconfirmed" and pred.value is None
    if gs == "uncertain":
        return ps in ("uncertain", "unconfirmed")
    if gs == "conflicting":
        return ps == "conflicting"
    return False


def is_unsupported_claim(gold, pred) -> bool:
    """A predicted confirmed field that gold does not confirm with the
    same value and condition. The critical failure."""
    if pred.status.value != "confirmed":
        return False
    return not (
        gold.status.value == "confirmed"
        and values_equal(gold.value, pred.value)
        and condition_match(gold.condition, pred.condition)
    )
