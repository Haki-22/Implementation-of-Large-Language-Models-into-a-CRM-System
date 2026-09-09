"""The ladder (levels.py) and the prompt catalog (prompts.py), without a database or a model."""

from __future__ import annotations

import pytest

from ucs.uc01_personalization import levels, prompts
from ucs.uc01_personalization.data import Brief, ContactRecord, Enrichment


def _contact(**over) -> ContactRecord:
    base = dict(
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
        frequent_words=["kabel", "zvuk"],
        style_excerpt="Tento kabel je výborný a zvuk je čistý.",
        prior_interactions="[hodnocení 5.0] Skvělý kabel",
        ocean={"O": 4.0, "C": 3.5, "E": 3.0, "A": 4.0, "N": 2.5},
        ocean_source="synthetic",
        reviewer_gender="f",
        gender_paired=True,
        amazon_group="A",
    )
    base.update(over)
    return ContactRecord(**base)


BRIEF = Brief(
    1,
    "seasonal_sale_launch",
    "invitation",
    "🔥 Výprodej startuje! Tohle je vaše šance, co jste odkládali. Přihlaste se.",
)

FULL = Enrichment(
    frequent_words=["kabel", "zvuk"],
    style_excerpt="Tento kabel je výborný.",
    purchases=[{"order_date": "2014-07-19", "name": "Kabel HDMI", "category": "Accessories"}],
    reviews="[hodnocení 5.0] Skvělý kabel",
    role="skladnice, Acme s.r.o.",
    aspects=[],
    ocean={"O": 4.0, "C": 3.5, "E": 3.0, "A": 4.0, "N": 2.5},
    recommendations=[{"name": "Reproduktor", "reason_cs": "Hodí se k tvému kabelu."}],
    topics=[{"label": "kabely / hdmi", "weight": 0.3}],
    lifecycle="aktivní zákazník",
    pricing={
        "full_price": {"name": "Reproduktor", "rank": 1, "price_czk": 2490},
        "discounted": {
            "name": "Stojan na reproduktor",
            "rank": 4,
            "list_price_czk": 590,
            "discount_percent": 15,
            "price_czk": 502,
        },
        "disclosure_cs": "Uvedená cena byla stanovena na míru na základě automatizovaného rozhodování.",
        "rule": "test",
    },
)


def test_ladder_order_and_model_flags():
    assert list(levels.LEVELS) == [
        "0",
        "1",
        "2",
        "3a",
        "3b",
        "3c",
        "3d",
        "3",
        "4",
        "5",
        "6a",
        "6b",
        "6c",
        "6d",
        "6",
    ]
    assert not levels.LEVELS["0"].uses_model and not levels.LEVELS["1"].uses_model
    assert all(levels.LEVELS[k].uses_model for k in levels.LADDER if k not in ("0", "1"))


def test_parse_levels_accepts_ids_with_or_without_prefix_and_all():
    assert [lvl.id for lvl in levels.parse_levels("L3a,2,l6")] == ["2", "3a", "6"]
    assert [lvl.id for lvl in levels.parse_levels("all")] == list(levels.LADDER)
    with pytest.raises(ValueError):
        levels.parse_levels("7")


def test_merge_inserts_the_greeting_and_swaps_the_register_but_not_free_text():
    """L1 is a mail merge: greeting + a fixed swap table; 'odkládali' stays plural (that is L2's job)."""
    informal_woman = _contact(formal=False, name_vocative="Ahoj Jano")
    text = levels.merge(BRIEF, informal_woman)
    assert text.startswith("Ahoj Jano, výprodej startuje!")
    assert "tvoje šance" in text and "co jsi odkládali" in text and "Přihlas se" in text
    formal = levels.merge(BRIEF, _contact())
    assert formal.startswith("Vážená paní Nováková, ") and "vaše šance" in formal


def test_generic_is_the_brief_untouched():
    assert levels.generic(BRIEF) == BRIEF.default_template


