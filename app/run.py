"""CLI: run one transcript through the pipeline.

Usage (from the project root):
    python -m app.run datasets/transcripts/tyre_shop_contradiction.json
    python -m app.run datasets/transcripts/florist_roses_clean.json \
        --prompt-version baseline-naive
    python -m app.run datasets/transcripts/florist_roses_clean.json \
        --provider openrouter --model openai/gpt-4o-mini

Prints the verified answer as JSON: per-field value, status, evidence
and reason. The unconfirmed and uncertain fields are part of the output
on purpose: where a call failed to establish something is information,
not an error.
"""

import argparse
import json
import sys

from .pipeline import run_pipeline
from .schemas import TranscriptDoc


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one call transcript through TruTrace."
    )
    parser.add_argument("transcript", help="path to a transcript JSON file")
    parser.add_argument("--provider", default="offline",
                        choices=["offline", "openrouter"])
    parser.add_argument("--model", default=None,
                        help="OpenRouter model (required for --provider openrouter)")
    parser.add_argument("--prompt-version", default="trutrace-1.0.0",
                        choices=["baseline-naive", "trutrace-1.0.0"])
    args = parser.parse_args(argv)

    with open(args.transcript, encoding="utf-8") as fh:
        doc = TranscriptDoc.model_validate(json.load(fh))
    try:
        result = run_pipeline(
            doc,
            provider_name=args.provider,
            prompt_version=args.prompt_version,
            model=args.model,
        )
    except RuntimeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(
        {
            "id": doc.id,
            "business_name": doc.business_name,
            "product": doc.product,
            "question": doc.question,
            "provider": result.provider,
            "model": result.model,
            "prompt_version": result.prompt_version,
            "config": result.config_label,
            "latency_ms": round(result.latency_ms, 2),
            "usage": result.usage,
            "answer": result.answer.confirmed_values(),
            "fields": {
                name: f.model_dump()
                for name, f in result.answer.fields.items()
            },
        },
        indent=2,
    ))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
