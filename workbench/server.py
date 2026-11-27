"""The TruTrace workbench server.

A FastAPI app (the target backend stack; this same app is what a
Railway deployment would run) serving the workbench UI and the JSON
APIs behind it:

  Prompt Lab        list, open, clone, edit, save immutable versions,
                    compare two versions (text and parameter diff)
  Experiment Runner set up and execute a run through the existing
                    verification engine, list persisted runs, compare
                    two runs on identical inputs, inspect one failed
                    case with its evidence and trace record

Persistence is the repo itself (prompts/ and runs/ as files) unless
DATABASE_URL is set, in which case prompts, datasets, runs, cases
and results live in PostgreSQL (workbench/pg_store.py, schema in
workbench/schema.sql) and survive redeployments. The selection rule
is workbench/store.py's; there is no silent fallback, and /health
and /api/status report which store is active.

The app runs locally with one command:

  .venv/bin/python -m workbench.server            # 127.0.0.1:8765
  TRUTRACE_PORT=9000 .venv/bin/python -m workbench.server

The same entrypoint serves hosted deployments (see DEPLOY.md and
railway.json): when the platform sets PORT, the app binds 0.0.0.0 on
that port instead. GET /health is the platform healthcheck.

Provider status is explicit, by design: gpt-4o-mini is verified
(recorded benchmark and load runs), Gemini is failed / not verified
(OpenRouter returned HTTP 404 for google/gemini-2.0-flash-001; it has
never run successfully), and Langfuse is not connected, so traces are
the local Langfuse-shaped records in each run's cases.jsonl.

The same app also serves the interactive product's API:

  POST /api/verify               verify a submitted extraction
                                 against its transcript (201); see
                                 workbench/verify.py
  POST /api/runs/{id}/review     record a human decision on one
                                 field of a run (201); GET
                                 /api/runs/{id} returns the recorded
                                 reviews alongside the results

Response contract (documented in STACK.md): POST /api/verify
returns the verify run record itself (run_id, kind, per-field
verdicts under "fields", a status-count "summary", the full stored
input); POST /api/runs/{id}/review returns the stored review object.
Errors are {"detail": "..."} with a plain-language message and a
meaningful status code (400 client error, 404 unknown run, 413
transcript too large, 429 rate limited, 502 provider failure).

/api/verify is public and the OpenRouter path spends real money, so
it is guarded: a transcript size cap, the model restricted to
openai/gpt-4o-mini or the offline provider, and a per-client rate
limit held in memory (10 runs per hour per client; it resets when
the service redeploys, stated plainly wherever it is described).
CORS allows exactly one origin, https://trutrace.pages.dev, the
Pages site the interactive page is served from.
"""

import os
import threading
import time

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.providers.base import ProviderError
from app.schemas import FIELDS

from . import prompt_store, reviews, runner, store
from . import verify as verify_mod
from .datasets import LABELS_STATUS, split_info

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="TruTrace Workbench", docs_url=None, redoc_url=None)

# The interactive page lives on Cloudflare Pages; the API stays on
# Railway. Exactly one origin may call it from a browser.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["https://trutrace.pages.dev"],
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
)


@app.on_event("startup")
def _startup() -> None:
    prompt_store.load_all()


class PromptIn(BaseModel):
    name: str
    version: str
    system: str
    user: str
    temperature: float = 0
    verification: str = "full"
    notes: str = ""
    parent: str | None = None


class RunIn(BaseModel):
    prompt_key: str
    provider: str = "offline"
    model: str | None = None
    split: str = "campaign"


class VerifyIn(BaseModel):
    transcript: str
    candidate: dict
    profile: str | list[str] | None = None
    provider: str = "openrouter"
    model: str | None = None
    product: str = ""
    question: str = ""


class ReviewIn(BaseModel):
    field: str
    decision: str
    note: str | None = None
    case_id: str | None = None


# ------------------------------------------------------- verify rate limit --
# POST /api/verify is public and spends OpenRouter credit, so one
# client may start a limited number of runs per hour. The window is
# held in memory only: it resets when the service redeploys, which
# is stated wherever the limit is described (STACK.md, DEPLOY.md).

