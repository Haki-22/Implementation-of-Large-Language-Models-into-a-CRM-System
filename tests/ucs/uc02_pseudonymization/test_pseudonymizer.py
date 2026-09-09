"""Tests for the UC-02 reversible pseudonymization workflow."""

from __future__ import annotations

from ucs.uc02_pseudonymization.code.pseudonymizer import (
    detect_rule_based,
    depseudonymize,
    pseudonymize,
    pseudonymize_text,
    restore_text,
)


def test_rule_detector_finds_format_pii():
    text = "Pište na jan.novak@email.cz nebo volejte +420 601 000 000. IČO 13692666."

    spans = detect_rule_based(text)

    assert {span["pii_type"] for span in spans} == {"EMAIL", "PHONE", "ICO"}


def test_pseudonymize_restore_roundtrip():
    text = "Kontakt: jan.novak@email.cz."
    spans = detect_rule_based(text)

    pseudonymized, mapping = pseudonymize_text(text, spans)
    restored = restore_text(pseudonymized, mapping)

    assert "<EMAIL_1>" in pseudonymized
    assert restored == text


def test_public_pseudonymize_uses_mocked_ner(monkeypatch):
    """Fast mock test for rule+NER fusion without loading HF models."""
    import ucs.uc02_pseudonymization.code.ner as ner_module

    text = "Jan Novák pište na jan.novak@email.cz."

    def fake_detect_ner(_text, **kwargs):
        return [
            {
                "span_start": text.index("Jan Novák"),
                "span_end": text.index("Jan Novák") + len("Jan Novák"),
                "pii_type": "PERSON",
                "surface_form": "Jan Novák",
                "ner_confidence": 0.99,
            }
        ]

    monkeypatch.setattr(ner_module, "detect_ner", fake_detect_ner)

    masked, mapping = pseudonymize(text, use_ner=True)

    assert "<PERSON_1>" in masked
    assert "<EMAIL_1>" in masked
    assert depseudonymize(masked, mapping) == text


def test_rule_span_wins_over_mocked_overlapping_ner(monkeypatch):
    """Rule-based EMAIL span must win over a bad overlapping NER span."""
    import ucs.uc02_pseudonymization.code.ner as ner_module

    text = "Pište na jan.novak@email.cz."
    email_start = text.index("jan.novak@email.cz")

    def fake_detect_ner(_text, **kwargs):
        return [
            {
                "span_start": email_start,
                "span_end": email_start + len("jan.novak"),
                "pii_type": "PERSON",
                "surface_form": "jan.novak",
                "ner_confidence": 0.99,
            }
        ]

    monkeypatch.setattr(ner_module, "detect_ner", fake_detect_ner)

    masked, mapping = pseudonymize(text, use_ner=True)

    assert "<EMAIL_1>" in masked
    assert {item["pii_type"] for item in mapping} == {"EMAIL"}


# ---------------------------------------------------------------------------
# Labels, merge rules and scoring (D-UC02-2)
# ---------------------------------------------------------------------------


def _ner(text: str, surface: str, pii_type: str, confidence: float = 0.9) -> dict:
    start = text.index(surface)
    return {
        "span_start": start,
        "span_end": start + len(surface),
        "pii_type": pii_type,
        "surface_form": surface,
        "ner_confidence": confidence,
        "source": "ner:test",
    }


def test_rule_labels_match_the_gold_taxonomy():
    text = "IBAN CZ65 0800 0000 1920 0014 5399, účet 19-2000145399/0800, PSČ 120 00."
    types = [s["pii_type"] for s in detect_rule_based(text)]
    assert "IBAN_CZ" in types
    assert "BBAN" in types
    assert "PSC" in types
    assert all(s["source"] == "rule" for s in detect_rule_based(text))


def test_postal_code_yields_to_containing_address():
    from ucs.uc02_pseudonymization.code.pseudonymizer import merge_spans

    text = "Doručovací adresa je Adélčina 72, 459 77 Poběžovice."
    address = "Adélčina 72, 459 77 Poběžovice"
    merged = merge_spans(detect_rule_based(text), [_ner(text, address, "ADDRESS")], text)
    assert [(s["pii_type"], s["surface_form"]) for s in merged] == [("ADDRESS", address)]


