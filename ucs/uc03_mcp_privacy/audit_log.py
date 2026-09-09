"""Append-only, hash-chained JSONL audit log of UC-03 tool calls.

One line per tool call, canonical JSON (sorted keys, no whitespace)::

    {"seq": 42, "ts": "2026-09-05T18:12:03Z", "tool": "create_note",
     "args_hash": "sha256...", "outcome": "ok", "duration_ms": 12,
     "manifest": "sha256...", "prev_hash": "sha256...", "this_hash": "sha256..."}

Chain rule
----------
``this_hash = sha256(prev_hash | seq | ts | tool | args_hash | outcome | duration_ms | manifest)``

The genesis line uses ``prev_hash = "0" * 64``. ``args_hash`` is the SHA-256 of
the canonical JSON of the call's arguments, so identical calls share a
fingerprint while the log itself never holds an argument value (under the
masking profiles the arguments are session tokens anyway). ``outcome`` is
``ok``, ``refused`` (the tool returned a structured error) or ``error`` (the
tool raised); ``manifest`` is the SHA-256 of the tool manifest the server was
running with, so a row can be tied to the tool definitions that were in force.

Concurrency
-----------
Several server processes may share one file (a browser bridge spawns one server
per turn). Every append runs under a cross-process file lock (``<path>.lock``),
and ``call()`` holds that lock from the moment the sequence number is reserved
until the row is written, so the number a write records is the number of the
row that describes it. Calls on one audit file are therefore serialised.

Tampering check
---------------
``verify(path)`` re-walks the chain. Any mismatched hash, broken sequence or
unreadable line returns ``(False, reason, index)``; a clean chain returns
``(True, "Chain valid, N entries", N)``.

CLI
---
    python -m ucs.uc03_mcp_privacy.audit_log verify [<path>]
    python -m ucs.uc03_mcp_privacy.audit_log inspect [<path>]
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as _dt
import fcntl
import hashlib
import json
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from ucs.uc03_mcp_privacy import config

GENESIS_HASH = "0" * 64
OUTCOMES: tuple[str, ...] = ("ok", "refused", "error")


# ---------------------------------------------------------------------------
# Hashing
# ---------------------------------------------------------------------------


def _canonical(obj: Any) -> bytes:
    """JSON-canonical bytes: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _sha256_hex(payload: bytes) -> str:
    """Return the SHA-256 hex digest of `payload`."""
    return hashlib.sha256(payload).hexdigest()


def hash_args(args: Any) -> str:
    """Return the SHA-256 hex digest of the canonical JSON form of ``args``."""
    return _sha256_hex(_canonical(args))


def _compute_this_hash(entry: dict[str, Any]) -> str:
    """Return `entry`'s chain hash per the module's chain rule (see module docstring)."""
    payload = "|".join(
        str(entry[key])
        for key in (
            "prev_hash",
            "seq",
            "ts",
            "tool",
            "args_hash",
            "outcome",
            "duration_ms",
            "manifest",
        )
    ).encode("utf-8")
    return _sha256_hex(payload)


def _utc_now() -> str:
    """Return the current UTC time as ``"YYYY-MM-DDTHH:MM:SSZ"``."""
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# The log
# ---------------------------------------------------------------------------


@dataclass
class CallRecord:
    """What a tool call learns and reports while its audit row is reserved."""

    seq: int
    outcome: str = "ok"