class _RateLimiter:
    """A small sliding-window limiter, one bucket per client key."""

    def __init__(self, limit: int, window_seconds: float):
        self.limit = limit
        self.window = window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str, now: float = None) -> bool:
        now = time.monotonic() if now is None else now
        with self._lock:
            hits = [
                t for t in self._hits.get(key, [])
                if now - t < self.window
            ]
            if len(hits) >= self.limit:
                self._hits[key] = hits
                return False
            hits.append(now)
            self._hits[key] = hits
            return True


VERIFY_RATE_LIMIT = 10
VERIFY_RATE_WINDOW_SECONDS = 3600.0
_verify_limiter = _RateLimiter(
    VERIFY_RATE_LIMIT, VERIFY_RATE_WINDOW_SECONDS
)


def _client_key(request: Request) -> str:
    """The rate-limit bucket for a request: the first address of
    X-Forwarded-For when a proxy set it (Railway does), else the
    direct peer."""
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


PROVIDER_STATUS = [
    {
        "id": "offline",
        "status": "available",
        "note": "Deterministic rule provider. No network, no key.",
    },
    {
        "id": "openrouter · openai/gpt-4o-mini",
        "status": "verified",
        "note": "Benchmark and load runs recorded in evals/results/.",
    },
    {
        "id": "openrouter · google/gemini-2.0-flash-001",
        "status": "failed / not verified",
        "note": "OpenRouter returned HTTP 404 for this model id on "
                "every attempt. It has never run successfully.",
    },
]


@app.get("/")
def index():
    return FileResponse(os.path.join(HERE, "workbench.html"))


@app.get("/health")
def health():
    """Platform healthcheck (railway.json points here).

    Reports the service as up plus the same explicit provider status
    as /api/status: gpt-4o-mini verified, Gemini failed / not
    verified, Langfuse not connected. Nothing is probed live and
    nothing is upgraded on paper.
    """
    return {
        "status": "ok",
        "service": "trutrace-workbench",
        "storage": store.storage_name(),
        "providers": PROVIDER_STATUS,
        "langfuse": runner.LANGFUSE_STATUS,
    }


@app.get("/api/status")
def status():
    return {
        "labels_status": LABELS_STATUS,
        "storage": store.storage_name(),
        "providers": PROVIDER_STATUS,
        "langfuse": runner.LANGFUSE_STATUS,
        "tracing": {
            "implemented": "Trace records per case in the workbench "
                           "store (cases.jsonl locally, eval_results "
                           "in PostgreSQL), Langfuse-shaped.",
            "direction": "Arize Phoenix, self-hosted, selected as the "
                         "tracing layer (see STACK.md). Not wired in "
                         "this slice.",
        },
        "verify": {
            "endpoint": "POST /api/verify",
            "transcript_max_chars": verify_mod.MAX_TRANSCRIPT_CHARS,
            "models": ["openai/gpt-4o-mini via openrouter", "offline"],
            "rate_limit": (
                f"{VERIFY_RATE_LIMIT} runs per hour per client, held "
                "in memory; it resets when the service redeploys"
            ),
        },
    }


# ------------------------------------------------------------- Prompt Lab --

@app.get("/api/prompts")
def prompts():
    prompt_store.load_all()
    return {"prompts": prompt_store.list_prompts()}


@app.get("/api/prompts/compare")
def prompts_compare(a: str = Query(...), b: str = Query(...)):
    try:
        return prompt_store.diff_prompts(a, b)
    except KeyError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/prompts/{key}")
def prompt_detail(key: str):
    try:
        return prompt_store.get_prompt(key)
    except KeyError:
        raise HTTPException(404, f"no prompt version {key!r}")


@app.post("/api/prompts", status_code=201)
def prompt_create(body: PromptIn):
    try:
        return prompt_store.save_new_version(
            name=body.name,
            version=body.version,
            system=body.system,
            user=body.user,
            temperature=body.temperature,
            verification=body.verification,
            notes=body.notes,
            parent=body.parent,
        )
    except FileExistsError as exc:
        raise HTTPException(409, str(exc))
    except ValueError as exc:
        raise HTTPException(400, str(exc))


# -------------------------------------------------------- Experiment Runner --

@app.get("/api/datasets")
def datasets():
    return {"splits": split_info(), "labels_status": LABELS_STATUS}


@app.get("/api/runs")
def runs():
    return {"runs": [runner._run_summary(r) for r in runner.list_runs()]}


