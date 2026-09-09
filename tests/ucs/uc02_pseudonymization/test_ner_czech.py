"""Czech NER detector + public pseudonymize/depseudonymize roundtrip tests.

The primary model (``bardsai/eu-pii-anonimization-multilang``) is downloaded on
first run (~200 MB ONNX INT8). All tests are skipped if neither the primary
nor the fallback model can be loaded — keeps the suite green on offline CI.
"""

from __future__ import annotations

import pytest

# Skip the whole module if the NER stack cannot be imported at all
pytest.importorskip("optimum")
pytest.importorskip("transformers")

from ucs.uc02_pseudonymization import depseudonymize, pseudonymize
from ucs.uc02_pseudonymization.code.ner import detect_ner


# --- 10 Czech sentences with PERSON and/or ADDRESS spans -------------------

CZECH_SENTENCES: list[tuple[str, set[str]]] = [
    # (text, expected_pii_types_subset)
    ("Jan Novák bydlí v Praze.", {"PERSON", "ADDRESS"}),
    ("Petr Svoboda volal z Brna ohledně objednávky.", {"PERSON", "ADDRESS"}),
    ("Paní Marie Dvořáková přišla na schůzku.", {"PERSON"}),
    (
        "Adresa pro doručení: Vinohradská 12, 120 00 Praha 2.",
        # The postal code inside the address yields to the NER's ADDRESS span
        # (merge_spans), so the whole address is one token.
        {"ADDRESS"},
    ),
    (
        "Kontaktujte prosím Tomáše Procházku, e-mail tomas@firma.cz.",
        {"PERSON", "EMAIL"},
    ),
    (
        "Karel Čapek napsal RUR. Pan Čapek žil v Praze.",
        {"PERSON"},
    ),
    (
        "Nová pobočka v ulici Masarykova 5, Ostrava, je otevřená.",
        {"ADDRESS"},
    ),
    (
        "Volala Eva Horáková z čísla +420 601 234 567.",
        {"PERSON", "PHONE"},
    ),
    (
        "Pan Pavel Krejčí má sídlo v Plzni a IČO 27074358.",
        {"PERSON", "ADDRESS", "ICO"},
    ),
    (
        "Lucie Veselá z Olomouce reklamovala dodávku.",
        {"PERSON", "ADDRESS"},
    ),
    (
        "Michal Fiala bydlí na adrese Korunní 30, 101 00 Praha 10.",
        # See the "Vinohradská" case above.
        {"PERSON", "ADDRESS"},
    ),
    (
        "Jana Marková z Brna platila na účet 1234567890/0800.",
        {"PERSON", "ADDRESS", "BBAN"},
    ),
]


# --- Module-scoped fixture: try to load NER once ---------------------------


@pytest.fixture(scope="module")
def ner_available() -> bool:
    """Return True if at least one Czech NER backend loaded successfully.

    On a fresh machine this triggers the bardsai ONNX download (~200 MB).
    """
    try:
        detect_ner("Jan Novák je v Praze.")
        return True
    except Exception:  # noqa: BLE001
        try:
            detect_ner("Jan Novák je v Praze.", use_fallback=True)
            return True
        except Exception:  # noqa: BLE001
            return False


# --- Individual sentence tests ---------------------------------------------


_SENTENCE_IDS = [
    "person+address_praha",
    "person+address_brno",
    "person_dvorakova",
    "address_vinohradska_psc",
    "person+email_prochazka",
    "person_capek_repeated",
    "address_masarykova",
    "person+phone_horakova",
    "person+address+ico_krejci",
    "person+address_vesela",
    "person+address+psc_korunni",
    "person+address_horni",
]


@pytest.mark.parametrize("text,expected_types", CZECH_SENTENCES, ids=_SENTENCE_IDS)
def test_pseudonymize_finds_expected_pii(
    text: str, expected_types: set[str], ner_available: bool
) -> None:
    """Each sentence must yield at least one span for each expected PII type."""
    if not ner_available:
        pytest.skip("Czech NER model unavailable (offline / download failed)")
    masked, mapping = pseudonymize(text)
    found_types = {item["pii_type"] for item in mapping}
    missing = expected_types - found_types
    assert not missing, f"missing PII types {missing} for: {text!r} (found {found_types})"


@pytest.mark.parametrize("text,_expected_types", CZECH_SENTENCES, ids=_SENTENCE_IDS)
def test_pseudonymize_roundtrip_exact(
    text: str, _expected_types: set[str], ner_available: bool
) -> None:
    """Pseudonymize → depseudonymize must restore the original text byte-for-byte."""
    if not ner_available:
        pytest.skip("Czech NER model unavailable (offline / download failed)")
    masked, mapping = pseudonymize(text)
    restored = depseudonymize(masked, mapping)
    assert restored == text


def test_placeholders_present_for_each_pii_type(ner_available: bool) -> None:
    """Each detected PII type must be referenced by a placeholder in the masked text."""
    if not ner_available:
        pytest.skip("Czech NER model unavailable (offline / download failed)")
    text = "Jan Novák bydlí v Praze a má e-mail jan@firma.cz."
    masked, mapping = pseudonymize(text)
    for item in mapping:
        assert item["token"] in masked, (
            f"placeholder {item['token']} missing from masked text: {masked!r}"
        )


def test_rule_only_mode_skips_ner() -> None:
    """``use_ner=False`` must produce only format-bearing PII (no PERSON/ADDRESS)."""
    text = "Jan Novák, e-mail jan@firma.cz."
    masked, mapping = pseudonymize(text, use_ner=False)
    found_types = {item["pii_type"] for item in mapping}
    assert "EMAIL" in found_types
    assert "PERSON" not in found_types
    assert "ADDRESS" not in found_types


def test_rule_wins_on_overlap(ner_available: bool) -> None:
    """When NER and rule recognizers overlap, the rule-based span must win.

    A bare e-mail address sometimes attracts a PERSON tag because of the
    name-like prefix; the deterministic EMAIL recognizer must take precedence.
    """
    if not ner_available:
        pytest.skip("Czech NER model unavailable (offline / download failed)")
    text = "Pište na novak.jan@firma.cz."
    _masked, mapping = pseudonymize(text)
    types_for_email_span = [
        item["pii_type"] for item in mapping if item["surface_form"] == "novak.jan@firma.cz"
    ]
    assert types_for_email_span == ["EMAIL"], f"expected exactly one EMAIL span, got {mapping}"


def test_depseudonymize_after_llm_edit(ner_available: bool) -> None:
    """Mapping must restore surface forms even if surrounding text was rewritten."""
    if not ner_available:
        pytest.skip("Czech NER model unavailable (offline / download failed)")
    text = "Jan Novák volal z Brna."
    masked, mapping = pseudonymize(text)
    # Simulate an LLM paraphrasing the masked transcript
    paraphrased = masked.replace("volal", "telefonoval").replace("z", "ze sídla")
    restored = depseudonymize(paraphrased, mapping)
    # Original surface forms must reappear in the paraphrased+restored text
    for item in mapping:
        assert item["surface_form"] in restored, (
            f"surface {item['surface_form']!r} missing after restore: {restored!r}"
        )
