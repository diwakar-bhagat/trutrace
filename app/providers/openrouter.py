"""The OpenRouter provider.

Talks to OpenRouter through the registered connection's helper
(~/workspace/custom-connectors/custom.openrouter/bin/or_call.py): the
payload goes in on stdin, the full response JSON comes back on stdout,
including token usage and a measured latency. No API key ever touches
this process.

Two models are benchmarked (see evals/): openai/gpt-4o-mini and
google/gemini-2.0-flash-001. The model is a constructor argument, so a
third model is a one-line change in the eval runner.
"""

import json
import os
import subprocess
import time

from ..context_builder import ExtractionContext
from ..prompts import build_prompt
from ..schemas import (
    FIELDS,
    PriceCandidate,
    RawExtraction,
    RawField,
    TimingCandidate,
)
from .base import ProviderError, ProviderResult

HELPER = os.path.expanduser(
    "~/workspace/custom-connectors/custom.openrouter/bin/or_call.py"
)

DEFAULT_MODELS = ["openai/gpt-4o-mini", "google/gemini-2.0-flash-001"]


class OpenRouterError(ProviderError):
    pass


def _parse_content(content: str) -> dict:
    content = content.strip()
    if content.startswith("```"):
        content = content.strip("`")
        if content.startswith("json"):
            content = content[4:]
    return json.loads(content)


class OpenRouterProvider:
    name = "openrouter"

    def __init__(self, model: str, temperature: float = 0):
        self.model = model
        self.temperature = temperature

    def extract(
        self, context: ExtractionContext, transcript: str, prompt_version: str
    ) -> ProviderResult:
        prompt = build_prompt(context.question, transcript, prompt_version)
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": self.temperature,
        }
        start = time.perf_counter()
        proc = subprocess.run(
            [HELPER, "chat"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=180,
        )
        latency_ms = (time.perf_counter() - start) * 1000.0
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            last_line = stderr.splitlines()[-1] if stderr else ""
            raise OpenRouterError(
                f"or_call.py chat failed for model {self.model}: {last_line}"
            )
        try:
            response = json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"helper returned non-JSON output: {exc}")
        if "error" in response:
            raise OpenRouterError(
                f"OpenRouter error for model {self.model}: "
                f"{json.dumps(response['error'])[:500]}"
            )
        usage = response.get("usage") or {}
        try:
            content = response["choices"][0]["message"]["content"]
            parsed = _parse_content(content)
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise OpenRouterError(
                f"unparseable model output for {self.model}: {exc}"
            )

        raw = RawExtraction()
        evidence = parsed.get("evidence") or {}
        for name in FIELDS:
            value = parsed.get(name)
            if value is not None:
                raw.fields[name] = RawField(
                    value=value, evidence=evidence.get(name)
                )
        for cand in parsed.get("price_candidates") or []:
            try:
                raw.price_candidates.append(
                    PriceCandidate(
                        value=float(cand.get("value")),
                        evidence=cand.get("evidence"),
                    )
                )
            except (TypeError, ValueError):
                continue
        if not raw.price_candidates and parsed.get("price") is not None:
            try:
                raw.price_candidates.append(
                    PriceCandidate(
                        value=float(parsed["price"]),
                        evidence=evidence.get("price"),
                    )
                )
            except (TypeError, ValueError):
                pass
        for cand in parsed.get("timing_candidates") or []:
            if isinstance(cand, dict) and cand.get("value"):
                raw.timing_candidates.append(
                    TimingCandidate(
                        value=str(cand["value"]).lower(),
                        evidence=cand.get("evidence"),
                    )
                )
        if not raw.timing_candidates and parsed.get("timing"):
            raw.timing_candidates.append(
                TimingCandidate(
                    value=str(parsed["timing"]).lower(),
                    evidence=evidence.get("timing"),
                )
            )
        if raw.price_candidates:
            raw.currency_evidence = raw.price_candidates[0].evidence

        return ProviderResult(
            raw=raw,
            latency_ms=response.get("_latency_ms", latency_ms),
            model=response.get("model", self.model),
            usage={
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
                "total_tokens": usage.get("total_tokens"),
                "reported_cost_usd": usage.get("cost"),
            },
        )
