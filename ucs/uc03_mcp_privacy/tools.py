"""UC-03 CRM tools: the middleware between the database and the chat.

Every tool is a plain method of :class:`CrmTools`, callable from Python (tests,
the demo smoke, the review CLI) and exposed unchanged over MCP by ``server.py``.
The tools read and write ``substrate.db`` through ``sqlite3`` directly, so the
server imports in milliseconds and needs no ORM at run time.

What the security profile changes (``config.security_profile``)
----------------------------------------------------------------
``open``
    Clear values, every column, ``query_sql`` for any read-only SELECT, every
    write applied at once. The model is the whole integration layer.
``masked``
    Every personal value in a result is a session token minted by the
    :class:`~ucs.uc03_mcp_privacy.envelope.SessionEnvelope`; row ids are
    handles; every token or handle in a tool argument is resolved back before
    the database is touched; the categoriser sees masked text. When the
    envelope cannot run the tool refuses (fail closed).
``strict``
    ``masked`` plus scope: contact and company records carry only the fields
    an assistant needs (no personality profile, no bank data, no birth date),
    ``query_sql`` is off, and a contact or company field change is recorded in
    ``uc_change_log`` but **held** until a person applies it (``review.py``).
    Notes are routine and are filed at once in every profile.

Provenance of every write
-------------------------
Each note carries ``author`` (``human``, or ``llm:<model>`` from ``UC03_AUTHOR``)
and ``audit_seq``, the sequence number of the audit row of the call that wrote
it; ``server.py`` sets the number in :data:`CURRENT_AUDIT_SEQ` around each call.
Field changes are ``uc_change_log`` rows with old and new value.
"""

from __future__ import annotations

import contextvars
import datetime as _dt
from functools import wraps
import os
import platform
import re
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

from substrate.constants import LIFECYCLE_STAGES, NOTE_CATEGORIES, REVIEWS_FTS_TABLE
from ucs.uc02_pseudonymization.code.pseudonymizer import entity_key
from ucs.uc03_mcp_privacy import config
from ucs.uc03_mcp_privacy.categorizer import categorize_text
from ucs.uc03_mcp_privacy.envelope import EnvelopeUnavailable, SessionEnvelope, TokenValidationError

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PACKAGE_NAME = "uc03-mcp-privacy"
PACKAGE_VERSION = "0.2.0"

CURRENT_AUDIT_SEQ: contextvars.ContextVar[int | None] = contextvars.ContextVar(
    "uc03_audit_seq", default=None
)
"""Sequence number of the audit row of the call in progress (set by ``server.py``)."""

LIFECYCLE_CODES: tuple[str, ...] = tuple(stage["code"] for stage in LIFECYCLE_STAGES)

# Personal columns and the UC-02 token type they take when masked. Every address
# part is masked, city, district and region included (user decision 2026-09-06):
# the model tells namesakes apart by company, lifecycle stage and last order, and
# the chat restores the city for the human.
CONTACT_PII: dict[str, str] = {
    "email": "EMAIL",
    "phone": "PHONE",
    "full_street": "ADDRESS",
    "city": "ADDRESS",
    "district": "ADDRESS",
    "region": "ADDRESS",
    "postal_code": "PSC",
    "date_of_birth": "DATE",
    "bank_account": "BBAN",
    "iban": "IBAN_CZ",
}
CONTACT_NAME_COLUMNS: tuple[str, ...] = ("first_name", "last_name", "nickname", "name_vocative")
CONTACT_TEXT_COLUMNS: tuple[str, ...] = ("prior_interactions", "style_excerpt", "frequent_words")
COMPANY_PII: dict[str, str] = {
    "name": "ORG",
    "ico": "ICO",
    "dic": "DIC",
    "full_street": "ADDRESS",
    "city": "ADDRESS",
    "district": "ADDRESS",
    "region": "ADDRESS",
    "postal_code": "PSC",
}

# Scope of the strict profile: what an assistant filing notes needs to see.
STRICT_CONTACT_COLUMNS: tuple[str, ...] = (
    "gender",
    "formal",
    "title",
    "email",
    "phone",
    "full_street",
    "city",
    "postal_code",
    "district",
    "region",
    "lifecycle_stage",
    "purchase_seniority",
    "relationship_warmth",
    "updated_at",
)
# Columns the model may change through update_contact / update_company.
CONTACT_UPDATABLE: tuple[str, ...] = (
    "first_name",
    "last_name",
    "nickname",
    "title",
    "formal",
    "email",
    "phone",
    "full_street",
    "city",
    "postal_code",
    "district",
    "region",
    "lifecycle_stage",
    "company_id",
    "date_of_birth",
    "bank_account",
    "iban",
    "prior_interactions",
)
STRICT_CONTACT_UPDATABLE: tuple[str, ...] = (
    "title",
    "email",
    "phone",
    "full_street",
    "city",
    "postal_code",
    "lifecycle_stage",
    "company_id",
)
COMPANY_UPDATABLE: tuple[str, ...] = (
    "name",
    "ico",
    "dic",
    "full_street",
    "city",
    "postal_code",
    "district",
    "region",
    "legal_form",
)
STRICT_COMPANY_UPDATABLE: tuple[str, ...] = ("full_street", "city", "postal_code", "legal_form")

# query_sql (open profile only): one SELECT, bounded rows, cells and time.
_SQL_SELECT_RE = re.compile(r"^\s*(select|with)\b", re.IGNORECASE)
_FTS_TOKEN_RE = re.compile(r"\w+", re.UNICODE)

