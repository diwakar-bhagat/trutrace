"""PostgreSQL store tests: what can honestly be unit tested without
a database.

Covered here: the store selection rule, the schema as written, the
pure row-building helpers (prompt rows, dataset payloads, run
decomposition), and the no-silent-fallback dispatch. NOT covered
here, by design: actual PostgreSQL behaviour (inserts, conflicts,
round trips through a server). That is verified live against the
real database when the store is exercised; faking a database in
unit tests would prove nothing about it.
"""

import os
import shutil
import unittest
from datetime import datetime, timezone
from unittest import mock

from workbench import pg_store, prompt_store, runner, store
from workbench.datasets import load_split

BOGUS_URL = "postgresql://nobody@127.0.0.1:1/none?connect_timeout=2"


class TestSelection(unittest.TestCase):
    def test_no_database_url_means_file_store(self):
        with mock.patch.dict(os.environ, {}, clear=False):
            os.environ.pop("DATABASE_URL", None)
            self.assertFalse(store.use_postgres())
            self.assertEqual(store.storage_name(), "files")

    def test_database_url_selects_postgres(self):
        with mock.patch.dict(os.environ, {"DATABASE_URL": BOGUS_URL}):
            self.assertTrue(store.use_postgres())
            self.assertEqual(store.storage_name(), "postgresql")

    def test_no_silent_fallback_when_postgres_unreachable(self):
        # With DATABASE_URL set, a dead database must raise, never
        # quietly serve the file store.
        import psycopg

        with mock.patch.dict(os.environ, {"DATABASE_URL": BOGUS_URL}):
            with self.assertRaises(psycopg.OperationalError):
                prompt_store.list_prompts()
            with self.assertRaises(psycopg.OperationalError):
                runner.list_runs()


