"""PostgreSQL-backed store for the workbench (the storage swap).

Used only when DATABASE_URL is set (see workbench/store.py for the
selection rule). Implements the same operations the file store
exposes — prompt list/get/save, run save/list/get, case traces, run
comparison inputs — against the five tables in workbench/schema.sql:

  eval_prompts    immutable prompt versions (insert only; a duplicate
                  (name, version) is refused, exactly like the file
                  store refuses to overwrite a version file)
  eval_datasets   the frozen dataset splits, registered as versioned
                  rows with a content hash
  eval_runs       one row per experiment: prompt and dataset
                  references, the full evaluation configuration, the
                  aggregate metrics, status and error log, and the
                  complete run record the API returns
  eval_cases      per run, per case: the actual input and the gold
                  labels exactly as scored
  eval_results    per run, per case: the raw model response
                  (verbatim, LLM providers), the raw extraction, the
                  verified output, per-field scores, unsupported
                  claims, token usage, latency, and the complete
                  trace record the API returns

A run therefore survives a redeployment with everything needed to
reproduce or audit it: inputs, configuration, raw responses and
scores, not just a final number.

Registration: on first use in a process, the schema is applied
(idempotent) and the store is seeded from the repo — the prompt
versions found in prompts/ (plus the legacy seed records) and the
dataset splits from workbench/datasets.py. Old file-based runs are
NOT backfilled; runs start fresh in the database. If a registered
prompt or dataset is later found with different content under the
same version, registration raises rather than silently serving
different data than the repo holds: versions are immutable here too.

The row-building helpers (prompt_row, prompt_record, dataset_payload,
run_rows) are pure and unit tested; everything that touches a real
database is verified live, not faked in tests.
"""

import hashlib
import json
import os

from app.schemas import FIELDS

from .datasets import LABELS_STATUS, SPLIT_NAMES, load_split

HERE = os.path.dirname(os.path.abspath(__file__))
SCHEMA_PATH = os.path.join(HERE, "schema.sql")

# The frozen splits (datasets/SPLIT.md, frozen 27 Nov 2026) register
# as this version. If a split's content ever changes, bump this and
# the new content registers as a new dataset version.
DATASET_VERSION = "1.0.0"

_ready = False


# ------------------------------------------------------------------ helpers --

def _canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False)


def prompt_row(record: dict) -> dict:
    """A prompt record (file-store shape) as eval_prompts columns."""
    from .prompt_store import prompt_fingerprint

    return {
        "key": record["key"],
        "name": record["name"],
        "version": record["version"],
        "parent": record.get("parent"),
        "created_at": record["created_at"],
        "legacy_version": record.get("legacy_version"),
        "verification": record["verification"],
        "params": record.get("params", {}),
        "system_text": record["system"],
        "user_text": record["user"],
        "notes": record.get("notes", ""),
        "fingerprint": prompt_fingerprint(record),
    }


def prompt_record(row: dict) -> dict:
    """An eval_prompts row back as a prompt record (file-store shape)."""
    created = row["created_at"]
    if not isinstance(created, str):
        created = created.isoformat(timespec="seconds")
    return {
        "key": row["key"],
        "name": row["name"],
        "version": row["version"],
        "parent": row["parent"],
        "created_at": created,
        "legacy_version": row["legacy_version"],
        "verification": row["verification"],
        "params": row["params"] or {},
        "system": row["system_text"],
        "user": row["user_text"],
        "notes": row["notes"],
    }


def dataset_payload(split: str) -> dict:
    """The versioned dataset row for one split: cases exactly as the
    loaders return them (sorted by id for a stable hash), the gold
    labels included, with their provenance attached."""
    docs = sorted(load_split(split), key=lambda d: d.id)
    cases = [d.model_dump(mode="json") for d in docs]
    return {
        "name": split,
        "version": DATASET_VERSION,
        "content_hash": hashlib.sha256(
            _canonical(cases).encode("utf-8")
        ).hexdigest(),
        "cases": cases,
        "labels_status": LABELS_STATUS,
    }


def unsupported_fields(trace: dict) -> list:
    evaluations = trace.get("evaluations") or {}
    fields = evaluations.get("fields") or {}
    return [name for name in FIELDS if fields.get(name, {}).get("unsupported_claim")]


