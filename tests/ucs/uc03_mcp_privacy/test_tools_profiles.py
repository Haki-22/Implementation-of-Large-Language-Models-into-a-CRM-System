"""The CRM tools under the three security profiles.

The masking tests share one invariant: no value planted in the scratch database
appears anywhere in a tool result under ``masked`` or ``strict``.
"""

from __future__ import annotations

import json
import sqlite3

import pytest

from tests.ucs.uc03_mcp_privacy.conftest import JAN, PLANTED_VALUES
from ucs.uc03_mcp_privacy.envelope import EnvelopeUnavailable, SessionEnvelope
from ucs.uc03_mcp_privacy.tools import CURRENT_AUDIT_SEQ, CrmTools


def _leaks(result) -> list[str]:
    """Which planted values (if any) appear verbatim in ``result``'s JSON serialization."""
    blob = json.dumps(result, ensure_ascii=False)
    return [value for value in PLANTED_VALUES if str(value) in blob]


@pytest.fixture
def open_tools(scratch_db):
    """``CrmTools`` under the ``open`` profile: clear values, human author, no envelope."""
    return CrmTools(profile="open", db_path=scratch_db, author="human")


@pytest.fixture
def masked_tools(scratch_db, envelope):
    """``CrmTools`` under the ``masked`` profile, wired to the envelope for token restore."""
    return CrmTools(profile="masked", db_path=scratch_db, envelope=envelope, author="llm:test")


@pytest.fixture
def strict_tools(scratch_db, envelope):
    """``CrmTools`` under the ``strict`` profile: sensitive fields dropped, edits held for review."""
    return CrmTools(profile="strict", db_path=scratch_db, envelope=envelope, author="llm:test")


# ---------------------------------------------------------------- open


def test_open_returns_clear_values_and_every_column(open_tools):
    found = open_tools.search_contacts("Novák Brno")
    assert found["count"] == 1 and found["contacts"][0]["name"] == "Jan Novák"
    record = open_tools.get_contact(found["contacts"][0]["id"])["contact"]
    assert (
        record["email"] == JAN["email"]
        and "ocean" in record
        and record["company"].startswith("Chocolate")
    )
    rows = open_tools.query_sql("select id, email from uc_contacts order by id")["rows"]
    assert rows[0]["email"] == JAN["email"]


def test_open_search_matches_company_and_every_word(open_tools):
    assert open_tools.search_contacts("Nováková")["count"] == 1
    assert open_tools.search_contacts("Novák", company="Chocolate")["count"] == 1
    # every word must match one contact; LIKE is a substring test, so Novák also finds Nováková
    assert open_tools.search_contacts("Novák Praha")["count"] == 1
    assert open_tools.search_contacts("Novák Ostrava")["count"] == 0
    assert open_tools.search_contacts("")["count"] == 0


def test_open_search_finds_declined_names(open_tools):
    """A dictated or typed name comes declined; the database holds the nominative."""
    found = open_tools.search_contacts("Janu Novákovi")
    assert found["count"] == 1 and found["contacts"][0]["name"] == "Jan Novák"
    found = open_tools.search_contacts("Evě Novákové")
    assert found["count"] == 1 and found["contacts"][0]["name"] == "Eva Nováková"
    # the stem alone would also match the namesake; the first name keeps it to one person
    assert open_tools.search_contacts("Novákovi")["count"] == 2
    assert open_tools.search_contacts("Novotného")["count"] == 0
    assert open_tools.search_contacts("Novákovi Ostrava")["count"] == 0


def test_open_sql_is_bounded(open_tools):
    big = open_tools.query_sql("select hex(randomblob(100000)) as payload")
    assert big["ok"] and len(big["rows"][0]["payload"]) <= 2001
    assert open_tools.query_sql("select 1; drop table uc_notes")["error"] == "not_a_select"
    assert open_tools.query_sql("pragma table_info(uc_notes)")["error"] == "not_a_select"


def test_open_update_is_applied_and_logged(open_tools, scratch_db):
    result = open_tools.update_contact("1", "city", "Olomouc", None)
    assert result["status"] == "applied"
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select city from uc_contacts where id = 1").fetchone()[0] == "Olomouc"
    log = conn.execute(
        "select field, old_value, new_value, applied, author from uc_change_log"
    ).fetchone()
    assert log == ("city", "Brno", "Olomouc", 1, "human")


# ---------------------------------------------------------------- masked


def test_masked_results_carry_no_planted_value(masked_tools):
    found = masked_tools.search_contacts("Novák")
    assert found["count"] == 2 and not _leaks(found)
    assert all(c["city"].startswith("<ADDRESS_") for c in found["contacts"])
    handle = masked_tools.search_contacts("Novák Brno")["contacts"][0][
        "id"
    ]  # server searches in clear
    assert handle.startswith("<CONTACT_")
    record = masked_tools.get_contact(handle)
    assert not _leaks(record)
    assert "ocean" in record["contact"] and "prior_interactions" in record["contact"]
    assert not _leaks(masked_tools.search_notes(contact_id=handle))
    assert not _leaks(masked_tools.search_reviews("sluchátka"))
    assert not _leaks(masked_tools.get_company(record["contact"]["company_id"]))
    assert masked_tools.query_sql("select email from uc_contacts")["error"] == "disabled"


