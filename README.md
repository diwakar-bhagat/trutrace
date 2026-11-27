# TruTrace

Verified answers from seller calls, with the evidence left in.

TruTrace reads a sales-call transcript and produces a structured
answer (price, currency, availability, quantity, delivery, timing,
next step) where **every field carries a status and its proof**:

- **confirmed**: the seller stated it plainly, and the field cites the
  exact transcript span, plus the speaker and timestamp where the
  transcript is labelled.
- **uncertain**: something was suggested but hedged, approximate or
  conditional ("around $35, I think"). The value is shown as
  unverified, never asserted.
- **unconfirmed**: the call never established it. The honest value is
  null.
- **conflicting**: the call states two incompatible things. Both are
  reported; neither is asserted.

The point is the discipline, demonstrated end to end on one thin
slice: a baseline that asserts hedges as facts, a verification layer
that stops it doing that, an eval suite that measures the difference,
a provider that dies mid run, and the numbers from all of it.

By Diwakar Bhagat.

## The slice: one campaign

One query, run against ten synthetic florist sellers: **"Red roses, a
dozen, delivery today."** The transcripts (`datasets/campaign/`)
carry [mm:ss] speaker labels, ASR-style noise and hedged answers. On
the showcase call, the seller says "around $35, I think", "usually in
stock", "probably tomorrow morning". The naive baseline returns $35
confirmed, in stock confirmed, tomorrow morning confirmed. TruTrace
returns all three as uncertain, each with its span, speaker and
timestamp attached. That contrast is pinned by an automated test
(`tests/test_campaign.py`), not just claimed here.

The wider 32-case dataset (`datasets/transcripts/`) is the eval and
regression backbone: 32 annotated calls across a failure taxonomy
(conditional pricing, ambiguous quantity, uncertain inventory,
contradiction, missing information, temporal mismatch, entity
confusion, unsupported inference, plus clean cases).

## Authorship of the expected answers

The transcripts and gold labels in this repository were drafted by an
AI coding agent during the build and are pending Diwakar Bhagat's
human review. Gold is one annotator's judgement, unreviewed; the
scoring rules treat a hedged value as not confirmed even when it
later turns out right, because the promise is verified answers, not
lucky ones.

## Architecture

```
transcript -> context assembly -> provider extraction -> verification -> answer
```

- **Context assembly** (`app/context_builder.py`): business, product,
  the buyer's question, requested fields.
- **Providers** (`app/providers/`): read the call and report what
  they found, including every price, timing and availability
  statement, not just their best guess. Providers report; they do not
  judge. Two are wired up: a deterministic offline rule provider, and
  an OpenRouter adapter (any model; the runs here used
  gpt-4o-mini). A killswitch wrapper can kill a provider on demand
  for degradation tests.
- **Verification engine** (`app/verification/`): schema validation,
  evidence grounding (a confirmed field must cite a span that
  actually appears in the transcript), contradiction detection across
  the whole call, stale-price and wrong-product rejection, and a
  confidence policy that demotes hedged, approximate and conditional
  statements instead of asserting them.
- **Fallback** (`app/pipeline.py`): if the primary provider fails,
  the batch falls back to a second provider per transcript; if none
  is available, the answer is every field unconfirmed with the
  failure recorded. A dead provider produces an honest empty answer,
  never an exception and never an invented one.

## Prompts

Prompts are assembled in code (`app/prompts.py`) from the context and
a declared output schema, and they are versioned: `baseline-naive`
(schema fields only, no evidence requested) and `trutrace-1.0.0`
(evidence, candidates and quality rules required). The prompt version
is an eval axis: the benchmark is the grid of provider x prompt
version, so changing a prompt is a measured event.

## The five metrics

Reported separately, never averaged into one score
(`evals/run_evals.py`):

1. **Extraction accuracy**: fields matching gold on value, status and
   condition.
2. **Evidence coverage**: share of confirmed fields whose cited span
   actually appears in the transcript.
3. **Unsupported claim rate**: confirmed fields that gold does not
   support. This is the critical failure: an asserted price or stock
   level with nothing behind it is worse than no answer, because
   someone acts on it.
4. **Contradiction detection**: recall on fields gold marks
   conflicting.
5. **Operational efficiency**: measured latency (mean, p50, p95) and,
   for real providers, token cost computed from returned usage.

## Results

Final protocol: the 32-case set is frozen into 20 dev and 12
held-out cases (`datasets/SPLIT.md`); final numbers come from the
held-out 12 and the campaign 10, three runs per configuration. Full
tables, spreads and per-run counts are in
`reports/benchmark_results.md`. Headlines:

- Held-out, gpt-4o-mini: baseline gets 61 of 84 fields right with 23
  of its 58–59 confirmations unsupported; the current configuration
  gets 65–69 of 84 right with 11–12 of 39–44 unsupported.
- Campaign, gpt-4o-mini: baseline 38–40 of 70 right, 30–32 of 63–65
  confirmations unsupported; current 55–56 of 70 right, 11–12 of
  40–41 unsupported, and speaker/timestamp proof matching gold on 37
  of 41 gold-confirmed fields (baseline: 0 of 41, its prompt never
  asks for evidence).
- The offline provider's current configuration is clean on the
  held-out set (84 of 84, 0 of 45 unsupported), with the caveat in
  the report: its rules and the dataset grew up together, so that
  row shows self-consistency. The model rows are the independent
  check.
