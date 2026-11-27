# TruTrace audit — before the Prompt Lab + Experiment Runner slice

Audited 27 November 2026, before any change was made for the workbench
build. This document records what exists, how it behaves, and where the
gaps against the target slice are. Nothing in the pipeline was changed
during the audit; the existing 38 tests pass (`python -m unittest
discover -s tests`).

## 1. Pipeline structure and entry points

The pipeline is a single linear path (`app/pipeline.py`):

```
transcript -> context assembly -> provider extraction -> verification -> answer
```

- `app/context_builder.py` builds an `ExtractionContext` from a
  `TranscriptDoc`: business, product, the buyer's question, requested
  fields, and token sets (product tokens, stems, head noun, question
  tokens) that let the verification engine recognise fees, stale
  prices and wrong-product prices.
- Providers (`app/providers/`) read the call and return a
  `RawExtraction` plus metadata (latency, token usage). Providers
  report; they never judge. Two are wired:
  - `offline.py`: a deterministic rule-based reader (regex patterns
    over seller sentences only). No network, no key. It is the
    regression baseline.
  - `openrouter.py`: an adapter that shells out to the registered
    connection helper (`~/workspace/custom-connectors/custom.openrouter/bin/or_call.py`,
    `chat` command, payload on stdin, full response JSON on stdout).
    No API key touches this process. It parses the model's JSON into
    a `RawExtraction` (fields, price candidates, timing candidates,
    evidence map) and returns token usage and the provider-reported
    cost from the response's `usage` block.
  - `killswitch.py`: wrappers (`DeadProvider`, `KillAfterProvider`)
    that kill a provider on demand for degradation tests.
- `app/verification/engine.py` (`verify()`) takes the raw extraction
  and decides, field by field, what the call established. Under the
  full configuration it runs: candidate enrichment (fee, threshold,
  stale, correction, per-unit and qualifier tagging in
  `candidates.py`), evidence grounding (a confirmed field must cite a
  span that actually appears in the transcript,
  `evidence_validator.py`), hedge / approximate / starting-price
  demotion (`confidence_policy.py`), contradiction detection across
  the whole call (`contradiction_detector.py`), stale-price and
  wrong-product rejection, correction supersede, and conditional
  pricing resolution. Speaker and timestamp proof is derived from the
  evidence span's transcript line (`app/textutil.py`), never reported
  by the provider.
- Degradation is contractual (`pipeline.run_pipeline` /
  `run_batch`): if the primary provider raises `ProviderError`, the
  batch falls back per transcript to a second provider when one is
  configured; if none is available, the answer is every field
  unconfirmed with the failure recorded. A dead provider produces an
  honest empty answer, never an exception and never an invented one.

Entry points:

- `python -m app.run <transcript.json> [--provider ...] [--model ...]
  [--prompt-version ...]` — one call through the pipeline, prints the
  verified answer as JSON.
- `evals/run_evals.py` — one provider x one prompt version over the
  full 32-case set; writes a scorecard JSON.
- `evals/run_final.py --set heldout|campaign --runs N` — the frozen
  final protocol: 3 runs per configuration, per-run artifacts plus an
  aggregated summary.
- `evals/build_report.py` — regenerates `reports/benchmark_results.md`
  from the recorded artifacts.
- `scripts/degradation_demo.py`, `scripts/load_test.py` — the
  degradation record and the labelled load runs.
- `demo/build_demo.py` — builds the static demo page from real
  outputs. The demo is live on Vercel and is out of scope for this
  build: it is not modified.

Configuration (`app/config.py`): a `PipelineConfig` is keyed by
prompt version and carries the verification toggles (grounding, hedge
demotion, contradiction detection, stale/fee filters, correction
supersede, product restriction and mismatch demotion, conditional
pricing, approximate demotion). Two configurations exist:
`baseline-naive` (every toggle off; the engine is a pass-through that
asserts the provider's first reading) and `trutrace-1.0.0` (every
toggle on). The config's `label` is "baseline" for the first and
"current" for everything else, and `verify()` branches on that label.

