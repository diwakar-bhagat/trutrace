"""Prompt Lab store: prompts as first-class, immutable version files.

Each prompt version is one JSON file in prompts/, named
<name>@<version>.json, holding:

  key, name, version, parent (the version it was cloned from),
  created_at, verification profile ("full" = every verification
  toggle on, "passthrough" = the baseline stance, every toggle off),
  params (model parameters, today just temperature), the system text,
  the user text, and notes.

Immutability is the point: save_new_version refuses to write a
version that already exists, so a version that a completed run
references can never be silently overwritten. Editing always produces
a new version. Cloning is just saving with a parent set.

On load, every file is registered with the existing pipeline:
app.prompts.register_prompt_version supplies the text and
app.config.register_config supplies the verification profile, so
run_pipeline(prompt_version=<key>) works with no further code. The
two legacy code-defined versions (baseline-naive, trutrace-1.0.0) are
untouched; the seed files below mirror them exactly (the seed text is
derived from the legacy templates, and a test asserts the assembled
prompts are byte-identical).

Storage: the files are the store unless DATABASE_URL is set, in
which case the same operations run against PostgreSQL
(workbench/pg_store.py) and the files serve only as the registration
source on first load. Selection is workbench/store.py's one rule;
there is no silent fallback between the two.
"""

import difflib
import hashlib
import json
import os
from datetime import datetime, timezone

from app import prompts as app_prompts
from app.config import PipelineConfig, register_config

from . import pg_store, store

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROMPTS_DIR = os.path.join(ROOT, "prompts")

PROFILES = ("full", "passthrough")

# The verification toggles a "passthrough" profile turns off: exactly
# the baseline configuration's stance in app/config.py.
_PASSTHROUGH_OFF = dict(
    grounding=False,
    hedge_demotion=False,
    contradiction_detection=False,
    stale_filter=False,
    fee_filter=False,
    correction_supersede=False,
    product_restriction=False,
    product_mismatch_demotion=False,
    conditional_pricing=False,
    approximate_demotion=False,
)


def key_of(name: str, version: str) -> str:
    return f"{name}@{version}"


def _path_for(name: str, version: str) -> str:
    return os.path.join(PROMPTS_DIR, f"{key_of(name, version)}.json")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------- seed --

def _split_template(template: str):
    """Split a legacy single-string template into (system, user) at the
    transcript block, undoing the str.format brace escapes in the tail."""
    head, sep, tail = template.partition("\n\nTranscript:\n")
    if not sep:
        raise ValueError("legacy template has no transcript block")
    return head, "Transcript:\n" + tail.replace("{{", "{").replace("}}", "}")


def _seed_records() -> list:
    """The two seed prompt records mirroring the legacy code-defined
    versions, as record dicts (no disk access)."""
    seeds = []
    head, user = _split_template(app_prompts._NAIVE_TEMPLATE)
    seeds.append({
        "name": "baseline-naive", "version": "1.0.0",
        "legacy_version": "baseline-naive", "verification": "passthrough",
        "system": head, "user": user,
        "notes": "Seeded from the legacy code-defined prompt "
                 "'baseline-naive' in app/prompts.py. The thin-wrapper "
                 "prompt: schema fields only, no evidence requested.",
    })
    head, user = _split_template(app_prompts._TRUTRACE_TEMPLATE)
    system = head.replace("{rules}", app_prompts._TRUTRACE_RULES)
    seeds.append({
        "name": "trutrace", "version": "1.0.0",
        "legacy_version": "trutrace-1.0.0", "verification": "full",
        "system": system, "user": user,
        "notes": "Seeded from the legacy code-defined prompt "
                 "'trutrace-1.0.0' in app/prompts.py. The harness "
                 "prompt: evidence, candidates and quality rules "
                 "required.",
    })
    return [
        {
            "key": key_of(seed["name"], seed["version"]),
            "name": seed["name"],
            "version": seed["version"],
            "parent": None,
            "created_at": _now(),
            "legacy_version": seed["legacy_version"],
            "verification": seed["verification"],
            "params": {"temperature": 0},
            "system": seed["system"],
            "user": seed["user"],
            "notes": seed["notes"],
        }
        for seed in seeds
    ]


def seed_legacy_prompts() -> None:
    """Write the two seed prompt files mirroring the legacy code-defined
    versions, if they are not already on disk. Never overwrites."""
    os.makedirs(PROMPTS_DIR, exist_ok=True)
    for record in _seed_records():
        path = _path_for(record["name"], record["version"])
        if os.path.exists(path):
            continue
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)


# --------------------------------------------------------------------- load --

