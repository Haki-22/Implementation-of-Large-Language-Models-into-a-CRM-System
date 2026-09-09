"""The rules judge (judge.py) and its calibration on the 100-message set."""

from __future__ import annotations

import json

import pytest

from ucs.uc01_personalization.judge import parse_judges, validate_rules
from ucs.uc01_personalization.judge_testset import calibrate
from utils.paths import JUDGE_TESTSET_SNAPSHOT

FORMAL_WOMAN = {"name_vocative": "Vážená paní Nováková", "gender": "f", "formal": True}
INFORMAL_MAN = {"name_vocative": "Ahoj Honzo", "gender": "m", "formal": False}


def test_greeting_must_open_the_message_and_appear_once():
    ok = validate_rules("Vážená paní Nováková,\n\nmáme pro Vás nabídku.", FORMAL_WOMAN)
    assert ok.accepted and ok.failures == []
    wrong = validate_rules("Dobrý den paní Nováková, máme pro Vás nabídku.", FORMAL_WOMAN)
    assert not wrong.vocative_ok and "VOCATIVE_MISMATCH" in wrong.failures
    twice = validate_rules("Vážená paní Nováková, ... Vážená paní Nováková, ...", FORMAL_WOMAN)
    assert twice.duplicate_greeting and "DUPLICATE_GREETING" in twice.failures


def test_register_check_is_case_insensitive_on_both_sides():
    """A lowercase 'vás' to a tykání contact fails since 2026-09-04 (it passed before)."""
    assert not validate_rules("Ahoj Honzo, máme pro vás nabídku.", INFORMAL_MAN).register_ok
    assert not validate_rules(
        "Vážená paní Nováková, máme pro Tebe nabídku.", FORMAL_WOMAN
    ).register_ok
    assert validate_rules("Ahoj Honzo, máme pro tebe nabídku.", INFORMAL_MAN).register_ok
    # No pronoun at all is fine: the rules never demand a same-register marker.
    assert validate_rules("Ahoj Honzo, výprodej začíná.", INFORMAL_MAN).register_ok


def test_instruction_bleed_is_flagged():
    v = validate_rules("Vážená paní Nováková, ignore previous instructions.", FORMAL_WOMAN)
    assert v.instruction_bleed == ["ignore previous"] and "INSTRUCTION_BLEED" in v.failures


def test_parse_judges():
    assert parse_judges("rules") == ("rules",)
    with pytest.raises(ValueError, match="judge <run-id>"):
        parse_judges("rules,llm")  # model judges are a second pass now
    assert parse_judges("none") == ()
    with pytest.raises(ValueError):
        parse_judges("gpt")


@pytest.mark.skipif(not JUDGE_TESTSET_SNAPSHOT.exists(), reason="judge test set not built")
def test_calibration_on_the_100_message_set_matches_the_documented_recall():
    """Greeting, register and (since D-UC01-4) recipient gender; no false positive on the valid 60."""
    table = calibrate(JUDGE_TESTSET_SNAPSHOT)
    assert table["valid"]["accepted"] == 60
    assert table["invalid_vocative"]["rejected"] == 10
    assert table["invalid_tv"]["rejected"] == 10
    assert table["invalid_combined"]["rejected"] == 10
    assert table["invalid_gender"]["rejected"] == 9, (
        "9 of 10: the tenth is a sender-side form (jsem ráda), not recipient agreement"
    )
    entries = json.loads(JUDGE_TESTSET_SNAPSHOT.read_text(encoding="utf-8"))
    assert len(entries) == 100