@app.post("/api/runs", status_code=201)
def runs_create(body: RunIn):
    try:
        run = runner.run_experiment(
            body.prompt_key, body.provider, body.model, body.split
        )
    except (KeyError, ValueError) as exc:
        raise HTTPException(400, str(exc))
    return runner._run_summary(run) | {"run_id": run["run_id"]}


@app.get("/api/runs/compare")
def runs_compare(a: str = Query(...), b: str = Query(...)):
    try:
        return runner.compare_runs(a, b)
    except FileNotFoundError as exc:
        raise HTTPException(404, str(exc))


@app.get("/api/runs/{run_id}")
def run_detail(run_id: str):
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id!r}")
    return {
        "run": run,
        "cases": runner.list_case_summaries(run_id),
        "reviews": reviews.list_reviews(run_id),
    }


# ------------------------------------------- interactive product (verify) --

@app.post("/api/verify", status_code=201)
def verify_create(body: VerifyIn, request: Request):
    """Verify one submitted extraction against its transcript. The
    full contract is in STACK.md; the guards are the size cap, the
    per-client rate limit and the model restriction."""
    if len(body.transcript) > verify_mod.MAX_TRANSCRIPT_CHARS:
        raise HTTPException(
            413,
            f"the transcript is {len(body.transcript)} characters; "
            f"the limit is {verify_mod.MAX_TRANSCRIPT_CHARS}",
        )
    if not _verify_limiter.allow(_client_key(request)):
        raise HTTPException(
            429,
            f"rate limit: {VERIFY_RATE_LIMIT} verification runs per "
            "hour per client. The limit is held in memory and resets "
            "when the service redeploys.",
        )
    try:
        return verify_mod.run_verify(
            body.transcript,
            body.candidate,
            profile=body.profile,
            provider_name=body.provider,
            model=body.model,
            product=body.product,
            question=body.question,
        )
    except ProviderError as exc:
        raise HTTPException(502, f"the provider failed: {exc}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.post("/api/runs/{run_id}/review", status_code=201)
def review_create(run_id: str, body: ReviewIn):
    """Record a human decision on one field of a run. Verify runs
    have a single case ("submission"), so case_id defaults to it;
    benchmark runs name the case explicitly."""
    if body.decision not in reviews.DECISIONS:
        raise HTTPException(
            400,
            f"decision must be one of {list(reviews.DECISIONS)}, "
            f"got {body.decision!r}",
        )
    if body.field not in FIELDS:
        raise HTTPException(
            400,
            f"unknown field {body.field!r}; choose from {FIELDS}",
        )
    try:
        run = runner.get_run(run_id)
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id!r}")
    case_id = body.case_id
    if run.get("kind") == "verify":
        if case_id is not None and case_id != verify_mod.CASE_ID:
            raise HTTPException(
                404, f"no case {case_id!r} in run {run_id!r}"
            )
        case_id = verify_mod.CASE_ID
    else:
        if case_id is None:
            raise HTTPException(
                400, "case_id is required for benchmark runs"
            )
        known = (run.get("dataset") or {}).get("case_ids") or []
        if case_id not in known:
            raise HTTPException(
                404, f"no case {case_id!r} in run {run_id!r}"
            )
    try:
        return reviews.record_review(
            run_id, case_id, body.field, body.decision, body.note
        )
    except FileNotFoundError:
        raise HTTPException(404, f"no run {run_id!r}")
    except ValueError as exc:
        raise HTTPException(400, str(exc))


@app.get("/api/runs/{run_id}/cases/{case_id}")
def run_case(run_id: str, case_id: str):
    try:
        return runner.get_case_trace(run_id, case_id)
    except (FileNotFoundError, KeyError):
        raise HTTPException(404, "no such case trace")


def main() -> None:
    import uvicorn

    if os.environ.get("PORT"):
        # Hosted (Railway and similar): the platform assigns the port
        # and routes external traffic to it, so bind every interface.
        uvicorn.run(app, host="0.0.0.0", port=int(os.environ["PORT"]))
        return
    port = int(os.environ.get("TRUTRACE_PORT", "8765"))
    uvicorn.run(app, host="127.0.0.1", port=port)


if __name__ == "__main__":
    main()