def run_rows(run: dict, traces: list, docs_by_id: dict) -> tuple:
    """Decompose a run record + traces into (run_row, case_rows,
    result_rows) for eval_runs / eval_cases / eval_results. Pure: the
    same decomposition the live insert uses, so it is unit testable
    without a database."""
    dataset = dataset_payload(run["dataset"]["split"])
    run_row = {
        "run_id": run["run_id"],
        "created_at": run["created_at"],
        "prompt_key": run["prompt"]["key"],
        "prompt_name": run["prompt"]["name"],
        "prompt_version": run["prompt"]["version"],
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_hash": dataset["content_hash"],
        "provider": run["provider"],
        "model": run["model"],
        "status": "error" if run.get("error") else "completed",
        "cases_run": run["cases_run"],
        "cases_total": run["dataset"]["cases_total"],
        "labels_status": run["labels_status"],
        "configuration": {
            "prompt": run["prompt"],
            "provider": run["provider"],
            "model": run["model"],
            "split": run["dataset"]["split"],
            "dataset": {
                "name": dataset["name"],
                "version": dataset["version"],
                "content_hash": dataset["content_hash"],
            },
            "langfuse": run["langfuse"],
        },
        "metrics": run["metrics"],
        "error_log": run.get("error"),
        "record": run,
    }
    case_rows = []
    result_rows = []
    for index, trace in enumerate(traces):
        doc = docs_by_id[trace["case_id"]]
        dump = doc.model_dump(mode="json")
        case_rows.append({
            "run_id": run["run_id"],
            "case_id": trace["case_id"],
            "case_index": index,
            "taxonomy": trace.get("taxonomy"),
            "input": {
                "question": dump["question"],
                "transcript": dump["transcript"],
                "business_name": dump["business_name"],
                "business_type": dump["business_type"],
                "product": dump["product"],
                "requested_fields": dump["requested_fields"],
                "taxonomy": dump["taxonomy"],
            },
            "gold": dump["gold"],
        })
        evaluations = trace.get("evaluations")
        result_rows.append({
            "run_id": run["run_id"],
            "case_id": trace["case_id"],
            "case_index": index,
            "trace_id": trace["trace_id"],
            "status": trace["status"],
            "raw_response": trace.get("raw_response"),
            "raw_extraction": trace.get("raw_extraction"),
            "parsed_output": trace.get("output"),
            "field_scores": (evaluations or {}).get("fields"),
            "unsupported_claims": unsupported_fields(trace),
            "evaluations": evaluations,
            "usage": trace.get("usage") or {},
            "latency_ms": trace.get("latency_ms"),
            "wall_latency_ms": trace.get("wall_latency_ms"),
            "provider_used": trace.get("provider_used"),
            "fallback_used": bool(trace.get("fallback_used")),
            "error": trace.get("error"),
            "trace": trace,
        })
    return run_row, case_rows, result_rows


# ------------------------------------------------------------------ database --

def _jb(value):
    """Wrap a value for a JSONB column. psycopg adapts a bare dict to
    JSONB but a bare list to a Postgres ARRAY, whose dict elements it
    then cannot adapt — so lists (dataset cases, unsupported claims)
    must be wrapped explicitly, and dicts go through the same path
    for uniformity."""
    if value is None:
        return None
    from psycopg.types.json import Jsonb

    return Jsonb(value)


def _wrap(row: dict, *keys: str) -> dict:
    out = dict(row)
    for key in keys:
        out[key] = _jb(out[key])
    return out


def _connect():
    import psycopg
    from psycopg.rows import dict_row

    return psycopg.connect(os.environ["DATABASE_URL"], row_factory=dict_row)


def _strip_comments(sql_text: str) -> str:
    """Remove -- comments (to end of line), honouring single-quoted
    string literals. Comments in the schema may contain semicolons,
    so they must go before any statement split."""
    out = []
    i, n = 0, len(sql_text)
    in_str = False
    while i < n:
        ch = sql_text[i]
        if in_str:
            out.append(ch)
            if ch == "'":
                if i + 1 < n and sql_text[i + 1] == "'":
                    out.append(sql_text[i + 1])
                    i += 2
                    continue
                in_str = False
            i += 1
        elif ch == "'":
            in_str = True
            out.append(ch)
            i += 1
        elif ch == "-" and i + 1 < n and sql_text[i + 1] == "-":
            while i < n and sql_text[i] != "\n":
                i += 1
        else:
            out.append(ch)
            i += 1
    return "".join(out)