def test_postal_code_alone_is_still_masked():
    from ucs.uc02_pseudonymization.code.pseudonymizer import merge_spans

    text = "Zásilka do 459 77 odchází zítra."
    merged = merge_spans(detect_rule_based(text), [], text)
    assert [(s["pii_type"], s["surface_form"]) for s in merged] == [("PSC", "459 77")]


def test_checksummed_rule_beats_overlapping_ner():
    from ucs.uc02_pseudonymization.code.pseudonymizer import merge_spans

    text = "Pište na jan.novak@email.cz prosím."
    merged = merge_spans(detect_rule_based(text), [_ner(text, "jan.novak", "PERSON", 0.99)], text)
    assert [s["pii_type"] for s in merged] == ["EMAIL"]


def test_adjacent_fragments_are_joined():
    from ucs.uc02_pseudonymization.code.pseudonymizer import join_adjacent_fragments

    text = "Doručovací adresa je Na Letné 156, 518 94 Habry."
    fragments = [
        _ner(text, "Na", "ADDRESS", 0.66),
        _ner(text, "Letné", "ADDRESS", 0.78),
        _ner(text, "156", "ADDRESS", 0.55),
        _ner(text, "518 94 Habry", "ADDRESS", 0.99),
    ]
    joined = join_adjacent_fragments(fragments, text)
    assert [s["surface_form"] for s in joined] == ["Na Letné 156, 518 94 Habry"]
    assert joined[0]["ner_confidence"] == 0.55


def test_fragments_of_different_types_stay_apart():
    from ucs.uc02_pseudonymization.code.pseudonymizer import join_adjacent_fragments

    text = "Jan Novák, Brno"
    spans = [_ner(text, "Jan Novák", "PERSON"), _ner(text, "Brno", "ADDRESS")]
    assert len(join_adjacent_fragments(spans, text)) == 2


def test_score_detection_reports_strict_and_partial():
    from ucs.uc02_pseudonymization.code.pseudonymizer import score_detection

    text = "Adresa: Adélčina 72, 459 77 Poběžovice."
    gold = {"m1": [_ner(text, "Adélčina 72, 459 77 Poběžovice", "ADDRESS")]}
    pred = {
        "m1": [_ner(text, "Adélčina 72", "ADDRESS"), _ner(text, "459 77 Poběžovice", "ADDRESS")]
    }
    summary = score_detection(gold, pred)
    assert summary["overall"]["tp"] == 0
    assert summary["overall"]["fp"] == 2
    assert summary["overall"]["fn"] == 1
    assert summary["partial"]["overall"]["tp"] == 1
    assert summary["partial"]["overall"]["fp"] == 1
    assert summary["partial"]["overall"]["fn"] == 0
    assert summary["partial"]["by_type"]["ADDRESS"]["recall"] == 1.0


def test_mapping_records_the_source_of_each_span():
    text = "Volejte +420 601 000 000."
    _masked, mapping = pseudonymize(text, use_ner=False)
    assert mapping[0]["source"] == "rule"


def test_postal_code_inside_gold_address_is_a_partial_hit():
    from ucs.uc02_pseudonymization.code.pseudonymizer import score_detection

    text = "Adresa: Adélčina 72, 459 77 Poběžovice."
    gold = {"m1": [_ner(text, "Adélčina 72, 459 77 Poběžovice", "ADDRESS")]}
    pred = {"m1": detect_rule_based(text)}
    summary = score_detection(gold, pred)
    assert summary["overall"]["tp"] == 0 and summary["overall"]["fp"] == 1
    assert summary["partial"]["overall"]["tp"] == 1 and summary["partial"]["overall"]["fp"] == 0


# ---------------------------------------------------------------------------
# Unification and numbering policies (D-UC02-4)
# ---------------------------------------------------------------------------