class AuditLog:
    """Append-only hash-chained JSONL log, safe across threads and processes.

    ``manifest_sha256`` is stamped on every row and can be set after
    construction, once the server has computed it.
    """

    def __init__(self, path: str | Path | None = None, *, manifest_sha256: str = "") -> None:
        """Open the log at `path` (default: `config.audit_path()`), creating its parent directory.

        Args:
            path: Location of the JSONL file. Defaults to the configured audit path.
            manifest_sha256: Tool-manifest hash stamped on rows appended from now
                on; may be left empty and set later via the attribute.
        """
        self.path = Path(path) if path is not None else config.audit_path()
        self.manifest_sha256 = manifest_sha256
        self._lock = threading.RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @contextlib.contextmanager
    def _exclusive(self):
        """Thread lock plus the cross-process file lock of this log."""
        with self._lock:
            with self.path.with_name(self.path.name + ".lock").open("a+") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    yield
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    # ------------------------------------------------------------------ append

    def next_seq(self) -> int:
        """Sequence number the next appended row will get."""
        with self._exclusive():
            return self._tail()[1]

    @contextlib.contextmanager
    def call(self, tool: str, args: Any):
        """Reserve the next row for one tool call and write it when the call ends.

        Yields a :class:`CallRecord` with the reserved ``seq`` (the number a write
        stores) and an ``outcome`` the caller may set to ``refused``; an exception
        inside the block is logged as ``error`` and re-raised. The file lock is
        held for the whole block.
        """
        with self._exclusive():
            record = CallRecord(seq=self._tail()[1])
            started = time.perf_counter()
            try:
                yield record
            except BaseException:
                record.outcome = "error"
                raise
            finally:
                self._append_locked(
                    tool,
                    args,
                    outcome=record.outcome,
                    duration_ms=int((time.perf_counter() - started) * 1000),
                    expected_seq=record.seq,
                )

    def append(
        self,
        tool: str,
        args: Any,
        *,
        outcome: str = "ok",
        duration_ms: int = 0,
        ts: str | None = None,
    ) -> dict[str, Any]:
        """Append one row and return it."""
        with self._exclusive():
            return self._append_locked(tool, args, outcome=outcome, duration_ms=duration_ms, ts=ts)

    def _append_locked(
        self,
        tool: str,
        args: Any,
        *,
        outcome: str,
        duration_ms: int,
        ts: str | None = None,
        expected_seq: int | None = None,
    ) -> dict[str, Any]:
        """Append one row while the exclusive lock is already held; return it.

        Args:
            tool: Tool name recorded on the row.
            args: Call arguments; only their hash is stored, never the values.
            outcome: One of `OUTCOMES`.
            duration_ms: Wall-clock duration of the call, in milliseconds.
            ts: Timestamp override for the row; defaults to `_utc_now()`.
            expected_seq: When given, must match the sequence number reserved
                by the caller, or `RuntimeError` is raised (another writer
                advanced the chain in between).
        """
        if outcome not in OUTCOMES:
            raise ValueError(f"outcome must be one of {OUTCOMES}, got {outcome!r}")
        prev_hash, seq = self._tail()
        if expected_seq is not None and seq != expected_seq:
            raise RuntimeError(
                f"audit log {self.path} advanced to {seq} while seq {expected_seq} was reserved"
            )
        entry: dict[str, Any] = {
            "seq": seq,
            "ts": ts or _utc_now(),
            "tool": tool,
            "args_hash": hash_args(args),
            "outcome": outcome,
            "duration_ms": int(duration_ms),
            "manifest": self.manifest_sha256,
            "prev_hash": prev_hash,
        }
        entry["this_hash"] = _compute_this_hash(entry)
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(_canonical(entry).decode("utf-8"))
            fh.write("\n")
        return entry

    # ------------------------------------------------------------------ read

    def _iter_lines(self) -> Iterable[dict[str, Any]]:
        """Yield every row of this log, parsed from JSON, oldest first."""
        if not self.path.exists():
            return
        with self.path.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if raw:
                    yield json.loads(raw)

    def _tail(self) -> tuple[str, int]:
        """Return ``(last this_hash, next seq)``; genesis is ``("0" * 64, 0)``."""
        last_hash = GENESIS_HASH
        last_seq = -1
        for entry in self._iter_lines():
            last_hash = entry["this_hash"]
            last_seq = int(entry["seq"])
        return last_hash, last_seq + 1

    def entries(self) -> list[dict[str, Any]]:
        """All rows, oldest first."""
        return list(self._iter_lines())

    def verify(self) -> tuple[bool, str, int]:
        """Re-walk this file's chain; see :func:`verify`."""
        return verify(self.path)


def verify(path: str | Path) -> tuple[bool, str, int]:
    """Re-walk the chain on disk and report ``(ok, message, rows checked)``."""
    p = Path(path)
    if not p.exists():
        return True, "Chain valid, 0 entries (no file)", 0

    prev_hash = GENESIS_HASH
    expected_seq = 0
    count = 0
    try:
        with p.open("r", encoding="utf-8") as fh:
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                entry = json.loads(raw)
                if int(entry["seq"]) != expected_seq:
                    return (
                        False,
                        f"seq break at line {count + 1}: got {entry['seq']}, want {expected_seq}",
                        count,
                    )
                if entry["prev_hash"] != prev_hash:
                    return False, f"prev_hash break at seq {expected_seq}", count
                if _compute_this_hash(entry) != entry["this_hash"]:
                    return False, f"this_hash mismatch at seq {expected_seq}", count
                prev_hash = entry["this_hash"]
                expected_seq += 1
                count += 1
    except (OSError, KeyError, json.JSONDecodeError) as exc:
        return False, f"read error at line {count + 1}: {exc}", count

    return True, f"Chain valid, {count} entries", count


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cli(argv: list[str] | None = None) -> int:
    """Entry point for ``verify`` and ``inspect``; return the process exit code."""
    parser = argparse.ArgumentParser(description="UC-03 audit log helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("verify", help="Re-walk the hash chain")
    v.add_argument("path", nargs="?", default=None)
    i = sub.add_parser("inspect", help="Print the rows")
    i.add_argument("path", nargs="?", default=None)
    args = parser.parse_args(argv)

    path = Path(args.path) if args.path else config.audit_path()
    if args.cmd == "verify":
        ok, msg, _ = verify(path)
        print(msg)
        return 0 if ok else 1
    for entry in AuditLog(path).entries():
        print(json.dumps(entry, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(_cli())
