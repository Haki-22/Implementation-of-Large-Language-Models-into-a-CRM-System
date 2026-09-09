"""Session envelope: tokens, handles, restore, persistence, fail closed."""

from __future__ import annotations

import random

import pytest

from tests.ucs.uc03_mcp_privacy.conftest import stub_detector
from ucs.uc03_mcp_privacy.envelope import TOKEN_RE, EnvelopeUnavailable, SessionEnvelope


def test_handles_are_random_stable_and_resolve(envelope):
    first = envelope.handle_for("CONTACT", 12)
    assert TOKEN_RE.fullmatch(first) and first.startswith("<CONTACT_")
    assert first != "<CONTACT_12>"  # a random number, never the row id
    assert envelope.handle_for("CONTACT", 12) == first
    assert envelope.handle_for("CONTACT", 13) != first
    assert envelope.resolve_id(first, "CONTACT", allow_raw=False) == 12


def test_raw_ids_only_when_allowed(envelope):
    with pytest.raises(LookupError):
        envelope.resolve_id("12", "CONTACT", allow_raw=False)
    assert envelope.resolve_id("12", "CONTACT", allow_raw=True) == 12
    with pytest.raises(LookupError):
        envelope.resolve_id("<COMPANY_1>", "CONTACT", allow_raw=False)  # unknown handle
    company = envelope.handle_for("COMPANY", 3)
    with pytest.raises(LookupError):
        envelope.resolve_id(company, "CONTACT", allow_raw=False)  # wrong kind


def test_value_tokens_share_a_number_per_entity_with_form_suffix(envelope):
    full = envelope.mask_value("PERSON", "Jan Novák", entity=("CONTACT", 1))
    vocative = envelope.mask_value("PERSON", "Vážený pane Nováku", entity=("CONTACT", 1))
    assert full != vocative
    assert full.rstrip(">") in vocative  # same number, letter suffix on the second form
    assert envelope.mask_value("PERSON", "Jan Novák", entity=("CONTACT", 1)) == full
    other = envelope.mask_value("PERSON", "Jan Novák", entity=("CONTACT", 2))
    assert other != full  # same spelling, another row, another number
    assert envelope.mask_value("EMAIL", None) is None
    assert envelope.mask_value("EMAIL", "   ") == "   "


def test_mask_text_and_restore_round_trip(envelope):
    text = "Schůzka s Emily z Chocolate Cake, tel 605 123 456."
    masked = envelope.mask_text(text)
    assert "Emily" not in masked and "Chocolate Cake" not in masked and "605 123 456" not in masked
    assert len(envelope.tokens_in(masked)) == 3
    assert envelope.restore(masked) == text
    # tokens already present are left alone and unknown tokens survive untouched
    assert envelope.restore("<PERSON_1>") == "<PERSON_1>"
    assert envelope.restore(42) == 42


def test_persistence_round_trip(tmp_path):
    path = tmp_path / "map.json"
    first = SessionEnvelope(path, detector=stub_detector, rng=random.Random(1))
    handle = first.handle_for("NOTE", 7)
    token = first.mask_value("PHONE", "+420 601 111 222", entity=("CONTACT", 1))
    masked = first.mask_text("Volal Jan Novák.")
    second = SessionEnvelope(path, detector=stub_detector, rng=random.Random(2))
    assert second.handle_for("NOTE", 7) == handle
    assert second.mask_value("PHONE", "+420 601 111 222", entity=("CONTACT", 1)) == token
    assert second.restore(masked) == "Volal Jan Novák."
    assert len(second) == len(first)


def test_numbers_are_unique_across_kinds(envelope):
    numbers = set()
    for i in range(50):
        for kind in ("CONTACT", "COMPANY", "NOTE"):
            numbers.add(envelope.handle_for(kind, i))
        numbers.add(envelope.mask_value("EMAIL", f"user{i}@example.cz"))
    bare = [int(TOKEN_RE.fullmatch(t).group(2)) for t in numbers]
    assert len(bare) == len(set(bare))


def test_two_writers_share_one_map_without_losing_or_repeating(tmp_path):
    """Two envelopes on one file (server + chat client): every token lands, no number twice."""
    path = tmp_path / "shared.json"
    a = SessionEnvelope(path, detector=stub_detector, rng=random.Random(1))
    b = SessionEnvelope(path, detector=stub_detector, rng=random.Random(1))  # same seed on purpose
    a_handle = a.handle_for("CONTACT", 1)
    b_handle = b.handle_for("CONTACT", 2)
    a_token = a.mask_value("EMAIL", "a@example.cz")
    b_token = b.mask_value("EMAIL", "b@example.cz")
    assert len({a_handle, b_handle, a_token, b_token}) == 4
    merged = SessionEnvelope(path, detector=stub_detector)
    assert merged.resolve_id(a_handle, "CONTACT", allow_raw=False) == 1
    assert merged.resolve_id(b_handle, "CONTACT", allow_raw=False) == 2
    assert merged.restore(f"{a_token} {b_token}") == "a@example.cz b@example.cz"
    numbers = [int(TOKEN_RE.fullmatch(t).group(2)) for t in (a_handle, b_handle, a_token, b_token)]
    assert len(set(numbers)) == 4


def test_fail_closed_when_detector_cannot_run():
    def broken(_text: str):
        raise EnvelopeUnavailable("NER backend missing")

    envelope = SessionEnvelope(detector=broken)
    with pytest.raises(EnvelopeUnavailable):
        envelope.mask_text("Volal Jan Novák.")
    assert envelope.mask_text("") == ""  # nothing to detect, nothing refused