def _spans(text: str, *items: tuple[str, str]) -> list[dict]:
    out = []
    cursor = 0
    for surface, pii_type in items:
        start = text.index(surface, cursor)
        out.append(
            {
                "span_start": start,
                "span_end": start + len(surface),
                "pii_type": pii_type,
                "surface_form": surface,
                "source": "rule",
            }
        )
        cursor = start + len(surface)
    return out


def test_unify_none_gives_every_occurrence_its_own_token():
    text = "Volal Jan Novák. Jan Novák chce fakturu."
    spans = _spans(text, ("Jan Novák", "PERSON"), ("Jan Novák", "PERSON"))
    masked, mapping = pseudonymize_text(text, spans, unify="none")
    assert masked == "Volal <PERSON_1>. <PERSON_2> chce fakturu."
    assert restore_text(masked, mapping) == text


def test_unify_exact_shares_a_token_for_the_same_surface_form():
    text = "Volal Jan Novák. Jan Novák chce fakturu."
    spans = _spans(text, ("Jan Novák", "PERSON"), ("Jan Novák", "PERSON"))
    masked, mapping = pseudonymize_text(text, spans, unify="exact")
    assert masked == "Volal <PERSON_1>. <PERSON_1> chce fakturu."
    assert restore_text(masked, mapping) == text
    from ucs.uc02_pseudonymization.code.pseudonymizer import unification_summary

    assert unification_summary(mapping) == {"spans": 2, "tokens": 1, "entities": 1}


def test_unify_entity_shares_the_number_and_marks_the_form():
    text = "Volal Jan Novák. Řekl jsem Novákovi, že paní Nováková zavolá."
    spans = _spans(text, ("Jan Novák", "PERSON"), ("Novákovi", "PERSON"), ("Nováková", "PERSON"))
    masked, mapping = pseudonymize_text(text, spans, unify="entity")
    assert masked == "Volal <PERSON_1>. Řekl jsem <PERSON_1b>, že paní <PERSON_2> zavolá."
    assert restore_text(masked, mapping) == text
    assert [m["entity"] for m in mapping] == [1, 1, 2]


def test_unify_entity_keeps_other_types_exact():
    text = "Účet 19-2000145399/0800 a znovu 19-2000145399/0800."
    masked, mapping = pseudonymize_text(text, detect_rule_based(text), unify="entity")
    assert masked == "Účet <BBAN_1> a znovu <BBAN_1>."
    assert restore_text(masked, mapping) == text


def test_entity_key_examples():
    from ucs.uc02_pseudonymization.code.pseudonymizer import entity_key

    assert entity_key("PERSON", "Jan Novák") == entity_key("PERSON", "Nováka")
    assert entity_key("PERSON", "Novákovi") == entity_key("PERSON", "Novák")
    assert entity_key("PERSON", "Nováková") != entity_key("PERSON", "Novák")
    assert entity_key("PERSON", "Novákové") == entity_key("PERSON", "Novákovou")
    assert entity_key("PERSON", "Černý") == entity_key("PERSON", "Černého")
    assert entity_key("PERSON", "Svoboda") == entity_key("PERSON", "Svobodovi")
    assert entity_key("EMAIL", "a@b.cz") != entity_key("EMAIL", "c@b.cz")


def test_random_numbering_is_seeded_and_unique_across_types():
    import random

    text = "Volejte +420 601 000 000 nebo pište na jan@x.cz."
    spans = detect_rule_based(text)
    masked_a, mapping_a = pseudonymize_text(text, spans, numbering="random", rng=random.Random(7))
    masked_b, _ = pseudonymize_text(text, spans, numbering="random", rng=random.Random(7))
    assert masked_a == masked_b
    numbers = [m["entity"] for m in mapping_a]
    assert len(set(numbers)) == 2 and all(1 <= n <= 9999 for n in numbers)
    assert restore_text(masked_a, mapping_a) == text


def test_suffixed_token_survives_a_preexisting_tag_scan():
    text = "Šablona <PERSON_1b> a Jan Novák."
    spans = _spans(text, ("Jan Novák", "PERSON"))
    masked, mapping = pseudonymize_text(text, spans)
    assert mapping[0]["token"] == "<PERSON_2>"
    assert restore_text(masked, mapping) == text


