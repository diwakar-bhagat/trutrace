"""Generate promptfoo/tests.json from the campaign dataset.

The test cases are the real campaign cases (id, question, transcript
as vars); nothing is retyped. Re-run after the dataset changes:

  .venv/bin/python promptfoo/generate_tests.py
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workbench.datasets import load_split  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    tests = [
        {
            "description": doc.id,
            "vars": {
                "case_id": doc.id,
                "question": doc.question,
                "transcript": doc.transcript,
            },
        }
        for doc in load_split("campaign")
    ]
    out = os.path.join(HERE, "tests.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(tests, fh, indent=2, ensure_ascii=False)
    print(f"wrote {out}: {len(tests)} tests")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
