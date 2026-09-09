"""UC-02 sandwich envelope: mask -> model call -> id echo and token check -> restore.

Public API (used by UC-03 and the live check)::

    from ucs.uc02_pseudonymization import with_envelope

    final_text = await with_envelope(text, my_llm_caller, max_attempts=3)

Design (user decisions of 2026-05-30 and 2026-05-31):

- Token numbers inside the envelope are random (1 to 9999 per call, never
  sequential), so an attacker cannot read the order of people in the original
  text off the masked one.
- Every call has its own ``mapping_id`` (UUID4 hex), the correlation token for
  concurrent calls. The model receives it in the prompt as ``<id>...</id>`` and
  must echo it character for character on the first line of its answer
  (``prompts_envelope.py``).
- The loop: masked text + id wrapper -> model -> check the id and every
  ``<TYPE_N>`` token -> retry with a reminder, or switch provider on a rate
  limit / quota / timeout -> restore.
- Strict id pairing: ``response_mid == mapping_id``. Orphan rule: when the id is
  missing or wrong and the ``MappingRegistry`` holds exactly one active mapping,
  the answer is taken as ours (the model destroyed the id).
- Three attempts per provider, then the next one in the chain. Rate limit,
  quota and timeout errors switch at once; other errors retry on the same
  provider. When every provider is exhausted: ``EnvelopeProviderError``.

Masking and restore are ``pseudonymizer.pseudonymize_text`` / ``restore_text``
with the random numbering policy; the prompts live in ``prompts_envelope.py``.
"""

from __future__ import annotations

import asyncio
import logging
import random
import re
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from typing import Any

