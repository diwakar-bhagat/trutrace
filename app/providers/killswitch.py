"""Providers that fail on demand.

These exist so degradation is testable, not theatrical: the test suite
and the degradation demo wrap a real provider in a KillAfterProvider
and watch the pipeline fall back. The death is simulated; everything
the pipeline does in response is the real code path.

- DeadProvider: every call raises ProviderError.
- KillAfterProvider: delegates to a wrapped provider and raises
  ProviderError once `kill_after` successful calls have happened,
  simulating a provider that dies mid run.
"""

from ..context_builder import ExtractionContext
from .base import ProviderError, ProviderResult


class DeadProvider:
    name = "dead"

    def __init__(self, message: str = "provider is down (simulated)"):
        self.message = message

    def extract(
        self, context: ExtractionContext, transcript: str, prompt_version: str
    ) -> ProviderResult:
        raise ProviderError(self.message)


class KillAfterProvider:
    """Wrap a provider; let `kill_after` calls through, then die."""

    def __init__(self, inner, kill_after: int):
        self.inner = inner
        self.kill_after = kill_after
        self.calls = 0
        self.name = f"killswitch({getattr(inner, 'name', 'provider')})"

    def extract(
        self, context: ExtractionContext, transcript: str, prompt_version: str
    ) -> ProviderResult:
        if self.calls >= self.kill_after:
            raise ProviderError(
                f"provider killed after {self.calls} successful calls (simulated)"
            )
        result = self.inner.extract(context, transcript, prompt_version)
        self.calls += 1
        return result
