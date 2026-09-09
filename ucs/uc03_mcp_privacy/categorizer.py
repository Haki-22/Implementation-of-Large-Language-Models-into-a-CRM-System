"""Transcript/note categorization for UC-03.

Two-layer design:

- ``categorize_text(text)``: dispatch entry. Tries the configured LLM
  categorizer through the local generation wrapper;
  falls back to the deterministic keyword rules below if anything fails.
  Both paths return the same ``CategoryResult`` shape so callers
  (``tools.create_note``, eval harness) need not branch.
- ``categorize_text_heuristic(text)``: the deterministic fallback used
  in tests, offline demos, and as the auto-degrade when LLM is
  unavailable.

The LLM path is privacy-safe by composition with the upstream envelope:
the caller (voice flow) masks the transcript via
``ucs.uc02_pseudonymization.with_envelope`` BEFORE it reaches this module —
the LLM never observes raw PII. If the input still contains ``<TYPE_N>``
placeholders the system prompt instructs the model to ignore them.

The deterministic fallback keeps tests and offline demos reproducible even
when no model provider is configured.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from substrate.constants import NOTE_CATEGORIES

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class CategoryResult:
    """Categorization result for one transcript or note."""

    category: str
    confidence: float
    reason: str
    provider: str = "heuristic"

    def to_dict(self) -> dict[str, str | float]:
        """Return JSON-serialisable result."""
        return {
            "category": self.category,
            "confidence": self.confidence,
            "reason": self.reason,
            "provider": self.provider,
        }


# One definition, in the substrate's constants leaf: the generator seeds notes
# from this list and this module refuses anything outside it, so a label added
# on one side must be visible to the other.
CATEGORIES = NOTE_CATEGORIES


_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("complaint", ("reklam", "vad", "broken", "refund", "vrácení", "nespokojen")),
    ("support", ("support", "warranty", "záruk", "servis", "help", "nefung")),
    ("sales", ("nabídk", "sleva", "discount", "quote", "poptáv", "velkoobchod")),
    ("follow_up", ("follow", "zavolat", "callback", "termín", "schůzk", "meeting")),
    ("delivery", ("doruč", "delivery", "address", "adresa", "přeprav", "shipping")),
)


def categorize_text_heuristic(text: str) -> CategoryResult:
    """Categorize a note/transcript with deterministic keyword rules."""
    lowered = (text or "").lower()
    if not lowered.strip():
        return CategoryResult("general", 0.0, "empty input")

    hits: list[tuple[str, int]] = []
    for category, keywords in _RULES:
        count = sum(1 for keyword in keywords if keyword in lowered)
        if count:
            hits.append((category, count))

    if not hits:
        return CategoryResult("general", 0.35, "no category keyword matched")

    hits.sort(key=lambda item: (-item[1], item[0]))
    category, count = hits[0]
    confidence = min(0.95, 0.55 + 0.15 * count)
    return CategoryResult(category, round(confidence, 2), f"matched {count} keyword(s)")


_LLM_DEFAULT_PROVIDER = "claude"
_LLM_DEFAULT_MODEL = "sonnet"
_LLM_TIMEOUT_SECONDS = 90
_LLM_SYSTEM_PROMPT = (
    "Jsi klasifikátor poznámek pro CRM systém. Tvým úkolem je zařadit krátký záznam"
    " (poznámku nebo přepis voice intake) do jedné ze šesti kategorií:"
    " complaint, support, sales, follow_up, delivery, general."
    " Odpověz POUZE jedním JSON objektem (bez Markdown obalů) ve tvaru:"
    ' {"category": "<kategorie>", "confidence": <0..1>, "reason": "<1 věta česky>"}.'
    " Poznámka může obsahovat zástupné tokeny jako <PERSON_1>, <PHONE_2>, <EMAIL_3> —"
    " to je očekávané (PII byla maskována upstream) a NEZOHLEDŇUJ je při klasifikaci."
)


def _llm_enabled() -> bool:
    """The LLM path runs only when the global switch (``utils.llm_switch``) is on."""
    from utils.llm_switch import llm_calls_enabled

    return llm_calls_enabled()


def _parse_json_response(raw: str) -> dict | None:
    """Best-effort parse of an LLM JSON response (handles markdown fences)."""
    import json
    import re as _re

    text = raw.strip()
    fence = _re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, _re.DOTALL)
    if fence:
        text = fence.group(1)
    # Find first {...} block
    brace_match = _re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", text, _re.DOTALL)
    if brace_match:
        text = brace_match.group(0)
    try:
        parsed = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def categorize_text_llm(
    text: str,
    *,
    provider: str | None = None,
    model: str | None = None,
    timeout: int = _LLM_TIMEOUT_SECONDS,
) -> CategoryResult:
    """Categorize via the configured LLM wrapper.

    Returns a fallback ``CategoryResult`` via the heuristic categorizer when
    the LLM dispatch fails for any reason (wrapper import, timeout, malformed
    JSON, category outside the enum). Never raises.
    """
    body = (text or "").strip()
    if not body:
        return CategoryResult("general", 0.0, "empty input", provider="llm-skipped")

    chosen_provider = provider or _LLM_DEFAULT_PROVIDER
    chosen_model = model or _LLM_DEFAULT_MODEL
    try:
        from utils.generation import generate_text
    except Exception as exc:  # pragma: no cover - lazy import guard
        log.debug("generation wrapper import failed, falling back to heuristic: %s", exc)
        return categorize_text_heuristic(body)

    user_prompt = (
        "Zařaď následující poznámku do jedné z kategorií:\n"
        "complaint, support, sales, follow_up, delivery, general\n\n"
        f'POZNÁMKA:\n"""\n{body}\n"""\n\n'
        "Vrať POUZE JSON objekt podle systémové role."
    )

    import asyncio

    try:
        raw = asyncio.run(
            generate_text(
                prompt=user_prompt,
                provider=chosen_provider,
                system_prompt=_LLM_SYSTEM_PROMPT,
                model=chosen_model,
                timeout=timeout,
            )
        )
    except Exception as exc:
        log.warning("LLM categorization failed (%s); using heuristic fallback", exc)
        return categorize_text_heuristic(body)

    parsed = _parse_json_response(raw)
    if parsed is None:
        return categorize_text_heuristic(body)

    raw_cat = str(parsed.get("category", "")).strip().lower()
    if raw_cat not in CATEGORIES:
        return categorize_text_heuristic(body)
    try:
        confidence = float(parsed.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.5
    confidence = max(0.0, min(0.99, confidence))
    reason = str(parsed.get("reason", "llm categorized")).strip() or "llm categorized"
    return CategoryResult(
        raw_cat,
        round(confidence, 2),
        reason,
        provider=f"{chosen_provider}/{chosen_model}",
    )


def categorize_text(text: str, *, prefer_llm: bool | None = None) -> CategoryResult:
    """Dispatch entry. Tries LLM if enabled; falls back to keyword rules.

    The default policy follows the global ``THESIS_LLM_CALLS`` switch
    (``utils.llm_switch``): with the switch off, offline demos use the
    heuristic. Pass ``prefer_llm=False`` to force the deterministic path
    (used in unit tests for stable golden output).
    """
    body = (text or "").strip()
    if not body:
        return CategoryResult("general", 0.0, "empty input")
    use_llm = _llm_enabled() if prefer_llm is None else bool(prefer_llm)
    if use_llm:
        return categorize_text_llm(body)
    return categorize_text_heuristic(body)
