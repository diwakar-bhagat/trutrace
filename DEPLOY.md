# Deploying the TruTrace backend

The chosen stack, and where each piece lives:

| Piece | Platform | Status |
|---|---|---|
| Backend API + workbench UI (this repo's FastAPI app) | Railway | Ready to deploy; not deployed yet |
| Database | PostgreSQL on Railway | Schema written (`workbench/schema.sql`); storage swap still to do |
| Frontend demo (`demo/`) | Cloudflare Pages | Separate, already live; untouched by this setup |

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
| `DATABASE_URL` | Railway (Postgres plugin) | Connection string for the Railway PostgreSQL database. Provisioned by Railway when the Postgres service is added and linked. **Not yet read by the app** — see the storage note below. |
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
- Provider status stays honest everywhere it is shown: Gemini has
  never run successfully (OpenRouter returned HTTP 404 for
  `google/gemini-2.0-flash-001`) and is reported as failed / not
  verified, and Langfuse is reported as not connected, with traces
  kept as local Langfuse-shaped records in each run's
  `cases.jsonl`.

**Still the file-backed store (the known limitation):**

- Prompts and runs persist as files in `prompts/` and `runs/`,
  exactly as they do locally. A Railway service's filesystem is
  ephemeral, so versions and runs created through a deployed
  workbench will **not** survive a redeploy or restart until the
  storage swap lands. The seeded prompts and recorded runs ship
  with the repo and are always present.
- `workbench/schema.sql` is the PostgreSQL shape those files map
  to, field for field. It is now idempotent (`IF NOT EXISTS`
  throughout), so it runs cleanly on a fresh Railway Postgres and
  can be re-run safely. It has been reviewed but **not executed**:
  no PostgreSQL server was available on the build machine.
- The remaining work is the storage swap inside
  `workbench/prompt_store.py` and `workbench/runner.py` to read and
  write PostgreSQL via `DATABASE_URL`. No API or UI change is
  needed when it lands.

## Local launch (unchanged)

```sh
.venv/bin/python -m workbench.server            # 127.0.0.1:8765
TRUTRACE_PORT=9000 .venv/bin/python -m workbench.server
```
