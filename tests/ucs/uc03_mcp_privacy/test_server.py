"""The real server over stdio: committed pin, strict verification, masked round trip, audit."""

from __future__ import annotations

import json

import pytest

from tests.ucs.uc03_mcp_privacy.conftest import EVA, PLANTED_VALUES
from ucs.uc03_mcp_privacy.audit_log import AuditLog, verify
from ucs.uc03_mcp_privacy.mcp_client import McpStdioClient
from ucs.uc03_mcp_privacy.tool_manifest import ToolManifest
from ucs.uc03_mcp_privacy.tools import TOOL_NAMES


def _env(tmp_path, scratch_db, **extra):
    env = {
        "UC03_DB_PATH": str(scratch_db),
        "UC03_AUDIT_PATH": str(tmp_path / "audit.jsonl"),
        "UC03_SESSION_MAP": str(tmp_path / "session-map.json"),
        "UC03_SECURITY": "strict",
        "UC03_AUTHOR": "llm:test",
    }
    env.update(extra)
    return env


def test_strict_server_round_trip_over_stdio(tmp_path, scratch_db):
    """Default manifest (the committed pin), strict verification on, masked tools end to end.

    Uses the contact without free-text columns so the schema masking alone
    serves the calls and no NER model has to load inside the server.
    """
    env = _env(tmp_path, scratch_db)
    with McpStdioClient(env=env) as client:
        assert {t["name"] for t in client.list_tools()} == set(TOOL_NAMES)
        found = client.call_tool("search_contacts", {"query": "Nováková"})
        assert found["count"] == 1
        handle = found["contacts"][0]["id"]
        assert handle.startswith("<CONTACT_")
        record = client.call_tool("get_contact", {"contact_id": handle, "include_notes": False})
        assert record["ok"] and not [v for v in PLANTED_VALUES if v in json.dumps(record)]
        assert record["contact"]["city"].startswith("<ADDRESS_")
        note = client.call_tool(
            "create_note",
            {
                "contact_id": handle,
                "content": f"Volala {record['contact']['name']}, chce nabídku.",
                "category": "sales",
            },
        )
        assert note["ok"] and note["author"] == "llm:test" and note["audit_seq"] == 2
        refused = client.call_tool("get_contact", {"contact_id": "2"})
        assert refused["error"] == "bad_id"
        assert client.call_tool("query_sql", {"sql": "select 1"})["error"] == "disabled"

    import sqlite3

    row = (
        sqlite3.connect(scratch_db)
        .execute("select content, author, audit_seq from uc_notes order by id desc limit 1")
        .fetchone()
    )
    assert row == (f"Volala {EVA['first_name']} {EVA['last_name']}, chce nabídku.", "llm:test", 2)

    ok, message, count = verify(tmp_path / "audit.jsonl")
    assert ok and count == 5, message
    rows = AuditLog(tmp_path / "audit.jsonl").entries()
    assert [r["tool"] for r in rows] == [
        "search_contacts",
        "get_contact",
        "create_note",
        "get_contact",
        "query_sql",
    ]
    assert [r["outcome"] for r in rows] == ["ok", "ok", "ok", "refused", "refused"]
    assert all(r["manifest"] for r in rows)
    assert (tmp_path / "session-map.json").exists()


def test_open_server_returns_clear_values(tmp_path, scratch_db):
    with McpStdioClient(env=_env(tmp_path, scratch_db, UC03_SECURITY="open")) as client:
        found = client.call_tool("search_contacts", {"query": "Nováková"})
        assert found["contacts"][0]["name"] == f"{EVA['first_name']} {EVA['last_name']}"
        assert isinstance(found["contacts"][0]["id"], int)
        assert client.call_tool("whoami").endswith("(open profile)")


def test_tampered_pin_stops_the_server(tmp_path, scratch_db):
    pin = ToolManifest(tmp_path / "pin.json")
    pinned = json.loads(ToolManifest().path.read_text(encoding="utf-8"))
    pinned["tools"]["create_note"]["sha256"] = "0" * 64
    pin.path.write_text(json.dumps(pinned), encoding="utf-8")
    client = McpStdioClient(
        env=_env(tmp_path, scratch_db, UC03_MANIFEST_PATH=str(pin.path)), connect_timeout=30
    )
    with pytest.raises((RuntimeError, TimeoutError)):
        client.start()
    client.close()
    assert not (tmp_path / "audit.jsonl").exists()  # nothing was served
