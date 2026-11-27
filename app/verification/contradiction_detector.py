"""Contradiction detection.

A call can disagree with itself in three ways TruTrace watches for:

- Price: two different current prices for the same product and the same
  conditions. Both are reported; neither is asserted. (Prices that
  differ by a stated condition are not a contradiction; they are
  conditional pricing, resolved by the engine. An explicit correction
  "actually, it is $5 now" is not a contradiction either; the correction
  supersedes.)
- Timing: two different times for the same thing.
- Availability: the seller says both "in stock" and "sold out". A
  statement about a different product ("the oat milk is sold out") is
  filtered out first: it is not this product contradicting itself.
"""

import re

from ..context_builder import ExtractionContext
from ..schemas import AvailabilitySignal, TimingCandidate
from ..textutil import STOPWORDS, stem


def distinct_values(candidates) -> list:
    out = []
    for c in candidates:
        if c.value not in out:
            out.append(c.value)
    return out


def _signal_is_foreign_product(
    signal: AvailabilitySignal, context: ExtractionContext
) -> bool:
    """True when the statement's product mention is a different product:
    the head noun appears with a modifier that is not part of the
    requested product's name ("oat milk" when almond milk was asked)."""
    if not context.head_stem or not signal.evidence:
        return False
    tokens = re.findall(r"[a-z0-9][a-z0-9\-']*", signal.evidence.lower())
    for i, tok in enumerate(tokens):
        if stem(tok) == context.head_stem and i > 0:
            prev = tokens[i - 1]
            if prev not in STOPWORDS and stem(prev) not in context.product_stems:
                return True
    return False


def resolve_availability_signals(
    signals: list[AvailabilitySignal], context: ExtractionContext
) -> tuple[list[AvailabilitySignal], list[AvailabilitySignal]]:
    """Split signals into (kept, dropped-as-other-product)."""
    kept, dropped = [], []
    for s in signals:
        if _signal_is_foreign_product(s, context):
            dropped.append(s)
        else:
            kept.append(s)
    return kept, dropped


def timing_conflict(candidates: list[TimingCandidate]):
    """The distinct timing values in a call, in order."""
    return distinct_values(candidates)