def test_entity_key_handles_the_fleeting_e():
    from ucs.uc02_pseudonymization.code.pseudonymizer import entity_key

    assert entity_key("PERSON", "Hájek") == entity_key("PERSON", "Hájka")
    assert entity_key("PERSON", "Havlíček") == entity_key("PERSON", "Havlíčkovi")


def test_ner_trim_keeps_the_dot_of_an_abbreviation():
    from ucs.uc02_pseudonymization.code.ner import trim_span

    text = "Faktura na firmu DětskýSvět Velkoobchod s.r.o., prosím."
    start = text.index("DětskýSvět")
    end = text.index(", prosím")
    assert text[slice(*trim_span(text, start, end + 1))] == "DětskýSvět Velkoobchod s.r.o."
    text2 = "Volal Jan Novák. "
    s2 = text2.index("Jan")
    assert text2[slice(*trim_span(text2, s2, len(text2)))] == "Jan Novák"


def test_ner_span_snaps_to_word_boundaries():
    from ucs.uc02_pseudonymization.code.ner import snap_to_word

    text = "Domluveno se Sedláčkovi, ozveme se."
    start = text.index("Sedláčkov")
    assert text[slice(*snap_to_word(text, start, start + len("Sedláčkov")))] == "Sedláčkovi"
    start = text.index("Jandou") if "Jandou" in text else None
    text2 = "Mluvil jsem s Jandou včera."
    s2 = text2.index("Jan")
    assert text2[slice(*snap_to_word(text2, s2, s2 + 3))] == "Jandou"
    assert snap_to_word(text2, s2, s2 + len("Jandou")) == (s2, s2 + len("Jandou"))


def test_label_to_type_covers_the_candidate_label_sets():
    from ucs.uc02_pseudonymization.code.ner import (
        CANDIDATE_MODELS,
        MODEL_IDS,
        NER_BACKENDS,
        label_to_type,
    )

    assert label_to_type("PERSON_NAME") == "PERSON" and label_to_type("B-PER") == "PERSON"
    assert label_to_type("GIVEN_NAME") == "PERSON" and label_to_type("SURNAME") == "PERSON"
    assert label_to_type("PERSON_IDENTIFIER") is None
    assert label_to_type("COMPANY_NAME") == "ORG" and label_to_type("I") == "ORG"
    assert label_to_type("STREET_ADDRESS") == "ADDRESS" and label_to_type("ZIP_CODE") == "ADDRESS"
    assert label_to_type("LOC") == "ADDRESS" and label_to_type("G") == "ADDRESS"
    assert label_to_type("DATE_OF_BIRTH") == "DATE" and label_to_type("T") == "DATE"
    assert label_to_type("MISC") is None and label_to_type("IBAN") is None
    assert label_to_type("TIME") is None
    assert set(CANDIDATE_MODELS) <= set(NER_BACKENDS) and "gliner2" in NER_BACKENDS
    assert set(MODEL_IDS) <= set(NER_BACKENDS)


def test_ner_trim_drops_a_leading_space():
    from ucs.uc02_pseudonymization.code.ner import trim_span

    text = "Volal Jiří Novák."
    start = text.index(" Jiří")
    assert text[slice(*trim_span(text, start, start + len(" Jiří")))] == "Jiří"


def test_date_fragments_join_across_dots():
    from ucs.uc02_pseudonymization.code.pseudonymizer import join_adjacent_fragments

    text = "Narozen 23. 3. 1969, volal včera."

    def at(start: int, end: int) -> dict:
        return {**_ner(text, text[start:end], "DATE"), "span_start": start, "span_end": end}

    fragments = [at(8, 10), at(12, 13), at(15, 19)]
    joined = join_adjacent_fragments(fragments, text)
    assert [s["surface_form"] for s in joined] == ["23. 3. 1969"]
    persons = [_ner(text, "Narozen", "PERSON"), _ner(text, "volal", "PERSON")]
    assert len(join_adjacent_fragments(persons, text)) == 2
