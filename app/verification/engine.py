"""The verification engine.

Takes a provider's RawExtraction and decides, field by field, what the
call actually established. The output is a VerifiedAnswer in which every
field is confirmed, unconfirmed, uncertain or conflicting, with the
evidence and the reason attached. Nothing is silently dropped and
nothing is silently kept: graceful degradation means a partial, honest
answer instead of a confident wrong one.

Under the baseline configuration the engine is a pass-through (assert
the provider's first reading of everything). Every stage below is what
the full configuration adds, and the eval suite prices each one.
"""

from ..config import PipelineConfig
from ..context_builder import ExtractionContext
from ..schemas import (
    FIELDS,
    FieldStatus,
    RawExtraction,
    TimingCandidate,
    VerifiedAnswer,
    VerifiedField,
)
from . import confidence_policy as policy
from .candidates import EnrichedCandidate, enrich
from .contradiction_detector import (
    distinct_values,
    resolve_availability_signals,
    timing_conflict,
)
from ..textutil import proof_for_span
from .evidence_validator import hedge_in, is_grounded

C = FieldStatus.CONFIRMED
U = FieldStatus.UNCONFIRMED
X = FieldStatus.UNCERTAIN
K = FieldStatus.CONFLICTING


def _vf(value=None, status=U, evidence=None, condition=None, reason=None,
        candidates=None) -> VerifiedField:
    return VerifiedField(
        value=value, status=status, evidence=evidence,
        condition=condition, reason=reason, candidates=candidates or [],
    )


def verify(
    raw: RawExtraction,
    context: ExtractionContext,
    transcript: str,
    config: PipelineConfig,
) -> VerifiedAnswer:
    if config.label == "baseline":
        answer = _verify_baseline(raw)
    else:
        fields = {
            "price": _verify_price(raw, context, transcript, config),
            "currency": _verify_currency(raw, transcript, config),
            "availability": _verify_availability(raw, context, transcript, config),
            "timing": _verify_timing(raw, transcript, config),
        }
        for name in ("quantity_or_stock", "delivery_or_pickup", "contact_next_step"):
            fields[name] = _verify_simple(raw, name, transcript, config)
        answer = VerifiedAnswer(fields={name: fields[name] for name in FIELDS})
    _attach_proof(answer, transcript)
    return answer


def _attach_proof(answer: VerifiedAnswer, transcript: str) -> None:
    """Fill speaker/timestamp on every field from its evidence span.

    Proof is derived, never reported by the provider: the span is
    located in the transcript and the line's label is read off it.
    Unlabelled transcripts simply leave both as None.
    """
    for f in answer.fields.values():
        if f.evidence:
            f.speaker, f.timestamp = proof_for_span(f.evidence, transcript)


def _verify_baseline(raw: RawExtraction) -> VerifiedAnswer:
    fields = {}
    for name in FIELDS:
        item = raw.fields.get(name)
        if item is not None and item.value is not None:
            fields[name] = _vf(
                value=item.value, status=C, evidence=item.evidence,
                reason="asserted as extracted (baseline: no verification)",
            )
        else:
            fields[name] = _vf(reason="not extracted (baseline)")
    return VerifiedAnswer(fields=fields)


# ------------------------------------------------------------------ price --

def _verify_price(raw, context, transcript, config) -> VerifiedField:
    enriched = [enrich(c, context) for c in raw.price_candidates]
    if not enriched:
        return _vf(reason="no price was quoted in the call")

    working = enriched
    dropped = []
    if config.fee_filter:
        kept = []
        for c in working:
            if c.is_fee or c.is_threshold:
                dropped.append(c)
            else:
                kept.append(c)
        working = kept
        if not working:
            return _vf(
                reason=policy.DROP_FEE,
                candidates=[c.value for c in dropped],
            )

    if config.stale_filter:
        current = [c for c in working if not c.is_stale]
        if not current:
            return _vf(
                status=X,
                reason=policy.DEMOTE_STALE,
                evidence=working[0].evidence,
                candidates=[c.value for c in working],
            )
        working = current

    if policy.price_mismatch_demotion(working, context) and (
        config.product_mismatch_demotion
    ):
        return _vf(
            status=X,
            reason=policy.DEMOTE_MISMATCH,
            evidence=working[0].evidence,
            candidates=[c.value for c in working],
        )

    if (
        config.correction_supersede
        and len(working) >= 2
        and working[-1].has_correction
    ):
        chosen = working[-1]
        return _confirm_price(
            chosen, transcript, config,
            reason="seller corrected the price; the correction supersedes",
        )

    if config.product_restriction and len(working) >= 2:
        clean = [c for c in working if c.clean]
        if len(clean) == 1 and len(clean) < len(working):
            working = clean

    values = distinct_values(working)
    if len(values) > 1:
        if config.conditional_pricing:
            chosen = _conditional_choice(working, context)
            if chosen is not None:
                condition = " ".join(sorted(chosen.qualifiers))
                return _confirm_price(
                    chosen, transcript, config, condition=condition,
                    reason="price depends on a condition stated in the call",
                )
        if config.contradiction_detection:
            return _vf(
                status=K,
                reason=(
                    "call states two different prices for the same product: "
                    + ", ".join(str(v) for v in values)
                ),
                evidence=working[-1].evidence,
                candidates=values,
            )
        return _confirm_price(working[0], transcript, config)

    chosen = working[0]
    return _confirm_price(chosen, transcript, config)