## 2. Where prompts live today, and whether they are versioned

Prompts live in code, in `app/prompts.py`. `build_prompt(question,
transcript, prompt_version)` assembles one user-message string from a
template, the declared output schema (`SCHEMA_DESCRIPTION`), and, for
the full version, a rules block (`_TRUTRACE_RULES`). Two versions
exist:

- `baseline-naive`: schema fields only, no evidence requested, no
  candidate lists, no quality rules. This is the thin-wrapper prompt
  most demos ship.
- `trutrace-1.0.0`: every field must carry an evidence sentence
  copied word for word, all price and timing candidates must be
  listed, and the rules state plainly what may not be asserted.

Versioning today is nominal, not real:

- A "version" is a string constant in a dict in a source file. There
  is no prompt artifact on disk, no metadata (author, date, parent,
  notes), and no model-parameter record: the OpenRouter provider
  hardcodes `temperature: 0` and takes the model from its constructor.
- Editing a prompt means editing code. Nothing prevents silently
  changing the text of `trutrace-1.0.0` after runs were recorded
  against it; the scorecards record the version string, not a hash or
  the text, so a past run cannot be reproduced exactly from its
  artifact alone.
- Prompt version and verification configuration are fused: the same
  string keys both `app/prompts.py` templates and `app/config.py`
  configs, and `get_config()` raises for any unknown version. There
  is no way to run a new prompt text without a code change in two
  files.

## 3. Dataset integrity

- 32 annotated cases in `datasets/transcripts/` (one JSON per case),
  flattened to `datasets/golden_dataset.jsonl` by
  `datasets/build_golden.py`. Each case is a `TranscriptDoc`: id,
  business, product, question, requested fields, taxonomy, transcript,
  and a gold annotation for the same 7 fields the pipeline outputs
  (`app/schemas.py`: price, currency, availability,
  quantity_or_stock, delivery_or_pickup, timing, contact_next_step),
  each with value, status, evidence, condition, and (for labelled
  transcripts) speaker and timestamp.
- Taxonomy coverage across the 32: contradiction 5,
  conditional_pricing 4, uncertain_inventory 4, missing_information
  4, clean 4, ambiguous_quantity 3, temporal_mismatch 3,
  entity_confusion 3, unsupported_inference 2.
- Split (`datasets/SPLIT.md`, `datasets/split.json`): frozen 27
  November 2026 at 20 dev / 12 held-out. Tuning after the freeze may
  use only the dev 20; held-out is opened only for final evaluation.
