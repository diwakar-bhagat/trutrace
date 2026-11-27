"""Interactive verify path tests: the offline provider, the guards,
the review round trip, and the PostgreSQL decomposition.

The verify tests run the real engine over the campaign_01 transcript
with the candidate the offline baseline actually produces for it
(the hedges asserted as facts), so the expected statuses are the
engine's own judgements, recorded here: the hedged price, stock and
timing come back uncertain, the plainly stated currency supported,
and the fields the candidate never claims unsupported.

PostgreSQL behaviour itself is verified live against the deployed
database, not faked here; what is tested here is the pure row
decomposition the live insert uses, exactly as test_pg_store does
for benchmark runs.
"""

import os
import shutil
import unittest

from app.pipeline import run_pipeline
from evals.run_evals import load_case_dir
from workbench import pg_store, prompt_store, reviews, runner, verify


def _campaign_01():
    docs = {d.id: d for d in load_case_dir("datasets/campaign")}
    return docs["campaign_01_showcase_hedged"]


def _baseline_candidate(doc):
    """The candidate JSON the demo preloads: the baseline style
    extraction of campaign_01, which asserts the hedges."""
    answer = run_pipeline(
        doc, provider_name="offline", prompt_version="baseline-naive"
    ).answer
    return {
        name: field.value
        for name, field in answer.fields.items()
        if field.value is not None
    }


class TestVerifyOffline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()
        cls.doc = _campaign_01()
        cls.candidate = _baseline_candidate(cls.doc)

    def _run(self, **kwargs):
        record = verify.run_verify(
            self.doc.transcript, self.candidate,
            provider_name="offline",
            product=self.doc.product, question=self.doc.question,
            **kwargs,
        )
        self.addCleanup(
            shutil.rmtree,
            os.path.join(runner.RUNS_DIR, record["run_id"]),
            ignore_errors=True,
        )
        return record

    def test_candidate_is_the_hedge_asserting_baseline(self):
        # Sanity on the fixture itself: the baseline asserts the
        # hedged price, stock and timing as plain facts.
        self.assertEqual(self.candidate["price"], 35)
        self.assertEqual(self.candidate["currency"], "USD")
        self.assertEqual(self.candidate["availability"], "in_stock")
        self.assertEqual(self.candidate["timing"], "tomorrow morning")

    def test_statuses_on_known_transcript_and_candidate(self):
        record = self._run()
        fields = record["fields"]
        # Stated plainly in the call: supported, with evidence.
        self.assertEqual(fields["currency"]["status"], "supported")
        self.assertIn("$35", fields["currency"]["evidence"])
        # Hedged in the call ("around", "usually", "probably"): the
        # engine demotes them, and the product says uncertain, which
        # is distinguishable from unsupported.
        for name in ("price", "availability", "timing"):
            self.assertEqual(fields[name]["status"], "uncertain", name)
            self.assertTrue(fields[name]["evidence"], name)
        # Never claimed by the candidate: unsupported, with the
        # absence stated as the reason and no evidence invented.
        for name in ("quantity_or_stock", "delivery_or_pickup",
                     "contact_next_step"):
            self.assertEqual(fields[name]["status"], "unsupported", name)
            self.assertIsNone(fields[name]["evidence"], name)
            self.assertIn(
                "does not provide", fields[name]["reason"], name)
        self.assertEqual(
            record["summary"],
            {"supported": 1, "uncertain": 3, "unsupported": 3,
             "contradictory": 0, "total": 7},
        )

    def test_every_field_carries_evidence_or_explicit_absence(self):
        record = self._run()
        for name, entry in record["fields"].items():
            if entry["evidence"] is None:
                # Absence is explicit: a reason says so, never a
                # blank where evidence should be.
                self.assertTrue(entry["reason"], name)
            else:
                self.assertIn(entry["evidence"], self.doc.transcript, name)

    def test_run_persists_distinguished_and_reproducible(self):
        record = self._run()
        self.assertEqual(record["kind"], "verify")
        self.assertIn("no gold labels", record["labels_status"])
        # The full input is stored, so the run is reproducible.
        self.assertEqual(record["input"]["transcript"], self.doc.transcript)
        self.assertEqual(record["input"]["candidate"], self.candidate)
        loaded = verify.get_verify_run(record["run_id"])
        self.assertEqual(loaded, record)
        # Benchmark run lists never see verify runs.
        listed = {r["run_id"] for r in runner.list_runs()}
        self.assertNotIn(record["run_id"], listed)

    def test_unverifiable_claim_is_unsupported_with_reason(self):
        candidate = dict(self.candidate, price=999)
        record = verify.run_verify(
            self.doc.transcript, candidate, provider_name="offline",
            product=self.doc.product, question=self.doc.question)
        self.addCleanup(
            shutil.rmtree,
            os.path.join(runner.RUNS_DIR, record["run_id"]),
            ignore_errors=True,
        )
        price = record["fields"]["price"]
        self.assertEqual(price["status"], "unsupported")
        self.assertIn("not supported", price["reason"])

    def test_extra_candidate_fields_are_reported_unverified(self):
        candidate = dict(self.candidate, warranty_years=2)
        record = verify.run_verify(
            self.doc.transcript, candidate, provider_name="offline",
            product=self.doc.product, question=self.doc.question)
        self.addCleanup(
            shutil.rmtree,
            os.path.join(runner.RUNS_DIR, record["run_id"]),
            ignore_errors=True,
        )
        self.assertIn("warranty_years", record["unverified"])
        self.assertNotIn("warranty_years", record["fields"])