def test_masked_refuses_raw_ids(masked_tools):
    assert masked_tools.get_contact("1")["error"] == "bad_id"
    assert masked_tools.create_note("1", "x")["error"] == "bad_id"


def test_masked_create_note_restores_tokens_and_records_provenance(
    masked_tools, scratch_db, envelope
):
    handle = masked_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    name_token = masked_tools.get_contact(handle, include_notes=False)["contact"]["name"]
    phone_token = envelope.mask_value("PHONE", "605 123 456")
    CURRENT_AUDIT_SEQ.set(41)
    try:
        result = masked_tools.create_note(
            handle, f"Volal {name_token}, tel {phone_token}, chce reklamaci."
        )
    finally:
        CURRENT_AUDIT_SEQ.set(None)
    assert (
        result["ok"]
        and result["note_id"].startswith("<NOTE_")
        and result["category"] == "complaint"
    )
    row = (
        sqlite3.connect(scratch_db)
        .execute(
            "select content, author, audit_seq, pseudonymized from uc_notes order by id desc limit 1"
        )
        .fetchone()
    )
    assert row == ("Volal Jan Novák, tel 605 123 456, chce reklamaci.", "llm:test", 41, 1)
    assert not _leaks(result)


def test_masked_update_is_applied(masked_tools, scratch_db):
    handle = masked_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    assert masked_tools.update_contact(handle, "phone", "777 000 111", None)["status"] == "applied"
    assert (
        sqlite3.connect(scratch_db)
        .execute("select phone from uc_contacts where id = 1")
        .fetchone()[0]
        == "777 000 111"
    )


# ---------------------------------------------------------------- strict


def test_strict_scope_drops_sensitive_columns_and_sql(strict_tools):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    record = strict_tools.get_contact(handle)["contact"]
    for column in (
        "ocean",
        "prior_interactions",
        "iban",
        "date_of_birth",
        "bank_account",
        "reviewer_id",
    ):
        assert column not in record
    assert record["email"].startswith("<EMAIL_") and record["lifecycle_stage"] == "active"
    assert record["city"].startswith("<ADDRESS_") and record["region"] is None
    assert strict_tools.query_sql("select 1")["error"] == "disabled"


def test_strict_holds_field_changes_until_reviewed(strict_tools, scratch_db):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    held = strict_tools.update_contact(handle, "phone", "777 000 111", None)
    assert held["status"] == "pending_review"
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select phone from uc_contacts where id = 1").fetchone()[0] == JAN["phone"]
    pending = strict_tools.pending_changes()
    assert [p["field"] for p in pending] == ["phone"] and pending[0]["applied"] == 0
    assert strict_tools.review_change(held["change_id"], "applied")["ok"]
    assert conn.execute("select phone from uc_contacts where id = 1").fetchone()[0] == "777 000 111"
    assert strict_tools.review_change(held["change_id"], "applied")["error"] == "already_reviewed"
    stamp = strict_tools.get_contact(handle, include_notes=False)["contact"]["updated_at"]
    assert stamp is not None
    assert strict_tools.update_contact(handle, "city", "Ostrava", None)["error"] == "stale"
    rejected = strict_tools.update_contact(handle, "city", "Ostrava", stamp)
    assert strict_tools.review_change(rejected["change_id"], "rejected")["outcome"] == "rejected"
    assert conn.execute("select city from uc_contacts where id = 1").fetchone()[0] == "Brno"


def test_review_refuses_to_overwrite_a_later_edit(strict_tools, open_tools, scratch_db):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    held = strict_tools.update_contact(handle, "phone", "777 000 111", None)
    assert (
        open_tools.update_contact("1", "phone", "608 999 000", None)["status"] == "applied"
    )  # a person edits
    result = strict_tools.review_change(held["change_id"], "applied")
    assert result["error"] == "conflict" and result["current"] == "608 999 000"
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select phone from uc_contacts where id = 1").fetchone()[0] == "608 999 000"
    assert (
        conn.execute(
            "select review_outcome from uc_change_log where id = ?", (held["change_id"],)
        ).fetchone()[0]
        == "conflict"
    )
    assert strict_tools.pending_changes() == []


def test_review_catches_an_edit_that_was_reverted(strict_tools, open_tools, scratch_db):
    """Value guard alone would miss this: the phone went A -> C -> A, the timestamp moved."""
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    held = strict_tools.update_contact(handle, "phone", "777 000 111", None)
    first = open_tools.update_contact("1", "phone", "608 999 000", None)
    assert first["status"] == "applied"
    back = open_tools.update_contact("1", "phone", JAN["phone"], first["updated_at"])
    assert back["status"] == "applied"
    result = strict_tools.review_change(held["change_id"], "applied")
    assert result["error"] == "conflict" and result["current"] == JAN["phone"]
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select phone from uc_contacts where id = 1").fetchone()[0] == JAN["phone"]
    assert conn.execute("select updated_at from uc_contacts where id = 1").fetchone()[0] is not None


