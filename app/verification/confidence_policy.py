"""The confidence policy: what may be asserted, and what must be demoted.

The policy is deliberately asymmetric. Asserting a field the call did not
establish is the critical failure (it becomes a wrong price on a product
page); withholding a field is a small, visible cost. So every demotion
rule errs toward uncertain:

- hedged evidence            -> uncertain (a suggestion, not a fact)
- approximate price          -> uncertain ("about $85" is not $85)
- starting price             -> uncertain, condition "starting price"
- price for another product  -> unconfirmed for this product
- stale price only           -> uncertain (it was true once; say so)
- fee / threshold amounts    -> never the product's price
"""

from .candidates import EnrichedCandidate

DEMOTE_HEDGE = "hedged in the call ('{marker}'); not a confirmed fact"
DEMOTE_APPROX = "quoted as an approximate price; not an exact figure"
DEMOTE_STARTING = "quoted as a starting price; the actual price was not stated"
DEMOTE_MISMATCH = (
    "the only price quoted is for a different item or condition; "
    "no price for the requested product was confirmed"
)
DEMOTE_STALE = "only a stale price was quoted; the current price was not confirmed"
DROP_FEE = "amount quoted is a fee or a threshold, not the product price"


def price_mismatch_demotion(
    working: list[EnrichedCandidate], context
) -> bool:
    """True when the working candidates never name the requested product,
    carry a condition the buyer did not ask about, and the buyer asked
    about no matching condition: the quoted price belongs to something
    else (a standard colour quoted to a balayage buyer)."""
    if not working:
        return False
    names_product = any(
        c.content_stems & context.product_stems for c in working
    )
    if names_product:
        return False
    asked = context.question_tokens | context.product_tokens
    has_qualifier = any(c.qualifiers for c in working)
    qualifier_asked = any(c.qualifiers & asked for c in working)
    return has_qualifier and not qualifier_asked