class TestSchema(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        with open(pg_store.SCHEMA_PATH, encoding="utf-8") as fh:
            cls.sql = fh.read()

    def test_six_tables_all_idempotent(self):
        for table in (
            "eval_prompts", "eval_datasets", "eval_runs",
            "eval_cases", "eval_results", "eval_reviews",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", self.sql)

    def test_verify_kind_marker_and_reviews_shape(self):
        # Verify runs are distinguished from benchmark runs by the
        # kind marker, added idempotently for existing databases.
        self.assertIn(
            "ALTER TABLE eval_runs ADD COLUMN IF NOT EXISTS kind",
            self.sql,
        )
        # Reviews hold one current decision per (run, case, field),
        # restricted to the three decisions the product offers.
        self.assertIn("PRIMARY KEY (run_id, case_id, field)", self.sql)
        self.assertIn(
            "CHECK (decision IN ('approve', 'reject', 'needs_review'))",
            self.sql,
        )

    def test_prompt_versions_unique_and_immutable_shape(self):
        self.assertIn("UNIQUE (name, version)", self.sql)

    def test_results_keep_raw_response_and_scores(self):
        for column in (
            "raw_response", "raw_extraction", "parsed_output",
            "field_scores", "unsupported_claims", "usage",
            "latency_ms",
        ):
            self.assertIn(column, self.sql)

    def test_statements_split_cleanly(self):
        statements = pg_store._statements(self.sql)
        creates = [s for s in statements if s.startswith("CREATE TABLE")]
        self.assertEqual(len(creates), 6)
        for statement in statements:
            self.assertNotIn("--", statement)

    def test_comment_semicolons_do_not_split_statements(self):
        sql = (
            "CREATE TABLE t (a TEXT -- a comment; with a semicolon\n"
            ");\nCREATE TABLE u (b TEXT); -- trailing; comment\n"
        )
        statements = pg_store._statements(sql)
        self.assertEqual(len(statements), 2)
        self.assertTrue(all(s.startswith("CREATE TABLE")
                            for s in statements))


class TestPromptRowMapping(unittest.TestCase):
    def test_record_row_record_roundtrip(self):
        record = {
            "key": "demo@0.1.0", "name": "demo", "version": "0.1.0",
            "parent": None, "created_at": "2026-11-27T05:03:08+00:00",
            "legacy_version": None, "verification": "full",
            "params": {"temperature": 0}, "system": "sys",
            "user": "usr", "notes": "n",
        }
        row = pg_store.prompt_row(record)
        self.assertEqual(row["system_text"], "sys")
        self.assertEqual(row["fingerprint"],
                         prompt_store.prompt_fingerprint(record))
        row["created_at"] = datetime(
            2026, 11, 27, 5, 3, 8, tzinfo=timezone.utc)
        self.assertEqual(pg_store.prompt_record(row), record)


class TestJsonbWrapping(unittest.TestCase):
    """psycopg adapts a bare list to a Postgres ARRAY, not JSONB, so
    every JSONB parameter must be wrapped before execute. This pins
    the mechanism the live failure (dataset registration) exposed."""

    def test_wrap_produces_jsonb_for_dicts_and_lists(self):
        from psycopg.types.json import Jsonb

        row = {"cases": [{"id": 1}], "params": {"temperature": 0},
               "name": "x", "error_log": None}
        wrapped = pg_store._wrap(row, "cases", "params", "error_log")
        self.assertIsInstance(wrapped["cases"], Jsonb)
        self.assertIsInstance(wrapped["params"], Jsonb)
        self.assertIsNone(wrapped["error_log"])
        self.assertEqual(wrapped["name"], "x")
        # The pure row builders stay unwrapped.
        self.assertNotIsInstance(row["cases"], Jsonb)


class TestDatasetPayload(unittest.TestCase):
    def test_splits_register_with_stable_hash_and_counts(self):
        expected = {"dev": 20, "heldout": 12, "campaign": 10, "all": 32}
        for split, count in expected.items():
            payload = pg_store.dataset_payload(split)
            self.assertEqual(len(payload["cases"]), count)
            self.assertEqual(payload["version"], pg_store.DATASET_VERSION)
            self.assertIn("pending human review",
                          payload["labels_status"])
            again = pg_store.dataset_payload(split)
            self.assertEqual(payload["content_hash"],
                             again["content_hash"])


class TestRunRows(unittest.TestCase):
    """Decomposition of a real offline run into the five-table rows,
    using the runner's own persisted artifacts as the input."""

    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()
        cls.run_record = runner.run_experiment(
            "baseline-naive@1.0.0", "offline", None, "campaign")
        cls.traces = runner._read_traces(cls.run_record["run_id"])
        cls.docs = {c.id: c for c in load_split("campaign")}

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(
            os.path.join(runner.RUNS_DIR, cls.run_record["run_id"]),
            ignore_errors=True)

    def test_run_row_carries_configuration_and_status(self):
        run_row, case_rows, result_rows = pg_store.run_rows(
            self.run_record, self.traces, self.docs)
        self.assertEqual(run_row["status"], "completed")
        self.assertIsNone(run_row["error_log"])
        config = run_row["configuration"]
        self.assertEqual(
            config["prompt"]["fingerprint"],
            self.run_record["prompt"]["fingerprint"])
        self.assertEqual(config["dataset"]["name"], "campaign")
        self.assertEqual(len(config["dataset"]["content_hash"]), 64)
        self.assertEqual(run_row["record"], self.run_record)
        self.assertEqual(len(case_rows), 10)
        self.assertEqual(len(result_rows), 10)

    def test_case_rows_carry_inputs_and_gold_as_scored(self):
        _, case_rows, _ = pg_store.run_rows(
            self.run_record, self.traces, self.docs)
        first = case_rows[0]
        doc = self.docs[first["case_id"]]
        self.assertEqual(first["input"]["transcript"], doc.transcript)
        self.assertEqual(
            first["gold"]["price"]["status"],
            doc.gold["price"].status.value)

    def test_result_rows_carry_raw_scores_and_unsupported(self):
        _, _, result_rows = pg_store.run_rows(
            self.run_record, self.traces, self.docs)
        total_unsupported = sum(
            len(r["unsupported_claims"]) for r in result_rows)
        self.assertEqual(
            total_unsupported,
            self.run_record["metrics"]["unsupported_claim_rate"]["unsupported"])
        for row in result_rows:
            # The offline provider has no response text (NULL is the
            # honest value) but its raw extraction is always kept.
            self.assertIsNone(row["raw_response"])
            self.assertIsNotNone(row["raw_extraction"])
            self.assertIsNotNone(row["parsed_output"])
            self.assertEqual(row["trace"]["case_id"], row["case_id"])


if __name__ == "__main__":
    unittest.main()