class TestVerifyGuards(unittest.TestCase):
    def test_size_cap(self):
        with self.assertRaises(ValueError) as ctx:
            verify.run_verify(
                "x" * (verify.MAX_TRANSCRIPT_CHARS + 1), {},
                provider_name="offline",
            )
        self.assertIn(str(verify.MAX_TRANSCRIPT_CHARS), str(ctx.exception))

    def test_model_restriction(self):
        with self.assertRaises(ValueError):
            verify.run_verify(
                "a transcript", {}, provider_name="openrouter",
                model="openai/gpt-4o",
            )
        with self.assertRaises(ValueError):
            verify.run_verify(
                "a transcript", {}, provider_name="offline",
                model="openai/gpt-4o-mini",
            )
        with self.assertRaises(ValueError):
            verify.run_verify(
                "a transcript", {}, provider_name="anthropic")

    def test_profile_validation(self):
        with self.assertRaises(ValueError):
            verify.resolve_profile(["price", "not_a_field"])
        with self.assertRaises(ValueError):
            verify.resolve_profile([])
        name, fields = verify.resolve_profile(None)
        self.assertEqual(name, "campaign")
        self.assertEqual(len(fields), 7)
        name, fields = verify.resolve_profile(["timing", "price"])
        self.assertEqual(fields, ["price", "timing"])


class TestReviews(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()
        cls.doc = _campaign_01()

    def test_review_round_trip_on_verify_run(self):
        record = verify.run_verify(
            self.doc.transcript, _baseline_candidate(self.doc),
            provider_name="offline",
            product=self.doc.product, question=self.doc.question,
        )
        run_dir = os.path.join(runner.RUNS_DIR, record["run_id"])
        self.addCleanup(shutil.rmtree, run_dir, ignore_errors=True)
        self.assertEqual(reviews.list_reviews(record["run_id"]), [])
        entry = reviews.record_review(
            record["run_id"], "submission", "price", "approve",
            note="hedge handled correctly",
        )
        self.assertEqual(entry["decision"], "approve")
        listed = reviews.list_reviews(record["run_id"])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["field"], "price")
        # A later decision on the same field replaces the earlier.
        reviews.record_review(
            record["run_id"], "submission", "price", "reject")
        listed = reviews.list_reviews(record["run_id"])
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0]["decision"], "reject")

    def test_review_on_benchmark_run(self):
        run = runner.run_experiment(
            "baseline-naive@1.0.0", "offline", None, "campaign")
        self.addCleanup(
            shutil.rmtree,
            os.path.join(runner.RUNS_DIR, run["run_id"]),
            ignore_errors=True,
        )
        entry = reviews.record_review(
            run["run_id"], "campaign_01_showcase_hedged", "price",
            "needs_review",
        )
        self.assertEqual(entry["case_id"], "campaign_01_showcase_hedged")
        self.assertEqual(
            reviews.list_reviews(run["run_id"])[0]["decision"],
            "needs_review",
        )

    def test_review_validation(self):
        with self.assertRaises(ValueError):
            reviews.record_review(
                "whatever", "submission", "price", "maybe")
        with self.assertRaises(FileNotFoundError):
            reviews.record_review(
                "no_such_run", "submission", "price", "approve")


class TestVerifyPgRows(unittest.TestCase):
    """The pure decomposition save_verify_run inserts with."""

    @classmethod
    def setUpClass(cls):
        prompt_store.load_all()
        doc = _campaign_01()
        # run_verify persists through the file store in the test
        # environment; read the trace back, then clean up.
        cls.record = verify.run_verify(
            doc.transcript, _baseline_candidate(doc),
            provider_name="offline",
            product=doc.product, question=doc.question,
        )
        run_dir = os.path.join(runner.RUNS_DIR, cls.record["run_id"])
        with open(os.path.join(run_dir, "cases.jsonl"),
                  encoding="utf-8") as fh:
            import json
            cls.trace = json.loads(fh.readline())
        shutil.rmtree(run_dir, ignore_errors=True)

    def test_rows_carry_the_kind_marker(self):
        run_row, case_row, result_row = pg_store.verify_run_rows(
            self.record, self.trace)
        self.assertEqual(run_row["kind"], "verify")
        self.assertEqual(run_row["record"]["kind"], "verify")
        self.assertEqual(run_row["prompt_key"], "trutrace@1.0.0")
        self.assertEqual(run_row["dataset_name"], "verify")
        self.assertEqual(run_row["cases_run"], 1)
        # The case carries the submitted input and no gold labels.
        self.assertEqual(case_row["gold"], {})
        self.assertEqual(
            case_row["input"]["candidate"],
            self.record["input"]["candidate"],
        )
        # Unsupported claims are the fields judged unsupported.
        self.assertEqual(
            sorted(result_row["unsupported_claims"]),
            ["contact_next_step", "delivery_or_pickup",
             "quantity_or_stock"],
        )

    def test_verify_dataset_payload_is_stable_and_labelless(self):
        a = pg_store.verify_dataset_payload()
        b = pg_store.verify_dataset_payload()
        self.assertEqual(a["content_hash"], b["content_hash"])
        self.assertEqual(a["cases"], [])
        self.assertIn("no gold labels", a["labels_status"])


class TestRateLimiter(unittest.TestCase):
    def test_limit_and_window(self):
        from workbench.server import _RateLimiter

        limiter = _RateLimiter(limit=3, window_seconds=60.0)
        self.assertTrue(limiter.allow("a", now=100.0))
        self.assertTrue(limiter.allow("a", now=101.0))
        self.assertTrue(limiter.allow("a", now=102.0))
        self.assertFalse(limiter.allow("a", now=103.0))
        # A different client has its own bucket.
        self.assertTrue(limiter.allow("b", now=103.0))
        # The window slides: the first hit expires.
        self.assertTrue(limiter.allow("a", now=161.0))


if __name__ == "__main__":
    unittest.main()
