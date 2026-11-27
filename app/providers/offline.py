"""The deterministic offline provider.

Rule-based reading of the seller's sentences. No network, no key, no
nondeterminism: the regression baseline every other provider is compared
against. It deliberately reports everything it finds (every price, every
timing, every availability statement) and judges none of it. Deciding
what counts as verified is the verification engine's job.

Only seller sentences are read. The agent's questions are context, never
evidence: a price the agent mentions is not a price the seller quoted.
"""

import re
import time

from ..context_builder import ExtractionContext
from ..schemas import (
    AvailabilitySignal,
    PriceCandidate,
    RawExtraction,
    RawField,
    TimingCandidate,
)
from ..textutil import seller_units
from .base import ProviderResult

_PRICE_RX = re.compile(r"\$\s*(\d+(?:\.\d{1,2})?)")

_NEGATIVE_PATTERNS = [
    (r"out of stock|sold out|don'?t have any|no stock|fully booked", "out_of_stock"),
]
_POSITIVE_PATTERNS = [
    (r"\bopening", "available"),
    (r"fit you in", "available"),
    (r"in stock", "in_stock"),
    (r"we have", "in_stock"),
    (r"we carry", "in_stock"),
    (r"we'?ve got", "in_stock"),
]

_QUANTITY_PATTERNS = [
    (
        r"(\d+)\s+(bunches|loaves|boxes|bottles|tyres|tires|units|pieces|bags|"
        r"cartons|tins|pairs|sets|trays|stems|jars|rolls|cakes|chairs|plants|crates)\b",
        lambda m: f"{m.group(1)} {m.group(2).lower()}",
    ),
    (r"(\d+)\s+(pack|packs)\b", lambda m: f"{m.group(1)} pack"),
    (r"(\d+)\s+in stock", lambda m: f"{m.group(1)} in stock"),
    (r"(\d+)\s+left", lambda m: f"{m.group(1)} left"),
]

_DELIVERY_PATTERNS = [
    (r"we deliver|we can deliver|can deliver|delivery is (?:free|available)|delivered by", "delivery"),
    (r"\bpickup\b|pick (?:it|them|one) up", "pickup"),
]

_TIMING_PATTERNS = [
    r"by\s+\d{1,2}\s*(?:am|pm)",
    r"in\s+\d+\s+(?:minutes?|hours?)",
    r"tomorrow\s+(?:morning|afternoon|evening)",
    r"this\s+(?:morning|afternoon|evening)",
    r"this\s+weekend",
    r"next\s+week",
    r"at\s+\d{1,2}\s*(?:am|pm)",
    r"on\s+(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)s?\b",
    r"\b(?:one|two|three|four|five)\s+(?:days|hours)\b",
    r"\d+\s+hours?",
]

# "this morning" in a seller's sentence is usually retrospective ("we
# baked 12 loaves this morning"), not a promised time. It only counts as
# a timing when the sentence carries commitment language.
_THIS_PART_OF_DAY = re.compile(r"^this\s+(morning|afternoon|evening)$")
_FUTURE_MARKERS = ("can ", "will ", "shall ", "by ")

_CONTACT_PATTERNS = [
    (r"call\s+(?:us\s+|me\s+)?back", "call back"),
    (r"book\s+online", "book online"),
    (r"book\s+(?:you\s+)?in", "book in"),
    (r"\btext\b", "text"),
    (r"\bhold\b", "hold"),
    (r"\breserve\b", "reserve"),
    (r"walk[- ]in", "walk in"),
]


def _first_match(units, patterns):
    """Pattern-major scan over (sentence, evidence) units: returns
    (value, evidence) of the first pattern that matches any sentence,
    else (None, None). Matching reads the sentence; the evidence is the
    unit's span (the full line in timestamped transcripts)."""
    for regex, value in patterns:
        rx = re.compile(regex, re.IGNORECASE)
        for s, ev in units:
            m = rx.search(s)
            if m:
                return (value(m) if callable(value) else value), ev
    return None, None