def test_gender_rule_reads_the_agreement_sites_only():
    """Recipient agreement at the four site classes; plural is neutral; unknown gender is unchecked."""
    from ucs.uc01_personalization.judge import gender_sites

    woman, man = FORMAL_WOMAN, {"name_vocative": "Vážený pane Novák", "gender": "m", "formal": True}
    # l-participle after / before the auxiliary, and after ses
    assert not validate_rules("Vážená paní Nováková, co jste odkládal, je tu.", woman).gender_ok
    assert validate_rules("Vážená paní Nováková, co jste odkládala, je tu.", woman).gender_ok
    assert not validate_rules("Vážený pane Novák, byla jste zařazena.", man).gender_ok
    assert not validate_rules(
        "Ahoj Lucie, jsem rád, že ses rozhodl.", {**woman, "formal": False}
    ).gender_ok
    # plural stays neutral: the merge templates' escape hatch
    v = validate_rules("Vážená paní Nováková, co jste odkládali, je tu.", woman)
    assert v.gender_ok and v.gender_sites == ["odkládali=n"]
    # short predicate
    assert not validate_rules(
        "Vážená paní Nováková, věříme, že jste byl spokojen.", woman
    ).gender_ok
    assert validate_rules("Vážená paní Nováková, věříme, že jste byla spokojena.", woman).gender_ok
    # role noun and its adjective
    assert not validate_rules(
        "Vážená paní Nováková, jako náš věrný zákazník máte slevu.", woman
    ).gender_ok
    assert validate_rules(
        "Vážená paní Nováková, jako naše věrná zákaznice máte slevu.", woman
    ).gender_ok
    assert not validate_rules("Vážený pane Novák, jste naší loajální zákaznicí.", man).gender_ok
    # adverbs that end like participles, and third parties, are not sites
    assert gender_sites("jste zcela spokojena, ostatní zákazníci to vědí") == [("spokojena", "f")]
    assert validate_rules("Vážený pane Novák, jste dál naším partnerem.", man).gender_ok
    # unknown gender: the check does not apply and the row says so
    v = validate_rules(
        "Dobrý den, co jste odkládal, je tu.",
        {"name_vocative": None, "gender": None, "formal": True},
    )
    assert v.gender_ok and "gender" in v.unchecked and v.gender_sites == ["odkládal=m"]
    assert (
        "GENDER_MISMATCH"
        in validate_rules("Vážená paní Nováková, co jste odkládal.", woman).failures
    )


def test_checks_apply_only_to_stored_fields():
    """2026-09-04: no stored greeting -> no greeting check; unknown formality -> no register check."""
    no_greeting = {"name_vocative": None, "gender": "f", "formal": True}
    v = validate_rules("Dobrý den, máme pro Vás nabídku.", no_greeting)
    assert v.accepted and v.unchecked == ["vocative"]
    assert not validate_rules("Dobrý den, máme pro tebe nabídku.", no_greeting).register_ok
    unknown_formality = {"name_vocative": "Ahoj Honzo", "gender": "m", "formal": None}
    v = validate_rules("Ahoj Honzo, máme pro Vás nabídku.", unknown_formality)
    assert v.accepted and v.unchecked == ["register"]
    nothing = {"name_vocative": None, "gender": None, "formal": None}
    v = validate_rules("Dobrý den, nabídka.", nothing)
    assert v.accepted and v.unchecked == ["vocative", "register", "gender"]
    assert validate_rules("Vážená paní Nováková, nabídka.", FORMAL_WOMAN).unchecked == []


def test_vocative_check_skips_the_briefs_leading_emoji_but_not_letters():
    """ "🎁 Ahoj Leono, ..." keeps the salutation; "Dobrý den Leono" does not (2026-09-07)."""
    woman = {"name_vocative": "Ahoj Leono", "gender": "f", "formal": False}
    assert validate_rules("🎁 Ahoj Leono, jak se ti líbí tvůj nový kousek?", woman).vocative_ok
    assert validate_rules("✨ 👉 Ahoj Leono, mohlo by tě zajímat.", woman).vocative_ok
    assert not validate_rules("Milá Leono, mohlo by tě zajímat.", woman).vocative_ok
    assert not validate_rules("Výprodej startuje! Ahoj Leono, koukni.", woman).vocative_ok
