"""Flatten datasets/transcripts/*.json into datasets/golden_dataset.jsonl.

One JSON object per line: the eval suite's input. The transcript files
are the source of truth; this file is generated, never hand-edited.

Usage: python datasets/build_golden.py
"""

import glob
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))


def main() -> int:
    paths = sorted(glob.glob(os.path.join(HERE, "transcripts", "*.json")))
    out_path = os.path.join(HERE, "golden_dataset.jsonl")
    with open(out_path, "w", encoding="utf-8") as out:
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            out.write(json.dumps(doc, ensure_ascii=False) + "\n")
    print(f"wrote {len(paths)} cases to {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
