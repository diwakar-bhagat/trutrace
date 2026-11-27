"""Price candidate enrichment.

A bare (value, sentence) pair is not enough to judge a price. Enrichment
annotates each candidate with the facts the verification engine needs:
is it a fee rather than the product's price, a threshold rather than a
price, stale, conditional, per-unit, approximate, a starting price, or an
explicit correction of an earlier quote.
"""

import re
from dataclasses import dataclass, field

from ..context_builder import ExtractionContext
from ..schemas import PriceCandidate
from ..textutil import content_tokens, stem

# (marker, group) — a candidate whose sentence names a fee is not quoting
# the product's price, unless that fee is itself the requested product.
_FEE_MARKERS = [
    ("delivery is", "delivery"),
    ("delivery fee", "delivery"),
    ("delivery and setup", "delivery"),
    ("delivery charge", "delivery"),
    ("for delivery", "delivery"),
    ("shipping", "delivery"),
    ("call-out", "callout"),
    ("call out", "callout"),
    ("installation", "setup"),
    ("setup is", "setup"),
    ("fitting is", "setup"),
]
_FEE_GROUP_TOKENS = {
    "delivery": {"delivery", "shipping"},
    "callout": {"call-out", "callout"},
    "setup": {"setup", "installation", "fitting"},
}

_THRESHOLD_RX = re.compile(r"orders?\s+over\s+\$|minimum\s+(order|spend)", re.I)

_STALE_MARKERS = [
    "last week", "last month", "last season", "last year", "yesterday",
    "previously", "used to", "old price",
]
_STALE_RX = re.compile(r"\b(was|were)\s+\$", re.I)

_CORRECTION_MARKERS = ["actually", "i meant", "went up", "went down", "correction"]

_QUALIFIERS = [
    "standard", "imported", "premium", "regular", "small", "large",
    "bulk", "single", "dozen", "fitted", "alone", "weekday", "weekend",
    "cash", "card", "organic", "local",
]

_PER_UNIT_RX = re.compile(r"\$\s*\d+(?:\.\d{1,2})?\s*(?:a|per)\s+([a-z]+)", re.I)
_APPROX_RX = re.compile(r"\b(about|around|roughly)\s*\$", re.I)
_STARTING_RX = re.compile(r"\bstart(?:s|ing)?\s+(?:at|from)\b|\bfrom\s+\$", re.I)


@dataclass
class EnrichedCandidate:
    value: float
    evidence: str | None
    is_fee: bool = False
    is_threshold: bool = False
    is_stale: bool = False
    has_correction: bool = False
    qualifiers: set[str] = field(default_factory=set)
    per_unit: str | None = None
    is_approximate: bool = False
    is_starting: bool = False
    content_stems: set[str] = field(default_factory=set)

    @property
    def clean(self) -> bool:
        """True when every meaningful token in the sentence belongs to
        the requested product's name: the sentence names this product
        and no other."""
        return bool(self.content_stems) and not self.foreign_stems

    foreign_stems: set[str] = field(default_factory=set)


def enrich(
    candidate: PriceCandidate, context: ExtractionContext
) -> EnrichedCandidate:
    span = candidate.evidence or ""
    low = span.lower()
    out = EnrichedCandidate(value=candidate.value, evidence=candidate.evidence)

    context_tokens = context.product_tokens | context.question_tokens
    for marker, group in _FEE_MARKERS:
        if marker in low:
            exempt = bool(_FEE_GROUP_TOKENS[group] & context_tokens)
            out.is_fee = not exempt
            break
    out.is_threshold = bool(_THRESHOLD_RX.search(span))
    out.is_stale = any(m in low for m in _STALE_MARKERS) or bool(
        _STALE_RX.search(span)
    )
    out.has_correction = any(m in low for m in _CORRECTION_MARKERS)
    out.qualifiers = {
        q for q in _QUALIFIERS if re.search(rf"\b{re.escape(q)}\b", low)
    }
    m = _PER_UNIT_RX.search(span)
    if m:
        out.per_unit = m.group(1).lower()
    out.is_approximate = bool(_APPROX_RX.search(span))
    out.is_starting = bool(_STARTING_RX.search(low))

    stems = {stem(t) for t in content_tokens(span)}
    out.content_stems = stems
    out.foreign_stems = stems - context.product_stems
    return out