- gemini-2.0-flash-001 did not run: OpenRouter returned HTTP 404
  for that model id, and the runs were stopped rather than retried
  or re-pointed.

## Degradation, measured

`scripts/degradation_demo.py` kills the primary provider after 3 of
6 campaign calls: 3 are served by the primary, 3 fall back to the
offline provider, 0 are lost. With both providers dead, all 6 come
back fully unconfirmed. The same scenarios are automated tests
(`tests/test_degradation.py`).

## Load, measured and labelled

- 10 and 100 transcripts: real sequential calls to gpt-4o-mini
  through the OpenRouter helper; throughput, error rate, latency and
  cost recorded in `evals/results/load_*.json` and the report.
- 1000 transcripts: simulated. The pipeline code ran in-process
  against the offline rule provider; no network calls were made and
  the latencies are rule-engine times, not a live model's. The
  report says exactly this, in the load section.

## What breaks next

Single process, sequential, no queue. What a real calling workload
breaks first: queueing under bursty arrivals; idempotent retries
(a transient 429 must not double-extract or double-bill);
per-seller concurrency caps so one campaign cannot spend the shared
provider rate limit; and partial results as a normal contract,
because a batch where most calls verify and some return unconfirmed
is the common case, not an error. Detail in the report.

## Limits

- The transcripts are synthetic, written for this project. They are
  not recordings of real calls.
- There is no live audio: no speech recognition, no audio pipeline.
  The campaign's ASR noise is written text imitating recognition
  errors.
- There is no real telephony: no dialling, no call recording, no
  carrier integration.
- Gold labels are unreviewed (see Authorship above), the dataset is
  small, and the offline provider was built alongside it. Nothing
  here estimates accuracy on real seller calls.

## Running everything

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt

# one call through the pipeline
.venv/bin/python -m app.run datasets/campaign/campaign_01_showcase_hedged.json

# tests (guardrails, schemas, regressions, degradation, campaign)
.venv/bin/python -m unittest discover -s tests

# evals: the frozen final protocol, 3 runs per configuration
.venv/bin/python -m evals.run_final --set heldout --runs 3
.venv/bin/python -m evals.run_final --set campaign --runs 3

# single-configuration eval over the full 32 (dev-era tool)
.venv/bin/python evals/run_evals.py --provider offline --prompt-version trutrace-1.0.0

# degradation demo and load runs
.venv/bin/python scripts/degradation_demo.py
.venv/bin/python scripts/load_test.py --n 10
.venv/bin/python scripts/load_test.py --n 1000   # simulated, labelled as such

# regenerate the report from the recorded artifacts
.venv/bin/python -m evals.build_report
```

The OpenRouter adapter reaches its key through a local helper
(`~/workspace/custom-connectors/custom.openrouter/bin/or_call.py`),
never an environment variable; paths are configurable in
`app/providers/openrouter.py`. Without it, everything runs on the
offline provider.

## Workbench — Prompt Lab + Experiment Runner

A local workbench around the same engine (audit: `AUDIT.md`; stack
record: `STACK.md`). Launch with one command:

```
.venv/bin/python -m workbench.server        # http://127.0.0.1:8765
```

- **Prompt Lab.** Prompts are immutable version files in `prompts/`
  (`<name>@<version>.json`). Open a version, clone it, edit system /
  user text and temperature, save as a new version (existing versions
  are never overwritten), and diff two versions — text, parameters,
  and the verification profile each version runs under.
- **Experiment Runner.** Run a prompt version + provider/model
  against a split (dev, heldout, campaign, all) through the existing
  pipeline and verification engine. Every run persists to `runs/`:
  the prompt snapshot with its fingerprint, per-case outputs,
  evidence, Langfuse-shaped trace records (`cases.jsonl`), latency,
  token usage, and cost computed from provider usage counts. Two
  runs compare in a table; the comparison states whether the inputs
  were identical and complete. A failed case opens with its
  transcript, gold vs actual per field, evidence spans, and the
  trace record.
- **Status, stated plainly in the UI:** gold labels are AI drafted
  and pending human review wherever scores appear; gpt-4o-mini is
  verified, Gemini is failed / not verified (OpenRouter HTTP 404 on
  `google/gemini-2.0-flash-001`, never run); Langfuse is **not
  connected** — the local records are the trace.
- **Promptfoo** runs the same comparison as a matrix
  (`promptfoo/promptfooconfig.yaml`): its prompts come from
  `build_prompt`, its provider delegates to `run_pipeline`, and its
  assertions score with `evals/metrics.py`, so its totals match the
  workbench's. DeepEval was assessed and deliberately not integrated
  — see `STACK.md`.

## Layout

```
app/          pipeline, providers, verification engine, schemas
datasets/     the 32-case set, the split, the campaign slice
evals/        the five-metric suite, final-run protocol, report builder
tests/        guardrails, schemas, regressions, degradation, campaign
scripts/      degradation demo, load runs
reports/      benchmark_results.md, degradation_record.json
demo/         the static demo page (built from real outputs)
prompts/      Prompt Lab version files (immutable)
runs/         persisted experiment runs (run.json + cases.jsonl)
workbench/    prompt store, datasets, runner, FastAPI server, UI
promptfoo/    Promptfoo comparison matrix over the same prompts
```
