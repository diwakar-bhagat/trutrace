"""Pipeline configurations, keyed by prompt version.

A configuration is the whole harness stance, not just a prompt string:

- "baseline-naive" is the thin wrapper: take the provider's first reading
  of every field and assert it. No grounding enforcement, no hedge
  demotion, no contradiction detection, no stale/fee/entity filtering.
  It exists so the eval suite can measure what the harness adds.
- "trutrace-1.0.0" is the full harness: every verification stage on.

The improvement loop in reports/benchmark_results.md is the diff between
these two configurations over the same dataset and the same providers.
"""

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class PipelineConfig:
    prompt_version: str
    label_override: Optional[str] = None
    grounding: bool = True
    hedge_demotion: bool = True
    contradiction_detection: bool = True
    stale_filter: bool = True
    fee_filter: bool = True
    correction_supersede: bool = True
    product_restriction: bool = True
    product_mismatch_demotion: bool = True
    conditional_pricing: bool = True
    approximate_demotion: bool = True

    @property
    def label(self) -> str:
        if self.label_override:
            return self.label_override
        return "baseline" if self.prompt_version == "baseline-naive" else "current"


CONFIGS = {
    "baseline-naive": PipelineConfig(
        prompt_version="baseline-naive",
        grounding=False,
        hedge_demotion=False,
        contradiction_detection=False,
        stale_filter=False,
        fee_filter=False,
        correction_supersede=False,
        product_restriction=False,
        product_mismatch_demotion=False,
        conditional_pricing=False,
        approximate_demotion=False,
    ),
    "trutrace-1.0.0": PipelineConfig(prompt_version="trutrace-1.0.0"),
}

CURRENT_PROMPT_VERSION = "trutrace-1.0.0"
BASELINE_PROMPT_VERSION = "baseline-naive"


# Configs for file-defined prompt versions (the Prompt Lab bridge).
# workbench/prompt_store.py registers one config per prompt file it
# loads: profile "full" maps to every toggle on, profile "passthrough"
# to every toggle off with a baseline label override, so the
# verification engine treats the version exactly as its file declares.
# The two code-defined configs above are unchanged.
_REGISTERED_CONFIGS = {}


def register_config(key: str, config: PipelineConfig) -> None:
    _REGISTERED_CONFIGS[key] = config


def get_config(prompt_version: str) -> PipelineConfig:
    if prompt_version in CONFIGS:
        return CONFIGS[prompt_version]
    if prompt_version in _REGISTERED_CONFIGS:
        return _REGISTERED_CONFIGS[prompt_version]
    raise ValueError(
        f"unknown prompt version {prompt_version!r}; "
        f"choose from {sorted(CONFIGS) + sorted(_REGISTERED_CONFIGS)}"
    )
