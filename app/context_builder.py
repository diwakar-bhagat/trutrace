"""Context assembly: what the pipeline knows before it reads the call.

Context engineering, in miniature: the extractor and the verification
engine do not get a bare transcript. They get the business, the product
the buyer asked about, the requested fields, and the product's token set,
so that "the price of the other product" and "the fee, not the price"
are recognisable as what they are.
"""

import re
from dataclasses import dataclass, field

from .schemas import TranscriptDoc
from .textutil import stem


@dataclass
class ExtractionContext:
    business_name: str
    business_type: str
    product: str
    question: str
    requested_fields: list[str]
    # whitespace tokens of the product name, hyphens kept ("all-season")
    product_tokens: set[str] = field(default_factory=set)
    # stemmed product tokens, for singular/plural tolerant matching
    product_stems: set[str] = field(default_factory=set)
    # stemmed head noun of the product name ("milk" in "almond milk")
    head_stem: str = ""
    # tokens of the buyer's question, for condition matching
    question_tokens: set[str] = field(default_factory=set)


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9][a-z0-9\-']*", text.lower())


def build_context(doc: TranscriptDoc) -> ExtractionContext:
    product_tokens = set(_tokens(doc.product))
    question_tokens = set(_tokens(doc.question))
    raw_tokens = _tokens(doc.product)
    head = stem(raw_tokens[-1]) if raw_tokens else ""
    return ExtractionContext(
        business_name=doc.business_name,
        business_type=doc.business_type,
        product=doc.product,
        question=doc.question,
        requested_fields=list(doc.requested_fields),
        product_tokens=product_tokens,
        product_stems={stem(t) for t in product_tokens},
        head_stem=head,
        question_tokens=question_tokens,
    )
