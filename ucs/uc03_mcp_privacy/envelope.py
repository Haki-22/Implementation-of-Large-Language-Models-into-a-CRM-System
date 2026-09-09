"""Session envelope: UC-02's masking applied at the MCP boundary of UC-03.

What it is for
--------------
The MCP server hands data from the CRM database to whatever language model is
the MCP host and takes the model's tool arguments back. Under the ``masked``
and ``strict`` security profiles nothing personal crosses that boundary in
clear: every personal value the server sends out is replaced by a token, every
token the model sends back is resolved by the server. The chat client applies
the same envelope to the human's own turn, so the model can refer to a person
it has never seen by name.

One session, one map
--------------------
A ``SessionEnvelope`` holds the token <-> value map of one chat session. The
server and the chat client share it through a small JSON file
(``config.session_map_path()``): the client masks the human's turn and saves,
the server loads, adds the tokens it mints for tool results, saves again, and
the client restores the answer for the human. The file lives next to the audit
log and never leaves the machine (chapter 5: the map is held locally).

Several processes may mint tokens into one map (a server and its chat client,
two servers of one bridge session). Every mutation therefore runs as one
critical section under a cross-process file lock (``<path>.lock``): reload the
file, allocate, write atomically, release. No update is lost and no number is
allocated twice.

Three kinds of token
--------------------
- **Value tokens** ``<TYPE_n>`` for personal values. The vocabulary and the
  unification rule are UC-02's: one number per entity, a letter suffix per
  distinct surface form (``<PERSON_412>`` is "Jan Novák", ``<PERSON_412b>`` is
  "Novákovi"), so every token restores to exactly the text it replaced.
  Structured columns are masked by schema (``mask_value``, the caller names the
  type and, when it knows it, the row the value belongs to); free text is masked
  by the UC-02 detector (``mask_text``).
- **Handles** ``<CONTACT_n>``, ``<COMPANY_n>``, ``<NOTE_n>`` for row ids. A
  database key is a stable pseudonym, so the model gets a per-session random
  handle instead and the server resolves it (``resolve_id``).
- Numbers are random (UC-02's ``RANDOM_ID_RANGE``) and unique across the whole
  session, so a number leaks neither the order of mentions nor the row id.

Fail closed
-----------
``mask_text`` needs the UC-02 NER layer. When it cannot run,
``EnvelopeUnavailable`` is raised and the caller refuses the operation; the
envelope never degrades to rules alone by itself.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import random
import re
import threading
import uuid
from pathlib import Path
from typing import Any, Callable

from ucs.uc02_pseudonymization.code.ner import NerBackendError, detect_ner
from ucs.uc02_pseudonymization.code.pseudonymizer import (
    RANDOM_ID_RANGE,
    _form_suffix as form_suffix,  # UC-02 keeps it private; one definition, not a copy
    detect_rule_based,
    entity_key,
    merge_spans,
)

# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

DetectorFn = Callable[[str], list[dict[str, Any]]]

HANDLE_KINDS: tuple[str, ...] = ("CONTACT", "COMPANY", "NOTE")
"""Row kinds that get a handle instead of their database id."""

TOKEN_RE = re.compile(r"<([A-Z][A-Z_]*?)_(\d{1,4})([a-z]*)>")
"""Shape of every token and handle the envelope mints."""

SESSION_MAP_VERSION = 1

# Decode token delimiters only, with at most one extra HTML-encoding layer.
# Literal HTML and ampersands elsewhere in a note belong to its author.
_TOKEN_ENCODING_RE = re.compile(
    r"(?:<|&(?:amp;)?(?:lt|#0*60|#x0*3[cC]);)"
    r"([A-Z][A-Z_]*?_\d{1,4}[a-z]*)"
    r"(?:>|&(?:amp;)?(?:gt|#0*62|#x0*3[eE]);)"
)
_TOKEN_HINT_RE = re.compile(
    r"(?:EMAIL|PHONE|ICO|DIC|RC|IBAN_CZ|BBAN|PSC|PERSON|ORG|ADDRESS|DATE|CONTACT|COMPANY|NOTE)"
    r"[\s\u200b-\u200f]*_[\s\u200b-\u200f]*\d",
    re.I,
)


class TokenValidationError(ValueError):
    """A model supplied an unknown, damaged, or inappropriate session token."""

    def __init__(self, code: str, message: str) -> None:
        """Store the machine-readable `code` a tool can return, alongside `message`."""
        super().__init__(message)
        self.code = code


class EnvelopeUnavailable(RuntimeError):
    """The UC-02 masking layer cannot run; the operation must be refused (fail closed)."""


def uc02_detector(text: str) -> list[dict[str, Any]]:
    """UC-02's rules + NER layer, merged into one span list.

    Raises ``EnvelopeUnavailable`` when the NER backend cannot load or run.
    The rules alone are never used as a fallback here.
    """
    try:
        ner_spans = detect_ner(text)
    except NerBackendError as exc:
        raise EnvelopeUnavailable(f"UC-02 NER layer unavailable: {exc}") from exc
    return merge_spans(detect_rule_based(text), ner_spans, text)


# ---------------------------------------------------------------------------
# The session envelope
# ---------------------------------------------------------------------------


class SessionEnvelope:
    """Token <-> value map of one chat session, shared by the server and the chat client.

    Args:
        path: JSON file the map is loaded from and saved to after every change.
            ``None`` keeps the map in memory only (tests).
        detector: Span detector for ``mask_text``; defaults to UC-02's rules + NER.
        rng: Random source for token numbers; pass a seeded one for reproducible tests.
    """

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        detector: DetectorFn | None = None,
        rng: random.Random | None = None,
    ) -> None:
        """Create the map (see the class docstring for `path` / `detector` / `rng`); loads `path` if it exists."""
        self.path = Path(path).expanduser() if path else None
        self._detector = detector or uc02_detector
        self._rng = rng or random.Random()
        self._lock = threading.RLock()
        self._value_by_token: dict[str, str] = {}
        self._number_by_entity: dict[str, int] = {}
        self._forms_by_entity: dict[str, list[str]] = {}
        self._handle_by_ref: dict[str, str] = {}
        self._ref_by_handle: dict[str, str] = {}
        self._used_numbers: set[int] = set()
        if self.path is not None and self.path.exists():
            self.load()

    # ------------------------------------------------------------------ numbering

    def _fresh_number(self) -> int:
        """Return a random token number no token or handle of this session uses yet."""
        for _ in range(500):
            n = self._rng.randint(*RANDOM_ID_RANGE)
            if n not in self._used_numbers:
                self._used_numbers.add(n)
                return n
        raise RuntimeError("could not allocate a fresh token number for this session")

    # ------------------------------------------------------------------ values

    def mask_value(
        self, pii_type: str, value: Any, *, entity: tuple[str, int] | None = None
    ) -> Any:
        """Return the token that stands for ``value`` in this session.

        ``entity`` names the row the value belongs to (``("CONTACT", 12)``), so
        every value of one person shares one number no matter how it is
        spelled; without it the entity is UC-02's ``entity_key`` of the value
        (surname stem for a PERSON, exact form otherwise). ``None`` and empty
        strings pass through unchanged, there is nothing to protect.
        """
        if value is None:
            return None
        collapsed = " ".join(str(value).split())
        if not collapsed:
            return value
        if entity is not None:
            key = f"{pii_type}|{entity[0]}:{int(entity[1])}"
        else:
            key = "|".join(entity_key(pii_type, collapsed))
        with self._exclusive():
            number = self._number_by_entity.get(key)
            if number is None:
                number = self._fresh_number()
                self._number_by_entity[key] = number
            forms = self._forms_by_entity.setdefault(key, [])
            if collapsed not in forms:
                forms.append(collapsed)
            token = f"<{pii_type}_{number}{form_suffix(forms.index(collapsed))}>"
            self._value_by_token[token] = collapsed
            self._save_locked()
        return token

    def mask_text(self, text: str) -> str:
        """Replace every personal value the UC-02 detector finds in ``text`` with a token.

        Raises ``EnvelopeUnavailable`` when the detector cannot run (fail closed).
        Text that already carries tokens of this session is left as it is:
        the detector does not match the ``<TYPE_n>`` shape.
        """
        if not text or not text.strip():
            return text
        spans = self._detector(text)
        masked = text
        for span in sorted(spans, key=lambda s: -int(s["span_start"])):
            start, end = int(span["span_start"]), int(span["span_end"])
            token = self.mask_value(str(span["pii_type"]), text[start:end])
            masked = masked[:start] + token + masked[end:]
        return masked

    # ------------------------------------------------------------------ handles

    def handle_for(self, kind: str, pk: int) -> str:
        """Return this session's handle for row ``pk`` of ``kind`` (minted on first use)."""
        kind = kind.upper()
        if kind not in HANDLE_KINDS:
            raise ValueError(f"unknown handle kind {kind!r}; choices: {HANDLE_KINDS}")
        ref = f"{kind}:{int(pk)}"
        with self._exclusive():
            handle = self._handle_by_ref.get(ref)
            if handle is None:
                handle = f"<{kind}_{self._fresh_number()}>"
                self._handle_by_ref[ref] = handle
                self._ref_by_handle[handle] = ref
                self._save_locked()
            return handle

    def resolve_id(self, value: Any, kind: str, *, allow_raw: bool) -> int:
        """Turn a tool argument into a database id.

        A handle of ``kind`` resolves through the session map. A plain integer is
        accepted only when ``allow_raw`` is true (the ``open`` profile); under a
        masking profile a bare number is a guess at a database key and is
        refused. Raises ``LookupError`` with a message the tool can return.
        """
        kind = kind.upper()
        text = str(value).strip() if value is not None else ""
        try:
            text = self.normalize_tokens(text)
        except TokenValidationError as exc:
            raise LookupError(str(exc)) from exc
        if not text:
            raise LookupError(f"missing {kind.lower()} id")
        if TOKEN_RE.fullmatch(text):
            if text in self._value_by_token:
                raise LookupError(
                    f"{kind.lower()}_id needs a {kind} handle, not a value token; "
                    "use search_contacts with the whole name token first"
                )
            ref = self._ref_by_handle.get(text)
            if ref is None or not ref.startswith(f"{kind}:"):
                raise LookupError(f"unknown {kind.lower()} handle {text}")
            return int(ref.split(":", 1)[1])
        if allow_raw:
            try:
                return int(text)
            except ValueError as exc:
                raise LookupError(f"not a {kind.lower()} id: {text!r}") from exc
        raise LookupError(
            f"{kind.lower()} ids are handles like <{kind}_1234> in this profile, got {text!r}"
        )

    # ------------------------------------------------------------------ restore

    def normalize_tokens(self, text: str) -> str:
        """Validate references and canonicalise supported HTML token spellings.

        Validation precedes substitution, so restored personal values are not
        interpreted as new tokens. Token-like bare identifiers are reserved
        in masked tool arguments. Numbers, types and spellings are never guessed.
        """
        normalized = _TOKEN_ENCODING_RE.sub(lambda match: f"<{match[1]}>", text)
        for match in TOKEN_RE.finditer(normalized):
            token = match[0]
            if token not in self._value_by_token and token not in self._ref_by_handle:
                raise TokenValidationError(
                    "unknown_token",
                    "Token is not in this session; copy a token returned in this conversation.",
                )
            if match.start() and normalized[match.start() - 1] == "\\":
                raise TokenValidationError(
                    "malformed_token", "Do not escape token brackets; copy the whole token exactly."
                )
        if _TOKEN_HINT_RE.search(TOKEN_RE.sub("", normalized)):
            raise TokenValidationError(
                "malformed_token",
                "Damaged token notation; copy the whole <TYPE_number> token exactly, including brackets.",
            )
        return normalized

    def restore_checked(self, text: Any, *, allow_handles: bool = False) -> Any:
        """Restore validated value tokens; optionally retain known row handles.

        Handles are allowed in answers and relationship-id fields. A search or
        note body needs values, not opaque row references.
        """
        if not isinstance(text, str):
            return text
        normalized = self.normalize_tokens(text)
        if not allow_handles and any(
            token in self._ref_by_handle for token in self.tokens_in(normalized)
        ):
            raise TokenValidationError(
                "wrong_token_type", "This argument needs a value token, not a row handle."
            )
        return self.restore(normalized)

    def restore(self, text: Any) -> Any:
        """Replace every token of this session in ``text`` with the value it stands for.

        Unknown tokens and handles are left untouched (a handle has no text
        value; use ``resolve_id`` for those). Non-strings pass through.
        """
        if not isinstance(text, str) or "<" not in text:
            return text

        def _swap(match: re.Match[str]) -> str:
            """Return the value for a matched token, or the token unchanged if unknown."""
            return self._value_by_token.get(match.group(0), match.group(0))

        return TOKEN_RE.sub(_swap, text)

    def restore_record(self, record: dict[str, Any]) -> dict[str, Any]:
        """Restore every string value of a flat dict (tool arguments)."""
        return {key: self.restore(value) for key, value in record.items()}

    # ------------------------------------------------------------------ inspection

    @property
    def entries(self) -> dict[str, str]:
        """Token -> value view (a copy) for clients and tests."""
        return dict(self._value_by_token)

    @property
    def handles(self) -> dict[str, str]:
        """``KIND:pk`` -> handle view (a copy)."""
        return dict(self._handle_by_ref)

    def tokens_in(self, text: str) -> set[str]:
        """Return the tokens and handles that occur in ``text``."""
        return {m.group(0) for m in TOKEN_RE.finditer(text or "")}

    def __len__(self) -> int:
        """Return the total number of value tokens plus handles minted in this session."""
        return len(self._value_by_token) + len(self._handle_by_ref)

    # ------------------------------------------------------------------ persistence

    def to_dict(self) -> dict[str, Any]:
        """JSON-serialisable state; everything ``load`` needs to continue the session."""
        return {
            "version": SESSION_MAP_VERSION,
            "values": dict(self._value_by_token),
            "entities": dict(self._number_by_entity),
            "forms": {key: list(forms) for key, forms in self._forms_by_entity.items()},
            "handles": dict(self._handle_by_ref),
        }

    @contextlib.contextmanager
    def _exclusive(self):
        """One critical section over the shared map: lock the file, reload it, yield, release.

        Every mutation saves before it leaves the section, so the file is the
        source of truth and reloading it first is a merge. In-memory envelopes
        (no path) only take the thread lock.
        """
        with self._lock:
            if self.path is None:
                yield
                return
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.with_name(self.path.name + ".lock").open("a+") as lock_file:
                fcntl.flock(lock_file, fcntl.LOCK_EX)
                try:
                    self.load()
                    yield
                finally:
                    fcntl.flock(lock_file, fcntl.LOCK_UN)

    def save(self) -> None:
        """Write the map to ``path`` atomically (no-op when the envelope has no path)."""
        with self._lock:
            self._save_locked()

    def _save_locked(self) -> None:
        """Write the map to `path` atomically; called while the exclusive lock is already held."""
        if self.path is None:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(f".{self.path.name}.{os.getpid()}.{uuid.uuid4().hex[:8]}.tmp")
        tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)

    def load(self) -> None:
        """Replace the in-memory state with the file at ``path``."""
        if self.path is None or not self.path.exists():
            return
        data = json.loads(self.path.read_text(encoding="utf-8"))
        if int(data.get("version", 0)) != SESSION_MAP_VERSION:
            raise ValueError(f"session map {self.path} has version {data.get('version')!r}")
        with self._lock:
            self._value_by_token = dict(data.get("values", {}))
            self._number_by_entity = {k: int(v) for k, v in data.get("entities", {}).items()}
            self._forms_by_entity = {k: list(v) for k, v in data.get("forms", {}).items()}
            self._handle_by_ref = dict(data.get("handles", {}))
            self._ref_by_handle = {h: ref for ref, h in self._handle_by_ref.items()}
            self._used_numbers = set(self._number_by_entity.values())
            for handle in self._handle_by_ref.values():
                match = TOKEN_RE.fullmatch(handle)
                if match:
                    self._used_numbers.add(int(match.group(2)))

    def reload(self) -> None:
        """Pick up changes another process wrote to ``path`` (the client after a model turn)."""
        self.load()


__all__ = [
    "HANDLE_KINDS",
    "TOKEN_RE",
    "EnvelopeUnavailable",
    "TokenValidationError",
    "SessionEnvelope",
    "uc02_detector",
]
