"""Gold metrics harness: known-answer fixture scoring.

The fixture is small enough to verify by hand. It includes gold
uncertain fields in both flavours (abstained, and asserted anyway)
and proves they are measured in the abstention block only: they enter
neither the recall denominator (gold positives) nor the false
positive rate denominator (gold negatives), while an asserted
uncertain still counts as an unsupported claim against precision,
because the run did assert it.
"""

import json
import os
import tempfile
import unittest

from evals.gold_metrics import (
    GOLD_VERSION_AI_DRAFTED,
    PROTOCOL_TO_ENGINE,
    GoldBook,
    compute_metrics,
    header_lines,
    load_gold,
    rows_from_final_results,
)


def row(gold_status, gold_value, pred_status, pred_value,
        gold_evidence=None, pred_evidence=None, gold_condition=None,
        pred_condition=None):
    return {
        "config": "fixture",
        "case_id": "case",
        "field": "price",
        "gold_status": gold_status,
        "gold_value": gold_value,
        "gold_condition": gold_condition,
        "gold_evidence": gold_evidence,
        "pred_status": pred_status,
        "pred_value": pred_value,
        "pred_condition": pred_condition,
        "pred_evidence": pred_evidence,
    }


FIXTURE = [
    # 1. true positive, evidence span matches
    row("confirmed", 8, "confirmed", 8,
        gold_evidence="A sourdough loaf is $8.",
        pred_evidence="A sourdough loaf is $8."),
    # 2. false negative: gold confirmed, run abstains
    row("confirmed", 60, "unconfirmed", None),
    # 3. false positive on a gold negative: gold unconfirmed, asserted
    row("unconfirmed", None, "confirmed", "dozen"),
    # 4. gold uncertain, run abstains: abstention block only
    row("uncertain", 35, "uncertain", 35),
    # 5. true negative: gold unconfirmed, run leaves it unconfirmed
    row("unconfirmed", None, "unconfirmed", None),
    # 6. true positive, evidence span does not match gold's span
    row("confirmed", 10, "confirmed", 10,
        gold_evidence="It costs $10.",
        pred_evidence="The price is ten dollars."),
    # 7. gold uncertain, run asserts it: abstention failure AND an
    #    unsupported claim against precision, but NOT a gold negative
    row("uncertain", None, "confirmed", "in_stock"),
]


class TestComputeMetrics(unittest.TestCase):
    def setUp(self):
        self.m = compute_metrics(FIXTURE)

    def test_precision_and_recall(self):
        m = self.m
        self.assertEqual(m["true_positives"], 2)          # rows 1, 6
        self.assertEqual(m["false_positives"], 2)         # rows 3, 7
        self.assertEqual(m["precision"], 0.5)              # 2 / (2 + 2)
        self.assertEqual(m["gold_confirmed"], 3)          # rows 1, 2, 6
        self.assertEqual(m["false_negatives"], 1)          # row 2
        self.assertEqual(m["recall"], round(2 / 3, 4))
        self.assertEqual(m["false_negative_rate"], round(1 / 3, 4))

    def test_false_positive_rate_excludes_uncertain(self):
        m = self.m
        # Gold negatives are rows 3 and 5 only. Row 7 (gold uncertain,
        # asserted) must not enter this denominator.
        self.assertEqual(m["gold_negative"], 2)
        self.assertEqual(m["false_positives_on_gold_negative"], 1)
        self.assertEqual(m["false_positive_rate"], 0.5)

    def test_evidence_accuracy(self):
        m = self.m
        self.assertEqual(m["evidence_compared"], 2)        # rows 1, 6
        self.assertEqual(m["evidence_matched"], 1)         # row 1 only
        self.assertEqual(m["evidence_accuracy"], 0.5)

    def test_abstention_measured_separately(self):
        au = self.m["abstention"]["gold_uncertain"]
        self.assertEqual(au["total"], 2)                   # rows 4, 7
        self.assertEqual(au["abstained"], 1)               # row 4
        self.assertEqual(au["asserted"], 1)                # row 7
        self.assertEqual(au["abstention_rate"], 0.5)
        an = self.m["abstention"]["gold_unconfirmed"]
        self.assertEqual(an["total"], 2)                   # rows 3, 5
        self.assertEqual(an["correct"], 1)                 # row 5
        self.assertEqual(an["asserted"], 1)                # row 3


