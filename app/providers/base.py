"""Provider interface.

A provider reads a call and reports what it found (a RawExtraction) plus
run metadata: wall-clock latency and, for paid models, token usage. A
provider never decides what is true; that is the verification engine's
job. Swapping providers changes who reads the call, never who judges it.
"""

from dataclasses import dataclass, field
from typing import Optional, Protocol

from ..context_builder import ExtractionContext
from ..schemas import RawExtraction


class ProviderError(Exception):
    """A provider failed to produce an extraction at all.

    Distinct from a bad extraction: a bad extraction is data the
    verification engine can judge; a ProviderError means no reading
    happened, and the pipeline's fallback path decides what happens
    next (second provider, or an honestly unconfirmed answer).
    """


@dataclass
class ProviderResult:
    raw: RawExtraction
    latency_ms: float
    model: Optional[str] = None
    usage: dict = field(default_factory=dict)  # prompt_tokens, completion_tokens, reported_cost_usd
    # The model's response text, verbatim, when the provider has one.
    # LLM providers set it; the offline rule provider has no response
    # text and leaves it None. Recorded by the workbench runner so a
    # persisted run keeps what the model actually said.
    raw_text: Optional[str] = None


class Provider(Protocol):
    name: str

    def extract(
        self, context: ExtractionContext, transcript: str, prompt_version: str
    ) -> ProviderResult:
        ...
