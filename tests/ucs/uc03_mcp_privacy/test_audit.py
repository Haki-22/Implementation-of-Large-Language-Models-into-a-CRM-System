"""Audit log: chain rule, outcome fields, tamper detection, concurrent appends."""

from __future__ import annotations

import json
import threading

import pytest

from ucs.uc03_mcp_privacy.audit_log import GENESIS_HASH, AuditLog, verify


def test_genesis_link_and_fields(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl", manifest_sha256="abc123")
    assert log.next_seq() == 0
    first = log.append("ping", {"kwargs": {"message": "x"}})
    second = log.append(
        "get_contact", {"kwargs": {"contact_id": "12"}}, outcome="refused", duration_ms=7
    )
    assert first["seq"] == 0 and first["prev_hash"] == GENESIS_HASH
    assert second["seq"] == 1 and second["prev_hash"] == first["this_hash"]
    assert second["outcome"] == "refused" and second["duration_ms"] == 7
    assert first["manifest"] == "abc123"
    assert "message" not in json.dumps(log.entries())  # arguments are hashed, never stored
    assert log.next_seq() == 2
    assert verify(log.path) == (True, "Chain valid, 2 entries", 2)


def test_tampering_breaks_the_chain(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")
    for i in range(3):
        log.append("ping", {"kwargs": {"i": i}})
    lines = log.path.read_text(encoding="utf-8").splitlines()
    row = json.loads(lines[1])
    row["outcome"] = "error"  # change one field, keep the stored hash
    lines[1] = json.dumps(row, sort_keys=True, separators=(",", ":"))
    log.path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    ok, message, count = verify(log.path)
    assert not ok and "this_hash mismatch at seq 1" in message and count == 1

    log.path.write_text(lines[0] + "\n" + lines[2] + "\n", encoding="utf-8")  # drop a row
    ok, message, _ = verify(log.path)
    assert not ok and "seq break" in message


def test_call_context_reserves_the_row_it_writes(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl", manifest_sha256="m")
    with log.call("create_note", {"kwargs": {"x": 1}}) as record:
        assert record.seq == 0
        assert log.path.exists() is False or log.entries() == []  # nothing written yet
    with log.call("get_contact", {}) as record:
        assert record.seq == 1
        record.outcome = "refused"
    with pytest.raises(RuntimeError):
        with log.call("ping", {}) as record:
            assert record.seq == 2
            raise RuntimeError("tool blew up")
    rows = log.entries()
    assert [(r["seq"], r["tool"], r["outcome"]) for r in rows] == [
        (0, "create_note", "ok"),
        (1, "get_contact", "refused"),
        (2, "ping", "error"),
    ]
    assert verify(log.path)[0]


def test_two_log_objects_on_one_file_keep_one_chain(tmp_path):
    """Two server processes behind one bridge share one file: the lock keeps the chain."""
    first = AuditLog(tmp_path / "audit.jsonl")
    second = AuditLog(tmp_path / "audit.jsonl")
    for i in range(5):
        first.append("ping", {"i": i})
        second.append("ping", {"i": -i})
    assert verify(tmp_path / "audit.jsonl") == (True, "Chain valid, 10 entries", 10)


def test_unknown_outcome_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        AuditLog(tmp_path / "a.jsonl").append("ping", {}, outcome="maybe")


def test_concurrent_appends_keep_one_chain(tmp_path):
    log = AuditLog(tmp_path / "audit.jsonl")

    def worker(n: int) -> None:
        for i in range(25):
            log.append("ping", {"kwargs": {"n": n, "i": i}})

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert verify(log.path) == (True, "Chain valid, 100 entries", 100)


def test_missing_file_is_an_empty_valid_chain(tmp_path):
    assert verify(tmp_path / "nothing.jsonl")[0] is True
