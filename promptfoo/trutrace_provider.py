"""Promptfoo provider: execution delegated to the TruTrace pipeline.

Promptfoo's model is prompt x provider, with the provider receiving
the rendered prompt text. TruTrace's pipeline builds its own prompt
from a version key, so this provider maps the rendered prompt back to
the registered Prompt Lab version it matches exactly, then runs the
case through app.pipeline.run_pipeline with that version. There is
exactly one extraction path and one verification engine; this file
adds no second implementation of either.

The provider is the deterministic offline provider, so a Promptfoo
run is free and reproducible. Switching the comparison to a live
model is a change to the run_pipeline call below, nothing else.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.pipeline import run_pipeline  # noqa: E402
from app.prompts import build_prompt, registered_prompt_versions  # noqa: E402
from workbench import prompt_store  # noqa: E402
from workbench.datasets import load_split  # noqa: E402

_CASES = {}


def _case(case_id):
    if not _CASES:
        for doc in load_split("campaign"):
            _CASES[doc.id] = doc
    return _CASES[case_id]


def call_api(prompt, options, context):
    prompt_store.load_all()
    vars_ = (context or {}).get("vars", {})
    doc = _case(vars_["case_id"])
    key = None
    for candidate in registered_prompt_versions():
        if build_prompt(doc.question, doc.transcript, candidate) == prompt:
            key = candidate
            break
    if key is None:
        return {
            "error": "rendered prompt matches no registered TruTrace "
                     "prompt version; refusing to run an unregistered prompt"
        }
    result = run_pipeline(doc, provider_name="offline", prompt_version=key)
    if result.provider_used is None:
        return {"error": f"pipeline provider failed: {result.error}"}
    output = {
        name: {
            "value": f.value,
            "status": f.status.value,
            "condition": f.condition,
            "evidence": f.evidence,
        }
        for name, f in result.answer.fields.items()
    }
    return {"output": json.dumps(output)}
