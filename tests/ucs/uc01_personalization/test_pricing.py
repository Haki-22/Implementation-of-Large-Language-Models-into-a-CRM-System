"""The price line of level 6d: the rule, the slot in the prompt, the rules judge's check."""

from __future__ import annotations

from ucs.uc01_personalization import levels, pricing, prompts
from ucs.uc01_personalization.data import Brief, ContactRecord, Enrichment
from ucs.uc01_personalization.judge import pricing_check, validate_rules

RECS = [
    {"rank": 1, "name": "Sluchátka Sony WH-1000XM5", "price": 7990.0, "reason_cs": "x"},
    {"rank": 2, "name": "Pouzdro na sluchátka", "price": None, "reason_cs": "x"},
    {"rank": 3, "name": "Kabel USB-C 2 m", "price": 249.0, "reason_cs": "x"},
    {"rank": 4, "name": "Powerbanka 20 000 mAh", "price": 899.0, "reason_cs": "x"},
    {"rank": 5, "name": "Bez ceny", "price": None, "reason_cs": "x"},
]

FORMAL_WOMAN = {"name_vocative": "Vážená paní Nováková", "gender": "f", "formal": True}


def test_offer_takes_rank_one_at_list_price_and_the_lowest_priced_rank_with_the_discount():
    o = pricing.offer(RECS)
    assert o["full_price"] == {"name": "Sluchátka Sony WH-1000XM5", "rank": 1, "price_czk": 7990}
    assert o["discounted"]["name"] == "Powerbanka 20 000 mAh" and o["discounted"]["rank"] == 4
    assert o["discounted"]["list_price_czk"] == 899
    assert o["discounted"]["discount_percent"] == pricing.DISCOUNT_PERCENT
    assert o["discounted"]["price_czk"] == 764  # 899 * 0.85 = 764.15
    assert o["disclosure_cs"] == pricing.DISCLOSURE_CS and o["rule"] == pricing.RULE


def test_offer_is_none_without_a_priced_rank_one_or_a_priced_lower_rank():
    assert pricing.offer([]) is None
    assert pricing.offer([{**RECS[0], "price": None}] + RECS[1:]) is None
    assert pricing.offer(RECS[:2]) is None


def test_format_czk_uses_a_space_as_the_thousands_separator():
    assert pricing.format_czk(7990) == "7 990 Kč" and pricing.format_czk(249) == "249 Kč"


def _contact() -> ContactRecord:
    return ContactRecord(
        id=1,
        first_name="Jana",
        last_name="Nováková",
        gender="f",
        formal=True,
        name_vocative="Vážená paní Nováková",
        is_clean=True,
        title=None,
        employer=None,
        lifecycle_stage="active",
        lifecycle_label="aktivní zákazník",
        frequent_words=["baterie"],
        style_excerpt="Píšu stručně.",
        prior_interactions="Skvělé.",
        ocean={"O": 4.0, "C": 4.0, "E": 3.0, "A": 4.0, "N": 2.0},
        ocean_source="inferred",
        reviewer_gender="f",
        gender_paired=True,
        amazon_group="A",
    )


def _enrichment() -> Enrichment:
    return Enrichment(
        frequent_words=["baterie"],
        style_excerpt="Píšu stručně.",
        purchases=[{"name": "Kabel", "category": "Elektronika", "order_date": "2014-07-01"}],
        reviews="Skvělé.",
        ocean={"O": 4.0, "C": 4.0, "E": 3.0, "A": 4.0, "N": 2.0},
        recommendations=RECS,
        pricing=pricing.offer(RECS),
    )


def test_level_6d_carries_the_price_line_and_the_rule_in_its_prompt():
    brief = Brief(
        id=26,
        title="personal_recommendation",
        category="upsell",
        default_template="Mohlo by vás také zajímat.",
    )
    lvl = levels.LEVELS["6d"]
    assert lvl.missing(_contact(), _enrichment()) == []
    without = Enrichment(**{**_enrichment().__dict__, "pricing": None})
    assert lvl.missing(_contact(), without) == ["pricing"]
    system, user = levels.build_prompt(lvl, _contact(), brief, _enrichment())
    assert "Cenová nabídka: Sluchátka Sony WH-1000XM5 za 7 990 Kč (plná cena, bez slevy); " in user
    assert "Powerbanka 20 000 mAh se slevou 15 % za 764 Kč (místo 899 Kč)" in user
    assert pricing.DISCLOSURE_CS in system and "Doporučené produkty" in user
    assert prompts.PROMPT_VERSION == "2.4.1"


def test_pricing_check_ignores_whitespace_and_case_and_names_what_is_missing():
    offer = pricing.offer(RECS)
    good = (
        "Vážená paní Nováková, mohlo by Vás zajímat: Sluchátka Sony za 7990 Kč a Powerbanka "
        "se slevou 15% za 764 Kč. Uvedená cena byla stanovena\nna míru na základě "
        "automatizovaného rozhodování."
    )
    ok, sites = pricing_check(good, offer)
    assert ok and sites == [
        "full_price=ok",
        "discounted_price=ok",
        "discount_percent=ok",
        "disclosure=ok",
    ]
    bad = "Vážená paní Nováková, Sluchátka Sony za 7 990 Kč a Powerbanka za 764 Kč."
    ok, sites = pricing_check(bad, offer)
    assert not ok and "discount_percent=missing" in sites and "disclosure=missing" in sites
    verdict = validate_rules(bad, FORMAL_WOMAN, pricing=offer)
    assert not verdict.accepted and verdict.failures == ["PRICING_MISMATCH"]
    assert verdict.to_dict()["pricing_sites"] == sites
    plain = validate_rules(bad, FORMAL_WOMAN)
    assert plain.accepted and plain.pricing_ok and plain.pricing_sites == []