def _conditional_choice(working, context):
    """If the candidates differ by stated condition and exactly one's
    distinguishing condition is what the buyer asked about, that one is
    the price. Shared qualifiers ("dozen" in both quotes) do not
    distinguish anything; only the differing ones can match the ask."""
    asked = context.question_tokens | context.product_tokens
    sets = [c.qualifiers for c in working]
    if any(not s for s in sets):
        return None
    if len({frozenset(s) for s in sets}) != len(sets):
        return None
    common = set.intersection(*sets)
    matches = [c for c in working if (c.qualifiers - common) & asked]
    if len(matches) == 1:
        return matches[0]
    return None


def _confirm_price(chosen: EnrichedCandidate, transcript, config,
                   condition=None, reason=None) -> VerifiedField:
    if config.grounding and not is_grounded(chosen.evidence, transcript):
        return _vf(
            reason="no supporting span in the transcript",
            evidence=chosen.evidence,
        )
    if config.approximate_demotion and chosen.is_starting:
        return _vf(
            value=chosen.value, status=X, evidence=chosen.evidence,
            condition="starting price", reason=policy.DEMOTE_STARTING,
        )
    if config.approximate_demotion and chosen.is_approximate:
        return _vf(
            value=chosen.value, status=X, evidence=chosen.evidence,
            reason=policy.DEMOTE_APPROX,
        )
    if config.hedge_demotion:
        marker = hedge_in(chosen.evidence)
        if marker:
            return _vf(
                value=chosen.value, status=X, evidence=chosen.evidence,
                reason=policy.DEMOTE_HEDGE.format(marker=marker),
            )
    if condition is None and chosen.per_unit:
        condition = f"per {chosen.per_unit}"
    return _vf(
        value=chosen.value, status=C, evidence=chosen.evidence,
        condition=condition, reason=reason,
    )


# --------------------------------------------------------------- currency --

def _verify_currency(raw, transcript, config) -> VerifiedField:
    item = raw.fields.get("currency")
    if item is None or item.value is None:
        return _vf(reason="no currency was established in the call")
    # A currency is established by the span that quotes an amount in it:
    # providers report that span as currency_evidence even when they do
    # not attach a currency-specific quote.
    evidence = item.evidence or raw.currency_evidence
    if config.grounding and not is_grounded(evidence, transcript):
        return _vf(reason="no supporting span in the transcript",
                   evidence=evidence)
    return _vf(value=item.value, status=C, evidence=evidence)


# ----------------------------------------------------------- availability --

def _verify_availability(raw, context, transcript, config) -> VerifiedField:
    kept, _dropped = resolve_availability_signals(
        raw.availability_signals, context
    )
    chosen = None
    if kept:
        polarities = {s.polarity for s in kept}
        if polarities == {"positive", "negative"} and (
            config.contradiction_detection
        ):
            negative = [s for s in kept if s.polarity == "negative"][-1]
            return _vf(
                status=K,
                reason="seller both confirmed and denied availability",
                evidence=negative.evidence,
                candidates=sorted({s.value for s in kept}),
            )
        positives = [s for s in kept if s.polarity == "positive"]
        chosen = positives[0] if positives else kept[0]
    if chosen is None:
        item = raw.fields.get("availability")
        if item is None or item.value is None:
            return _vf(reason="availability was not established in the call")
        chosen = item
    if config.grounding and not is_grounded(chosen.evidence, transcript):
        return _vf(reason="no supporting span in the transcript",
                   evidence=chosen.evidence)
    if config.hedge_demotion:
        marker = hedge_in(chosen.evidence)
        if marker:
            return _vf(
                value=chosen.value, status=X, evidence=chosen.evidence,
                reason=policy.DEMOTE_HEDGE.format(marker=marker),
            )
    return _vf(value=chosen.value, status=C, evidence=chosen.evidence)


# ----------------------------------------------------------------- timing --

def _verify_timing(raw, transcript, config) -> VerifiedField:
    candidates = raw.timing_candidates
    if not candidates:
        item = raw.fields.get("timing")
        if item is None or item.value is None:
            return _vf(reason="no timing was established in the call")
        candidates = [TimingCandidate(value=item.value,
                                      evidence=item.evidence)]
    values = timing_conflict(candidates)
    if len(values) > 1 and config.contradiction_detection:
        return _vf(
            status=K,
            reason=(
                "call states two different times: "
                + ", ".join(str(v) for v in values)
            ),
            evidence=candidates[-1].evidence,
            candidates=values,
        )
    chosen = candidates[0]
    if config.grounding and not is_grounded(chosen.evidence, transcript):
        return _vf(reason="no supporting span in the transcript",
                   evidence=chosen.evidence)
    if config.hedge_demotion:
        marker = hedge_in(chosen.evidence)
        if marker:
            return _vf(
                value=chosen.value, status=X, evidence=chosen.evidence,
                reason=policy.DEMOTE_HEDGE.format(marker=marker),
            )
    return _vf(value=chosen.value, status=C, evidence=chosen.evidence)


# ----------------------------------------------------------------- simple --

def _verify_simple(raw, name, transcript, config) -> VerifiedField:
    item = raw.fields.get(name)
    if item is None or item.value is None:
        return _vf(reason=f"{name} was not established in the call")
    if config.grounding and not is_grounded(item.evidence, transcript):
        return _vf(reason="no supporting span in the transcript",
                   evidence=item.evidence)
    if config.hedge_demotion:
        marker = hedge_in(item.evidence)
        if marker:
            return _vf(
                value=item.value, status=X, evidence=item.evidence,
                reason=policy.DEMOTE_HEDGE.format(marker=marker),
            )
    return _vf(value=item.value, status=C, evidence=item.evidence)
