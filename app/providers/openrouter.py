"""The OpenRouter provider.

Two transports, one wire format:

Local development (default): talks to OpenRouter through the
registered connection's helper
(~/workspace/custom-connectors/custom.openrouter/bin/or_call.py): the
payload goes in on stdin, the full response JSON comes back on stdout,
including token usage and a measured latency. No API key ever touches
this process.

Hosted runs (OPENROUTER_API_KEY set in the environment, e.g. Railway,
where the helper does not exist): POSTs directly to the OpenRouter
API. The key is read from the environment at call time and placed
only in the Authorization header; it is never logged, printed, or
persisted anywhere.

Two models are benchmarked (see evals/): openai/gpt-4o-mini and
google/gemini-2.0-flash-001. The model is a constructor argument, so a
third model is a one-line change in the eval runner.
"""

import json
import os
import subprocess
import time
import urllib.error
import urllib.request

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

API_URL = "https://openrouter.ai/api/v1/chat/completions"

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

    def _send(self, payload: dict) -> dict:
        """Send one chat payload to OpenRouter; return the response dict.

        Uses the direct API when OPENROUTER_API_KEY is set in the
        environment (hosted runs), and the local helper subprocess
        otherwise. See the module docstring for the key-handling rules.
        """
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if api_key:
            request = urllib.request.Request(
                API_URL,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                method="POST",
            )
            try:
                with urllib.request.urlopen(request, timeout=180) as resp:
                    return json.loads(resp.read().decode("utf-8"))
            except urllib.error.HTTPError as exc:
                body = exc.read().decode("utf-8", "replace")[:500]
                raise OpenRouterError(
                    f"OpenRouter HTTP {exc.code} for model "
                    f"{self.model}: {body}"
                ) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                raise OpenRouterError(
                    f"OpenRouter request failed for model "
                    f"{self.model}: {exc}"
                ) from exc
        proc = subprocess.run(
            [HELPER, "chat"],
            input=json.dumps(payload),
            capture_output=True,
            text=True,
            timeout=180,
        )
        if proc.returncode != 0:
            stderr = proc.stderr.strip()
            last_line = stderr.splitlines()[-1] if stderr else ""
            raise OpenRouterError(
                f"or_call.py chat failed for model {self.model}: {last_line}"
            )
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as exc:
            raise OpenRouterError(f"helper returned non-JSON output: {exc}")

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
        response = self._send(payload)
        latency_ms = (time.perf_counter() - start) * 1000.0
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
