"""Which store the workbench uses, and why.

One rule, no silent fallback:

- DATABASE_URL set   -> PostgreSQL (workbench/pg_store.py), schema
  in workbench/schema.sql. If the database is unreachable or the
  schema does not apply, operations raise: a deployed workbench must
  never quietly write runs to an ephemeral filesystem and call that
  persistence.
- DATABASE_URL unset -> the file store (prompts/ and runs/ in the
  repo), exactly as the workbench has always behaved locally.

The pipeline, metrics and API shapes are identical either way; only
where records live changes.
"""

import os


def use_postgres() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def storage_name() -> str:
    return "postgresql" if use_postgres() else "files"