def test_each_level_carries_exactly_its_slots_in_the_prompt():
    c = _contact()
    system, user = levels.build_prompt(levels.LEVELS["2"], c, BRIEF, FULL)
    assert "<obohacení>" not in user and "Navíc" not in system
    for level_id, present, absent in (
        ("3a", ("Častá slova", "Ukázka stylu psaní"), ("Poslední nákupy", "OCEAN", "Doporučené")),
        ("3b", ("Poslední nákupy",), ("Častá slova", "OCEAN")),
        ("3c", ("Co o produktech",), ("Poslední nákupy",)),
        ("3d", ("Pracovní role",), ("Poslední nákupy",)),
        (
            "3",
            ("Častá slova", "Poslední nákupy", "Co o produktech", "Pracovní role"),
            ("OCEAN", "Doporučené"),
        ),
        ("5", ("OCEAN", "Častá slova"), ("Doporučené", "Témata zájmu", "Fáze vztahu")),
        ("6a", ("Doporučené produkty",), ("Témata zájmu", "Fáze vztahu")),
        ("6b", ("Témata zájmu",), ("Doporučené", "Fáze vztahu")),
        ("6c", ("Fáze vztahu",), ("Doporučené", "Témata zájmu")),
        (
            "6d",
            ("Doporučené produkty", "Cenová nabídka: Reproduktor za 2 490 Kč"),
            ("Témata zájmu", "Fáze vztahu"),
        ),
        ("6", ("Doporučené produkty", "Témata zájmu", "Fáze vztahu", "OCEAN"), ("Cenová nabídka",)),
    ):
        system, user = levels.build_prompt(levels.LEVELS[level_id], c, BRIEF, FULL)
        for label in present:
            assert label in user, (level_id, label)
        for label in absent:
            assert label not in user, (level_id, label)
        assert "Oslovení: Vážená paní Nováková" in user and BRIEF.default_template in user
        assert prompts.UNTRUSTED_NOTE in system


def test_ocean_slot_is_numbers_only():
    assert prompts.format_slot("ocean", FULL) == "O=4.0, C=3.5, E=3.0, A=4.0, N=2.5"


def test_prompt_text_never_calls_the_recipient_he():
    """2.0.1: a recipient may be a woman, so no rule or label says 'jeho' / 'mu' about them."""
    for text in (*prompts.SLOT_RULES.values(), *prompts.SLOT_LABELS.values()):
        assert " jeho " not in f" {text} " and " mu " not in f" {text} ", text


def test_product_titles_are_cut_at_a_word_boundary():
    long_title = "NOVINKA! Creative Sound Blaster Roar: Přenosný bezdrátový Bluetooth reproduktor s technologií NFC a aptX/AAC. 5 měničů, vestavěný subwoofer"
    short = prompts.short_title(long_title)
    assert short.endswith("…") and len(short) <= prompts.TITLE_CHARS + 1
    assert short[:-1] == long_title[: len(short) - 1] and not long_title[len(short) - 1].isalnum()
    assert prompts.short_title("Kabel HDMI") == "Kabel HDMI"
    purchases = Enrichment(
        purchases=[{"order_date": "2014-07-19", "name": long_title, "category": "Home Audio"}]
    )
    assert prompts.format_slot("purchases", purchases) == f"{short} (Home Audio, 2014-07-19)"


def test_missing_inputs_are_named_and_identity_gaps_never_block():
    lvl = levels.LEVELS["3"]
    assert lvl.missing(_contact(), FULL) == []
    assert lvl.missing(_contact(), Enrichment(frequent_words=["x"])) == [
        "style_excerpt",
        "purchases",
        "reviews",
    ]
    assert levels.LEVELS["6"].missing(
        _contact(), Enrichment(**{**FULL.__dict__, "recommendations": []})
    ) == ["recommendations"]
    defective = _contact(name_vocative=None, gender=None, formal=None)
    assert levels.LEVELS["2"].missing(defective, FULL) == []
    assert levels.LEVELS["0"].missing(defective, Enrichment()) == []
    system, user = prompts.build(defective, BRIEF, FULL, ())
    assert "Jméno: Jana Nováková" in user and "Oslovení: není uloženo" in user
    assert "Pohlaví: neuvedeno" in user and "Formálnost: neuvedeno" in user
    assert "Chybějící údaj" in system


def test_merge_gives_a_half_known_contact_what_a_mail_merge_would():
    """No greeting, unknown gender and formality: 'Dobrý den' and the template's vykání kept."""
    text = levels.merge(BRIEF, _contact(name_vocative=None, gender=None, formal=None))
    assert text.startswith("Dobrý den, výprodej startuje!")
    assert "vaše šance" in text and "Přihlaste se" in text
    # tykání without a stored greeting: the first name in the nominative, as a mail merge does
    assert levels.merge(BRIEF, _contact(name_vocative=None, formal=False)).startswith("Ahoj Jana, ")
