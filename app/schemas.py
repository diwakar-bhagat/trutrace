"""Typed schemas for TruTrace.

Every value that moves through the pipeline is validated against one of
these models. Extraction output that does not fit the schema is rejected
by the verification engine, never silently coerced: a malformed answer is
a failed answer, and the eval suite should see it fail.

Gold annotations use the same status vocabulary as pipeline output, so the
eval suite compares like with like:

- confirmed:   the seller stated it plainly; safe to assert.
- unconfirmed: the call never established it; the honest value is null.
- uncertain:   something was suggested, but hedged, approximate or
               conditional in a way that was not resolved; do not assert.
- conflicting: the call states two incompatible things; report both,
               assert neither.
"""

from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field

FIELDS = [
    "price",
    "currency",
    "availability",
    "quantity_or_stock",
    "delivery_or_pickup",
    "timing",
    "contact_next_step",
]


class FieldStatus(str, Enum):
    CONFIRMED = "confirmed"
    UNCONFIRMED = "unconfirmed"
    UNCERTAIN = "uncertain"
    CONFLICTING = "conflicting"


class GoldField(BaseModel):
    """One field of a human-style gold annotation.

    For the campaign subset, whose transcripts carry speaker labels and
    timestamps, the annotation also records who said the evidence and
    when: `speaker` and `timestamp` are part of the proof, not metadata.
    """

    value: Any = None
    status: FieldStatus
    evidence: Optional[str] = None
    condition: Optional[str] = None
    speaker: Optional[str] = None
    timestamp: Optional[str] = None


class TranscriptDoc(BaseModel):
    """One annotated seller call: the dataset's unit of truth."""

    id: str
    business_name: str
    business_type: str
    product: str
    question: str
    requested_fields: list[str] = Field(default_factory=lambda: list(FIELDS))
    taxonomy: str
    transcript: str
    gold: dict[str, GoldField]


class PriceCandidate(BaseModel):
    """One price mentioned in a call, with the sentence that stated it."""

    value: float
    evidence: Optional[str] = None


class TimingCandidate(BaseModel):
    value: str
    evidence: Optional[str] = None


class AvailabilitySignal(BaseModel):
    """One availability statement found in the call."""

    polarity: str  # "positive" | "negative"
    value: str  # in_stock | available | out_of_stock
    evidence: Optional[str] = None


class RawField(BaseModel):
    value: Any = None
    evidence: Optional[str] = None


class RawExtraction(BaseModel):
    """What a provider reports, before verification decides anything.

    Providers report; they do not judge. The single-value fields carry the
    provider's first/best reading, and the candidate/signal lists carry
    everything else the verification engine needs to catch contradictions,
    stale prices, fees and wrong-entity prices.
    """

    fields: dict[str, RawField] = Field(default_factory=dict)
    price_candidates: list[PriceCandidate] = Field(default_factory=list)
    timing_candidates: list[TimingCandidate] = Field(default_factory=list)
    availability_signals: list[AvailabilitySignal] = Field(default_factory=list)
    currency_evidence: Optional[str] = None


class VerifiedField(BaseModel):
    """One field of the verified answer.

    Extraction with proof: alongside the value and its status, a field
    carries the transcript span that supports it and, where the
    transcript is labelled, the speaker and timestamp of that span.
    A confirmed field without a span is a bug, not an answer.
    """

    value: Any = None
    status: FieldStatus = FieldStatus.UNCONFIRMED
    evidence: Optional[str] = None
    condition: Optional[str] = None
    reason: Optional[str] = None
    candidates: list[Any] = Field(default_factory=list)
    speaker: Optional[str] = None
    timestamp: Optional[str] = None


class VerifiedAnswer(BaseModel):
    fields: dict[str, VerifiedField]

    def confirmed_values(self) -> dict[str, Any]:
        """The assertable answer: confirmed fields only."""
        return {
            name: f.value
            for name, f in self.fields.items()
            if f.status == FieldStatus.CONFIRMED
        }
