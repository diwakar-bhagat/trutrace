"""The pipeline: context assembly, extraction, verification.

    transcript -> context -> provider extraction -> verification -> answer

The provider and the prompt version are the two swappable axes. The eval
suite runs the grid of both and reports the five metrics for each cell,
so a model or prompt change is a measured event, not a vibe.

Degradation is part of the contract, not an afterthought: if the
primary provider fails (ProviderError), the pipeline falls back to a
second provider when one is configured; if none is available, the
answer is every field unconfirmed with the failure recorded. A dead
provider produces an honest empty answer, never an exception and never
an invented one.
"""

import time
from dataclasses import dataclass, field
from typing import Optional

from .config import PipelineConfig, get_config
from .context_builder import build_context
from .providers.base import Provider, ProviderError
from .providers.offline import OfflineProvider
from .providers.openrouter import OpenRouterProvider
from .schemas import (
    FIELDS,
    FieldStatus,
    RawExtraction,
    TranscriptDoc,
    VerifiedAnswer,
    VerifiedField,
)
from .verification.engine import verify


@dataclass
class PipelineResult:
    answer: VerifiedAnswer
    provider: str
    model: Optional[str]
    prompt_version: str
    config_label: str
    latency_ms: float
    usage: dict = field(default_factory=dict)
    provider_used: Optional[str] = None
    fallback_used: bool = False
    error: Optional[str] = None
    # What the provider reported, before verification judged it: the
    # raw extraction, plus the model's verbatim response text when
    # the provider has one (LLM providers; None for the offline
    # provider). Carried so callers can persist a run completely;
    # verification neither reads nor changes these.
    raw_extraction: Optional[RawExtraction] = None
    raw_text: Optional[str] = None


def make_provider(name: str, model: Optional[str] = None) -> Provider:
    if name == "offline":
        return OfflineProvider()
    if name == "openrouter":
        if not model:
            raise ValueError("the openrouter provider needs a model")
        return OpenRouterProvider(model)
    raise ValueError(f"unknown provider {name!r}")


def _unavailable_answer(reason: str) -> VerifiedAnswer:
    return VerifiedAnswer(fields={
        name: VerifiedField(
            status=FieldStatus.UNCONFIRMED,
            reason=f"provider unavailable: {reason}",
        )
        for name in FIELDS
    })


def _run_with_providers(
    doc: TranscriptDoc,
    primary: Provider,
    fallback: Optional[Provider],
    config: PipelineConfig,
    prompt_version: str,
    primary_label: str,
    fallback_label: Optional[str],
) -> PipelineResult:
    context = build_context(doc)
    start = time.perf_counter()
    try:
        result = primary.extract(context, doc.transcript, prompt_version)
        answer = verify(result.raw, context, doc.transcript, config)
        return PipelineResult(
            answer=answer,
            provider=primary_label,
            model=result.model,
            prompt_version=prompt_version,
            config_label=config.label,
            latency_ms=result.latency_ms,
            usage=result.usage,
            provider_used=primary_label,
            raw_extraction=result.raw,
            raw_text=result.raw_text,
        )
    except ProviderError as exc:
        primary_error = str(exc)
    if fallback is not None:
        try:
            result = fallback.extract(context, doc.transcript, prompt_version)
            answer = verify(result.raw, context, doc.transcript, config)
            return PipelineResult(
                answer=answer,
                provider=primary_label,
                model=result.model,
                prompt_version=prompt_version,
                config_label=config.label,
                latency_ms=(time.perf_counter() - start) * 1000.0,
                usage=result.usage,
                provider_used=fallback_label,
                fallback_used=True,
                error=f"primary failed: {primary_error}",
                raw_extraction=result.raw,
                raw_text=result.raw_text,
            )
        except ProviderError as exc:
            primary_error = f"{primary_error}; fallback failed: {exc}"
    return PipelineResult(
        answer=_unavailable_answer(primary_error),
        provider=primary_label,
        model=None,
        prompt_version=prompt_version,
        config_label=config.label,
        latency_ms=(time.perf_counter() - start) * 1000.0,
        provider_used=None,
        error=primary_error,
    )


def run_pipeline(
    doc: TranscriptDoc,
    provider_name: str = "offline",
    prompt_version: str = "trutrace-1.0.0",
    model: Optional[str] = None,
    provider: Optional[Provider] = None,
    fallback_provider_name: Optional[str] = None,
    fallback_model: Optional[str] = None,
    fallback_provider: Optional[Provider] = None,
) -> PipelineResult:
    config: PipelineConfig = get_config(prompt_version)
    primary = provider or make_provider(provider_name, model)
    primary_label = provider_name if provider is None else primary.name
    fallback = fallback_provider
    fallback_label = fallback_provider_name
    if fallback is None and fallback_provider_name is not None:
        fallback = make_provider(fallback_provider_name, fallback_model)
    if fallback is not None and fallback_label is None:
        fallback_label = fallback.name
    return _run_with_providers(
        doc, primary, fallback, config, prompt_version,
        primary_label, fallback_label,
    )


def run_batch(
    docs: list[TranscriptDoc],
    provider: Provider,
    prompt_version: str = "trutrace-1.0.0",
    fallback_provider: Optional[Provider] = None,
    provider_label: Optional[str] = None,
    fallback_label: Optional[str] = None,
) -> tuple[list[PipelineResult], dict]:
    """Run a batch through ONE provider instance.

    Sharing the instance is the point: a provider that dies mid run
    (see KillAfterProvider) dies for the rest of the batch, and each
    remaining transcript independently falls back or comes back
    unconfirmed. Partial results are preserved: the batch returns one
    result per input, in order, plus a summary of what served what.
    """
    config: PipelineConfig = get_config(prompt_version)
    label = provider_label or provider.name
    fb_label = fallback_label or (fallback_provider.name if fallback_provider else None)
    results = [
        _run_with_providers(doc, provider, fallback_provider, config,
                            prompt_version, label, fb_label)
        for doc in docs
    ]
    summary = {
        "total": len(results),
        "served_by_primary": sum(1 for r in results if r.provider_used == label),
        "served_by_fallback": sum(1 for r in results if r.fallback_used),
        "unavailable": sum(1 for r in results if r.provider_used is None),
    }
    return results, summary
