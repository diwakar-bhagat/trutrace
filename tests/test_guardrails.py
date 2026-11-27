"""Guardrail tests, carried over from the Verified Answers MVP and
adapted to the TruTrace engine: grounding, hedge demotion and
contradiction behaviour on synthetic raw extractions.

The guardrails are the product: providers can be swapped (rules today,
an LLM tomorrow), but the rule that an answer must be grounded,
unhedged and uncontradicted may not regress.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.config import get_config  # noqa: E402
from app.context_builder import ExtractionContext  # noqa: E402
from app.schemas import (  # noqa: E402
    PriceCandidate,
    RawExtraction,
    RawField,
)
from app.verification.engine import verify  # noqa: E402

TRANSCRIPT = (
    "Seller: A dozen red roses is $45.\n"
    "Seller: Yes, we have red roses in stock.\n"
    "Seller: We carry them, though I am not sure how many are on the shelf.\n"
    "Seller: That size runs $120 a tyre. The all-season ones are $135."
)

CONTEXT = ExtractionContext(
    business_name="Test", business_type="Florist", product="red roses",
    question="How much is a dozen red roses?",
    requested_fields=["price"],
    product_tokens={"red", "roses"}, product_stems={"red", "rose"},
    head_stem="rose", question_tokens={"how", "much", "is", "a", "dozen",
                                       "red", "roses"},
)
CONFIG = get_config("trutrace-1.0.0")


def raw_with_price(value, evidence, candidates=None):
    raw = RawExtraction()
    raw.fields["price"] = RawField(value=value, evidence=evidence)
    raw.price_candidates = candidates or [
        PriceCandidate(value=value, evidence=evidence)
    ]
    return raw


class TestGrounding(unittest.TestCase):
    def test_grounded_value_is_confirmed(self):
        raw = raw_with_price(45.0, "A dozen red roses is $45.")
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["price"].status.value, "confirmed")
        self.assertEqual(out.fields["price"].value, 45.0)

    def test_invented_span_is_unconfirmed(self):
        raw = raw_with_price(99.0, "The price is ninety nine dollars.")
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["price"].status.value, "unconfirmed")
        self.assertIsNone(out.fields["price"].value)

    def test_missing_evidence_is_unconfirmed(self):
        raw = raw_with_price(45.0, None)
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["price"].status.value, "unconfirmed")

    def test_missing_value_is_unconfirmed_not_invented(self):
        out = verify(RawExtraction(), CONTEXT, TRANSCRIPT, CONFIG)
        self.assertIsNone(out.fields["price"].value)
        self.assertEqual(out.fields["price"].status.value, "unconfirmed")


class TestHedging(unittest.TestCase):
    def test_hedged_availability_is_demoted(self):
        raw = RawExtraction()
        raw.fields["availability"] = RawField(
            value="in_stock",
            evidence="We carry them, though I am not sure how many are on the shelf.",
        )
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["availability"].status.value, "uncertain")

    def test_clean_availability_is_confirmed(self):
        raw = RawExtraction()
        raw.fields["availability"] = RawField(
            value="in_stock", evidence="Yes, we have red roses in stock."
        )
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["availability"].status.value, "confirmed")


class TestContradiction(unittest.TestCase):
    def test_two_prices_flag_conflict(self):
        raw = raw_with_price(
            120.0,
            "That size runs $120 a tyre.",
            candidates=[
                PriceCandidate(value=120.0,
                               evidence="That size runs $120 a tyre."),
                PriceCandidate(value=135.0,
                               evidence="The all-season ones are $135."),
            ],
        )
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["price"].status.value, "conflicting")
        self.assertIsNone(out.fields["price"].value)
        self.assertEqual(out.fields["price"].candidates, [120.0, 135.0])

    def test_single_price_is_not_a_conflict(self):
        raw = raw_with_price(45.0, "A dozen red roses is $45.")
        out = verify(raw, CONTEXT, TRANSCRIPT, CONFIG)
        self.assertEqual(out.fields["price"].status.value, "confirmed")


if __name__ == "__main__":
    unittest.main()
