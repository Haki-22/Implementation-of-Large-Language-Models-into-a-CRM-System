"""
mock — deterministic test double for utils.generation.

This module implements the utils.generation provider interface without
launching any subprocess or making any network call.  It is used by all
unit and integration tests to keep the test suite fast, offline, and free.

generate_text  → returns a fixed Czech message string (deterministic).
generate_json  → returns a canned dict with keys matching common schemas
                 (prior_interactions + frequent_words by default; a UC-01
                 judge verdict; an OCEAN profile with evidence quotes; the
                 UC-04 outputs for UC-01: reason, persona, aspects; the UC-04
                 model methods: a ranking in prompt order, three purchase lines).

Both functions accept (and ignore) all provider-specific keyword arguments
so tests can call them with the same signature as real providers.
"""

from __future__ import annotations

import re

_CANDIDATE_LINE = re.compile(r"^C[0-9]{3}\s")


# ---------------------------------------------------------------------------
# Canned responses
# ---------------------------------------------------------------------------

_CANNED_TEXT = (
    "Vážený pane Nováku,\n\n"
    "dovolujeme si Vám oznámit, že Vaše objednávka č. 20261234 byla odeslána "
    "a dorazí do 3 pracovních dnů. "
    "Těšíme se na Vaši další návštěvu.\n\n"
    "S pozdravem,\nZákaznický servis"
)

_CANNED_DICT = {
    "prior_interactions": "Telefonát – zájem o jarní výprodej, zákazník požádal o zasílání novinek.",
    "frequent_words": ["výprodej", "doprava zdarma", "věrnostní program"],
}

# A BFI-2 profile inside the 1-5 range, so the OCEAN inference's validation and
# freeze path run offline end to end (ucs/uc01_personalization/ocean_inference.py).
_CANNED_OCEAN = {
    "O": 3.8,
    "C": 3.6,
    "E": 3.2,
    "A": 3.7,
    "N": 2.9,
    "evidence_quotes": {trait: "mock evidence quote" for trait in "OCEAN"},
}


# ---------------------------------------------------------------------------
# Provider interface
# ---------------------------------------------------------------------------


async def generate_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> str:
    """
    Return a deterministic Czech message string.

    When the prompt contains the UC-01 SALUTATION field, the mock mirrors that
    greeting so offline corpus runs exercise the same validation path as live
    provider runs.  Otherwise it returns the fixed canned string.

    Returns
    -------
    str
        Fixed Czech personalised-message string.
    """
    salutation = _extract_uc01_salutation(prompt)
    if salutation:
        if "INFORMAL" in prompt or "Formálnost: tykání" in prompt:
            return (
                f"{salutation}\n\n"
                "máme pro tebe novou nabídku z e-shopu. Podívej se na ni ještě dnes, "
                "mohla by se ti hodit.\n\n"
                "Tvůj zákaznický tým"
            )
        return (
            f"{salutation}\n\n"
            "dovolujeme si Vám poslat novou nabídku z našeho e-shopu. "
            "Věříme, že pro Vás bude užitečná.\n\n"
            "S pozdravem,\nZákaznický servis"
        )
    return _CANNED_TEXT


def _extract_uc01_salutation(prompt: str) -> str | None:
    """Extract the greeting from a UC-01 generation prompt.

    The current prompt (``ucs/uc01_personalization/prompts.py``, since 2026-09-04)
    carries it as an ``Oslovení: …`` line inside ``<příjemce>``; the pre-2026-05-31
    layout carried it under ``## FIELD 1 — SALUTATION``. Both are read so the mock
    keeps mirroring the greeting and offline runs pass the rules judge.
    """
    lines = prompt.splitlines()
    for i, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("Oslovení:"):
            value = stripped[len("Oslovení:") :].strip()
            if value:
                return value
        if stripped == "## FIELD 1 — SALUTATION":
            for candidate in lines[i + 1 : i + 5]:
                value = candidate.strip()
                if value and not value.startswith("Use exactly"):
                    return value
    return None


async def generate_json(
    prompt: str,
    schema: dict,
    *,
    system_prompt: str | None = None,
    system_prompt_mode: str = "concat",
    model: str | None = None,
    tier: str | None = None,
    timeout: int | None = None,
) -> dict:
    """
    Return a deterministic canned dict matching common thesis schemas.

    A UC-01 judge schema (``vocative_ok`` among the properties) gets a FULL
    valid verdict that quotes the first line of the ``<zpráva>`` block in the
    prompt as the span of all three criteria (a real span, so the span check
    labels it found), so an offline cascade run routes every message to VALID. An
    OCEAN schema (``evidence_quotes`` among the properties) gets a fixed in-range
    BFI-2 profile. Any other schema gets the enrichment dict ("prior_interactions",
    "frequent_words") used by the substrate tests.

    Returns
    -------
    dict
        Canned dict for the schema's shape.
    """
    properties = schema.get("properties", {})
    if (
        "ranking" in properties
    ):  # UC-04 model methods: the candidates in the order the prompt lists them
        ids = [ln.split()[0] for ln in prompt.splitlines() if _CANDIDATE_LINE.match(ln)]
        return {"ranking": ids}
    if (
        "next_purchases" in properties
    ):  # UC-04 describe-and-retrieve: the last history title, three ways
        history = [ln for ln in prompt.splitlines() if ln.startswith("- ") and " ★" in ln]
        last = history[-1].split(" ", 3)[-1] if history else "mock product"
        return {"next_purchases": [last, f"{last} accessory", f"{last} replacement"]}
    if "vocative_ok" in properties:
        return _judge_verdict(prompt, schema)
    if "evidence_quotes" in properties:
        return {**_CANNED_OCEAN, "evidence_quotes": dict(_CANNED_OCEAN["evidence_quotes"])}
    if "evidence_ids" in properties:  # UC-04 recommendation reason
        return {
            "reason": "Doplňuje dřívější nákup zákazníka ze stejné kategorie.",
            "evidence_ids": ["H01"],
        }
    if "narrative_cs" in properties:  # UC-04 persona
        return {
            "label": "mock_zakaznik",
            "narrative_cs": "Zákazník kupuje příslušenství k elektronice a vrací se v krátkých cyklech. Míří na střední cenovou hladinu.",
            "tags": ["příslušenství", "elektronika", "pravidelný"],
            "price_segment": "mid",
        }
    if (
        "aspects" in properties
    ):  # UC-04 aspects: the evidence quotes the first review line of the prompt
        start, end = prompt.find("<recenze>"), prompt.find("</recenze>")
        block = prompt[start + len("<recenze>") : end] if 0 <= start < end else ""
        first = next((ln.strip() for ln in block.splitlines() if ln.strip()), "mock")
        quote = first.split(": ", 1)[-1][:120]
        return {"aspects": [{"aspect": "zvuk", "sentiment": "positive", "evidence": quote}]}
    return dict(_CANNED_DICT)


def _judge_verdict(prompt: str, schema: dict) -> dict:
    """Build a FULL judge verdict, quoting the message's first line as every criterion's evidence."""
    start, end = prompt.find("<zpráva>"), prompt.find("</zpráva>")
    message = prompt[start + len("<zpráva>") : end] if 0 <= start < end else ""
    first_line = next((ln.strip() for ln in message.splitlines() if ln.strip()), "")
    verdict = {
        "vocative_ok": True,
        "vocative_evidence": first_line,
        "register_ok": True,
        "register_evidence": first_line,
        "gender_ok": True,
        "gender_evidence": first_line,
    }
    if "reason" in schema.get("required", []):
        verdict["reason"] = "mock arbiter: deterministic verdict"
    return verdict