class OfflineProvider:
    name = "offline"

    def extract(
        self, context: ExtractionContext, transcript: str, prompt_version: str
    ) -> ProviderResult:
        start = time.perf_counter()
        units = seller_units(transcript)
        raw = RawExtraction()

        # Every price mentioned, in order, with its evidence span.
        seen = set()
        for s, ev in units:
            for m in _PRICE_RX.finditer(s):
                v = float(m.group(1))
                key = (v, ev)
                if key not in seen:
                    seen.add(key)
                    raw.price_candidates.append(
                        PriceCandidate(value=v, evidence=ev)
                    )
        if raw.price_candidates:
            first = raw.price_candidates[0]
            raw.fields["price"] = RawField(value=first.value, evidence=first.evidence)
            raw.fields["currency"] = RawField(value="USD", evidence=first.evidence)
            raw.currency_evidence = first.evidence

        # Availability: every statement is a signal; the first-match value
        # is the naive reading the baseline asserts.
        for s, ev in units:
            for regex, value in _NEGATIVE_PATTERNS:
                if re.search(regex, s, re.IGNORECASE):
                    raw.availability_signals.append(
                        AvailabilitySignal(polarity="negative", value=value, evidence=ev)
                    )
            for regex, value in _POSITIVE_PATTERNS:
                if re.search(regex, s, re.IGNORECASE):
                    raw.availability_signals.append(
                        AvailabilitySignal(polarity="positive", value=value, evidence=ev)
                    )
        value, span = _first_match(
            units, _NEGATIVE_PATTERNS + _POSITIVE_PATTERNS
        )
        if value is not None:
            raw.fields["availability"] = RawField(value=value, evidence=span)

        # Quantity, delivery, contact: first match wins.
        value, span = _first_match(units, _QUANTITY_PATTERNS)
        if value is not None:
            raw.fields["quantity_or_stock"] = RawField(value=value, evidence=span)
        value, span = _first_match(units, _DELIVERY_PATTERNS)
        if value is not None:
            raw.fields["delivery_or_pickup"] = RawField(value=value, evidence=span)
        value, span = _first_match(units, _CONTACT_PATTERNS)
        if value is not None:
            raw.fields["contact_next_step"] = RawField(value=value, evidence=span)

        # Every timing expression, in order. Overlapping matches in one
        # sentence ("in 2 hours" and its substring "2 hours") are one
        # mention, not two: keep the longest.
        seen_t = set()
        for s, ev in units:
            matches = []
            for pattern in _TIMING_PATTERNS:
                for m in re.finditer(pattern, s, re.IGNORECASE):
                    matches.append((m.start(), m.end(), m.group(0)))
            matches.sort(key=lambda t: (-(t[1] - t[0]), t[0]))
            kept_ranges = []
            # NB: the span variables are named m_start/m_end on
            # purpose: plain `start` here would rebind the timer
            # start above and corrupt the reported latency.
            for m_start, m_end, text in matches:
                if any(m_start >= ks and m_end <= ke for ks, ke in kept_ranges):
                    continue
                kept_ranges.append((m_start, m_end))
                v = " ".join(text.lower().split())
                if _THIS_PART_OF_DAY.match(v) and not any(
                    marker in s.lower() for marker in _FUTURE_MARKERS
                ):
                    continue
                if (v, ev) not in seen_t:
                    seen_t.add((v, ev))
                    raw.timing_candidates.append(
                        TimingCandidate(value=v, evidence=ev)
                    )
        if raw.timing_candidates:
            first = raw.timing_candidates[0]
            raw.fields["timing"] = RawField(value=first.value, evidence=first.evidence)

        latency_ms = (time.perf_counter() - start) * 1000.0
        return ProviderResult(raw=raw, latency_ms=latency_ms, model="offline-rules")