MAX_LIMIT = 50
MAX_SQL_ROWS = 200
SQL_DEADLINE_SECONDS = 2.0
SQL_CELL_CHARS = 2000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now_str() -> str:
    """Wall-clock UTC in the format SQLAlchemy stores datetimes with (the wall clock, one format, for live writes)."""
    now = _dt.datetime.now(tz=_dt.timezone.utc).replace(tzinfo=None)
    return now.isoformat(sep=" ", timespec="microseconds")


def _utc_now_iso() -> str:
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------------------
# Matching a query word against a contact (declined names included)
# ---------------------------------------------------------------------------

_SEARCH_FIELDS = ("first_name", "last_name", "email", "phone", "city", "company_name")


def _name_match(word: str, name: str) -> int:
    """How a query word matches one name field: 4 equal, 3 substring, 2 same stem, 1 ending, 0 none.

    Czech declension changes the end of a name ("Petru Bartošovi" for Petr Bartoš,
    "Evě Novákové" for Eva Nováková, "Sedláčkovi" for Sedláček with its fleeting e).
    A dictated or typed query carries the declined form while the database holds
    the nominative, so a plain substring test never finds the contact (lab log
    uc-03, 2026-09-07). Two tolerant paths follow the substring test: the paradigm
    key UC-02 uses to unify the forms of one person (``entity_key``: stem plus paradigm
    class, so Sedláčkovi = Sedláček and Novákové = Nováková while Nováková ≠ Novák), and
    for the names outside those
    paradigms a shared prefix with at most two letters of ending on either side
    (Krejčího → Krejčí, Evě → Eva). Neither path touches e-mail, phone, city or
    employer, which still match as substrings only.
    """
    if not word or not name:
        return 0
    w, n = word.casefold(), name.casefold()
    if w == n:
        return 4
    if w in n:
        return 3
    if entity_key("PERSON", w) == entity_key("PERSON", n):
        return 2
    prefix = 0
    for a, b in zip(w, n):
        if a != b:
            break
        prefix += 1
    if prefix >= 3 and len(w) - prefix <= 2 and len(n) - prefix <= 2:
        return 1
    if prefix == 2 and len(w) <= 4 and len(n) <= 4:
        return 1
    return 0


def _word_score(word: str, row: sqlite3.Row) -> int:
    """The best match of one query word over the searchable fields of a contact row."""
    best = 0
    for field in _SEARCH_FIELDS:
        value = row[field]
        if value is None:
            continue
        if field in ("first_name", "last_name"):
            best = max(best, _name_match(word, str(value)))
        elif word.casefold() in str(value).casefold():
            best = max(best, 3)
    return best


def _clamp(limit: Any, *, default: int = 10, maximum: int = MAX_LIMIT) -> int:
    try:
        value = int(limit)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, maximum))


def _error(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"ok": False, "error": code, "message": message, **extra}


def _checked_arguments(method):
    """Return a tool refusal for invalid tokens, before any database mutation."""

    @wraps(method)
    def checked(*args, **kwargs):
        try:
            return method(*args, **kwargs)
        except TokenValidationError as exc:
            return _error(exc.code, str(exc))

    return checked


def _fts_match_expression(query: str) -> str:
    """Turn free text into a safe FTS5 expression: every word quoted, implicit AND."""
    words = _FTS_TOKEN_RE.findall(query or "")
    return " ".join(f'"{word}"' for word in words)


# ---------------------------------------------------------------------------
# The tools
# ---------------------------------------------------------------------------


