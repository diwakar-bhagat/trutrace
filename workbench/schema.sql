-- TruTrace workbench — PostgreSQL schema (five tables).
--
-- This replaces the earlier three-table scaffold (prompt_versions,
-- runs, case_traces), which was never executed anywhere: no
-- PostgreSQL server existed when it was written, and the Railway
-- database was empty when this schema first ran. The tables below
-- are the store the workbench actually uses when DATABASE_URL is
-- set (see workbench/pg_store.py); without DATABASE_URL the file
-- store in prompts/ and runs/ is used instead, unchanged.
--
-- Design rule (Diwakar, 27 Nov 2026): a run must remain
-- reproducible after a redeployment. So eval_runs stores the full
-- evaluation configuration (prompt snapshot with its text, provider,
-- model, dataset version and content hash), eval_cases stores the
-- actual inputs and the gold labels exactly as scored, and
-- eval_results stores the raw model response, the raw extraction,
-- the verified output and the per-field scores. Not just the final
-- score.
--
-- Gold-label provenance is carried on every run (labels_status):
-- the labels were drafted by an AI coding agent and are pending
-- Diwakar Bhagat's human review. Scores are measured against
-- unreviewed labels, never validated ground truth.
--
-- Every statement uses IF NOT EXISTS, so the script is idempotent:
-- it runs cleanly against a fresh database and can be re-run after
-- a partial provisioning without erroring. The server applies it on
-- startup whenever DATABASE_URL is present.

CREATE TABLE IF NOT EXISTS eval_prompts (
    key            TEXT PRIMARY KEY,          -- "<name>@<version>"
    name           TEXT NOT NULL,
    version        TEXT NOT NULL,
    parent         TEXT,                      -- key of the version it was cloned from
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

CREATE TABLE IF NOT EXISTS eval_datasets (
    name         TEXT NOT NULL,               -- split name: dev | heldout | campaign | all
    version      TEXT NOT NULL,
    content_hash TEXT NOT NULL,               -- SHA-256 over the canonical cases payload
    cases        JSONB NOT NULL,              -- the cases, exactly as loaded and scored
    labels_status TEXT NOT NULL,              -- gold-label provenance, travels with the data
    created_at   TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (name, version)
);

CREATE TABLE IF NOT EXISTS eval_runs (
    run_id         TEXT PRIMARY KEY,
    created_at     TIMESTAMPTZ NOT NULL,
    prompt_key     TEXT NOT NULL REFERENCES eval_prompts(key),
    prompt_name    TEXT NOT NULL,
    prompt_version TEXT NOT NULL,
    dataset_name   TEXT NOT NULL,
    dataset_version TEXT NOT NULL,
    dataset_hash   TEXT NOT NULL,
    provider       TEXT NOT NULL,             -- 'offline' | 'openrouter'
    model          TEXT,
    status         TEXT NOT NULL CHECK (status IN ('completed', 'error')),
    cases_run      INTEGER NOT NULL,
    cases_total    INTEGER NOT NULL,
    labels_status  TEXT NOT NULL,             -- gold-label provenance, shown with every score
    configuration  JSONB NOT NULL,            -- prompt snapshot (text, params, fingerprint), provider, model, split, langfuse status
    metrics        JSONB NOT NULL,            -- the five benchmark metrics, with counts
    error_log      JSONB,                     -- {"case": ..., "message": ...} when the run stopped
    record         JSONB NOT NULL,            -- the complete run record, exactly as the API returns it
    FOREIGN KEY (dataset_name, dataset_version)
        REFERENCES eval_datasets(name, version)
);

CREATE TABLE IF NOT EXISTS eval_cases (
    run_id     TEXT NOT NULL REFERENCES eval_runs(run_id),
    case_id    TEXT NOT NULL,
    case_index INTEGER NOT NULL,              -- position within the run, preserves order
    taxonomy   TEXT,
    input      JSONB NOT NULL,                -- question, transcript, business, product, requested fields
    gold       JSONB NOT NULL,                -- the gold labels exactly as scored (AI drafted, pending human review)
    PRIMARY KEY (run_id, case_id)
);

CREATE TABLE IF NOT EXISTS eval_results (
    run_id            TEXT NOT NULL REFERENCES eval_runs(run_id),
    case_id           TEXT NOT NULL,
    case_index        INTEGER NOT NULL,
    trace_id          TEXT NOT NULL,          -- uuid, Langfuse-shaped record id
    status            TEXT NOT NULL,          -- 'ok' | 'error'
    raw_response      TEXT,                   -- the model's response, verbatim (LLM providers; NULL for offline, which has no response text)
    raw_extraction    JSONB,                  -- the provider's raw extraction, as reported, before verification
    parsed_output     JSONB,                  -- the verified answer fields (the pipeline's output)
    field_scores      JSONB,                  -- per-field gold / predicted / correct / unsupported / grounded
    unsupported_claims JSONB NOT NULL DEFAULT '[]',  -- field names flagged as unsupported claims
    evaluations       JSONB,                  -- full per-case evaluation summary (correct/total/failed fields)
    usage             JSONB,                  -- token counts + reported cost
    latency_ms        DOUBLE PRECISION,
    wall_latency_ms   DOUBLE PRECISION,
    provider_used     TEXT,
    fallback_used     BOOLEAN NOT NULL DEFAULT FALSE,
    error             TEXT,
    trace             JSONB NOT NULL,         -- the complete trace record, exactly as the API returns it
    PRIMARY KEY (run_id, case_id),
    FOREIGN KEY (run_id, case_id) REFERENCES eval_cases(run_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_eval_results_run ON eval_results(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_cases_run ON eval_cases(run_id);
CREATE INDEX IF NOT EXISTS idx_eval_runs_prompt ON eval_runs(prompt_key);
CREATE INDEX IF NOT EXISTS idx_eval_runs_created ON eval_runs(created_at);