- Campaign slice: 10 florist transcripts in `datasets/campaign/`
  (also `datasets/campaign.jsonl`), one query ("Red roses, a dozen,
  delivery today"), with [mm:ss] speaker labels and ASR-style noise.
  The campaign is part of neither split and was never tuned against.
- **Gold label provenance: the transcripts and gold labels were
  drafted by an AI coding agent during the build and are pending
  Diwakar Bhagat's human review.** This is stated in the README and
  in `reports/benchmark_results.md`. Gold is one annotator's
  judgement, unreviewed. Every score in this repo is measured against
  unreviewed labels and must be presented that way.
- **Freeze disclosure:** the split was frozen after a first build
  round whose fixes were driven by failures observed across all 32
  cases (offline timing patterns, the conditional-pricing
  discriminator, two stopwords, the currency-evidence fallback).
  Held-out numbers are therefore not a clean-room measurement; the
  report and README say so. Post-freeze changes were feature work
  (proof fields, provider fallback, reporting), not tuning.

## 4. The verification engine's checks and how metrics are computed

The engine's per-field checks are listed in section 1. Scoring lives
in `evals/metrics.py` and `evals/run_evals.py`, and the correctness
rules are deliberately strict:

- gold confirmed: correct iff predicted confirmed, same value
  (normalised), and the condition matches (token subset either way).
- gold unconfirmed: correct iff predicted unconfirmed with no value.
- gold uncertain: correct iff predicted uncertain or unconfirmed;
  asserting it as confirmed is exactly the failure this project
  exists to catch.
- gold conflicting: correct iff predicted conflicting.
- A predicted confirmed field that gold does not confirm with the
  same value and condition is an **unsupported claim** — the critical
  failure metric.

Five metrics are computed per run and never averaged into one score:

1. **Extraction accuracy**: fields correct, as a count of total
   fields (and per-field rates).
2. **Evidence coverage**: of predicted confirmed fields, the share
   whose cited span actually appears in the transcript
   (`span_in_transcript`).
3. **Unsupported claim rate**: unsupported claims as a count of
   predicted confirmed fields.
4. **Contradiction detection**: recall over fields gold marks
   conflicting.
5. **Operational efficiency**: measured latency (mean, p50, p95)
   and, for paid models, token usage and cost. Cost is computed from
   returned usage counts at published per-token prices
   (`evals/run_evals.py` `PRICES`: gpt-4o-mini $0.15 in / $0.60 out
   per 1M; gemini-2.0-flash-001 $0.10 in / $0.40 out), with the
   provider-reported cost recorded alongside as a check; in every
   completed gpt-4o-mini run the two matched.

The final protocol (`evals/run_final.py`) runs each configuration 3
times per set and reports per-run counts with denominators plus the
spread, because model output varies between runs even at temperature
0. Proof accuracy (speaker + timestamp matching gold, over
gold-confirmed fields that carry gold proof) is computed from the
scorecard rows for the campaign.

## 5. Run artifacts that exist, and their format

- `evals/results/*_scorecard.json` (from `run_evals.py`): one JSON
  per provider x configuration over the full 32. Fields: provider,
  model, prompt_version, config label, cases run/total, error (null
  or {case, message}), the five metrics with counts, a `failures`
  list (case, taxonomy, field, gold object, predicted object), and a
  `cases` list with per-field gold/predicted status, value, condition,
  correctness and proof fields.
- `evals/results/final_<set>_<provider>_<config>_run<N>.json`: the
  same scorecard shape, one per run of the frozen protocol, for the
  held-out and campaign sets. Two stopped attempts are preserved with
  `_error429` in the filename.
- `evals/results/final_<set>_summary.json`: the aggregated spread
  across the 3 runs per cell, counts as "X of Y" strings.
- `evals/results/load_<n>_<kind>.json`: the load records (10 and 100
  real, 1000 simulated and labelled as such).
- `reports/degradation_record.json`: the two degradation scenarios
  with per-transcript provider-used records.
- `reports/benchmark_results.md`: the human-readable report,
  regenerated from the artifacts by `evals/build_report.py`.

What the artifacts do not hold: the prompt text (only the version
string), the model parameters, the raw model output, or a per-case
trace that ties input, output, latency, tokens and evaluation into
one record. The scorecard's per-case rows are close, but the raw
extraction and the assembled prompt are gone once a run finishes.

## 6. Provider status

- **OpenRouter via the helper** (`or_call.py check` at audit time):
  key limit $100, $0.0515 spent, free-tier flag off for this key's
  usage accounting as recorded at connection time; the helper is the
  only path, and no key is in the repo or the environment.
- **openai/gpt-4o-mini: works.** It is the model behind every model
  row in the benchmark: held-out and campaign, baseline and current,
  3 runs each, plus the 10 and 100 real load runs. Zero errors in the
  load runs; two eval attempts stopped on HTTP 429 and were re-run
  once after the limit cleared (artifacts preserved).
- **google/gemini-2.0-flash-001: has NEVER run successfully.**
  OpenRouter returned HTTP 404 for that model id on the first call of
  both configurations; the runs were stopped per protocol, not
  retried in a loop and not silently re-pointed at another model id.
  The failure is recorded in
  `evals/results/openrouter_gemini-2.0-flash-001_baseline_scorecard.json`
  and `..._current_scorecard.json` (cases_run 0, error message
  recorded). Provider status must stay explicit: Gemini is
  failed / not verified until a real successful run is recorded.
- **Offline provider: works**, deterministically, and its current
  configuration is clean on the held-out set (84 of 84, 0 of 45
  unsupported) with the standing caveat that its rules and the
  dataset grew up together, so that row shows self-consistency. The
  model rows are the independent check.

## 7. Evaluation and observability frameworks: assessment

Reference set studied for this layer: Promptfoo, DeepEval, Langfuse,
Arize Phoenix, Comet Opik, Ragas, OpenAI Evals (and the OpenAI
evaluation best-practices guidance), Inspect AI, Pydantic AI, and
LangChain AgentEvals. The standing rule for all of them: **the
existing verification engine is the one source of truth for
correctness.** Frameworks may run configurations, record traces, or
add a metric the custom checks do not cover; none of them replaces
or duplicates the engine's field-level evidence checks, because no
generic LLM-judge metric can independently establish whether a
seller actually confirmed a price.

- **Promptfoo** (matrix testing over prompt x model): fits the
  experiment-runner axis directly — the same dataset and prompts
  across configurations, with assertions. Its assertions can call
  this repo's own scoring (`evals/metrics.py`) from a Python
  assertion, so correctness still comes from the engine. Requires
  Node >= 22.22; Node v24.22.1 and npm/npx 10.9.4 are present on this
  machine. Verdict: integrate for systematic comparison, calling the
  same prompts and dataset, not a parallel toy setup.
- **DeepEval** (Python test cases and metrics, pytest-shaped): its
  deterministic value is thin here — most of its headline metrics
  (faithfulness, answer relevancy, hallucination) are LLM-judged and
  would need a judge model and a second, weaker correctness story
  next to the engine's deterministic checks. It earns a place only
  if it installs cleanly in the project venv and contributes a
  metric the custom checks do not cover. Verdict: attempt the
  install; integrate only on a clean install plus a non-duplicative
  metric, otherwise record and move on.
- **Langfuse** (prompt management, versioning, traces): the trace
  model is the right shape — prompt version, model, input, output,
  tokens, latency, evaluation outcomes per case. But Langfuse needs
  an account and API keys, which we do not have, and faking an
  integration is not an option. Verdict: build local trace records
  in the Langfuse shape now; mark Langfuse "not connected" in the UI
  and reports until keys exist.
- **Arize Phoenix** (OpenTelemetry-based tracing and evaluation,
  self-hostable, runs locally with no account): the strongest
  self-hosted tracing candidate. It can run as a local server on
  this machine, ingest spans over OTLP, and needs no external keys —
  which removes exactly the blocker Langfuse has. Its evaluation
  helpers are LLM-judge oriented, so traces yes, correctness no:
  spans would carry the engine's own verdicts as attributes.
  Verdict: the recommended self-hosted tracing option when tracing
  outgrows local JSON records; not required for this slice.
- **Comet Opik** (open-source tracing and evaluation, self-hostable
  via Docker, also a hosted tier): comparable to Phoenix in shape —
  traces, datasets, experiments, LLM-judge evaluations. Self-hosting
  is heavier (a multi-service Docker deployment) than Phoenix's
  single local server, and its experiment model overlaps the runner
  this slice builds. Verdict: a credible alternative to Phoenix;
  second choice on operational weight for a one-person project.
- **Ragas** (RAG evaluation): TruTrace is not a retrieval system;
  its metrics (faithfulness to retrieved context, context precision)
  do not map onto transcript evidence grounding, which the engine
  already checks deterministically. Verdict: not applicable here.
- **OpenAI Evals / evaluation best practices**: a hosted,
  OpenAI-model-centric harness; the guidance (grade with
  deterministic checks where possible, keep evals close to the
  failure taxonomy, never tune on the test set) matches what this
  repo already does. Verdict: methodology reference only; the
  harness itself would tie runs to one provider's platform.
- **Inspect AI** (UK AISI's eval framework): strong task/scorer
  model and transcript logging, aimed at capability and safety
  evaluations of frontier models. Heavier than this slice needs and
  its scorers would sit beside, not inside, the engine. Verdict:
  reference for eval design; not adopted.
- **Pydantic AI**: an agent framework, not an evaluator. The repo
  already validates with Pydantic v2 schemas (`app/schemas.py`),
  which is the part that matters here. Verdict: not needed; no agent
  framework is introduced.
- **LangChain AgentEvals**: trajectory and agent-step evaluation for
  LangChain agents. TruTrace has no agent trajectory — one
  extraction call, then deterministic verification. Verdict: not
  applicable.

Net position for this slice: Promptfoo for the comparison matrix,
local Langfuse-shaped trace records for observability (Phoenix as
the named self-hosted upgrade path, Opik as the alternative),
DeepEval only if it installs cleanly and adds a non-duplicative
metric, and the verification engine unchanged as the judge.

## 8. Target stack direction

Recorded as direction, not built in this slice: the eventual
workbench is Next.js (frontend) + FastAPI (experiment and evaluation
endpoints) + Pydantic schemas + PostgreSQL (datasets, prompt
metadata, runs), with Cloudflare and Railway as the platform
references. This slice deliberately stays on the existing Python
codebase with file-persisted prompts and runs, so the slice can be
measured before any stack migration is priced.

**Deployment rule (binding): the workbench is not deployed on
Vercel.** If this slice needs a deployment target it is Railway or
Cloudflare; for this slice it stays local, launched with one
command. The existing static demo on Vercel is a separate,
already-live artifact: it is not modified, moved, or redeployed in
this build; any migration of it is Diwakar's separate decision.

## 9. Gaps against the target slice

Target: Prompt Lab (open, clone, edit, save immutable versions,
compare versions, configure model parameters) + Experiment Runner
(run a prompt version against the dataset through the existing
engine, persist outputs and measured metrics, compare runs on
identical inputs, inspect individual failures with evidence and
trace), with the custom checks primary, DeepEval/Promptfoo in
supporting roles, and trace records in place of a Langfuse
connection.

1. **No prompt artifacts.** Prompts are code strings (section 2).
   The Lab needs prompts as first-class, immutable, on-disk version
   files with metadata and model parameters, plus a registry so the
   pipeline can run a file-defined version without code edits — and
   a minimal bridge in `app/prompts.py` / `app/config.py` so a file
   version resolves to a template and a verification profile.
2. **No parameter surface.** Temperature is hardcoded in the
   provider; the model is a constructor argument only. The Lab's
   "configure model parameters" needs the provider to accept the
   prompt version's declared parameters.
3. **No run persistence of the workbench kind.** Scorecards exist
   (section 5) but runs are not first-class objects tying together
   prompt version (with text), dataset split, per-case outputs,
   evidence, traces, and cost in one place, and there is no run
   comparison view. The runner must persist all of it under `runs/`.
4. **No failure inspector.** Failures exist as rows in scorecard
   JSON; there is no way to open one case and see transcript,
   expected, actual, evidence spans, the engine's reasons, and the
   trace record together.
5. **No interface.** Everything is CLI. The slice needs a local
   workbench UI: prompt list/open, editor with clone/save-as-version,
   version compare (text and parameter diff), experiment setup and
   run, run comparison table, failed-case inspector.
6. **No trace records.** Langfuse is not connected (no account, no
   keys) and nothing emits traces. The slice builds local trace
   records in the Langfuse shape and labels them as such, with
   Langfuse status explicit.
7. **Provider status is implicit.** Gemini's failure lives in a
   scorecard file and the report prose. The UI must surface provider
   status explicitly: gpt-4o-mini verified, Gemini failed (HTTP 404)
   / not verified, offline available.
8. **Label status is prose-only.** "AI drafted, pending human
   review" is stated in documents; wherever the UI shows a score it
   must carry that status with it, so no screen presents evaluation
   numbers as validated ground truth.
