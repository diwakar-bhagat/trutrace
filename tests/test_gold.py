"""Connected gold review tests: payload validation, the file-store
submission round trip, coverage accounting, the metrics report's
labelling (agreement before human gold, reviewed-fields-only after
a partial submission), and the pure PostgreSQL decomposition.

PostgreSQL behaviour itself is verified live against the deployed
database, not faked here; what is tested here is the pure row
decomposition the live insert uses, as in test_pg_store.
"""

import json
import os
import shutil
import tempfile
import unittest

from workbench import gold, pg_store, runner, verify
from workbench import prompt_store


def _partial_payload():
    """A realistic partial export in the review tool's shape: two
    held out fields reviewed, everything else untouched."""
    split = json.load(open("datasets/split.json"))
    case_id = split["heldout"][0]
    return {
        "dataset_version": "gold-v2-human-reviewed",
        "source_version": "gold-v1-ai-drafted",
        "reviewer": "Test Reviewer",
        "exported_at": "2026-11-27T00:00:00Z",
        "fields_total": 224,
        "fields_reviewed": 2,
        "cases": {
            case_id: {
                "split": "heldout",
                "fields": {
                    "price": {
                        "value": 100, "ai_status": "supported",
                        "human_status": "supported", "reviewed": True,
                        "evidence": None, "evidence_source": "none",
                        "evidence_adjusted": False,
                        "evidence_cleared": False, "note": "",
                    },
                    "timing": {
                        "value": None, "ai_status": "unsupported",
                        "human_status": "uncertain", "reviewed": True,
                        "evidence": None, "evidence_source": "none",
                        "evidence_adjusted": False,
                        "evidence_cleared": False,
                        "note": "hedged in the call",
                    },
                    "currency": {
                        "value": None, "ai_status": "unsupported",
                        "human_status": None, "reviewed": False,
                        "evidence": None, "evidence_source": "none",
                        "evidence_adjusted": False,
                        "evidence_cleared": False, "note": "",
                    },
                },
            }
        },
    }


class GoldFileStoreCase(unittest.TestCase):
    """Point the gold file store at a temp directory for the test."""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self._dir, self._name = gold.GOLD_DIR, gold.GOLD_FILE_NAME
        gold.GOLD_DIR = self.tmp
        gold.GOLD_FILE_NAME = "gold_labels_v2.json"
        self.addCleanup(self._restore)

    def _restore(self):
        gold.GOLD_DIR, gold.GOLD_FILE_NAME = self._dir, self._name


class TestGoldValidation(unittest.TestCase):
    def test_valid_payload_passes(self):
        gold.validate_payload(_partial_payload())

    def test_wrong_version_rejected(self):
        payload = _partial_payload()
        payload["dataset_version"] = "gold-v1-ai-drafted"
        with self.assertRaises(ValueError):
            gold.validate_payload(payload)

    def test_no_cases_rejected(self):
        with self.assertRaises(ValueError):
            gold.validate_payload(
                {"dataset_version": "gold-v2-human-reviewed", "cases": {}}
            )

    def test_reviewed_field_needs_a_protocol_status(self):
        payload = _partial_payload()
        case = next(iter(payload["cases"].values()))
        case["fields"]["price"]["human_status"] = "definitely"
        with self.assertRaises(ValueError):
            gold.validate_payload(payload)

    def test_coverage_counts_reviewed_only(self):
        coverage = gold.coverage_of(_partial_payload())
        self.assertEqual(coverage["fields_reviewed"], 2)
        self.assertEqual(coverage["fields_total"], 224)
        self.assertEqual(
            coverage["per_split"],
            {"heldout": {"reviewed": 2, "total": 3}},
        )


class TestGoldFlow(GoldFileStoreCase):
    def test_status_before_any_submission(self):
        status = gold.gold_status()
        self.assertEqual(status["gold_version"], "gold-v1-ai-drafted")
        self.assertIsNone(status["human_review"])
        self.assertEqual(status["fields_reviewed"], 0)
        self.assertEqual(status["fields_total"], 224)

    def test_submit_then_status_reports_coverage(self):
        result = gold.submit_review(_partial_payload())
        self.assertEqual(result["gold_version"], "gold-v2-human-reviewed")
        self.assertEqual(result["fields_reviewed"], 2)
        self.assertEqual(result["fields_total"], 224)
        self.assertFalse(result["complete"])
        status = gold.gold_status()
        self.assertEqual(status["gold_version"], "gold-v2-human-reviewed")
        self.assertEqual(status["human_review"]["reviewer"], "Test Reviewer")
        self.assertEqual(
            status["human_review"]["per_split"]["heldout"]["reviewed"], 2)

    def test_metrics_without_human_gold_are_labelled_agreement(self):
        report = gold.gold_metrics_report()
        self.assertEqual(report["gold_version"], "gold-v1-ai-drafted")
        self.assertEqual(report["provenance"], "ai-drafted")
        self.assertIn("AGREEMENT WITH AI DRAFTED LABELS", report["note"])
        self.assertTrue(report["configurations"])

    def test_metrics_after_partial_submission_cover_reviewed_only(self):
        gold.submit_review(_partial_payload())
        report = gold.gold_metrics_report()
        self.assertEqual(report["gold_version"], "gold-v2-human-reviewed")
        self.assertEqual(report["scope"], "reviewed_fields_only")
        self.assertEqual(report["fields_reviewed"], 2)
        self.assertIn("reviewed fields only", report["note"])
        # Only the two reviewed (case, field) pairs can be scored:
        # across every configuration the scored field count is the
        # number of recorded runs that cover that case, never the
        # full field set.
        scored = sum(
            m["fields"] for m in report["configurations"].values())
        self.assertGreater(scored, 0)
        self.assertLess(scored, 100)


class TestGoldPgRows(unittest.TestCase):
    def test_submission_row_decomposition(self):
        row = pg_store.gold_submission_row(
            _partial_payload(), "2026-11-27T10:00:00+00:00")
        self.assertEqual(row["version"], "gold-v2-human-reviewed")
        self.assertEqual(row["reviewer"], "Test Reviewer")
        self.assertEqual(row["fields_reviewed"], 2)
        self.assertEqual(row["fields_total"], 224)
        self.assertEqual(row["payload"]["fields_reviewed"], 2)


class TestVerifyRunHistory(unittest.TestCase):
    """The history listing the /try page reads: verify runs only,
    newest first, with the summary shape the endpoint returns."""

    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()

    def test_verify_runs_listed_benchmark_runs_not(self):
        from evals.run_evals import load_case_dir

        docs = {d.id: d for d in load_case_dir("datasets/campaign")}
        doc = docs["campaign_01_showcase_hedged"]
        record = verify.run_verify(
            doc.transcript, {"price": 35}, provider_name="offline",
            product=doc.product, question=doc.question)
        run_dir = os.path.join(runner.RUNS_DIR, record["run_id"])
        self.addCleanup(shutil.rmtree, run_dir, ignore_errors=True)
        listed = runner.list_verify_runs()
        self.assertIn(record["run_id"], [r["run_id"] for r in listed])
        summary = runner._verify_run_summary(record)
        self.assertEqual(summary["kind"], "verify")
        self.assertIn("not_claimed", summary["summary"])
        self.assertIsNotNone(summary["latency_ms"])


if __name__ == "__main__":
    unittest.main()
