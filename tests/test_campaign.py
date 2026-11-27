"""Campaign subset tests: the florist slice and its proof fields.

The showcase case is pinned here: on campaign_01, the baseline asserts
the hedged price and the hedged stock as confirmed facts, and the
current configuration demotes both. If that contrast ever disappears,
the demo's centrepiece is lying and this suite says so.
"""

import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.pipeline import run_pipeline  # noqa: E402
from app.schemas import TranscriptDoc  # noqa: E402

DATA = os.path.join(os.path.dirname(__file__), "..", "datasets", "campaign")
QUERY = "Red roses, a dozen, delivery today"


def load(case_id):
    with open(os.path.join(DATA, case_id + ".json"), encoding="utf-8") as fh:
        return TranscriptDoc.model_validate(json.load(fh))


class TestCampaignShape(unittest.TestCase):
    def test_ten_cases_one_query(self):
        paths = sorted(glob.glob(os.path.join(DATA, "*.json")))
        self.assertEqual(len(paths), 10)
        for path in paths:
            doc = TranscriptDoc.model_validate(json.load(open(path)))
            self.assertEqual(doc.question, QUERY, doc.id)
            self.assertEqual(doc.business_type, "Florist", doc.id)

    def test_gold_proof_is_complete(self):
        for path in sorted(glob.glob(os.path.join(DATA, "*.json"))):
            doc = TranscriptDoc.model_validate(json.load(open(path)))
            for name, g in doc.gold.items():
                if g.evidence:
                    self.assertIn(g.evidence, doc.transcript, f"{doc.id}:{name}")
                    self.assertEqual(g.speaker, "Seller", f"{doc.id}:{name}")
                    self.assertTrue(g.timestamp, f"{doc.id}:{name}")
                    self.assertTrue(
                        g.evidence.startswith(f"[{g.timestamp}]"),
                        f"{doc.id}:{name}",
                    )


class TestShowcaseContrast(unittest.TestCase):
    def test_baseline_asserts_the_hedge_current_demotes_it(self):
        doc = load("campaign_01_showcase_hedged")
        base = run_pipeline(doc, provider_name="offline",
                            prompt_version="baseline-naive").answer
        now = run_pipeline(doc, provider_name="offline",
                           prompt_version="trutrace-1.0.0").answer
        # The failing behaviour, on the record:
        self.assertEqual(base.fields["price"].status.value, "confirmed")
        self.assertEqual(base.fields["price"].value, 35.0)
        self.assertEqual(base.fields["availability"].status.value, "confirmed")
        # The fixed behaviour, same transcript:
        self.assertEqual(now.fields["price"].status.value, "uncertain")
        self.assertEqual(now.fields["availability"].status.value, "uncertain")
        self.assertEqual(now.fields["timing"].status.value, "uncertain")

    def test_proof_fields_are_derived_from_the_span(self):
        doc = load("campaign_02_clean_confirm")
        answer = run_pipeline(doc, provider_name="offline",
                              prompt_version="trutrace-1.0.0").answer
        price = answer.fields["price"]
        self.assertEqual(price.status.value, "confirmed")
        self.assertEqual(price.speaker, "Seller")
        self.assertEqual(price.timestamp, "00:05")


if __name__ == "__main__":
    unittest.main()
