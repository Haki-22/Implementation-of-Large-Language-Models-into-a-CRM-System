"""Malformed references must not turn into empty searches or persisted notes."""

import html
import sqlite3

import pytest

from ucs.uc03_mcp_privacy.envelope import TokenValidationError
from ucs.uc03_mcp_privacy.tools import CrmTools


@pytest.mark.parametrize(
    "encode",
    [
        lambda token: token,
        html.escape,
        lambda token: html.escape(html.escape(token)),
        lambda token: token.replace("<", "&#60;").replace(">", "&#62;"),
        lambda token: token.replace("<", "&#x3C;").replace(">", "&#x3E;"),
    ],
)
@pytest.mark.parametrize("profile", ["masked", "strict"])
def test_encoded_search_and_handle_round_trip(scratch_db, envelope, encode, profile):
    tools = CrmTools(profile=profile, db_path=scratch_db, envelope=envelope)
    name = envelope.mask_value("PERSON", "Jan Novák")
    found = tools.search_contacts(encode(name))
    assert found["count"] == 1
    contact = found["contacts"][0]
    assert contact["name"] != name  # full-name row identity differs from query identity
    assert envelope.restore_checked(contact["name"]) == "Jan Novák"
    orders = tools.list_orders(encode(contact["id"]), limit=1)
    assert orders["ok"] and orders["orders"][0]["unit_price"] == 990.0
    assert tools.get_contact(encode(name))["error"] == "bad_id"


@pytest.mark.parametrize(
    "damage",
    [
        lambda token: token[1:-1],
        lambda token: token.replace("_", "_ "),
        lambda token: token.replace("_", "_\u200b"),
        lambda token: token.lower(),
        lambda token: token.replace("<", "＜").replace(">", "＞"),
        lambda token: token.replace("<", r"\<"),
        lambda token: token.replace("<", "%3C").replace(">", "%3E"),
        lambda token: html.escape(html.escape(html.escape(token))),
    ],
)
def test_damaged_search_is_an_error_not_zero_matches(scratch_db, envelope, damage):
    tools = CrmTools(profile="strict", db_path=scratch_db, envelope=envelope)
    name = envelope.mask_value("PERSON", "Jan Novák")
    result = tools.search_contacts(damage(name))
    assert not result["ok"] and result["error"] == "malformed_token"
    assert "contacts" not in result


def test_unknown_tokens_refuse_all_mutations(scratch_db, envelope):
    tools = CrmTools(profile="masked", db_path=scratch_db, envelope=envelope)
    contact = envelope.handle_for("CONTACT", 1)
    note = envelope.handle_for("NOTE", 1)
    company = envelope.handle_for("COMPANY", 1)
    with sqlite3.connect(scratch_db) as conn:
        before = list(conn.iterdump())
    unknown = "<PERSON_0>"
    assert unknown not in envelope.entries
    results = [
        tools.create_note(contact, f"Volal {unknown}", category="general"),
        tools.update_note(note, None, content=unknown),
        tools.update_contact(contact, "city", unknown, None),
        tools.update_company(company, "city", unknown, None),
        tools.search_contacts(unknown),
        tools.search_notes(unknown),
        tools.search_reviews(unknown),
    ]
    assert all(result["error"] == "unknown_token" for result in results)
    with sqlite3.connect(scratch_db) as conn:
        assert list(conn.iterdump()) == before


def test_only_token_notation_is_decoded_in_a_note(scratch_db, envelope):
    tools = CrmTools(profile="strict", db_path=scratch_db, envelope=envelope)
    contact = envelope.handle_for("CONTACT", 1)
    token = envelope.mask_value("PERSON", "Jan Novák")
    result = tools.create_note(
        contact, f"Volal {html.escape(token)}; &lt;b&gt; A &amp; B.", "general"
    )
    assert result["ok"]
    with sqlite3.connect(scratch_db) as conn:
        body = conn.execute("select content from uc_notes order by id desc limit 1").fetchone()[0]
    assert body == "Volal Jan Novák; &lt;b&gt; A &amp; B."


def test_checked_answer_accepts_subset_and_known_handles(envelope):
    name = envelope.mask_value("PERSON", "Jan Novák")
    envelope.mask_value("EMAIL", "unused@example.cz")
    contact = envelope.handle_for("CONTACT", 1)
    assert (
        envelope.restore_checked(f"{html.escape(name)} ({contact})", allow_handles=True)
        == f"Jan Novák ({contact})"
    )
    with pytest.raises(TokenValidationError, match="not in this session"):
        envelope.restore_checked("<PERSON_0>", allow_handles=True)
    with pytest.raises(TokenValidationError, match="row handle"):
        envelope.restore_checked(contact)


def test_ordinary_product_codes_are_not_damaged_tokens(envelope):
    text = "Pofung BF_S112, MODEL_2026, verze 3."
    assert envelope.restore_checked(text) == text


def test_clarification_combines_name_and_city_tokens(scratch_db, envelope):
    tools = CrmTools(profile="strict", db_path=scratch_db, envelope=envelope)
    name = envelope.mask_value("PERSON", "Jan")
    city = envelope.mask_value("ADDRESS", "Brno")
    result = tools.search_contacts(f"{name} {city}")
    assert result["ok"] and result["count"] == 1
    assert envelope.restore_checked(result["contacts"][0]["name"]) == "Jan Novák"
