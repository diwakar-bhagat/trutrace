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

Persistence in this slice is the repo itself (prompts/ and runs/ as
files); workbench/schema.sql holds the PostgreSQL shape those files
map to when the store moves.

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
"""

import os

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import prompt_store, runner
from .datasets import LABELS_STATUS, split_info

HERE = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(title="TruTrace Workbench", docs_url=None, redoc_url=None)


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
        "providers": PROVIDER_STATUS,
        "langfuse": runner.LANGFUSE_STATUS,
    }


@app.get("/api/status")
def status():
    return {
        "labels_status": LABELS_STATUS,
        "providers": PROVIDER_STATUS,
        "langfuse": runner.LANGFUSE_STATUS,
        "tracing": {
            "implemented": "Local trace records in each run's "
                           "cases.jsonl (Langfuse-shaped).",
            "direction": "Arize Phoenix, self-hosted, selected as the "
                         "tracing layer (see STACK.md). Not wired in "
                         "this slice.",
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
    return {"run": run, "cases": runner.list_case_summaries(run_id)}


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