def _config_for(record: dict) -> PipelineConfig:
    key = record["key"]
    if record["verification"] == "full":
        return PipelineConfig(prompt_version=key)
    return PipelineConfig(
        prompt_version=key, label_override="baseline", **_PASSTHROUGH_OFF
    )


def load_all() -> list:
    """Seed (if needed), then register every prompt version with the
    pipeline. Returns the prompt records, sorted by name and version.

    With DATABASE_URL set, the versions live in PostgreSQL: the repo's
    prompt files and seed records are registered into eval_prompts
    (see pg_store.ensure_ready) and read back from there. Without it,
    the files in prompts/ are the store, as before."""
    if store.use_postgres():
        registration = {r["key"]: r for r in _seed_records()}
        for record in _read_file_records():
            registration[record["key"]] = record
        pg_store.ensure_ready(list(registration.values()))
        records = pg_store.list_prompts()
    else:
        seed_legacy_prompts()
        records = _read_file_records()
    for record in records:
        app_prompts.register_prompt_version(
            record["key"], record["system"], record["user"]
        )
        register_config(record["key"], _config_for(record))
    return records


def _read_file_records() -> list:
    if not os.path.isdir(PROMPTS_DIR):
        return []
    records = []
    for fname in sorted(os.listdir(PROMPTS_DIR)):
        if not fname.endswith(".json"):
            continue
        with open(os.path.join(PROMPTS_DIR, fname), encoding="utf-8") as fh:
            records.append(json.load(fh))
    records.sort(key=lambda r: (r["name"], r["version"]))
    return records


def list_prompts() -> list:
    if store.use_postgres():
        return pg_store.list_prompts()
    return _read_file_records()


def get_prompt(key: str) -> dict:
    if store.use_postgres():
        return pg_store.get_prompt(key)
    for record in _read_file_records():
        if record["key"] == key:
            return record
    raise KeyError(f"no prompt version {key!r}")


# --------------------------------------------------------------------- save --

def save_new_version(
    name: str,
    version: str,
    system: str,
    user: str,
    temperature: float = 0,
    verification: str = "full",
    notes: str = "",
    parent: str = None,
) -> dict:
    """Save a NEW immutable prompt version. Refuses to overwrite an
    existing version: that refusal is what makes a completed run's
    prompt reference exact."""
    if verification not in PROFILES:
        raise ValueError(
            f"verification profile must be one of {PROFILES}, "
            f"got {verification!r}"
        )
    if not name or not version:
        raise ValueError("name and version are required")
    if "/" in name or "/" in version or "@" in name:
        raise ValueError("name and version may not contain '/' or '@' in name")
    record = {
        "key": key_of(name, version),
        "name": name,
        "version": version,
        "parent": parent,
        "created_at": _now(),
        "legacy_version": None,
        "verification": verification,
        "params": {"temperature": temperature},
        "system": system,
        "user": user,
        "notes": notes,
    }
    if store.use_postgres():
        pg_store.insert_prompt(record)
    else:
        os.makedirs(PROMPTS_DIR, exist_ok=True)
        path = _path_for(name, version)
        if os.path.exists(path):
            raise FileExistsError(
                f"prompt version {key_of(name, version)} already exists and "
                "versions are immutable; save under a new version number"
            )
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(record, fh, indent=2, ensure_ascii=False)
    app_prompts.register_prompt_version(record["key"], system, user)
    register_config(record["key"], _config_for(record))
    return record


# --------------------------------------------------------------------- diff --

def prompt_fingerprint(record: dict) -> str:
    """SHA-256 over the exact texts and parameters: what a run records
    so its prompt can be verified byte for byte later."""
    blob = json.dumps(
        {
            "system": record["system"],
            "user": record["user"],
            "params": record.get("params", {}),
            "verification": record["verification"],
        },
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def diff_prompts(key_a: str, key_b: str) -> dict:
    a, b = get_prompt(key_a), get_prompt(key_b)
    out = {"a": key_a, "b": key_b}
    for part in ("system", "user"):
        diff = difflib.unified_diff(
            a[part].splitlines(),
            b[part].splitlines(),
            fromfile=f"{key_a} {part}",
            tofile=f"{key_b} {part}",
            lineterm="",
        )
        out[f"{part}_diff"] = "\n".join(diff)
    params = {}
    keys = set(a.get("params", {})) | set(b.get("params", {}))
    for k in sorted(keys):
        va, vb = a.get("params", {}).get(k), b.get("params", {}).get(k)
        if va != vb:
            params[k] = [va, vb]
    out["param_changes"] = params
    out["verification_change"] = (
        [a["verification"], b["verification"]]
        if a["verification"] != b["verification"]
        else None
    )
    out["fingerprint_a"] = prompt_fingerprint(a)
    out["fingerprint_b"] = prompt_fingerprint(b)
    return out