def _statements(sql_text: str) -> list:
    """Split a DDL script into statements: strip comments first
    (they may contain semicolons), then split on ';'. The schema
    uses no semicolons inside string literals or function bodies,
    so the split is exact."""
    return [
        s.strip() for s in _strip_comments(sql_text).split(";") if s.strip()
    ]


def _apply_schema(cur) -> None:
    with open(SCHEMA_PATH, encoding="utf-8") as fh:
        for statement in _statements(fh.read()):
            cur.execute(statement)


def _register_prompts(cur, records: list) -> None:
    for record in records:
        row = prompt_row(record)
        cur.execute(
            """
            INSERT INTO eval_prompts (key, name, version, parent,
                created_at, legacy_version, verification, params,
                system_text, user_text, notes, fingerprint)
            VALUES (%(key)s, %(name)s, %(version)s, %(parent)s,
                %(created_at)s, %(legacy_version)s, %(verification)s,
                %(params)s, %(system_text)s, %(user_text)s, %(notes)s,
                %(fingerprint)s)
            ON CONFLICT (name, version) DO NOTHING
            """,
            _wrap(row, "params"),
        )
        cur.execute(
            "SELECT fingerprint FROM eval_prompts "
            "WHERE name = %s AND version = %s",
            (row["name"], row["version"]),
        )
        existing = cur.fetchone()
        if existing and existing["fingerprint"] != row["fingerprint"]:
            raise RuntimeError(
                f"prompt {row['key']} is registered in the database "
                "with different content; prompt versions are "
                "immutable, so register the changed text under a "
                "new version number"
            )


def _register_datasets(cur) -> None:
    for split in SPLIT_NAMES:
        payload = dataset_payload(split)
        cur.execute(
            """
            INSERT INTO eval_datasets (name, version, content_hash,
                cases, labels_status, created_at)
            VALUES (%(name)s, %(version)s, %(content_hash)s,
                %(cases)s, %(labels_status)s, now())
            ON CONFLICT (name, version) DO NOTHING
            """,
            _wrap(payload, "cases"),
        )
        cur.execute(
            "SELECT content_hash FROM eval_datasets "
            "WHERE name = %s AND version = %s",
            (payload["name"], payload["version"]),
        )
        existing = cur.fetchone()
        if existing and existing["content_hash"] != payload["content_hash"]:
            raise RuntimeError(
                f"dataset {payload['name']}@{payload['version']} is "
                "registered in the database with different content; "
                "the splits are frozen, so changed content must "
                "register under a new dataset version"
            )


def ensure_ready(prompt_records: list = None) -> None:
    """Apply the schema and register the repo's prompts and datasets.
    Idempotent; safe to call on every startup. Raises on any failure:
    with DATABASE_URL set there is no file-store fallback."""
    global _ready
    with _connect() as conn:
        with conn.cursor() as cur:
            if not _ready:
                _apply_schema(cur)
                _register_datasets(cur)
                _register_verify_dataset(cur)
            if prompt_records:
                _register_prompts(cur, prompt_records)
    _ready = True


def _ensure_schema() -> None:
    if not _ready:
        ensure_ready()


# ------------------------------------------------------------------- prompts --

def list_prompts() -> list:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM eval_prompts ORDER BY name, version")
            return [prompt_record(row) for row in cur.fetchall()]


def get_prompt(key: str) -> dict:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM eval_prompts WHERE key = %s", (key,))
            row = cur.fetchone()
    if row is None:
        raise KeyError(f"no prompt version {key!r}")
    return prompt_record(row)