from ucs.uc02_pseudonymization.code.prompts_envelope import (
    DETECTION_CLAUSES,
)
from ucs.uc02_pseudonymization.code.prompts_envelope import (
    ENVELOPE_SYS_HINT as _ENVELOPE_SYS_HINT_SPEC,
)
from ucs.uc02_pseudonymization.code.pseudonymizer import (
    TAG_PATTERN,
    pseudonymize_text,
    restore_text,
)
from ucs.uc02_pseudonymization.code.prompts_envelope import (
    RETRY_REMINDER_MID as _RETRY_REMINDER_MID_SPEC,
)
from ucs.uc02_pseudonymization.code.prompts_envelope import (
    RETRY_REMINDER_TAGS as _RETRY_REMINDER_TAGS_SPEC,
)
from ucs.uc02_pseudonymization.code.prompts_envelope import (
    RETRY_REMINDER_TAGS_EXTRA_CLAUSE,
    RETRY_REMINDER_TAGS_MISSING_CLAUSE,
)
from ucs.uc02_pseudonymization.code.prompts_envelope import (
    USER_PROMPT_TEMPLATE as _USER_PROMPT_TEMPLATE_SPEC,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MID_PATTERN = re.compile(r"<id>([0-9a-f]{32})</id>")  # matches the envelope wrapper

DEFAULT_TIMEOUT_PER_ATTEMPT_S = 180  # 3 minutes per user spec
DEFAULT_MAX_RETRIES = 3

# Public re-exports — callers depend on these names directly. `.system_instruction`
# gives the raw prompt text; the PromptSpec wrapper carries prompt_id / version /
# purpose metadata.
ENVELOPE_SYS_HINT = _ENVELOPE_SYS_HINT_SPEC.system_instruction


# ---------------------------------------------------------------------------
# Mapping + ID generation
# ---------------------------------------------------------------------------


@dataclass
class EnvelopeMapping:
    """Per-call mapping store. Lives in caller's local memory only — never persisted.

    ``mapping_id`` is a UUID4 hex string that uniquely identifies this mapping
    across concurrent calls (MCP server, async UC-03 voice pipeline, batch). It
    has two practical uses:
      1. Log correlation — every log line / metric / audit row can carry the id
         so you can trace one envelope's lifecycle across services.
      2. Stateless API — callers that maintain a registry (see ``MappingRegistry``)
         can stash the mapping under ``mapping_id`` and pass the id over the wire
         to a depseudonymize service that holds the registry.
    """

    entries: dict[str, str] = field(default_factory=dict)  # token -> original value
    mapping_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    # The per-span records from ``pseudonymize_text`` (type, offsets, entity, source);
    # ``entries`` is their token -> value view, which is all restore needs.
    records: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_records(cls, records: list[dict[str, Any]]) -> "EnvelopeMapping":
        """Build a mapping from ``pseudonymize_text`` records."""
        return cls(
            entries={r["token"]: r["surface_form"] for r in records},
            records=list(records),
        )

    def expected_tokens(self) -> set[str]:
        """Return the tokens the model must echo back unchanged."""
        return set(self.entries.keys())

    def is_empty(self) -> bool:
        """Return whether no personal data was detected (nothing to protect)."""
        return not self.entries


class MappingRegistry:
    """In-memory registry for cross-call mapping lookup by ``mapping_id``.

    Use when callers (e.g. UC-03 MCP server) need to stash the mapping after a
    pseudonymize call and retrieve it later for depseudonymize — for example
    when the masked text is handed off to an external service that then sends
    the (still-masked) response back through a different code path.

    ``pending_count`` is used by :func:`with_envelope` for the orphan rule —
    when the LLM destroyed the id and exactly one envelope is in flight, the response
    can be safely attributed to that envelope.

    Thread-safety: the underlying dict is fine for cooperative asyncio. For
    multi-process / multi-thread use, wrap with a ``threading.Lock`` or replace
    with a Redis-backed store.

    Persistence: NONE by default — entries live only for the process lifetime.
    For audit-grade persistence, subclass and override ``put`` / ``get``.
    """

    def __init__(self) -> None:
        """Create an empty registry — no mappings are pre-populated."""
        self._store: dict[str, EnvelopeMapping] = {}

    def put(self, mapping: EnvelopeMapping) -> str:
        """Register a mapping and return its ``mapping_id`` (same as ``mapping.mapping_id``)."""
        self._store[mapping.mapping_id] = mapping
        return mapping.mapping_id

    def get(self, mapping_id: str) -> EnvelopeMapping | None:
        """Return the mapping registered under ``mapping_id``, or ``None``."""
        return self._store.get(mapping_id)

    def pop(self, mapping_id: str) -> EnvelopeMapping | None:
        """Retrieve and remove — use after the sandwich completes to free memory."""
        return self._store.pop(mapping_id, None)

    def pending_count(self) -> int:
        """Return the number of currently active mappings (orphan-rule input)."""
        return len(self._store)

    def active_ids(self) -> list[str]:
        """Return a snapshot of currently active ``mapping_id`` strings."""
        return list(self._store.keys())

    def __contains__(self, mapping_id: str) -> bool:
        """Return whether `mapping_id` is currently registered."""
        return mapping_id in self._store

    def __len__(self) -> int:
        """Return the number of currently active mappings (same as `pending_count`)."""
        return len(self._store)


# ---------------------------------------------------------------------------
# LLM prompt composition (caller's task prompt + ENVELOPE_SYS_HINT)
# ---------------------------------------------------------------------------


def compose_system_prompt(task_prompt: str, *, detection: str = "rules+ner") -> str:
    """Prefix the caller's task prompt with ``ENVELOPE_SYS_HINT`` for one envelope level.

    The hint goes FIRST so the integrity rules are read before any task
    instructions that might tempt the model to paraphrase placeholders. ``detection``
    names what the caller's detector replaced (``"rules+ner"`` or ``"rules"``) and
    fills the hint's ``{detection_clause}``; the hint also tells the model that every
    token is restored locally after its answer. Body text comes from
    :mod:`prompts_envelope` (see that module for versioning).
    """
    if detection not in DETECTION_CLAUSES:
        raise ValueError(
            f"unknown detection level {detection!r}; known: {', '.join(DETECTION_CLAUSES)}"
        )
    hint = ENVELOPE_SYS_HINT.replace("{detection_clause}", DETECTION_CLAUSES[detection])
    return hint + "\n---\n" + task_prompt


def compose_user_prompt(masked_text: str, mapping_id: str) -> str:
    """Wrap the masked text with the envelope ``<id>...</id>`` correlation token.

    The MID lives at the end of the user prompt (not in the system prompt)
    because the system prompt is per-session while envelope ID is per-request.
    """
    return _USER_PROMPT_TEMPLATE_SPEC.system_instruction.format(
        masked_text=masked_text, mapping_id=mapping_id
    )


# ---------------------------------------------------------------------------
# Detection + masking
# ---------------------------------------------------------------------------

# A detector returns span records: span_start, span_end, pii_type, surface_form,
# source (see ``pseudonymizer``).
DetectorFn = Callable[[str], list[dict[str, Any]]]


def rule_only_detector(text: str) -> list[dict[str, Any]]:
    """Detector with the rule layer alone, for callers that choose to run without NER.

    Names, organisations and addresses are not detected on this path; it is a
    choice the caller makes explicitly, never a fallback the envelope takes on
    its own.
    """
    from ucs.uc02_pseudonymization.code.pseudonymizer import detect_rule_based

    return detect_rule_based(text)


def default_detector(text: str) -> list[dict[str, Any]]:
    """The envelope's default detector: rules + the package's NER backend, merged.

    Raises ``ner.NerBackendError`` when the NER layer cannot run; the envelope
    never degrades to rules alone by itself.
    """
    from ucs.uc02_pseudonymization.code.ner import detect_ner
    from ucs.uc02_pseudonymization.code.pseudonymizer import (
        detect_rule_based,
        merge_spans,
    )

    return merge_spans(detect_rule_based(text), list(detect_ner(text)), text)


def make_detector(use_ner: bool = True, ner_backend: str | None = None) -> DetectorFn:
    """Return the detector for a caller's choice: rules alone, or rules + one NER backend.

    ``ner_backend`` ``None`` means the package default (``default_detector``); any
    other name in ``ner.NER_BACKENDS`` loads that backend on first use. The demo
    page's NER picker goes through here, so a choice made there runs the same code
    as the CLI and the table.
    """
    from ucs.uc02_pseudonymization.code.ner import (
        DEFAULT_NER_BACKEND,
        NER_BACKENDS,
        detect_ner,
    )
    from ucs.uc02_pseudonymization.code.pseudonymizer import (
        detect_rule_based,
        merge_spans,
    )

    if not use_ner:
        return rule_only_detector
    if ner_backend is None or ner_backend == DEFAULT_NER_BACKEND:
        return default_detector
    if ner_backend not in NER_BACKENDS:
        raise ValueError(f"unknown NER backend {ner_backend!r}; known: {', '.join(NER_BACKENDS)}")

    def detector(text: str) -> list[dict[str, Any]]:
        """Rules merged with the `ner_backend` NER backend selected by `make_detector`."""
        return merge_spans(
            detect_rule_based(text), list(detect_ner(text, backend=ner_backend)), text
        )

    detector.__name__ = f"rules_plus_{ner_backend}_detector"
    return detector


# The envelope's unification policy (D-UC02-4, user 2026-09-05): the model is told
# that two mentions are one person ("the model might need to know that those are
# the same persons"), every token still comes back, restore stays exact. Paths
# that only file a note (UC-03) keep plain tokens through ``pseudonymizer``.
DEFAULT_UNIFY = "entity"


def mask(
    text: str,
    *,
    detector: DetectorFn | None = None,
    unify: str = DEFAULT_UNIFY,
    rng: random.Random | None = None,
) -> tuple[str, EnvelopeMapping]:
    """Detect personal data and replace it with random-numbered tokens.

    Masking is ``pseudonymizer.pseudonymize_text`` with ``numbering="random"``: the
    number of a token leaks nothing about the order of mentions in the text.
    ``unify`` is the unification policy (``"none"`` / ``"exact"`` / ``"entity"``,
    see ``pseudonymize_text``). Pass ``detector`` to override the default
    rules + NER detector, and ``rng`` to make the numbering reproducible.
    """
    spans = (detector or default_detector)(text)
    masked, records = pseudonymize_text(text, spans, unify=unify, numbering="random", rng=rng)
    return masked, EnvelopeMapping.from_records(records)


def unmask(masked_or_response: str, mapping: EnvelopeMapping) -> str:
    """Replace every token in ``masked_or_response`` with the value it stands for."""
    return restore_text(
        masked_or_response,
        [{"token": token, "surface_form": value} for token, value in mapping.entries.items()],
    )


# ---------------------------------------------------------------------------
# Integrity check
# ---------------------------------------------------------------------------


@dataclass
class IntegrityResult:
    """Outcome of comparing the tokens in a response with the tokens sent."""

    ok: bool
    missing_in_response: set[str]  # tokens that disappeared
    extra_in_response: set[str]  # tokens the model invented (not in the mapping)

    def summary(self) -> str:
        """Return ``"ok"`` or a one-line list of the missing and extra tokens."""
        bits = []
        if self.missing_in_response:
            bits.append(f"missing={sorted(self.missing_in_response)}")
        if self.extra_in_response:
            bits.append(f"extra={sorted(self.extra_in_response)}")
        return "ok" if not bits else "; ".join(bits)


def check_envelope_integrity(response: str, mapping: EnvelopeMapping) -> IntegrityResult:
    """Check that the response carries exactly the tokens that were sent.

    A missing token means personal data cannot be restored at that place; an
    extra token means the model invented one. Both trigger a retry.
    """
    expected = mapping.expected_tokens()
    found = {f"<{m.group(1)}_{m.group(2)}{m.group(3)}>" for m in TAG_PATTERN.finditer(response)}
    return IntegrityResult(
        ok=(found == expected),
        missing_in_response=expected - found,
        extra_in_response=found - expected,
    )


# ---------------------------------------------------------------------------
# Sandwich orchestration
# ---------------------------------------------------------------------------


LlmCall = Callable[[str], Awaitable[str]]  # masked text -> response text


class EnvelopeIntegrityError(RuntimeError):
    """LLM failed to preserve placeholders or MID wrapper across all attempts."""

    def __init__(
        self,
        msg: str,
        *,
        mapping: EnvelopeMapping,
        last_response: str,
        last_check: IntegrityResult | None,
    ):
        """Store the mapping, the last raw response and its integrity check alongside `msg`."""
        super().__init__(msg)
        self.mapping = mapping
        self.last_response = last_response
        self.last_check = last_check


class EnvelopeProviderError(RuntimeError):
    """All LLM providers in the fallback chain exhausted rate-limit / quota / timeout.

    Distinct from :class:`EnvelopeIntegrityError` (which means "the LLM responded
    but mangled the envelope contract"). This error means "no LLM responded at
    all" and the caller cannot recover by retrying with a new prompt — the chain
    needs more providers, or the calling system needs to wait and try later.
    """

    def __init__(
        self,
        msg: str,
        *,
        mapping: EnvelopeMapping,
        last_provider_error: Exception | None,
    ):
        """Store the mapping and the last provider-level exception alongside `msg`."""
        super().__init__(msg)
        self.mapping = mapping
        self.last_provider_error = last_provider_error


def _retry_reminder_tags(masked: str, mapping_id: str, missing: set[str], extra: set[str]) -> str:
    """Build retry prompt for missing / invented ``<TYPE_N>`` tokens."""
    missing_clause = (
        RETRY_REMINDER_TAGS_MISSING_CLAUSE.format(missing_list=", ".join(sorted(missing)))
        if missing
        else ""
    )
    extra_clause = (
        RETRY_REMINDER_TAGS_EXTRA_CLAUSE.format(extra_list=", ".join(sorted(extra)))
        if extra
        else ""
    )
    return _RETRY_REMINDER_TAGS_SPEC.system_instruction.format(
        masked_text=masked,
        mapping_id=mapping_id,
        missing_clause=missing_clause,
        extra_clause=extra_clause,
    )


def _retry_reminder_mid(masked: str, mapping_id: str) -> str:
    """Build retry prompt for missing / mangled ``<id>...</id>`` wrapper."""
    return _RETRY_REMINDER_MID_SPEC.system_instruction.format(
        masked_text=masked, mapping_id=mapping_id
    )


def _extract_mid(response: str) -> str | None:
    """Return the first ``<id>...</id>`` UUID4 hex found in ``response``, or None."""
    m = MID_PATTERN.search(response)
    return m.group(1) if m else None


def _strip_mid_line(response: str) -> str:
    """Remove the first line containing ``<id>...</id>`` plus leading blank lines.

    The MID wrapper is a protocol artefact; the caller shouldn't see it in the
    final restored text. PII placeholders (``<TYPE_N>``) on the same line are
    NOT stripped — only the MID line is dropped.
    """
    lines = response.split("\n")
    out: list[str] = []
    stripped = False
    for line in lines:
        if not stripped and MID_PATTERN.search(line):
            stripped = True
            continue
        out.append(line)
    while out and out[0].strip() == "":
        out.pop(0)
    return "\n".join(out)


async def _call_with_timeout(llm_call: LlmCall, prompt: str, timeout: float | None) -> str:
    """Wrap an LLM call with a per-attempt timeout.

    ``asyncio.TimeoutError`` is converted to ``ProviderTimeoutError`` so the
    outer provider-switch loop can treat it as a provider-level failure rather
    than a generic exception. The ``utils.generation`` providers may also raise
    their own ``ProviderTimeoutError`` from inside the CLI subprocess; both
    paths funnel into the same handler.
    """
    if timeout is None:
        return await llm_call(prompt)
    # Import lazily so envelope.py stays importable when utils.generation is
    # not on sys.path (e.g. tests that exercise pure-detection code).
    from utils.generation.errors import ProviderTimeoutError

    try:
        return await asyncio.wait_for(llm_call(prompt), timeout=timeout)
    except asyncio.TimeoutError as e:
        raise ProviderTimeoutError(
            "envelope",
            f"LLM call exceeded {timeout:.0f}s per-attempt budget.",
            hint="The provider may be overloaded — switching to the next caller in the chain.",
        ) from e


def _strip_stray_mid(response: str) -> str:
    """Drop a leading ``<id>...</id>`` line from a passthrough answer.

    The system prompt tells the model that its first line must be the wrapper; when
    nothing was masked no wrapper was sent, and a model may copy the example id from
    the rules instead (codex, 2026-09-07). The line carries nothing, so it goes; the
    rest of the answer is returned as it came.
    """
    stripped = response.lstrip()
    match = MID_PATTERN.match(stripped)
    if match is None:
        return response
    rest = stripped[match.end() :]
    if rest and not rest.startswith("\n"):
        return response
    return rest.lstrip("\n")


async def with_envelope(
    text: str,
    llm_call: LlmCall | None = None,
    *,
    llm_calls: list[LlmCall] | None = None,
    registry: MappingRegistry | None = None,
    detector: DetectorFn | None = None,
    unify: str = DEFAULT_UNIFY,
    rng: random.Random | None = None,
    max_attempts: int = DEFAULT_MAX_RETRIES,
    timeout_per_attempt: float | None = DEFAULT_TIMEOUT_PER_ATTEMPT_S,
    on_attempt: Callable[[dict[str, Any]], None] | None = None,
    on_empty: str = "passthrough",
) -> str:
    """Sandwich helper. Returns final text with original PII restored.

    Args:
        text: Caller's raw text with potentially-real PII.
        llm_call: Single LLM caller (shortcut for ``llm_calls=[llm_call]``).
        llm_calls: List of LLM callers used as a fallback chain. On rate-limit,
            quota, or timeout from one caller, the next caller is tried.
        registry: Optional ``MappingRegistry``. When provided, the mapping is
            registered for its lifetime and the orphan rule kicks in (if the
            LLM mangles the MID and this is the only active envelope in the
            registry, the response is accepted anyway).
        detector: Optional detector callable; defaults to the rule + NER fusion.
        unify: Token unification policy (``"none"`` / ``"exact"`` / ``"entity"``);
            the default ``DEFAULT_UNIFY`` is ``"entity"``.
        rng: Seeded ``random.Random`` for reproducible token numbers.
        max_attempts: Total attempts per provider. After this many failed
            attempts, the chain advances to the next provider; after the last
            provider fails, ``EnvelopeIntegrityError`` is raised.
        timeout_per_attempt: Per-attempt budget in seconds. ``None`` disables
            the timeout. Default 180 s matches the per-attempt window the
            UC-02 sender waits before assuming the provider is stuck.
        on_attempt: Optional observer called once per model response (and once
            per provider error) with a record: provider index, attempt number,
            prompt, response, ``mid_ok``, ``orphan_accepted``, ``integrity_ok``,
            missing and extra tokens; or ``error`` with the exception name. Used
            by the live check to record what the contract saw.
        on_empty: What to do when the detector finds nothing to mask:
            ``"passthrough"`` (default) sends the text as it is, with no id
            wrapper and no token check, and reports it to ``on_attempt`` as
            ``passthrough``; ``"raise"`` refuses with ``ValueError`` so a caller
            that must never send unmasked text can say so. A detector miss is
            the same leak in either mode; the knob only makes the empty case an
            explicit decision.

    Returns:
        Final text with placeholders restored to their original PII.

    Raises:
        EnvelopeIntegrityError: All providers responded but mangled the
            envelope (missing tokens or wrong MID) for all attempts.
        EnvelopeProviderError: All providers failed with rate-limit, quota,
            or timeout errors — no usable response was ever obtained.
    """
    if (llm_call is None) == (llm_calls is None):
        raise ValueError(
            "with_envelope: pass exactly one of `llm_call` (single) or "
            "`llm_calls` (fallback chain), not both / neither."
        )
    callers: list[LlmCall] = (
        list(llm_calls) if llm_calls is not None else [llm_call]  # type: ignore[list-item]
    )
    if not callers:
        raise ValueError("`llm_calls` must contain at least one caller.")
    if max_attempts < 1:
        raise ValueError(f"max_attempts must be >= 1, got {max_attempts}")
    if on_empty not in ("passthrough", "raise"):
        raise ValueError(f"on_empty must be 'passthrough' or 'raise', got {on_empty!r}")

    # Import provider error types lazily — they are only needed for the chain
    # fallback path and live in utils.generation, which we don't want as a hard
    # dependency of pure-mask test code paths.
    from utils.generation.errors import (
        ProviderQuotaError,
        ProviderRateLimitError,
        ProviderTimeoutError,
    )

    masked, mapping = mask(text, detector=detector, unify=unify, rng=rng)
    if registry is not None:
        registry.put(mapping)

    try:
        if mapping.is_empty():
            # Nothing detected: no envelope semantics. The text goes as it is to
            # the first provider that answers; limit / timeout errors still walk
            # the chain. The passthrough is logged and reported so it is never a
            # silent path.
            if on_empty == "raise":
                raise ValueError("with_envelope: no personal data detected and on_empty='raise'")
            logger.info("envelope[%s] nothing detected, passthrough", mapping.mapping_id)
            if on_attempt is not None:
                on_attempt({"provider_index": 0, "attempt": 1, "passthrough": True})
            for caller in callers:
                try:
                    return _strip_stray_mid(
                        await _call_with_timeout(caller, masked, timeout_per_attempt)
                    )
                except (
                    ProviderRateLimitError,
                    ProviderQuotaError,
                    ProviderTimeoutError,
                ):
                    continue
            raise EnvelopeProviderError(
                f"No-PII passthrough exhausted all {len(callers)} providers (LLM provider error).",
                mapping=mapping,
                last_provider_error=None,
            )

        masked_with_mid = compose_user_prompt(masked, mapping.mapping_id)
        last_provider_error: Exception | None = None
        last_integrity_error: EnvelopeIntegrityError | None = None

        for provider_idx, caller in enumerate(callers):
            current_prompt = masked_with_mid
            last_result: IntegrityResult | None = None
            last_response = ""

            try:
                for attempt in range(max_attempts):
                    response = await _call_with_timeout(caller, current_prompt, timeout_per_attempt)
                    last_response = response

                    response_mid = _extract_mid(response)
                    mid_ok = response_mid == mapping.mapping_id
                    orphan_accepted = False
                    if (
                        not mid_ok
                        and registry is not None
                        and registry.pending_count() == 1
                        and mapping.mapping_id in registry
                    ):
                        mid_ok = True
                        orphan_accepted = True
                        logger.warning(
                            "envelope[%s] MID mismatch (got %r) but only this envelope is active; "
                            "accepting response as orphan",
                            mapping.mapping_id,
                            response_mid,
                        )

                    integrity = check_envelope_integrity(response, mapping)
                    last_result = integrity
                    if on_attempt is not None:
                        on_attempt(
                            {
                                "provider_index": provider_idx,
                                "attempt": attempt + 1,
                                "prompt": current_prompt,
                                "response": response,
                                "mid_ok": mid_ok,
                                "orphan_accepted": orphan_accepted,
                                "integrity_ok": integrity.ok,
                                "missing": sorted(integrity.missing_in_response),
                                "extra": sorted(integrity.extra_in_response),
                            }
                        )

                    if mid_ok and integrity.ok:
                        logger.debug(
                            "envelope[%s] OK on attempt %d/%d provider %d/%d%s",
                            mapping.mapping_id,
                            attempt + 1,
                            max_attempts,
                            provider_idx + 1,
                            len(callers),
                            " (orphan)" if orphan_accepted else "",
                        )
                        return unmask(_strip_mid_line(response), mapping)

                    if attempt >= max_attempts - 1:
                        break

                    # MID failure takes priority — it's structural and the
                    # combined reminder for "MID wrong AND tokens wrong" would
                    # bury the more important fault. A second pass after MID
                    # fix will surface remaining token issues if any.
                    if not mid_ok:
                        logger.warning(
                            "envelope[%s] MID mismatch on attempt %d/%d (provider %d): got %r",
                            mapping.mapping_id,
                            attempt + 1,
                            max_attempts,
                            provider_idx + 1,
                            response_mid,
                        )
                        current_prompt = _retry_reminder_mid(masked, mapping.mapping_id)
                    else:
                        logger.warning(
                            "envelope[%s] integrity failed on attempt %d/%d (provider %d): %s",
                            mapping.mapping_id,
                            attempt + 1,
                            max_attempts,
                            provider_idx + 1,
                            integrity.summary(),
                        )
                        current_prompt = _retry_reminder_tags(
                            masked,
                            mapping.mapping_id,
                            integrity.missing_in_response,
                            integrity.extra_in_response,
                        )

                # Provider exhausted on integrity / MID failures. Switch providers
                # if any remain; otherwise raise.
                last_integrity_error = EnvelopeIntegrityError(
                    f"LLM provider {provider_idx + 1}/{len(callers)} mangled the "
                    f"envelope across {max_attempts} attempts. "
                    f"Last result: {last_result.summary() if last_result else 'unknown'}. "
                    f"Expected: {sorted(mapping.expected_tokens())}",
                    mapping=mapping,
                    last_response=last_response,
                    last_check=last_result,
                )
                if provider_idx >= len(callers) - 1:
                    raise last_integrity_error
                logger.warning(
                    "envelope[%s] provider %d/%d exhausted on integrity; switching",
                    mapping.mapping_id,
                    provider_idx + 1,
                    len(callers),
                )
                continue

            except (
                ProviderRateLimitError,
                ProviderQuotaError,
                ProviderTimeoutError,
            ) as exc:
                last_provider_error = exc
                if on_attempt is not None:
                    on_attempt(
                        {
                            "provider_index": provider_idx,
                            "attempt": None,
                            "error": type(exc).__name__,
                        }
                    )
                logger.warning(
                    "envelope[%s] provider %d/%d hit %s; switching to next provider",
                    mapping.mapping_id,
                    provider_idx + 1,
                    len(callers),
                    type(exc).__name__,
                )
                continue

        # Fall-through: every provider failed on rate-limit / quota / timeout.
        raise EnvelopeProviderError(
            f"All {len(callers)} LLM providers exhausted on rate-limit / quota / timeout "
            f"(LLM provider error).",
            mapping=mapping,
            last_provider_error=last_provider_error,
        )
    finally:
        if registry is not None:
            registry.pop(mapping.mapping_id)


__all__ = [
    "DEFAULT_MAX_RETRIES",
    "DEFAULT_TIMEOUT_PER_ATTEMPT_S",
    "DEFAULT_UNIFY",
    "ENVELOPE_SYS_HINT",
    "EnvelopeIntegrityError",
    "EnvelopeMapping",
    "EnvelopeProviderError",
    "IntegrityResult",
    "MID_PATTERN",
    "MappingRegistry",
    "TAG_PATTERN",
    "check_envelope_integrity",
    "compose_system_prompt",
    "make_detector",
    "DETECTION_CLAUSES",
    "compose_user_prompt",
    "mask",
    "unmask",
    "with_envelope",
]
