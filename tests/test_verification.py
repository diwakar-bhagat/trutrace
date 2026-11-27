"""Verification behaviour tests on real dataset cases (offline
provider): each test pins one engine rule on the call that exercises it.
"""

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from app.schemas import TranscriptDoc  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "datasets", "transcripts")


def field(case_id, name):
    with open(os.path.join(DATA, case_id + ".json"), encoding="utf-8") as fh:
        doc = TranscriptDoc.model_validate(json.load(fh))
    result = run_pipeline(doc, provider_name="offline",
                          prompt_version="trutrace-1.0.0")
    return result.answer.fields[name]


class TestPriceResolution(unittest.TestCase):
    def test_conditional_pricing_resolves_to_the_asked_condition(self):
        f = field("florist_roses_conditional", "price")
        self.assertEqual(f.status.value, "confirmed")
        self.assertEqual(f.value, 35.0)
        self.assertIn("standard", f.condition)

    def test_correction_supersedes_the_earlier_quote(self):
        f = field("grocery_oatmilk_correction", "price")
        self.assertEqual(f.status.value, "confirmed")
        self.assertEqual(f.value, 5.0)

    def test_wrong_entity_price_is_not_picked(self):
        f = field("pharmacy_d2d3_confusion", "price")
        self.assertEqual(f.status.value, "confirmed")
        self.assertEqual(f.value, 14.0)

    def test_starting_price_is_uncertain_with_condition(self):
        f = field("cake_wedding_starting_price", "price")
        self.assertEqual(f.status.value, "uncertain")
        self.assertEqual(f.condition, "starting price")

    def test_approximate_price_is_uncertain(self):
        f = field("electronics_battery_uncertain", "price")
        self.assertEqual(f.status.value, "uncertain")
        self.assertEqual(f.value, 85.0)

    def test_stale_only_price_is_uncertain(self):
        f = field("toy_store_kite_uncertain", "price")
        self.assertEqual(f.status.value, "uncertain")
        self.assertIsNone(f.value)

    def test_per_unit_price_carries_its_condition(self):
        f = field("bookstore_boxset_ambiguous", "price")
        self.assertEqual(f.status.value, "confirmed")
        self.assertEqual(f.value, 12.0)
        self.assertEqual(f.condition, "per book")


class TestAvailabilityResolution(unittest.TestCase):
    def test_other_products_sold_out_is_not_a_conflict(self):
        f = field("grocery_milk_confusion", "availability")
        self.assertEqual(f.status.value, "confirmed")
        self.assertEqual(f.value, "in_stock")

    def test_same_product_contradiction_is_flagged(self):
        f = field("furniture_chair_contradiction", "availability")
        self.assertEqual(f.status.value, "conflicting")
        self.assertIsNone(f.value)


if __name__ == "__main__":
    unittest.main()
