"""Evidence validation: grounding and hedging.

Two questions about every field a provider asserts:

- Grounding: does the quoted supporting sentence actually appear in the
  transcript? A field whose evidence cannot be found in the call is not
  an answer, whatever the provider says.
- Hedging: does that sentence hedge? "Probably", "not sure", "I think"
  are not confirmations. A hedged statement is a suggestion, and the
  confidence policy treats it as one.
"""

from ..textutil import norm, span_in_transcript

HEDGE_MARKERS = [
    "not sure",
    "probably",
    "maybe",
    "i think",
    "i believe",
    "sometime",
    "usually",
    "might",
    "have to check",
    "need to check",
    "should be",
    "supposed to",
    "last i checked",
    "as far as i know",
    "cannot say",
    "could not say",
]


def is_grounded(evidence, transcript: str) -> bool:
    return span_in_transcript(evidence, transcript)


def hedge_in(span) -> str | None:
    """The first hedge marker found in a sentence, or None."""
    if not span:
        return None
    text = norm(span)
    for marker in HEDGE_MARKERS:
        if marker in text:
            return marker
    return None
