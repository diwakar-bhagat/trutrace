"""Promptfoo prompt function: the Prompt Lab version baseline-naive@1.0.0.

Returns the exact prompt text the TruTrace pipeline assembles for
that version (app.prompts.build_prompt), so the comparison matrix
shows and runs the real prompt, not a copy pasted into a config.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.prompts import build_prompt  # noqa: E402
from workbench import prompt_store  # noqa: E402


def get_prompt(context):
    prompt_store.load_all()
    vars_ = context["vars"]
    return build_prompt(vars_["question"], vars_["transcript"], "baseline-naive@1.0.0")
