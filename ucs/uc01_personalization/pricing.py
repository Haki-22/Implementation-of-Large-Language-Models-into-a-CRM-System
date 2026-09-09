"""The price line of level 6d: the product the customer wants at list price, one they would pass over with a discount.

The idea (user 2026-09-07): a personalised offer need not discount what the
customer would buy anyway. UC-04's recommendations arrive ranked; the best one
is offered at its list price, and the lowest-ranked priced one, the product the
customer would pass over, carries the discount that is meant to move it. The
rule is deterministic and lives here, never in the model: the model only writes
the sentence, and the rules judge checks that the numbers in the message are the
numbers of the rule (``judge.validate_rules``, check ``pricing``).

Framing for the thesis: a price adapted to a person on the basis of automated
decision-making has to be disclosed to the consumer (Directive (EU) 2019/2161
added Article 6(1)(ea) to the Consumer Rights Directive 2011/83/EU; in Czech law
through Act No. 374/2022 Coll.), so the offer carries the disclosure sentence
and the judge requires it verbatim. The exact legal wording for the chapter is
the text track's to verify against the source. The same message is the thesis'
leitmotiv in one line: useful for the margin, borderline for the customer.

The offer is None when the recommendations have no price at rank 1 or none at
the discount ranks (the substrate has 1 075 products without a price); level 6d
is then skipped for the contact with ``pricing`` named as the missing input.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# The rule
# ---------------------------------------------------------------------------

# Rank 1 of UC-04's list is the product the customer is most likely to want:
# offered at its list price. The discount goes to the lowest-ranked priced
# recommendation at rank DISCOUNT_RANK_FROM or below.
LIST_PRICE_RANK = 1
DISCOUNT_RANK_FROM = 3
DISCOUNT_PERCENT = 15

# The sentence the message must carry verbatim (the judge flattens whitespace
# and case before comparing). No pronoun, so it reads the same under Ty and Vy.
DISCLOSURE_CS = "Uvedená cena byla stanovena na míru na základě automatizovaného rozhodování."

RULE = (
    f"rank {LIST_PRICE_RANK} of UC-04's recommendations at its list price, no discount; the "
    f"lowest-ranked priced recommendation at rank {DISCOUNT_RANK_FROM} or below with "
    f"{DISCOUNT_PERCENT} % off; both prices in CZK as the substrate stores them; the disclosure "
    "sentence verbatim"
)


# ---------------------------------------------------------------------------
# The offer for one contact
# ---------------------------------------------------------------------------


def format_czk(amount: int) -> str:
    """``1234`` -> ``1 234 Kč`` (a space as the thousands separator, as Czech text writes it)."""
    return f"{int(amount):,}".replace(",", " ") + " Kč"


def offer(recommendations: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The price line for a contact from UC-04's ranked recommendations, or None when the rule cannot apply.

    ``recommendations`` are the rows of ``data.recommendations`` (rank, name, price, ...),
    best first. The result names both products, the prices the message must carry, the
    discount and the disclosure sentence; ``rule`` says how it was made.
    """
    priced = [r for r in recommendations if r.get("price") not in (None, "", 0)]
    top = next((r for r in priced if int(r["rank"]) == LIST_PRICE_RANK), None)
    lower = [r for r in priced if int(r["rank"]) >= DISCOUNT_RANK_FROM]
    if top is None or not lower:
        return None
    cheap = max(lower, key=lambda r: int(r["rank"]))
    list_price = int(round(float(cheap["price"])))
    after = int(round(list_price * (100 - DISCOUNT_PERCENT) / 100))
    return {
        "full_price": {
            "name": top["name"],
            "rank": int(top["rank"]),
            "price_czk": int(round(float(top["price"]))),
        },
        "discounted": {
            "name": cheap["name"],
            "rank": int(cheap["rank"]),
            "list_price_czk": list_price,
            "discount_percent": DISCOUNT_PERCENT,
            "price_czk": after,
        },
        "disclosure_cs": DISCLOSURE_CS,
        "rule": RULE,
    }


# ---------------------------------------------------------------------------
# What the rules judge looks for
# ---------------------------------------------------------------------------


def expected_in_message(pricing: dict[str, Any]) -> dict[str, str]:
    """What the rules judge looks for in a 6d message: the two prices, the discount, the sentence.

    Values are compared with whitespace removed and case folded, so ``1 234 Kč``,
    ``1234 Kč`` and ``1 234 Kč`` all count; a price is its digit string.
    """
    return {
        "full_price": str(pricing["full_price"]["price_czk"]),
        "discounted_price": str(pricing["discounted"]["price_czk"]),
        "discount_percent": f"{pricing['discounted']['discount_percent']}%",
        "disclosure": pricing["disclosure_cs"],
    }
