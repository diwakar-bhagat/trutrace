"""Prompt assembly, versioned.

Prompts are assembled in one place from a template, the answer schema,
the grounding rules, the buyer's question and the transcript, so a prompt
change is a code change the eval suite can grade. The scorecard records
which version produced its numbers.

Two versions exist on purpose:

- "baseline-naive": the thin-wrapper prompt. Extract the values, return
  JSON. No evidence requirement, no candidate lists, no quality rules.
  This is what most demos ship; the eval suite measures what it costs.
- "trutrace-1.0.0": the harness prompt. Every field must carry its
  evidence sentence, all price and timing candidates must be listed, and
  the rules state plainly what may not be asserted.
"""

from .schemas import FIELDS

SCHEMA_DESCRIPTION = """{
  "price": number or null,
  "currency": "USD" or null,
  "availability": "in_stock" | "out_of_stock" | "available" | null,
  "quantity_or_stock": string or null,
  "delivery_or_pickup": "delivery" | "pickup" | null,
  "timing": string or null,
  "contact_next_step": string or null
}"""

_NAIVE_TEMPLATE = """You extract a structured answer from a phone call between an agent
and a local business. The business was asked: "{question}"

Extract exactly this schema:
{schema}

Transcript:
\"\"\"
{transcript}
\"\"\"

Respond with a JSON object with the schema fields only."""

_TRUTRACE_RULES = """Rules:
- Only state what the seller actually confirmed on the call. If a field was
  never confirmed, return null for it. Never guess a quantity, never round
  a vague or hedged answer into a fact.
- If the seller gives two different prices, return all of them under
  "price_candidates" instead of picking one. Do the same for conflicting
  times under "timing_candidates".
- For every non-null field, include an "evidence" object mapping the field
  name to the exact sentence from the transcript that supports it, copied
  word for word. If you cannot quote a supporting sentence, the field
  must be null.
- A price quoted for a different product, a delivery or setup fee, or a
  price the seller says has changed is not the product's price.
- Return JSON only, no commentary."""

_TRUTRACE_TEMPLATE = """You extract a structured answer from a phone call between an agent
and a local business. The business was asked: "{question}"

Extract exactly this schema:
{schema}

{rules}

Transcript:
\"\"\"
{transcript}
\"\"\"

Respond with a JSON object with the schema fields, a "price_candidates"
list of {{"value": number, "evidence": sentence}}, a "timing_candidates"
list of {{"value": string, "evidence": sentence}}, and an "evidence"
object."""

_TEMPLATES = {
    "baseline-naive": _NAIVE_TEMPLATE,
    "trutrace-1.0.0": _TRUTRACE_TEMPLATE,
}


# ---------------------------------------------------------------------------
# Registered prompt versions (the Prompt Lab bridge).
#
# The workbench stores prompts as immutable files on disk (see
# workbench/prompt_store.py) and registers them here at load time. A
# registered version is two texts, a system part and a user part, with
# {question}, {schema} and {transcript} placeholders substituted by
# plain replacement (never str.format, so edited text may contain any
# braces it likes). The two code-defined versions above are untouched:
# registered versions are an addition, not a replacement, and the eval
# suite's behaviour for the legacy versions is unchanged.
# ---------------------------------------------------------------------------

_REGISTERED = {}


def register_prompt_version(key: str, system: str, user: str) -> None:
    """Register (or replace the registration of) a file-defined prompt
    version. Immutability is enforced by the store, which never writes
    the same version twice; this registry only holds what the store
    loaded."""
    _REGISTERED[key] = {"system": system, "user": user}


def registered_prompt_versions() -> list:
    return sorted(_REGISTERED)


def _render_registered(template: str, question: str, transcript: str) -> str:
    return (
        template.replace("{question}", question)
        .replace("{schema}", SCHEMA_DESCRIPTION)
        .replace("{transcript}", transcript.strip())
    )


def build_prompt(question: str, transcript: str, prompt_version: str) -> str:
    """Assemble the extraction prompt for one call under one version."""
    if prompt_version in _REGISTERED:
        parts = _REGISTERED[prompt_version]
        system = _render_registered(parts["system"], question, transcript)
        user = _render_registered(parts["user"], question, transcript)
        return f"{system}\n\n{user}" if system else user
    if prompt_version not in _TEMPLATES:
        raise ValueError(f"unknown prompt version {prompt_version!r}")
    template = _TEMPLATES[prompt_version]
    if prompt_version == "baseline-naive":
        return template.format(
            question=question, schema=SCHEMA_DESCRIPTION,
            transcript=transcript.strip(),
        )
    return template.format(
        question=question, schema=SCHEMA_DESCRIPTION,
        rules=_TRUTRACE_RULES, transcript=transcript.strip(),
    )


__all__ = [
    "FIELDS", "SCHEMA_DESCRIPTION", "build_prompt",
    "register_prompt_version", "registered_prompt_versions",
]
