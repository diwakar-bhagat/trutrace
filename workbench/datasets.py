"""Dataset splits for the Experiment Runner.

The splits are the frozen ones (datasets/SPLIT.md): dev 20, held-out
12, campaign 10, all 32. Loading reuses the eval suite's loaders so
the workbench runs exactly the cases the benchmark ran.

Label status, carried everywhere scores appear: the gold labels were
drafted by an AI coding agent and are pending Diwakar Bhagat's human
review. They are not validated ground truth.
"""

import json
import os

from evals.run_evals import load_case_dir, load_cases

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

LABELS_STATUS = (
    "AI drafted, pending human review: scores are measured against "
    "unreviewed labels, not validated ground truth"
)

# The gold-label version every run is scored against. The frozen
# labels in datasets/ (golden_dataset.jsonl + campaign/) are version
# gold-v1-ai-drafted: drafted by an AI coding agent, pending Diwakar
# Bhagat's human review. A completed human review lands as a NEW
# version (gold-v2-human-reviewed, exported by tools/gold_review.html)
# and never overwrites v1; when that happens this constant is bumped
# and new runs name the new version. See GOLD_REVIEW.md.
GOLD_LABELS_VERSION = "gold-v1-ai-drafted"

SPLIT_NAMES = ("dev", "heldout", "campaign", "all")


def load_split(name: str) -> list:
    if name == "campaign":
        return load_case_dir(os.path.join(ROOT, "datasets", "campaign"))
    cases = load_cases()
    if name == "all":
        return cases
    if name in ("dev", "heldout"):
        with open(os.path.join(ROOT, "datasets", "split.json")) as fh:
            ids = set(json.load(fh)[name])
        return [c for c in cases if c.id in ids]
    raise ValueError(f"unknown split {name!r}; choose from {SPLIT_NAMES}")


def split_info() -> list:
    return [
        {
            "name": name,
            "cases": len(load_split(name)),
            "labels_status": LABELS_STATUS,
        }
        for name in SPLIT_NAMES
    ]