def test_apply_stamps_updated_at(strict_tools, scratch_db):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select updated_at from uc_contacts where id = 1").fetchone()[0] is None
    held = strict_tools.update_contact(handle, "city", "Olomouc", None)
    assert strict_tools.review_change(held["change_id"], "applied")["ok"]
    city, stamp = conn.execute("select city, updated_at from uc_contacts where id = 1").fetchone()
    assert city == "Olomouc" and stamp is not None


def test_stale_stamp_is_refused_with_the_current_value(masked_tools, open_tools):
    """The model must name the updated_at it read; a moved row comes back as stale, masked."""
    handle = masked_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    seen = masked_tools.get_contact(handle, include_notes=False)["contact"]["updated_at"]
    assert seen is None
    human = open_tools.update_contact("1", "phone", "608 999 000", None)  # someone edits meanwhile
    stale = masked_tools.update_contact(handle, "phone", "777 000 111", seen)
    assert stale["error"] == "stale" and stale["field"] == "phone"
    assert (
        stale["current_value"].startswith("<PHONE_")
        and stale["current_updated_at"] == human["updated_at"]
    )
    assert not _leaks(stale)
    retry = masked_tools.update_contact(handle, "phone", "777 000 111", stale["current_updated_at"])
    assert retry["status"] == "applied" and retry["updated_at"] != human["updated_at"]


def test_note_edits_name_the_stamp_they_read(strict_tools):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    note = strict_tools.get_contact(handle, note_limit=1)["notes"][0]
    assert note["updated_at"] is None
    first = strict_tools.update_note(note["id"], None, category="sales")
    assert first["ok"] and first["updated_at"] is not None
    stale = strict_tools.update_note(note["id"], None, category="support")
    assert stale["error"] == "stale" and stale["current_updated_at"] == first["updated_at"]
    assert strict_tools.delete_note(note["id"], None)["error"] == "stale"
    assert strict_tools.delete_note(note["id"], first["updated_at"])["deleted"]


def test_update_errors_are_structured(strict_tools, open_tools):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    wrong_kind = strict_tools.update_contact(handle, "company_id", handle, None)
    assert wrong_kind["error"] == "bad_value"
    assert open_tools.update_contact("1", "company_id", "999", None)["error"] == "bad_value"
    assert open_tools.update_contact("1", "company_id", "", None)["status"] == "applied"  # detach


def test_strict_validates_fields_and_vocabularies(strict_tools):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    assert strict_tools.update_contact(handle, "iban", "CZ00", None)["error"] == "bad_field"
    assert (
        strict_tools.update_contact(handle, "lifecycle_stage", "vip", None)["error"] == "bad_value"
    )
    assert strict_tools.create_note(handle, "text", category="urgent")["error"] == "bad_category"
    assert strict_tools.create_note(handle, "   ")["error"] == "empty_content"
    assert strict_tools.get_contact("<CONTACT_1>")["error"] == "bad_id"


def test_notes_are_routine_in_strict_and_edits_are_logged(strict_tools, scratch_db):
    handle = strict_tools.search_contacts("Novák Brno")["contacts"][0]["id"]
    created = strict_tools.create_note(handle, "Poslat nabídku na sluchátka.", category="sales")
    assert created["ok"]
    changed = strict_tools.update_note(created["note_id"], None, category="follow_up")
    assert changed["changed"] == ["category"]
    assert strict_tools.delete_note(created["note_id"], changed["updated_at"])["deleted"]
    conn = sqlite3.connect(scratch_db)
    assert conn.execute("select count(*) from uc_notes where category = 'sales'").fetchone()[0] == 0
    fields = [
        r[0]
        for r in conn.execute(
            "select field from uc_change_log where entity_type = 'note' order by id"
        )
    ]
    assert fields == ["category", "deleted"]


def test_fail_closed_when_envelope_cannot_run(scratch_db):
    def broken(_text: str):
        """A detector that always fails, simulating an unavailable NER backend."""
        raise EnvelopeUnavailable("NER backend missing")

    tools = CrmTools(
        profile="strict", db_path=scratch_db, envelope=SessionEnvelope(detector=broken)
    )
    handle = tools.search_contacts("Novák Brno")["contacts"][0][
        "id"
    ]  # schema masking needs no detector
    assert tools.search_notes(contact_id=handle)["error"] == "envelope_unavailable"
    assert tools.create_note(handle, "Volal kvůli reklamaci.")["error"] == "envelope_unavailable"
    assert tools.create_note(handle, "Volal kvůli reklamaci.", category="complaint")[
        "ok"
    ]  # no detector needed
