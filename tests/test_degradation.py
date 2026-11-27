"""Degradation tests: a provider dying is a tested behaviour.

The scenario from the report, as automated tests: a provider is killed
on demand (DeadProvider, KillAfterProvider) and the pipeline must fall
back to the second provider, or return every field unconfirmed. It
must never raise out of the pipeline and never invent an answer.
Reproduce with: python -m unittest tests.test_degradation
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_batch, run_pipeline  # noqa: E402
from app.providers.killswitch import DeadProvider, KillAfterProvider  # noqa: E402
from app.providers.offline import OfflineProvider  # noqa: E402
from app.schemas import FIELDS, TranscriptDoc  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "datasets", "transcripts")


def load(case_id):
    with open(os.path.join(DATA, case_id + ".json"), encoding="utf-8") as fh:
        return TranscriptDoc.model_validate(json.load(fh))


DOC = load("florist_roses_clean")


class TestFallback(unittest.TestCase):
    def test_dead_primary_falls_back(self):
        result = run_pipeline(
            DOC,
            provider=DeadProvider(),
            fallback_provider=OfflineProvider(),
        )
        self.assertTrue(result.fallback_used)
        self.assertEqual(result.provider_used, "offline")
        self.assertTrue(result.answer.confirmed_values())

    def test_dead_primary_without_fallback_is_unconfirmed_not_invented(self):
        result = run_pipeline(DOC, provider=DeadProvider())
        self.assertIsNone(result.provider_used)
        self.assertIsNotNone(result.error)
        for name in FIELDS:
            f = result.answer.fields[name]
            self.assertEqual(f.status.value, "unconfirmed", name)
            self.assertIsNone(f.value, name)
            self.assertIn("provider unavailable", f.reason)

    def test_dead_primary_and_dead_fallback_is_unconfirmed(self):
        result = run_pipeline(
            DOC,
            provider=DeadProvider("primary down"),
            fallback_provider=DeadProvider("fallback down"),
        )
        self.assertIsNone(result.provider_used)
        self.assertIn("primary down", result.error)
        self.assertIn("fallback down", result.error)
        self.assertEqual(result.answer.confirmed_values(), {})


class TestMidRunDeath(unittest.TestCase):
    def test_provider_killed_mid_batch_falls_back_per_transcript(self):
        docs = [load(c) for c in (
            "florist_roses_clean", "bakery_sourdough_clean",
            "pet_store_dogfood_clean", "bike_shop_tuneup_clean",
        )]
        primary = KillAfterProvider(OfflineProvider(), kill_after=2)
        results, summary = run_batch(
            docs, primary, fallback_provider=OfflineProvider(),
        )
        self.assertEqual(len(results), 4)
        self.assertEqual(summary["served_by_primary"], 2)
        self.assertEqual(summary["served_by_fallback"], 2)
        self.assertEqual(summary["unavailable"], 0)
        for r in results:
            self.assertTrue(r.answer.confirmed_values())

    def test_provider_killed_mid_batch_without_fallback_keeps_partials(self):
        docs = [load(c) for c in (
            "florist_roses_clean", "bakery_sourdough_clean",
            "bike_shop_tuneup_clean",
        )]
        primary = KillAfterProvider(OfflineProvider(), kill_after=1)
        results, summary = run_batch(docs, primary)
        self.assertEqual(len(results), 3)
        self.assertEqual(summary["served_by_primary"], 1)
        self.assertEqual(summary["unavailable"], 2)
        self.assertTrue(results[0].answer.confirmed_values())
        for r in results[1:]:
            self.assertEqual(r.answer.confirmed_values(), {})


if __name__ == "__main__":
    unittest.main()