class TestGoldBook(unittest.TestCase):
    def test_default_book_is_the_ai_drafted_version(self):
        book = load_gold()
        self.assertEqual(book.version, GOLD_VERSION_AI_DRAFTED)
        self.assertEqual(book.provenance, "ai-drafted")
        self.assertEqual(book.total_fields, 224 + 70)  # 32 annotated + campaign 10x7
        entry = book.get("bakery_sourdough_clean", "price")
        self.assertEqual(entry["status"], "confirmed")
        self.assertFalse(entry["reviewed"])

    def test_honesty_header_for_ai_drafted_gold(self):
        text = "\n".join(header_lines(load_gold()))
        self.assertIn(GOLD_VERSION_AI_DRAFTED, text)
        self.assertIn("AGREEMENT WITH AI DRAFTED LABELS", text)
        self.assertIn("not validated correctness", text)

    def test_protocol_vocabulary_mapping(self):
        self.assertEqual(PROTOCOL_TO_ENGINE["supported"], "confirmed")
        self.assertEqual(PROTOCOL_TO_ENGINE["unsupported"], "unconfirmed")
        self.assertEqual(PROTOCOL_TO_ENGINE["contradictory"], "conflicting")
        self.assertEqual(PROTOCOL_TO_ENGINE["uncertain"], "uncertain")

    def test_export_overlay_replaces_only_reviewed_fields(self):
        export = {
            "dataset_version": "gold-v2-human-reviewed",
            "reviewer": "Fixture Reviewer",
            "exported_at": "2026-11-27T00:00:00+00:00",
            "cases": {
                "bakery_sourdough_clean": {
                    "split": "dev",
                    "fields": {
                        "price": {
                            "reviewed": True,
                            "human_status": "contradictory",
                            "evidence": {"text": "A sourdough loaf is $8.",
                                         "start": 0, "end": 24},
                        },
                        "timing": {"reviewed": False, "human_status": None},
                    },
                }
            },
        }
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "gold_labels_v2.json")
            with open(path, "w") as fh:
                json.dump(export, fh)
            book = load_gold(path)
        self.assertEqual(book.version, "gold-v2-human-reviewed")
        self.assertEqual(book.provenance, "human-reviewed")
        self.assertEqual(book.reviewed_fields, 1)
        price = book.get("bakery_sourdough_clean", "price")
        self.assertEqual(price["status"], "conflicting")  # contradictory mapped
        self.assertTrue(price["reviewed"])
        timing = book.get("bakery_sourdough_clean", "timing")
        self.assertEqual(timing["status"], "unconfirmed")  # AI draft kept
        self.assertFalse(timing["reviewed"])
        header = "\n".join(header_lines(book))
        self.assertIn("gold-v2-human-reviewed", header)
        self.assertIn("Fixture Reviewer", header)


class TestRecordedRunScoring(unittest.TestCase):
    def test_final_results_file_scores_without_model_calls(self):
        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        path = os.path.join(
            root, "evals", "results", "final_campaign_offline_baseline_run1.json"
        )
        rows = rows_from_final_results(path, load_gold())
        self.assertEqual(len(rows), 70)  # campaign 10 cases x 7 fields
        m = compute_metrics(rows)
        self.assertEqual(m["fields"], 70)
        # The recorded baseline run asserted hedges as confirmed, so
        # precision must be well below the verified configuration's.
        self.assertLess(m["precision"], 0.8)
        # This format records no evidence spans: accuracy is honestly
        # not measurable rather than silently zero.
        self.assertEqual(m["evidence_compared"], 0)
        self.assertIsNone(m["evidence_accuracy"])


if __name__ == "__main__":
    unittest.main()
