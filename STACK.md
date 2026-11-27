# TruTrace workbench — stack record

Decisions set by Diwakar (27 Nov 2026): frontend Cloudflare, backend
Railway + FastAPI, database PostgreSQL, validation Pydantic, tracing
Phoenix or Opik, evaluation Promptfoo + DeepEval + the existing
custom deterministic checks, each with a distinct job. **No Vercel
for the workbench.** The static demo is a separate, already-live
artifact and is not touched by this build.

## What is implemented now vs scaffolded

| Layer | Now (this slice) | Scaffolded direction |
|---|---|---|
| Frontend | One static page (`workbench/workbench.html`), vanilla JS, served by the local app. Design system: `DESIGN.apple.md` (see "Design source" below). | Same static assets deploy to Cloudflare Pages unchanged; no build step exists or is needed. |
| Backend | FastAPI app (`workbench/server.py`) + the `workbench` package (prompt store, datasets, runner). Runs locally with one command. | The same FastAPI app is the Railway service. Nothing in the request path is local-only except file persistence (below). |
| Database | The repo is the store: `prompts/*.json` (immutable versions), `runs/<run_id>/run.json` + `cases.jsonl`. | `workbench/schema.sql` defines the PostgreSQL tables with the same shapes (prompts, runs, case_traces). Moving is a storage-layer swap inside `prompt_store` and `runner`; no API or UI change. No PostgreSQL server exists on this machine, so the DDL is written and reviewed, not executed. |
| Validation | Pydantic throughout: pipeline schemas (existing), API request models (`PromptIn`, `RunIn`), prompt-file and run-record shapes are plain JSON with the same field names as the DDL. | Unchanged on Railway. |
| Tracing | Local trace records per case in `cases.jsonl`, Langfuse-shaped (trace id, prompt version, model, latency, tokens, per-field eval outcomes). Langfuse status: **not connected** (no account or keys), stated in the UI and in every run record. | Phoenix, self-hosted — see the assessment below. The trace records map onto Phoenix spans without changing what is recorded. |
| Evaluation | The verification engine + `evals/metrics.py` are the correctness source of truth. Promptfoo integrated as the comparison matrix (below). DeepEval assessed, not integrated (below). | Unchanged. |

## Tracing assessment: Phoenix vs Opik (self-hosted)

Both were assessed as the self-hosted tracing layer to replace the
"Langfuse not connected" gap. Langfuse itself also self-hosts, but
it needs Postgres + ClickHouse + Redis + S3-compatible storage —
four moving parts for one tracer — and the hosted route needs an
account and keys we do not have.

**Arize Phoenix — chosen.**
- One container (`arizephoenix/phoenix`), embedded SQLite by
  default, optional Postgres backend. Runs comfortably in ~1 GB RAM
  next to the FastAPI service on a small Railway instance.
- OpenTelemetry-native: the FastAPI app instruments once with OTEL
  and can re-point at any collector later. Spans, evaluations and
  prompt versioning are first-class; TruTrace's per-field eval
  outcomes attach as span annotations / evaluations.
- Apache 2.0 licence (with Elastic Licence components in some
  distributions — check the exact image licence before any
  commercial hosted use; for self-hosted internal use it is fine).
- Fit: closest to what the local trace records already capture.

**Comet Opik — credible second, not chosen.**
- Heavier: separate frontend, backend, ClickHouse, MySQL, Redis and
  a Python SDK service. Realistic self-hosting wants ~4 GB+ RAM and
  several containers; on Railway that is a multi-service bill for a
  tracing sidecar.
- Strong evaluation features (datasets, experiments, LLM judges),
  but those overlap the evaluation layer this project deliberately
  keeps in the verification engine + Promptfoo, so the extra weight
  buys duplication risk.
- Apache 2.0.

**Decision:** Phoenix when tracing is wired. Until then the local
Langfuse-shaped records are the trace, labelled as such. This slice
does not deploy Phoenix; the choice and the cost picture are
recorded here so the deployment pass does not re-litigate them.

## Evaluation: three tools, three distinct jobs

- **Custom deterministic checks (primary).** The verification engine
  (`app/verification/`) judges each answer; `evals/metrics.py`
  scores fields against gold (`field_correct`,
  `is_unsupported_claim`, span grounding). This is the only
  correctness source of truth. Gold labels are AI drafted, pending
  human review — every surface that shows a score says so.
- **Promptfoo (comparison matrix).** `promptfoo/promptfooconfig.yaml`
  runs the campaign slice across prompt versions. Its Python prompt
  functions call `app.prompts.build_prompt` (Promptfoo 0.126
  requires the `file://….py:get_prompt` suffix — without it the
  prompt silently renders empty), its provider delegates execution
  to `app.pipeline.run_pipeline`, and its assertion scores with
  `evals/metrics.py`. Evidence: a real run is saved at
  `promptfoo/results.json` + `promptfoo/last_run.log`, and its
  totals match the Experiment Runner's offline runs exactly
  (baseline 52/70 fields, 9 unsupported; trutrace 56/70, 4
  unsupported). Promptfoo adds the matrix and reporting; it has no
  opinion of its own about correctness.
- **DeepEval (assessed, deliberately not integrated).** Install
  test: DeepEval 4.3.6 installs cleanly on this Python 3.12 (into a
  scratch venv, ~70 packages including its own OpenAI/gRPC/
  telemetry stack). It is not integrated because every metric it
  offers for this task is either LLM-judged — a probabilistic
  duplicate of the engine's deterministic evidence-grounding and
  unsupported-claim checks, which would create a second correctness
  source — or aimed at RAG/conversational shapes this pipeline does
  not have. Forcing it in would violate the no-duplicated-evaluation
  rule. Its reserved job, if a need appears the deterministic checks
  cannot cover (for example judged quality of free-text next steps),
  is that judge role, run through the same OpenRouter helper.

## Framework notes (from the audit)

- **Langfuse:** right trace shape, not connected (no account/keys).
  Local records follow its model so a later import is mechanical.
- **Ragas:** RAG-shaped (needs retrieved context); not applicable.
- **OpenAI Evals / Inspect AI:** methodology references (eval
  design, held-out discipline), not adopted as runners.
- **Pydantic AI:** not needed; the pipeline's own Pydantic schemas
  already do structured output and validation.
- **LangChain AgentEvals:** agent-trajectory shaped; this is a
  single-call extraction pipeline, not applicable.

## Design source

The workbench frontend follows `DESIGN.apple.md` (the full Apple
design analysis installed in this repo): Action Blue #0066cc as the
single interactive colour, the SF Pro ladder (300/400/600/700 —
weight 500 absent), body copy at 17px, black global nav, frosted
parchment sub-nav, edge-to-edge alternating tiles (the dark tile
carries the case trace record), pill CTAs, no decorative gradients,
and the system's single drop shadow reserved for product imagery
(this UI has no product imagery, so it uses no shadows). Inter is
the named substitute off Apple platforms. This supersedes the
merged Apple+Nike `DESIGN.md` for the frontend; Stageshow
principles govern on top. Field-state colour (verified /
conflicting / unconfirmed) appears only on state labels — content,
never chrome or controls.