class CrmTools:
    """The CRM tool surface for one security profile and one session.

    Args:
        profile: ``open`` / ``masked`` / ``strict``; ``None`` reads ``UC03_SECURITY``.
        db_path: SQLite file; ``None`` reads ``UC03_DB_PATH`` or the substrate default.
        envelope: The session envelope to use under a masking profile; ``None``
            opens the shared session map file (``config.session_map_path()``).
        author: Who writes through this instance; ``None`` reads ``UC03_AUTHOR``.
    """

    def __init__(
        self,
        *,
        profile: str | None = None,
        db_path: str | Path | None = None,
        envelope: SessionEnvelope | None = None,
        author: str | None = None,
    ) -> None:
        self.profile = config.security_profile(profile)
        self.masking = self.profile != "open"
        self.strict = self.profile == "strict"
        self._db_path = Path(db_path).expanduser() if db_path else None
        self.author = (author or config.author()).strip() or "llm"
        # ``SessionEnvelope`` defines ``__len__``, so an empty envelope is falsy:
        # test for None explicitly, never ``envelope or ...``.
        if envelope is not None:
            self.envelope = envelope
        elif self.masking:
            self.envelope = SessionEnvelope(config.session_map_path())
        else:
            self.envelope = None

    # ------------------------------------------------------------------ plumbing

    def db_path(self) -> Path:
        """The SQLite file this instance reads and writes."""
        return self._db_path or config.db_path()

    def _connect(self, *, read_only: bool = False) -> sqlite3.Connection:
        path = self.db_path()
        if not path.exists():
            raise FileNotFoundError(f"UC-03 database not found: {path}")
        if read_only:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            conn.execute("PRAGMA query_only = 1")
        else:
            conn = sqlite3.connect(path)
            conn.execute("PRAGMA foreign_keys = ON")
        conn.row_factory = sqlite3.Row
        return conn

    def _restore(self, value: Any, *, allow_handles: bool = False) -> Any:
        """Resolve session tokens in a tool argument (a no-op under ``open``)."""
        return (
            self.envelope.restore_checked(value, allow_handles=allow_handles)
            if self.masking
            else value
        )

    def _resolve(self, value: Any, kind: str) -> int:
        """Turn a tool argument into a row id: a handle under masking, a plain integer under open."""
        if self.masking:
            return self.envelope.resolve_id(value, kind, allow_raw=False)
        try:
            return int(str(value).strip())
        except (TypeError, ValueError) as exc:
            raise LookupError(f"not a {kind.lower()} id: {value!r}") from exc

    def _ident(self, kind: str, pk: int) -> Any:
        """The id the model sees for a row: the key under ``open``, a handle otherwise."""
        return self.envelope.handle_for(kind, pk) if self.masking else int(pk)

    def _mask(self, pii_type: str, value: Any, entity: tuple[str, int] | None = None) -> Any:
        return self.envelope.mask_value(pii_type, value, entity=entity) if self.masking else value

    def _mask_text(self, text: Any) -> Any:
        if not self.masking or not isinstance(text, str):
            return text
        return self.envelope.mask_text(text)

    def _audit_seq(self) -> int | None:
        return CURRENT_AUDIT_SEQ.get()

    @staticmethod
    def _same_stamp(expected: Any, current: Any) -> bool:
        """True when the model's ``expected_updated_at`` names the row's current ``updated_at``."""
        if expected is None or str(expected).strip().lower() in ("", "null", "none"):
            return current is None
        return current is not None and str(expected).strip() == str(current)

    def _field_view(self, entity: str, pk: int, column: str, value: Any) -> Any:
        """One field as the model may see it under the current profile (for stale answers)."""
        if not self.masking or value is None:
            return value
        if entity == "contact":
            if column in CONTACT_NAME_COLUMNS:
                return self._mask("PERSON", value, ("CONTACT", pk))
            if column in CONTACT_PII:
                return self._mask(CONTACT_PII[column], value, ("CONTACT", pk))
            if column in CONTACT_TEXT_COLUMNS:
                return self._mask_text(value)
            if column == "company_id":
                return self._ident("COMPANY", int(value))
            return value
        if entity == "company":
            if column in COMPANY_PII:
                return self._mask(COMPANY_PII[column], value, ("COMPANY", pk))
            return value
        if entity == "note" and column == "content":
            return self._mask_text(value)
        return value

    def _stale(self, entity: str, pk: int, column: str, current_value: Any, current_stamp: Any):
        """The refusal for a write whose ``expected_updated_at`` no longer matches the row."""
        try:
            view = self._field_view(entity, pk, column, current_value)
        except EnvelopeUnavailable as exc:
            return _error("envelope_unavailable", str(exc))
        return _error(
            "stale",
            "the record changed since it was read; show the current value to the user and "
            "retry with the current updated_at if they still want the change",
            field=column,
            current_value=view,
            current_updated_at=current_stamp,
        )

    # ------------------------------------------------------------------ record shaping

    def _contact_record(self, row: sqlite3.Row) -> dict[str, Any]:
        """One contact as the model may see it under the current profile."""
        data = dict(row)
        company_name = data.pop("company_name", None)
        company_id = data.get("company_id")
        pk = int(data["id"])
        entity = ("CONTACT", pk)
        full_name = " ".join(
            part for part in (data.get("first_name"), data.get("last_name")) if part
        )

        if not self.masking:
            data["name"] = full_name
            data["company"] = company_name
            data["company_id"] = company_id
            return data

        record: dict[str, Any] = {
            "id": self._ident("CONTACT", pk),
            "name": self._mask("PERSON", full_name, entity),
        }
        if not self.strict:
            record["name_vocative"] = self._mask("PERSON", data.get("name_vocative"), entity)
            record["nickname"] = self._mask("PERSON", data.get("nickname"), entity)
        columns = (
            STRICT_CONTACT_COLUMNS
            if self.strict
            else tuple(
                key
                for key in data
                if key not in ("id", "company_id", "company_name")
                and key not in CONTACT_NAME_COLUMNS
            )
        )
        for column in columns:
            value = data.get(column)
            if column in CONTACT_PII:
                record[column] = self._mask(CONTACT_PII[column], value, entity)
            elif column in CONTACT_TEXT_COLUMNS:
                record[column] = self._mask_text(value)
            else:
                record[column] = value
        if company_id is not None:
            record["company_id"] = self._ident("COMPANY", int(company_id))
            record["company"] = self._mask("ORG", company_name, ("COMPANY", int(company_id)))
        else:
            record["company_id"] = None
            record["company"] = None
        return record

    def _contact_summary(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        pk = int(data["id"])
        full_name = " ".join(
            part for part in (data.get("first_name"), data.get("last_name")) if part
        )
        company_id = data.get("company_id")
        summary = {
            "id": self._ident("CONTACT", pk),
            "name": self._mask("PERSON", full_name, ("CONTACT", pk)),
            "company_id": (
                self._ident("COMPANY", int(company_id)) if company_id is not None else None
            ),
            "company": (
                self._mask("ORG", data.get("company_name"), ("COMPANY", int(company_id)))
                if company_id is not None
                else None
            ),
            "city": self._mask("ADDRESS", data.get("city"), ("CONTACT", pk)),
            "lifecycle_stage": data.get("lifecycle_stage"),
            "note_count": int(data.get("note_count") or 0),
            "last_order_date": data.get("last_order_date"),
            "updated_at": data.get("updated_at"),
        }
        return summary

    def _note_record(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        pk = int(data["id"])
        contact_pk = int(data["contact_id"])
        record = {
            "id": self._ident("NOTE", pk),
            "contact_id": self._ident("CONTACT", contact_pk),
            "content": self._mask_text(data.get("content")),
            "category": data.get("category"),
            "created_at": data.get("created_at"),
            "author": data.get("author"),
            "updated_at": data.get("updated_at"),
        }
        if "first_name" in data:
            full_name = " ".join(
                part for part in (data.get("first_name"), data.get("last_name")) if part
            )
            record["contact"] = self._mask("PERSON", full_name, ("CONTACT", contact_pk))
        return record

    def _company_record(self, row: sqlite3.Row) -> dict[str, Any]:
        data = dict(row)
        pk = int(data["id"])
        entity = ("COMPANY", pk)
        if not self.masking:
            return data
        record: dict[str, Any] = {"id": self._ident("COMPANY", pk)}
        for column, value in data.items():
            if column == "id":
                continue
            if column in COMPANY_PII:
                record[column] = self._mask(COMPANY_PII[column], value, entity)
            else:
                record[column] = value
        return record

    # ------------------------------------------------------------------ infrastructure tools

    def ping(self, message: str = "ping") -> dict[str, Any]:
        """Round-trip liveness check; echoes the message with the server time and PID."""
        return {
            "echo": message,
            "ts": _utc_now_iso(),
            "pid": os.getpid(),
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
        }

    def server_info(self) -> dict[str, Any]:
        """Static and runtime metadata: package, Python, platform, security profile, tools."""
        return {
            "package": PACKAGE_NAME,
            "version": PACKAGE_VERSION,
            "ts": _utc_now_iso(),
            "python": sys.version.split()[0],
            "platform": platform.platform(),
            "security_profile": self.profile,
            "masking": self.masking,
            "tools_registered": list(TOOL_NAMES),
        }

    def whoami(self) -> str:
        """One-line identity string of the server."""
        return f"{PACKAGE_NAME} {PACKAGE_VERSION} ({self.profile} profile)"

    # ------------------------------------------------------------------ reads

    @_checked_arguments
    def search_contacts(
        self, query: str, company: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Find contacts by name, e-mail, phone, city or employer.

        Every word of ``query`` must match one contact field: as a substring (so
        "Emily Nováková" and "Nováková Brno" both work), or, for the first and last
        name, as a declined form of it ("Petru Bartošovi" finds Petr Bartoš, "Evě
        Novákové" finds Eva Nováková; see ``_name_match``). ``company`` narrows to an
        employer name. Session tokens in either argument are resolved first. The
        strongest matches come first: substring before stem before ending tolerance.
        """
        limit = _clamp(limit)
        words = [w for w in str(self._restore(query) or "").split() if w]
        company_needle = str(self._restore(company) or "").strip()
        if not words and not company_needle:
            return {"ok": True, "count": 0, "contacts": []}

        params: list[Any] = []
        where = "1 = 1"
        if company_needle:
            where = "co.name LIKE ?"
            params.append(f"%{company_needle}%")
        sql = f"""
            SELECT c.id, c.first_name, c.last_name, c.email, c.phone, c.city,
                   c.lifecycle_stage, c.company_id, c.updated_at, co.name AS company_name,
                   (SELECT COUNT(*) FROM uc_notes n WHERE n.contact_id = c.id) AS note_count,
                   (SELECT MAX(o.order_date) FROM uc_orders o WHERE o.contact_id = c.id)
                       AS last_order_date
            FROM uc_contacts c
            LEFT JOIN uc_companies co ON co.id = c.company_id
            WHERE {where}
            ORDER BY c.last_name, c.first_name, c.id
        """
        with self._connect(read_only=True) as conn:
            candidates = conn.execute(sql, params).fetchall()
        scored: list[tuple[int, sqlite3.Row]] = []
        for row in candidates:
            total = 0
            for word in words:
                score = _word_score(word, row)
                if not score:
                    break
                total += score
            else:
                scored.append((total, row))
        scored.sort(
            key=lambda item: (-item[0], item[1]["last_name"], item[1]["first_name"], item[1]["id"])
        )
        rows = [row for _, row in scored[:limit]]
        return {
            "ok": True,
            "count": len(rows),
            "contacts": [self._contact_summary(row) for row in rows],
        }

    def get_contact(
        self, contact_id: str, include_notes: bool = True, note_limit: int = 10
    ) -> dict[str, Any]:
        """Return one contact record with the employer name and, optionally, recent notes."""
        try:
            pk = self._resolve(contact_id, "CONTACT")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        note_limit = _clamp(note_limit)
        with self._connect(read_only=True) as conn:
            row = conn.execute(
                """
                SELECT c.*, co.name AS company_name
                FROM uc_contacts c
                LEFT JOIN uc_companies co ON co.id = c.company_id
                WHERE c.id = ?
                """,
                (pk,),
            ).fetchone()
            if row is None:
                return _error("not_found", "no contact with that id")
            notes: list[dict[str, Any]] = []
            if include_notes:
                note_rows = conn.execute(
                    """
                    SELECT id, contact_id, content, category, created_at, author, updated_at
                    FROM uc_notes WHERE contact_id = ?
                    ORDER BY created_at DESC, id DESC LIMIT ?
                    """,
                    (pk, note_limit),
                ).fetchall()
                notes = [self._note_record(n) for n in note_rows]
        try:
            contact = self._contact_record(row)
        except EnvelopeUnavailable as exc:
            return _error("envelope_unavailable", str(exc))
        return {"ok": True, "contact": contact, "notes": notes}

    def get_company(self, company_id: str, contact_limit: int = 20) -> dict[str, Any]:
        """Return one company with its identifiers, address and the contacts employed there."""
        try:
            pk = self._resolve(company_id, "COMPANY")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        contact_limit = _clamp(contact_limit)
        with self._connect(read_only=True) as conn:
            row = conn.execute("SELECT * FROM uc_companies WHERE id = ?", (pk,)).fetchone()
            if row is None:
                return _error("not_found", "no company with that id")
            people = conn.execute(
                """
                SELECT c.id, c.first_name, c.last_name, c.city, c.lifecycle_stage, c.company_id,
                       c.updated_at, co.name AS company_name,
                       (SELECT COUNT(*) FROM uc_notes n WHERE n.contact_id = c.id) AS note_count,
                       NULL AS last_order_date
                FROM uc_contacts c LEFT JOIN uc_companies co ON co.id = c.company_id
                WHERE c.company_id = ? ORDER BY c.last_name, c.first_name LIMIT ?
                """,
                (pk, contact_limit),
            ).fetchall()
        return {
            "ok": True,
            "company": self._company_record(row),
            "contacts": [self._contact_summary(p) for p in people],
        }

    @_checked_arguments
    def search_notes(
        self, query: str | None = None, contact_id: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Search notes by text and/or contact, newest first."""
        limit = _clamp(limit)
        clauses: list[str] = []
        params: list[Any] = []
        text = str(self._restore(query) or "").strip()
        if text:
            clauses.append("n.content LIKE ?")
            params.append(f"%{text}%")
        if contact_id not in (None, ""):
            try:
                params.append(self._resolve(contact_id, "CONTACT"))
            except LookupError as exc:
                return _error("bad_id", str(exc))
            clauses.append("n.contact_id = ?")
        where = " AND ".join(clauses) if clauses else "1 = 1"
        with self._connect(read_only=True) as conn:
            rows = conn.execute(
                f"""
                SELECT n.id, n.contact_id, n.content, n.category, n.created_at, n.author,
                       n.updated_at, c.first_name, c.last_name
                FROM uc_notes n JOIN uc_contacts c ON c.id = n.contact_id
                WHERE {where}
                ORDER BY n.created_at DESC, n.id DESC LIMIT ?
                """,
                (*params, limit),
            ).fetchall()
        try:
            notes = [self._note_record(row) for row in rows]
        except EnvelopeUnavailable as exc:
            return _error("envelope_unavailable", str(exc))
        return {"ok": True, "count": len(notes), "notes": notes}

    @_checked_arguments
    def search_reviews(
        self, query: str, contact_id: str | None = None, limit: int = 10
    ) -> dict[str, Any]:
        """Full-text search over the customers' product reviews (Czech and English).

        ``query`` is plain words; all must occur. Narrow to one customer with
        ``contact_id``. Returns the product, rating, date and the review text.
        """
        limit = _clamp(limit)
        expression = _fts_match_expression(str(self._restore(query) or ""))
        if not expression:
            return {"ok": True, "count": 0, "reviews": []}
        params: list[Any] = [expression]
        contact_clause = ""
        if contact_id not in (None, ""):
            try:
                params.append(self._resolve(contact_id, "CONTACT"))
            except LookupError as exc:
                return _error("bad_id", str(exc))
            contact_clause = "AND r.contact_id = ?"
        params.append(limit)
        with self._connect(read_only=True) as conn:
            rows = conn.execute(
                f"""
                SELECT r.id, r.contact_id, r.rating, r.review_date,
                       COALESCE(r.summary_cs, r.summary_en) AS summary,
                       COALESCE(r.text_cs, r.text_en) AS text,
                       p.name_cs AS product, p.name AS product_en, c.first_name, c.last_name
                FROM {REVIEWS_FTS_TABLE} f
                JOIN uc_reviews r ON r.id = f.rowid
                JOIN uc_products p ON p.id = r.product_id
                JOIN uc_contacts c ON c.id = r.contact_id
                WHERE {REVIEWS_FTS_TABLE} MATCH ? {contact_clause}
                ORDER BY r.review_date DESC LIMIT ?
                """,
                params,
            ).fetchall()
        reviews = []
        try:
            for row in rows:
                data = dict(row)
                contact_pk = int(data["contact_id"])
                full_name = " ".join(
                    part for part in (data.get("first_name"), data.get("last_name")) if part
                )
                reviews.append(
                    {
                        "contact_id": self._ident("CONTACT", contact_pk),
                        "contact": self._mask("PERSON", full_name, ("CONTACT", contact_pk)),
                        "product": data.get("product") or data.get("product_en"),
                        "rating": data.get("rating"),
                        "review_date": data.get("review_date"),
                        "summary": self._mask_text(data.get("summary")),
                        "text": self._mask_text(data.get("text")),
                    }
                )
        except EnvelopeUnavailable as exc:
            return _error("envelope_unavailable", str(exc))
        return {"ok": True, "count": len(reviews), "reviews": reviews}

    def list_orders(self, contact_id: str, limit: int = 20) -> dict[str, Any]:
        """List a customer's purchases, newest first: product, quantity, unit price, date."""
        try:
            pk = self._resolve(contact_id, "CONTACT")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        limit = _clamp(limit)
        with self._connect(read_only=True) as conn:
            rows = conn.execute(
                """
                SELECT o.order_date, o.quantity, o.unit_price, p.name_cs AS product,
                       p.name AS product_en, p.category
                FROM uc_orders o JOIN uc_products p ON p.id = o.product_id
                WHERE o.contact_id = ? ORDER BY o.order_date DESC, o.id DESC LIMIT ?
                """,
                (pk, limit),
            ).fetchall()
        orders = [
            {
                "order_date": r["order_date"],
                "product": r["product"] or r["product_en"],
                "category": r["category"],
                "quantity": r["quantity"],
                "unit_price": r["unit_price"],
            }
            for r in rows
        ]
        return {
            "ok": True,
            "contact_id": self._ident("CONTACT", pk),
            "count": len(orders),
            "orders": orders,
        }

    def query_sql(self, sql: str, limit: int = 50) -> dict[str, Any]:
        """Run one read-only SELECT against the CRM database (open profile only).

        A column-name policy cannot mask arbitrary SQL (aliases, expressions,
        joins and unions defeat it), so under ``masked`` and ``strict`` the tool
        answers ``disabled`` instead of pretending. Under ``open`` the statement
        runs on a read-only connection, at most ``limit`` rows come back, cells
        longer than ``SQL_CELL_CHARS`` are cut and the query is interrupted after
        ``SQL_DEADLINE_SECONDS``.
        """
        if self.masking:
            return _error("disabled", "query_sql is available in the open profile only")
        statement = str(sql or "").strip().rstrip(";")
        if not _SQL_SELECT_RE.match(statement) or ";" in statement:
            return _error("not_a_select", "only a single SELECT statement is allowed")
        limit = _clamp(limit, default=50, maximum=MAX_SQL_ROWS)
        deadline = time.monotonic() + SQL_DEADLINE_SECONDS
        try:
            with self._connect(read_only=True) as conn:
                conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 2000)
                cur = conn.execute(f"SELECT * FROM ({statement}) LIMIT ?", (limit,))
                columns = [d[0] for d in cur.description]
                rows = [dict(zip(columns, r)) for r in cur.fetchall()]
        except sqlite3.OperationalError as exc:
            if "interrupted" in str(exc).lower():
                return _error("timeout", f"query stopped after {SQL_DEADLINE_SECONDS:g} s")
            return _error("sql_error", str(exc))
        except sqlite3.Error as exc:
            return _error("sql_error", str(exc))
        for row in rows:
            for column, value in row.items():
                if isinstance(value, str) and len(value) > SQL_CELL_CHARS:
                    row[column] = value[:SQL_CELL_CHARS] + "…"
                elif isinstance(value, bytes):
                    row[column] = f"<{len(value)} bytes>"
        return {"ok": True, "columns": columns, "count": len(rows), "rows": rows}

    # ------------------------------------------------------------------ writes: notes

    @_checked_arguments
    def create_note(
        self, contact_id: str, content: str, category: str | None = None
    ) -> dict[str, Any]:
        """File a note on a contact.

        Session tokens in ``content`` are restored before the row is written, so
        the database holds the real values while the model only ever handled
        tokens. ``category`` must be one of the note categories; when omitted the
        categoriser assigns one from the masked text. The row records who wrote
        it (``author``) and the audit sequence number of this call.
        """
        try:
            pk = self._resolve(contact_id, "CONTACT")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        received = str(content or "").strip()
        if not received:
            return _error("empty_content", "content must not be empty")
        chosen = self._validate_category(category)
        if isinstance(chosen, dict):
            return chosen
        body = str(self._restore(received))
        categorization = None
        if chosen is None:
            try:
                for_categoriser = self._mask_text(body) if self.masking else body
            except EnvelopeUnavailable as exc:
                return _error("envelope_unavailable", str(exc))
            categorization = categorize_text(for_categoriser)
            chosen = categorization.category
        now = _now_str()
        with self._connect() as conn:
            if conn.execute("SELECT 1 FROM uc_contacts WHERE id = ?", (pk,)).fetchone() is None:
                return _error("not_found", "no contact with that id")
            cur = conn.execute(
                """
                INSERT INTO uc_notes
                    (contact_id, content, category, created_at, pseudonymized, author, audit_seq)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (pk, body, chosen, now, int(self.masking), self.author, self._audit_seq()),
            )
            conn.commit()
            note_pk = int(cur.lastrowid)
        return {
            "ok": True,
            "note_id": self._ident("NOTE", note_pk),
            "contact_id": self._ident("CONTACT", pk),
            "category": chosen,
            "categorization": categorization.to_dict() if categorization else None,
            "created_at": now,
            "author": self.author,
            "audit_seq": self._audit_seq(),
            "updated_at": None,
        }

    @_checked_arguments
    def update_note(
        self,
        note_id: str,
        expected_updated_at: str | None,
        content: str | None = None,
        category: str | None = None,
    ) -> dict[str, Any]:
        """Change the text and/or category of a note the model has read.

        ``expected_updated_at`` is the note's ``updated_at`` as returned by the
        server (``null`` for a note never edited). A different current value
        means someone changed the note in between: the answer is ``stale`` with
        the current content, nothing is written.
        """
        try:
            pk = self._resolve(note_id, "NOTE")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        new_body = str(self._restore(str(content).strip())) if content else None
        chosen = self._validate_category(category) if category is not None else None
        if isinstance(chosen, dict):
            return chosen
        if new_body is None and chosen is None:
            return _error("nothing_to_change", "pass content and/or category")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, content, category, updated_at FROM uc_notes WHERE id = ?", (pk,)
            ).fetchone()
            if row is None:
                return _error("not_found", "no note with that id")
            if not self._same_stamp(expected_updated_at, row["updated_at"]):
                return self._stale("note", pk, "content", row["content"], row["updated_at"])
            stamp = _now_str()
            changes: list[tuple[str, Any, Any]] = []
            if new_body is not None and new_body != row["content"]:
                changes.append(("content", row["content"], new_body))
            if chosen is not None and chosen != row["category"]:
                changes.append(("category", row["category"], chosen))
            for field, old, new in changes:
                conn.execute(
                    f"UPDATE uc_notes SET {field} = ?, updated_at = ? WHERE id = ?",
                    (new, stamp, pk),
                )
                self._log_change(
                    conn,
                    "note",
                    pk,
                    field,
                    old,
                    new,
                    applied=True,
                    entity_updated_at=row["updated_at"],
                )
            conn.commit()
        return {
            "ok": True,
            "note_id": self._ident("NOTE", pk),
            "changed": [field for field, _, _ in changes],
            "updated_at": stamp if changes else row["updated_at"],
        }

    def delete_note(self, note_id: str, expected_updated_at: str | None) -> dict[str, Any]:
        """Delete a note the model has read; its text stays in the change log.

        Same rule as ``update_note``: a stale ``expected_updated_at`` is refused
        with the current content.
        """
        try:
            pk = self._resolve(note_id, "NOTE")
        except LookupError as exc:
            return _error("bad_id", str(exc))
        with self._connect() as conn:
            row = conn.execute(
                "SELECT id, content, updated_at FROM uc_notes WHERE id = ?", (pk,)
            ).fetchone()
            if row is None:
                return _error("not_found", "no note with that id")
            if not self._same_stamp(expected_updated_at, row["updated_at"]):
                return self._stale("note", pk, "content", row["content"], row["updated_at"])
            conn.execute("DELETE FROM uc_notes WHERE id = ?", (pk,))
            self._log_change(
                conn,
                "note",
                pk,
                "deleted",
                row["content"],
                None,
                applied=True,
                entity_updated_at=row["updated_at"],
            )
            conn.commit()
        return {"ok": True, "note_id": self._ident("NOTE", pk), "deleted": True}

    def _validate_category(self, category: str | None) -> str | None | dict[str, Any]:
        if category is None or str(category).strip() == "":
            return None
        value = str(category).strip().lower()
        if value not in NOTE_CATEGORIES:
            return _error("bad_category", f"category must be one of {', '.join(NOTE_CATEGORIES)}")
        return value

    # ------------------------------------------------------------------ writes: fields

    @_checked_arguments
    def update_contact(
        self, contact_id: str, field: str, value: str, expected_updated_at: str | None
    ) -> dict[str, Any]:
        """Change one field of a contact the model has read.

        ``expected_updated_at`` is the contact's ``updated_at`` as returned by
        ``search_contacts`` / ``get_contact`` (``null`` for a row never written
        through the server). When the row moved since, the answer is ``stale``
        with the current value of the field, nothing is written. Under ``open``
        and ``masked`` a matching stamp applies the change and logs it; under
        ``strict`` it records the change for a human reviewer (``pending_review``).
        Tokens in ``value`` are restored first.
        """
        return self._update_field("contact", contact_id, field, value, expected_updated_at)

    @_checked_arguments
    def update_company(
        self, company_id: str, field: str, value: str, expected_updated_at: str | None
    ) -> dict[str, Any]:
        """Change one field of a company; same stamp and review rules as ``update_contact``."""
        return self._update_field("company", company_id, field, value, expected_updated_at)

    def _update_field(
        self, entity: str, ident: Any, field: str, value: Any, expected_updated_at: Any
    ) -> dict[str, Any]:
        kind = "CONTACT" if entity == "contact" else "COMPANY"
        table = "uc_contacts" if entity == "contact" else "uc_companies"
        if self.strict:
            allowed = STRICT_CONTACT_UPDATABLE if entity == "contact" else STRICT_COMPANY_UPDATABLE
        else:
            allowed = CONTACT_UPDATABLE if entity == "contact" else COMPANY_UPDATABLE
        try:
            pk = self._resolve(ident, kind)
        except LookupError as exc:
            return _error("bad_id", str(exc))
        column = str(field or "").strip().lower()
        if column not in allowed:
            return _error("bad_field", f"field must be one of {', '.join(allowed)}")
        new_value: Any = self._restore(value, allow_handles=column == "company_id")
        if isinstance(new_value, str):
            new_value = new_value.strip()
        try:
            new_value = self._coerce_field(entity, column, new_value)
        except (ValueError, LookupError) as exc:
            return _error("bad_value", str(exc))
        with self._connect() as conn:
            row = conn.execute(
                f"SELECT {column}, updated_at FROM {table} WHERE id = ?", (pk,)
            ).fetchone()
            if row is None:
                return _error("not_found", f"no {entity} with that id")
            old_value, current_stamp = row[0], row[1]
            if not self._same_stamp(expected_updated_at, current_stamp):
                return self._stale(entity, pk, column, old_value, current_stamp)
            if column == "company_id" and new_value is not None:
                exists = conn.execute("SELECT 1 FROM uc_companies WHERE id = ?", (new_value,))
                if exists.fetchone() is None:
                    return _error("bad_value", "no company with that id")
            if self.strict:
                change_id = self._log_change(
                    conn,
                    entity,
                    pk,
                    column,
                    old_value,
                    new_value,
                    applied=False,
                    entity_updated_at=current_stamp,
                )
                conn.commit()
                return {
                    "ok": True,
                    "status": "pending_review",
                    "change_id": change_id,
                    f"{entity}_id": self._ident(kind, pk),
                    "field": column,
                    "updated_at": current_stamp,
                    "message": "recorded; a person applies or rejects it in the review queue",
                }
            stamp = _now_str()
            try:
                conn.execute(
                    f"UPDATE {table} SET {column} = ?, updated_at = ? WHERE id = ?",
                    (new_value, stamp, pk),
                )
            except sqlite3.IntegrityError as exc:
                conn.rollback()
                return _error("bad_value", f"the database refused the value: {exc}")
            change_id = self._log_change(
                conn,
                entity,
                pk,
                column,
                old_value,
                new_value,
                applied=True,
                entity_updated_at=current_stamp,
            )
            conn.commit()
        return {
            "ok": True,
            "status": "applied",
            "change_id": change_id,
            f"{entity}_id": self._ident(kind, pk),
            "field": column,
            "updated_at": stamp,
        }

    def _coerce_field(self, entity: str, column: str, value: Any) -> Any:
        """Type and vocabulary checks before a value reaches the row."""
        if column == "lifecycle_stage":
            if str(value) not in LIFECYCLE_CODES:
                raise ValueError(f"lifecycle_stage must be one of {', '.join(LIFECYCLE_CODES)}")
            return str(value)
        if column == "formal":
            text = str(value).strip().lower()
            if text in ("1", "true", "yes", "vy"):
                return 1
            if text in ("0", "false", "no", "ty"):
                return 0
            raise ValueError("formal must be true/false")
        if column == "company_id":
            if value in (None, "", "null"):
                return None
            return self._resolve(value, "COMPANY")
        if column == "date_of_birth":
            _dt.date.fromisoformat(str(value))
            return str(value)
        if value == "":
            return None
        return value

    def _log_change(
        self,
        conn: sqlite3.Connection,
        entity: str,
        pk: int,
        field: str,
        old: Any,
        new: Any,
        *,
        applied: bool,
        entity_updated_at: Any = None,
    ) -> int:
        cur = conn.execute(
            """
            INSERT INTO uc_change_log
                (entity_type, entity_id, field, old_value, new_value, author, audit_seq,
                 created_at, entity_updated_at, applied)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entity,
                pk,
                field,
                None if old is None else str(old),
                None if new is None else str(new),
                self.author,
                self._audit_seq(),
                _now_str(),
                entity_updated_at,
                int(applied),
            ),
        )
        return int(cur.lastrowid)

    # ------------------------------------------------------------------ review queue (CLI side)

    def pending_changes(self) -> list[dict[str, Any]]:
        """Held changes not yet reviewed, each with the field's current value and stamp.

        Clear values: this is the local, human side of the queue.
        """
        tables = {"contact": "uc_contacts", "company": "uc_companies", "note": "uc_notes"}
        with self._connect(read_only=True) as conn:
            rows = [
                dict(r)
                for r in conn.execute(
                    "SELECT * FROM uc_change_log WHERE applied = 0 AND review_outcome IS NULL "
                    "ORDER BY id"
                ).fetchall()
            ]
            for row in rows:
                current = conn.execute(
                    f"SELECT {row['field']}, updated_at FROM {tables[row['entity_type']]} "
                    "WHERE id = ?",
                    (row["entity_id"],),
                ).fetchone()
                row["current_value"] = None if current is None else current[0]
                row["current_updated_at"] = None if current is None else current[1]
                row["still_current"] = current is not None and (
                    current[1] == row["entity_updated_at"]
                )
        return rows

    def review_change(self, change_id: int, outcome: str) -> dict[str, Any]:
        """Apply or reject one held change (``outcome`` = ``applied`` / ``rejected``).

        Applying requires the entity's ``updated_at`` to be the one the model read
        when it asked (``entity_updated_at``); the stamp moves on every write, so
        it is the only guard needed. Otherwise the row is closed as ``conflict``
        with the current value, and nothing is written to the entity.
        """
        if outcome not in ("applied", "rejected"):
            raise ValueError("outcome must be 'applied' or 'rejected'")
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM uc_change_log WHERE id = ?", (int(change_id),)
            ).fetchone()
            if row is None:
                return _error("not_found", "no change with that id")
            if row["review_outcome"] is not None or row["applied"]:
                return _error("already_reviewed", "this change was reviewed already")
            table = {"contact": "uc_contacts", "company": "uc_companies"}[row["entity_type"]]
            if outcome == "applied":
                current = conn.execute(
                    f"SELECT {row['field']}, updated_at FROM {table} WHERE id = ?",
                    (row["entity_id"],),
                ).fetchone()
                if current is None or current[1] != row["entity_updated_at"]:
                    conn.execute(
                        "UPDATE uc_change_log SET review_outcome = 'conflict', reviewed_at = ? "
                        "WHERE id = ?",
                        (_now_str(), int(change_id)),
                    )
                    conn.commit()
                    return _error(
                        "conflict",
                        "the entity changed after the request was recorded; nothing applied",
                        requested_old=row["old_value"],
                        requested_new=row["new_value"],
                        current=None if current is None else current[0],
                        current_updated_at=None if current is None else current[1],
                        change_id=int(change_id),
                    )
                conn.execute(
                    f"UPDATE {table} SET {row['field']} = ?, updated_at = ? "
                    "WHERE id = ? AND updated_at IS ?",
                    (row["new_value"], _now_str(), row["entity_id"], current[1]),
                )
            conn.execute(
                """
                UPDATE uc_change_log
                SET applied = ?, review_outcome = ?, reviewed_at = ? WHERE id = ?
                """,
                (int(outcome == "applied"), outcome, _now_str(), int(change_id)),
            )
            conn.commit()
        return {"ok": True, "change_id": int(change_id), "outcome": outcome}


# The tool surface in the order the server registers it (and the manifest lists it).
TOOL_NAMES: tuple[str, ...] = (
    "ping",
    "server_info",
    "whoami",
    "search_contacts",
    "get_contact",
    "get_company",
    "search_notes",
    "search_reviews",
    "list_orders",
    "query_sql",
    "create_note",
    "update_note",
    "delete_note",
    "update_contact",
    "update_company",
)


__all__ = [
    "CONTACT_PII",
    "COMPANY_PII",
    "CURRENT_AUDIT_SEQ",
    "CrmTools",
    "PACKAGE_NAME",
    "PACKAGE_VERSION",
    "STRICT_CONTACT_COLUMNS",
    "TOOL_NAMES",
]
