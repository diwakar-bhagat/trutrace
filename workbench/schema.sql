-- TruTrace workbench — PostgreSQL shape (scaffold).
--
-- These tables mirror the file-based store used by the local slice:
--   prompts/<name>@<version>.json   -> prompt_versions
--   runs/<run_id>/run.json          -> runs
--   runs/<run_id>/cases.jsonl       -> case_traces (one row per line)
--
-- Moving to Railway + PostgreSQL is a storage-layer swap inside
-- workbench/prompt_store.py and workbench/runner.py; field names
-- here match the JSON records exactly so no API or UI change is
-- needed. Not executed in this slice: no PostgreSQL server is
-- available on the build machine.

CREATE TABLE prompt_versions (
    key            TEXT PRIMARY KEY,          -- "<name>@<version>"
    name           TEXT NOT NULL,
    version        TEXT NOT NULL,
    parent         TEXT REFERENCES prompt_versions(key),
    created_at     TIMESTAMPTZ NOT NULL,
    legacy_version TEXT,
    verification   TEXT NOT NULL CHECK (verification IN ('full', 'passthrough')),
    params         JSONB NOT NULL DEFAULT '{}',
    system_text    TEXT NOT NULL,
    user_text      TEXT NOT NULL,
    notes          TEXT NOT NULL DEFAULT '',
    fingerprint    TEXT NOT NULL,             -- SHA-256 over texts+params+profile
    UNIQUE (name, version)                    -- versions are immutable: insert only
);

CREATE TABLE runs (
    run_id        TEXT PRIMARY KEY,
    created_at    TIMESTAMPTZ NOT NULL,
    prompt_key    TEXT NOT NULL REFERENCES prompt_versions(key),
    provider      TEXT NOT NULL,              -- 'offline' | 'openrouter'
    model         TEXT,
    split         TEXT NOT NULL,              -- 'dev' | 'heldout' | 'campaign' | 'all'
    case_ids      TEXT[] NOT NULL,
    cases_run     INTEGER NOT NULL,
    labels_status TEXT NOT NULL,              -- gold-label provenance, shown with every score
    metrics       JSONB NOT NULL,             -- the five benchmark metrics, with counts
    langfuse      JSONB NOT NULL,             -- {"connected": false, "status": "not connected"}
    error         JSONB
);

CREATE TABLE case_traces (
    trace_id       TEXT PRIMARY KEY,          -- uuid, Langfuse-shaped record id
    run_id         TEXT NOT NULL REFERENCES runs(run_id),
    case_id        TEXT NOT NULL,
    taxonomy       TEXT,
    status         TEXT NOT NULL,             -- 'ok' | 'error'
    prompt_version TEXT NOT NULL,
    provider       TEXT NOT NULL,
    model          TEXT,
    fallback_used  BOOLEAN NOT NULL DEFAULT FALSE,
    latency_ms     DOUBLE PRECISION,
    usage          JSONB,                     -- token counts + reported cost
    input          JSONB NOT NULL,            -- question + transcript
    output         JSONB,                     -- verified answer fields
    evaluations    JSONB,                     -- per-field gold/predicted/correct/unsupported/grounded
    error          TEXT,
    UNIQUE (run_id, case_id)
);

CREATE INDEX idx_case_traces_run ON case_traces(run_id);
CREATE INDEX idx_runs_prompt ON runs(prompt_key);