def insert_prompt(record: dict) -> dict:
    """Insert one NEW prompt version. Refuses a duplicate (name,
    version) with FileExistsError, the file store's refusal."""
    _ensure_schema()
    row = prompt_row(record)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_prompts (key, name, version, parent,
                    created_at, legacy_version, verification, params,
                    system_text, user_text, notes, fingerprint)
                VALUES (%(key)s, %(name)s, %(version)s, %(parent)s,
                    %(created_at)s, %(legacy_version)s,
                    %(verification)s, %(params)s, %(system_text)s,
                    %(user_text)s, %(notes)s, %(fingerprint)s)
                ON CONFLICT (name, version) DO NOTHING
                """,
                _wrap(row, "params"),
            )
            if cur.rowcount == 0:
                raise FileExistsError(
                    f"prompt version {row['key']} already exists and "
                    "versions are immutable; save under a new version "
                    "number"
                )
    return record


# ---------------------------------------------------------------------- runs --

def save_run(run: dict, traces: list, docs_by_id: dict) -> None:
    """Persist one finished (or stopped) run in a single transaction:
    the run row, one eval_cases row per case with its input and gold,
    and one eval_results row per case with its raw response, output
    and scores."""
    _ensure_schema()
    run_row, case_rows, result_rows = run_rows(run, traces, docs_by_id)
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO eval_runs (run_id, created_at, prompt_key,
                    prompt_name, prompt_version, dataset_name,
                    dataset_version, dataset_hash, provider, model,
                    status, cases_run, cases_total, labels_status,
                    configuration, metrics, error_log, record)
                VALUES (%(run_id)s, %(created_at)s, %(prompt_key)s,
                    %(prompt_name)s, %(prompt_version)s,
                    %(dataset_name)s, %(dataset_version)s,
                    %(dataset_hash)s, %(provider)s, %(model)s,
                    %(status)s, %(cases_run)s, %(cases_total)s,
                    %(labels_status)s, %(configuration)s, %(metrics)s,
                    %(error_log)s, %(record)s)
                """,
                _wrap(run_row, "configuration", "metrics",
                      "error_log", "record"),
            )
            for row in case_rows:
                cur.execute(
                    """
                    INSERT INTO eval_cases (run_id, case_id,
                        case_index, taxonomy, input, gold)
                    VALUES (%(run_id)s, %(case_id)s, %(case_index)s,
                        %(taxonomy)s, %(input)s, %(gold)s)
                    """,
                    _wrap(row, "input", "gold"),
                )
            for row in result_rows:
                cur.execute(
                    """
                    INSERT INTO eval_results (run_id, case_id,
                        case_index, trace_id, status, raw_response,
                        raw_extraction, parsed_output, field_scores,
                        unsupported_claims, evaluations, usage,
                        latency_ms, wall_latency_ms, provider_used,
                        fallback_used, error, trace)
                    VALUES (%(run_id)s, %(case_id)s, %(case_index)s,
                        %(trace_id)s, %(status)s, %(raw_response)s,
                        %(raw_extraction)s, %(parsed_output)s,
                        %(field_scores)s, %(unsupported_claims)s,
                        %(evaluations)s, %(usage)s, %(latency_ms)s,
                        %(wall_latency_ms)s, %(provider_used)s,
                        %(fallback_used)s, %(error)s, %(trace)s)
                    """,
                    _wrap(row, "raw_extraction", "parsed_output",
                          "field_scores", "unsupported_claims",
                          "evaluations", "usage", "trace"),
                )


def list_runs() -> list:
    """Benchmark runs only. Verify runs live in the same table,
    marked kind='verify' in their record, and the benchmark list (and
    the workbench UI built on it) never sees them."""
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT record FROM eval_runs ORDER BY run_id DESC"
            )
            return [
                row["record"] for row in cur.fetchall()
                if row["record"].get("kind") != "verify"
            ]


def get_run(run_id: str) -> dict:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT record FROM eval_runs WHERE run_id = %s",
                (run_id,),
            )
            row = cur.fetchone()
    if row is None:
        raise FileNotFoundError(f"no run {run_id!r}")
    return row["record"]


def get_traces(run_id: str) -> list:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trace FROM eval_results WHERE run_id = %s "
                "ORDER BY case_index",
                (run_id,),
            )
            traces = [row["trace"] for row in cur.fetchall()]
    if not traces:
        raise FileNotFoundError(f"no run {run_id!r}")
    return traces


