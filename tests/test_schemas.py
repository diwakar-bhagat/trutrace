"""Schema tests: the typed contracts the pipeline runs on."""

import glob
import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pydantic import ValidationError  # noqa: E402

from app.schemas import (  # noqa: E402
    FIELDS,
    FieldStatus,
    GoldField,
    RawExtraction,
    TranscriptDoc,
    VerifiedAnswer,
    VerifiedField,
)

DATA = os.path.join(os.path.dirname(__file__), "..", "datasets", "transcripts")


class TestTranscriptDoc(unittest.TestCase):
    def test_every_dataset_file_validates(self):
        paths = sorted(glob.glob(os.path.join(DATA, "*.json")))
        self.assertEqual(len(paths), 32)
        for path in paths:
            with open(path, encoding="utf-8") as fh:
                doc = TranscriptDoc.model_validate(json.load(fh))
            self.assertEqual(set(doc.gold), set(FIELDS), doc.id)
            for name, gold in doc.gold.items():
                if gold.status == FieldStatus.CONFIRMED:
                    self.assertIsNotNone(gold.value, f"{doc.id}:{name}")
                    self.assertIn(gold.evidence, doc.transcript,
                                  f"{doc.id}:{name}")

    def test_bad_status_is_rejected(self):
        with self.assertRaises(ValidationError):
            GoldField(value=1, status="definitely")

    def test_confirmed_gold_requires_an_evidence_span_that_exists(self):
        doc = {
            "id": "x", "business_name": "B", "business_type": "T",
            "product": "p", "question": "q", "taxonomy": "clean",
            "transcript": "Seller: It is $5.",
            "gold": {f: {"value": None, "status": "unconfirmed"}
                     for f in FIELDS},
        }
        parsed = TranscriptDoc.model_validate(doc)
        self.assertEqual(parsed.id, "x")


class TestRawAndVerified(unittest.TestCase):
    def test_raw_extraction_defaults_are_empty(self):
        raw = RawExtraction()
        self.assertEqual(raw.fields, {})
        self.assertEqual(raw.price_candidates, [])

    def test_confirmed_values_only_returns_confirmed(self):
        answer = VerifiedAnswer(fields={
            "price": VerifiedField(value=45.0, status=FieldStatus.CONFIRMED),
            "timing": VerifiedField(value=None, status=FieldStatus.UNCERTAIN),
        })
        self.assertEqual(answer.confirmed_values(), {"price": 45.0})

    def test_verified_field_rejects_unknown_status(self):
        with self.assertRaises(ValidationError):
            VerifiedField(value=1, status="verified-ish")


if __name__ == "__main__":
    unittest.main()
