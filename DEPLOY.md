# Deploying the TruTrace backend

**Live backend: https://trutrace-production.up.railway.app** (health: `/health`)
Railway project: https://railway.com/project/7fe4bdac-d2a5-4a5c-806f-897ab4f05011
First deployed 27 Nov 2026. **Deployment mechanics, as verified
27 Nov 2026: the service has NO GitHub repo trigger** (checked via
the Railway API: `repoTriggers` is empty), so pushes to `main` do
NOT auto-deploy; creating a trigger fails with "no one in the
project has access to it" because Railway's GitHub app is not
authorized on the repo — authorizing it is Diwakar's step in the
Railway dashboard. Until then, deploys are `railway up` uploads of
this repo's tree (`.railwayignore` excludes `.venv/`, caches and
`.git/`). Two upload gotchas, both hit and fixed on 27 Nov: the
Railpack builder needs the repo's `Procfile` to find the start
command (railway.json's Nixpacks start command is not read by
Railpack), and a service variable whose name contains a dot (a
stray `openrouter.ai` variable) breaks every Railpack build with
"failed to solve: secret openrouter not found" — variable names
must stay plain identifiers.
`OPENROUTER_API_KEY` is set in the Railway dashboard by Diwakar; without it only the
offline provider runs.

The chosen stack, and where each piece lives:

| Piece | Platform | Status |
|---|---|---|
| Backend API + workbench UI (this repo's FastAPI app) | Railway | Live at the URL above |
| Database | PostgreSQL on Railway | Live: the app reads `DATABASE_URL` and stores prompts, datasets, runs, cases, results, reviews and gold submissions in the seven-table schema (`workbench/schema.sql`). Without `DATABASE_URL` the file store remains the local default. |
| Frontend (`demo/`) | Cloudflare Pages | Live at https://trutrace.pages.dev: `index.html` is the benchmark story (its gold tile reads this backend's `/api/gold/status` and `/api/gold/metrics` at load), `try.html` is the interactive workbench page calling this backend's `/api/verify`, review and run history endpoints, and `review.html` is the gold review tool (from `tools/gold_review.html`) submitting to `/api/gold/review` |

## How Railway runs this repo

- **Builder:** Nixpacks (declared in `railway.json`). It detects
  `requirements.txt` and installs it; `.python-version` pins the
  interpreter to Python 3.12.
- **Start command** (in `railway.json`):
  `python -m workbench.server`
- **Port:** Railway sets `PORT`; `workbench/server.py` binds
  `0.0.0.0:$PORT` when `PORT` is present. With no `PORT` set (local
  development) the entrypoint behaves exactly as before:
  `127.0.0.1` on `TRUTRACE_PORT` or 8765.
- **Healthcheck:** `GET /health` (path declared in `railway.json`).
  It returns the service status plus the explicit provider status:
  gpt-4o-mini verified, Gemini **failed / not verified**, Langfuse
  not connected. It probes nothing live and upgrades nothing on
  paper.

## Environment variables to set in Railway

Names and purpose only. Set the values in the Railway dashboard;
never commit them.

| Variable | Set by | Purpose |
|---|---|---|
| `OPENROUTER_API_KEY` | You | Lets the OpenRouter provider call the API directly. Locally the provider uses the connector helper instead and this variable is unset; the moment it is set, the direct API path is used. Required on Railway for any live-model run (the helper does not exist there). Without it, only the offline provider works. |
| `DATABASE_URL` | Railway (Postgres plugin) | Connection string for the Railway PostgreSQL database. Provisioned by Railway when the Postgres service is added and linked. **The app reads it**: its presence selects the PostgreSQL store (see the storage section below). Never commit its value. |
| `PORT` | Railway | Port the platform routes traffic to. Provided automatically; do not set it by hand. |
| `TRUTRACE_PORT` | Local only | Local development port override (default 8765). Ignored whenever `PORT` is set. Do not set on Railway. |

No other environment variables are used by the backend today.

## What runs on Railway today vs. what still needs work

**Works as deployed:**

- The workbench UI at `/` and all `/api/*` endpoints, including the
  Prompt Lab and the Experiment Runner.
- Experiments against the **offline** provider, end to end.
- Experiments against **OpenRouter / gpt-4o-mini**, once
  `OPENROUTER_API_KEY` is set.
- The interactive product endpoints: `POST /api/verify` (verify a
  submitted extraction against its transcript; the run persists as
  kind `verify`, distinct from benchmark runs),
  `POST /api/runs/{run_id}/review` (a human decision per field;
  `GET /api/runs/{run_id}` returns the recorded reviews alongside
  the results), and `GET /api/runs?kind=verify` (the run history
  the workspace page reloads past runs from). The response
  contract is in STACK.md.
- The connected gold endpoints: `POST /api/gold/review` (a
  submitted human review export, stored verbatim as the current
  gold-v2-human-reviewed), `GET /api/gold/status` (current gold
  version and review coverage) and `GET /api/gold/metrics` (the
  recorded runs scored against the current gold by
  `evals/gold_metrics.py`; agreement-labelled while the gold is AI
  drafted, reviewed-fields-only after a partial human review).
- Provider status stays honest everywhere it is shown: Gemini has
  never run successfully (OpenRouter returned HTTP 404 for
  `google/gemini-2.0-flash-001`) and is reported as failed / not
  verified, and Langfuse is reported as not connected, with traces
  kept as Langfuse-shaped records in the store (below).

**Storage: the PostgreSQL swap is done (27 Nov 2026).**

- One selection rule (`workbench/store.py`): `DATABASE_URL` set →
  PostgreSQL (`workbench/pg_store.py`); unset → the file store in
  `prompts/` and `runs/`, byte for byte the old local behaviour.
  There is no silent fallback: if the database is unreachable, the
  app fails loudly instead of writing runs to an ephemeral
  filesystem. `/health` and `/api/status` report which store is
  active.
- The schema is seven tables (`workbench/schema.sql`): eval_prompts
  (immutable versions), eval_datasets (the frozen splits as
  versioned rows with a content hash), eval_runs (configuration,
  metrics, status, error log, the full run record, and a `kind`
  marker: `benchmark` or `verify`), eval_cases (actual inputs and
  gold labels as scored), eval_results (raw model responses, raw
  extractions, verified outputs, per-field scores, token usage,
  latency, the full trace record), eval_reviews (one current human
  decision per run, case and field), eval_gold_submissions (one row
  per submitted human gold review, payload verbatim; the latest
  row is the current gold-v2-human-reviewed, and
  gold-v1-ai-drafted is never touched by it). A run therefore
  survives a redeploy with everything needed to reproduce it, not
  just its score. Verify runs reference a registered `verify` dataset whose
  case list is empty by design: the submitted transcript and
  candidate live on the run's own eval_cases row, with no gold
  labels (the run's labels_status says so).
- The server applies the schema on startup (idempotent
  `IF NOT EXISTS` throughout) whenever `DATABASE_URL` is present,
  and registers the repo's prompt versions and dataset splits into
  empty tables. A registered prompt or dataset whose content later
  differs under the same version makes startup fail rather than
  silently serving different data.
- **Not backfilled:** runs recorded in the old file store stay in
  `runs/` and are not copied into the database; database runs start
  fresh. The seeded prompts and the file-based recorded runs still
  ship with the repo and remain the local record.
- Gold labels remain AI drafted and pending Diwakar Bhagat's human
  review wherever scores appear, in both stores.

## The interactive product (try.html + /api/verify)

- **Page:** https://trutrace.pages.dev/try.html, generated by
  `demo/build_demo.py` alongside `index.html`; the Pages dist holds
  three files: `index.html`, `try.html` and `review.html` (the gold
  review tool, copied from `tools/gold_review.html`). The demo page
  links to the workspace from a "Try TruTrace" tile and to the
  review tool from its gold tile. The pages call this backend
  directly; CORS allows exactly one origin,
  `https://trutrace.pages.dev`.
- **What it does:** the visitor supplies a transcript and the flat
  JSON an AI extracted from it; the backend runs the existing
  verification engine over the claims (it does not extract in this
  path) and returns per-field verdicts with evidence. Human review
  decisions on each field are recorded through the review endpoint
  and persist in PostgreSQL with the run.
- **Guards on `POST /api/verify`** (public, and the OpenRouter path
  spends money): transcripts are capped at 12,000 characters (413
  above it); the model is restricted to `openai/gpt-4o-mini` via
  OpenRouter or the offline provider (anything else is a 400); each
  client (first `X-Forwarded-For` address, else the peer) may start
  10 verify runs per hour, held in memory, so the counter resets
  when the service redeploys. No auth in V1.
- **Sample:** try.html preloads the campaign_01 call with a
  candidate JSON in the baseline style (it asserts the seller's
  hedges), labelled on the page as an example extraction being
  checked, not ground truth.

## Local launch (unchanged)

```sh
.venv/bin/python -m workbench.server            # 127.0.0.1:8765
TRUTRACE_PORT=9000 .venv/bin/python -m workbench.server
```