def get_case_trace(run_id: str, case_id: str) -> dict:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT trace FROM eval_results "
                "WHERE run_id = %s AND case_id = %s",
                (run_id, case_id),
            )
            row = cur.fetchone()
    if row is None:
        raise KeyError(f"no case {case_id!r} in run {run_id!r}")
    return row["trace"]


# ------------------------------------------------------------- verify runs --
# The interactive product's runs (workbench/verify.py) persist in the
# same tables as benchmark runs, distinguished by the kind marker:
# eval_runs.kind = 'verify' and kind='verify' inside the record. The
# dataset reference points at a registered 'verify' dataset whose
# cases list is empty by design: a verify run's input is one
# caller-supplied transcript, stored on its own eval_cases row, and
# it carries no gold labels (its labels_status says so).

VERIFY_DATASET_NAME = "verify"
VERIFY_DATASET_VERSION = "1.0.0"


def verify_dataset_payload() -> dict:
    """The registered dataset row verify runs reference. Empty cases
    on purpose: the input lives on the run's eval_cases row."""
    from .verify import LABELS_STATUS as VERIFY_LABELS_STATUS

    return {
        "name": VERIFY_DATASET_NAME,
        "version": VERIFY_DATASET_VERSION,
        "content_hash": hashlib.sha256(
            _canonical([]).encode("utf-8")
        ).hexdigest(),
        "cases": [],
        "labels_status": VERIFY_LABELS_STATUS,
    }


def _register_verify_dataset(cur) -> None:
    payload = verify_dataset_payload()
    cur.execute(
        """
        INSERT INTO eval_datasets (name, version, content_hash,
            cases, labels_status, created_at)
        VALUES (%(name)s, %(version)s, %(content_hash)s,
            %(cases)s, %(labels_status)s, now())
        ON CONFLICT (name, version) DO NOTHING
        """,
        _wrap(payload, "cases"),
    )


def verify_run_rows(record: dict, trace: dict) -> tuple:
    """Decompose a verify run record + its single trace into
    (run_row, case_row, result_row). Pure, like run_rows: the same
    decomposition the live insert uses."""
    dataset = verify_dataset_payload()
    run_row = {
        "run_id": record["run_id"],
        "kind": "verify",
        "created_at": record["created_at"],
        "prompt_key": "trutrace@1.0.0",
        "prompt_name": "trutrace",
        "prompt_version": "1.0.0",
        "dataset_name": dataset["name"],
        "dataset_version": dataset["version"],
        "dataset_hash": dataset["content_hash"],
        "provider": record["provider"],
        "model": record["model"],
        "status": "error" if record.get("error") else "completed",
        "cases_run": 1,
        "cases_total": 1,
        "labels_status": record["labels_status"],
        "configuration": {
            "kind": "verify",
            "prompt_version": record["prompt_version"],
            "profile": record["profile"],
            "provider": record["provider"],
            "model": record["model"],
            "langfuse": record["langfuse"],
        },
        "metrics": record["summary"],
        "error_log": record.get("error"),
        "record": record,
    }
    case_row = {
        "run_id": record["run_id"],
        "case_id": trace["case_id"],
        "case_index": 0,
        "taxonomy": "user_submitted",
        "input": {
            "question": record["input"].get("question", ""),
            "product": record["input"].get("product", ""),
            "transcript": record["input"]["transcript"],
            "candidate": record["input"]["candidate"],
            "profile": record["profile"],
        },
        "gold": {},
    }
    result_row = {
        "run_id": record["run_id"],
        "case_id": trace["case_id"],
        "case_index": 0,
        "trace_id": trace["trace_id"],
        "status": trace["status"],
        "raw_response": trace.get("raw_response"),
        "raw_extraction": trace.get("raw_extraction"),
        "parsed_output": trace.get("output"),
        "field_scores": record["fields"],
        "unsupported_claims": [
            name for name, entry in record["fields"].items()
            if entry["status"] == "unsupported"
        ],
        "evaluations": None,
        "usage": trace.get("usage") or {},
        "latency_ms": trace.get("latency_ms"),
        "wall_latency_ms": trace.get("wall_latency_ms"),
        "provider_used": trace.get("provider_used"),
        "fallback_used": bool(trace.get("fallback_used")),
        "error": trace.get("error"),
        "trace": trace,
    }
    return run_row, case_row, result_row


