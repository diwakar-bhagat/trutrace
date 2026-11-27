"""Regression tests: real baseline failures, pinned.

Each test names a case where the baseline configuration (prompt
"baseline-naive", verification off) demonstrably failed on the golden
dataset — the failure is recorded in
evals/results/offline_baseline_scorecard.json — and asserts that the
current configuration gets it right. If a future change reintroduces
the failure, the suite says which call it came back on.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from app.schemas import TranscriptDoc  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "datasets", "transcripts")


def run_case(case_id, prompt_version):
    with open(os.path.join(DATA, case_id + ".json"), encoding="utf-8") as fh:
        doc = TranscriptDoc.model_validate(json.load(fh))
    return run_pipeline(doc, provider_name="offline",
                        prompt_version=prompt_version)


def field(case_id, name, prompt_version="trutrace-1.0.0"):
    return run_case(case_id, prompt_version).answer.fields[name]


class TestBaselineFailuresNowFixed(unittest.TestCase):
    def test_contradictory_prices_are_flagged_not_asserted(self):
        # baseline asserted $120; the call also says $135.
        base = field("tyre_shop_contradiction", "price", "baseline-naive")
        self.assertEqual(base.status.value, "confirmed")
        self.assertEqual(base.value, 120.0)
        now = field("tyre_shop_contradiction", "price")
        self.assertEqual(now.status.value, "conflicting")
        self.assertIsNone(now.value)
        self.assertEqual(sorted(now.candidates), [120.0, 135.0])

    def test_stale_price_is_not_the_current_price(self):
        # baseline asserted last week's $42; the call says $48 today.
        base = field("hardware_paint_temporal", "price", "baseline-naive")
        self.assertEqual(base.value, 42.0)
        now = field("hardware_paint_temporal", "price")
        self.assertEqual(now.status.value, "confirmed")
        self.assertEqual(now.value, 48.0)

    def test_delivery_fee_is_not_the_product_price(self):
        # baseline asserted the $10 delivery fee as the price of roses.
        base = field("florist_delivery_fee_inference", "price", "baseline-naive")
        self.assertEqual(base.value, 10.0)
        now = field("florist_delivery_fee_inference", "price")
        self.assertEqual(now.status.value, "unconfirmed")
        self.assertIsNone(now.value)

    def test_hedged_availability_is_not_asserted(self):
        # baseline asserted in_stock on "we carry them, though I am not
        # sure any bottles are on the shelf".
        base = field("pharmacy_vitamind_uncertain", "availability",
                     "baseline-naive")
        self.assertEqual(base.status.value, "confirmed")
        now = field("pharmacy_vitamind_uncertain", "availability")
        self.assertEqual(now.status.value, "uncertain")

    def test_conflicting_times_are_flagged(self):
        # baseline asserted 3 pm; the seller corrected it to 4 pm in a
        # way that leaves both times on the record.
        base = field("salon_timing_contradiction", "timing", "baseline-naive")
        self.assertEqual(base.value, "at 3 pm")
        now = field("salon_timing_contradiction", "timing")
        self.assertEqual(now.status.value, "conflicting")
        self.assertIsNone(now.value)

    def test_price_for_another_product_is_not_asserted(self):
        # baseline asserted the $70 standard colour price as the price
        # of a balayage, which the seller never priced.
        base = field("salon_balayage_conditional", "price", "baseline-naive")
        self.assertEqual(base.value, 70.0)
        now = field("salon_balayage_conditional", "price")
        self.assertEqual(now.status.value, "uncertain")
        self.assertIsNone(now.value)


if __name__ == "__main__":
    unittest.main()
