"""The casing table's transforms: offsets survive a case change, gold spans survive a lemma change."""

from __future__ import annotations

import pytest

from ucs.uc02_pseudonymization.eval.casing_table import lemmatize_text, recase, recase_corpus

TEXT = "Řekni mi něco o Petru Bartošovi, volal z Brna, tel. 604 123 456."
GOLD = [
    {
        "message_id": "m1",
        "span_start": 16,
        "span_end": 31,
        "pii_type": "PERSON",
        "surface_form": "Petru Bartošovi",
    },
    {
        "message_id": "m1",
        "span_start": 41,
        "span_end": 45,
        "pii_type": "ADDRESS",
        "surface_form": "Brna",
    },
    {
        "message_id": "m1",
        "span_start": 52,
        "span_end": 63,
        "pii_type": "PHONE",
        "surface_form": "604 123 456",
    },
]


def test_case_changes_keep_every_offset():
    for casing in ("original", "lower", "upper"):
        assert len(recase(TEXT, casing)) == len(TEXT)
    with pytest.raises(ValueError):
        recase(TEXT, "shouted")


def test_lemma_keeps_names_and_digits_and_maps_the_spans():
    pytest.importorskip("simplemma")
    new, map_span = lemmatize_text(TEXT)
    assert new.startswith("řeknout ")  # a common word is lemmatised
    for span in GOLD:
        start, end = map_span(span["span_start"], span["span_end"])
        assert (
            new[start:end]
            == {"PERSON": "Petru Bartošovi", "ADDRESS": "Brno", "PHONE": "604 123 456"}[
                span["pii_type"]
            ]
        )
    lowered, _ = lemmatize_text(TEXT, lower=True)
    assert lowered == new.lower()


def test_recase_corpus_carries_the_gold_over():
    pytest.importorskip("simplemma")
    corpus = [{"message_id": "m1", "text": TEXT}]
    gold = {"m1": GOLD}
    for casing in ("lower", "lemma", "lemma_lower"):
        out_corpus, out_gold, dropped = recase_corpus(corpus, gold, casing)
        assert not dropped and len(out_gold["m1"]) == 3
        text = out_corpus[0]["text"]
        for span in out_gold["m1"]:
            assert text[span["span_start"] : span["span_end"]] == span["surface_form"]
            assert span["surface_form"]  # never empty after the mapping