def save_verify_run(record: dict, trace: dict) -> None:
    """Persist one verify run in a single transaction: the run row
    (kind='verify'), its single case row (the submitted input, no
    gold), and its result row (the per-field verdicts)."""
    _ensure_schema()
    run_row, case_row, result_row = verify_run_rows(record, trace)
    with _connect() as conn:
        with conn.cursor() as cur:
            _register_verify_dataset(cur)
            cur.execute(
                """
                INSERT INTO eval_runs (run_id, kind, created_at,
                    prompt_key, prompt_name, prompt_version,
                    dataset_name, dataset_version, dataset_hash,
                    provider, model, status, cases_run, cases_total,
                    labels_status, configuration, metrics, error_log,
                    record)
                VALUES (%(run_id)s, %(kind)s, %(created_at)s,
                    %(prompt_key)s, %(prompt_name)s,
                    %(prompt_version)s, %(dataset_name)s,
                    %(dataset_version)s, %(dataset_hash)s,
                    %(provider)s, %(model)s, %(status)s,
                    %(cases_run)s, %(cases_total)s,
                    %(labels_status)s, %(configuration)s, %(metrics)s,
                    %(error_log)s, %(record)s)
                """,
                _wrap(run_row, "configuration", "metrics",
                      "error_log", "record"),
            )
            cur.execute(
                """
                INSERT INTO eval_cases (run_id, case_id,
                    case_index, taxonomy, input, gold)
                VALUES (%(run_id)s, %(case_id)s, %(case_index)s,
                    %(taxonomy)s, %(input)s, %(gold)s)
                """,
                _wrap(case_row, "input", "gold"),
            )
            cur.execute(
                """
                INSERT INTO eval_results (run_id, case_id,
                    case_index, trace_id, status, raw_response,
                    raw_extraction, parsed_output, field_scores,
                    unsupported_claims, evaluations, usage,
                    latency_ms, wall_latency_ms, provider_used,
                    fallback_used, error, trace)
                VALUES (%(run_id)s, %(case_id)s, %(case_index)s,
                    %(trace_id)s, %(status)s, %(raw_response)s,
                    %(raw_extraction)s, %(parsed_output)s,
                    %(field_scores)s, %(unsupported_claims)s,
                    %(evaluations)s, %(usage)s, %(latency_ms)s,
                    %(wall_latency_ms)s, %(provider_used)s,
                    %(fallback_used)s, %(error)s, %(trace)s)
                """,
                _wrap(result_row, "raw_extraction", "parsed_output",
                      "field_scores", "unsupported_claims",
                      "evaluations", "usage", "trace"),
            )


# ------------------------------------------------------------------ reviews --

def _review_record(row: dict) -> dict:
    created = row["created_at"]
    if not isinstance(created, str):
        created = created.isoformat(timespec="seconds")
    return {
        "run_id": row["run_id"],
        "case_id": row["case_id"],
        "field": row["field"],
        "decision": row["decision"],
        "note": row["note"],
        "created_at": created,
    }


def save_review(run_id: str, case_id: str, field: str,
                decision: str, note: str = None) -> dict:
    """Insert or replace one field decision. The primary key is
    (run, case, field), so a later decision replaces the earlier
    one and the table always holds the current decision."""
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT 1 FROM eval_runs WHERE run_id = %s", (run_id,)
            )
            if cur.fetchone() is None:
                raise FileNotFoundError(f"no run {run_id!r}")
            cur.execute(
                """
                INSERT INTO eval_reviews (run_id, case_id, field,
                    decision, note, created_at)
                VALUES (%s, %s, %s, %s, %s, now())
                ON CONFLICT (run_id, case_id, field) DO UPDATE SET
                    decision = EXCLUDED.decision,
                    note = EXCLUDED.note,
                    created_at = EXCLUDED.created_at
                RETURNING *
                """,
                (run_id, case_id, field, decision, note),
            )
            row = cur.fetchone()
    return _review_record(row)


def list_reviews(run_id: str) -> list:
    _ensure_schema()
    with _connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM eval_reviews WHERE run_id = %s "
                "ORDER BY case_id, field",
                (run_id,),
            )
            return [_review_record(row) for row in cur.fetchall()]
