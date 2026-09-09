"""The single call: one contact, one brief, one level -> one message with its provenance.

This is the unit everything else composes: the CLI's ``generate`` command, the
runner's loop over a pick, and the frontend's live generation all call
``generate()``. It reads the contact and the level's inputs from the database,
builds the level's prompt, dispatches through ``utils.generation`` (behind the
``THESIS_LLM_CALLS`` switch, unless the level needs no model), and runs the free
rules judge when asked. The model judges are a second pass over a finished run
(``judge_run.py``), never part of generation. A contact that lacks an input the
level needs is *skipped*, with the missing slot recorded, never called.
"""

from __future__ import annotations

import asyncio
import sqlite3
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any

from ucs.uc01_personalization import data, levels, prompts
from ucs.uc01_personalization.judge import RulesVerdict, validate_rules
from utils.generation import resolve_model, resolve_tier

DEFAULT_PROVIDER = "mock"
DEFAULT_TIER = "low"
DISPATCH_TIMEOUT = 180


# ---------------------------------------------------------------------------
# The record of one message
# ---------------------------------------------------------------------------


@dataclass
class Generation:
    """One generated (or skipped) message and everything needed to reproduce it."""

    contact_id: int
    brief_id: int
    level: str
    level_name: str
    created_at: str
    text: str | None
    used_model: bool
    provider: str | None
    model: str | None
    tier: str | None
    prompt_version: str
    slots: list[str]
    system_prompt: str | None
    user_prompt: str | None
    skipped: list[str] = field(default_factory=list)
    error: str | None = None
    seconds: float = 0.0
    rules: dict[str, Any] | None = None
    # facts about the contact a table may split on
    gender: str | None = None
    formal: bool | None = None
    gender_paired: bool = False
    ocean_source: str | None = None
    lifecycle_stage: str | None = None
    # the run whose identical call this row was copied from (``run --reuse``), else None
    reused_from: str | None = None

    @property
    def ok(self) -> bool:
        """A message exists: the level ran, nothing was skipped, no provider error."""
        return self.error is None and not self.skipped and self.text is not None

    def to_dict(self) -> dict[str, Any]:
        """The row written to messages.jsonl (adds the derived ``ok``)."""
        d = asdict(self)
        d["ok"] = self.ok
        return d


def _now() -> str:
    """The current UTC time as an ISO-8601 string with second precision, for ``created_at``."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# Reuse of an earlier run's identical call
# ---------------------------------------------------------------------------


def reusable(stored: dict[str, Any], gen: Generation) -> bool:
    """A stored messages.jsonl row stands for this generation when every input is identical.

    Same provider, resolved model and tier, prompt version, and both prompt texts to
    the character; and the stored call produced a message. Anything else (a prompt
    edit, another model, a failed or skipped row) is generated afresh. Mirrors the
    ``--reuse`` rule of UC-04's model arena (2026-09-07).
    """
    return bool(
        stored.get("ok")
        and stored.get("text")
        and stored.get("provider") == gen.provider
        and stored.get("model") == gen.model
        and stored.get("tier") == gen.tier
        and stored.get("prompt_version") == gen.prompt_version
        and stored.get("system_prompt") == gen.system_prompt
        and stored.get("user_prompt") == gen.user_prompt
    )


# ---------------------------------------------------------------------------
# One message: load, build the prompt, call (or copy), judge
# ---------------------------------------------------------------------------


async def generate(
    contact_id: int,
    brief_id: int,
    level: str | levels.Level,
    *,
    provider: str = DEFAULT_PROVIDER,
    model: str | None = None,
    tier: str | None = DEFAULT_TIER,
    judges: tuple[str, ...] = ("rules",),
    conn: sqlite3.Connection | None = None,
    ocean_override: dict[str, float] | None = None,
    reuse: dict[str, Any] | None = None,
    brief: data.Brief | None = None,
) -> Generation:
    """Generate one message for one contact at one level, judged as asked.

    ``reuse`` is a row of an earlier run's ``messages.jsonl`` (with its ``run_id``
    added); when ``reusable`` says its inputs are identical, its text is copied
    instead of calling the model and the row says ``reused_from``. The rules judge
    runs afresh either way.

    Args:
        contact_id / brief_id: primary keys in ``substrate.db``.
        level: a ladder id ("0", "1", "2", "3a", ... "6") or a ``Level``.
        provider / model / tier: forwarded to ``utils.generation``; ``mock`` costs nothing.
        judges: ``("rules",)`` for the free rules judge, ``()`` for none. The model
            judges run afterwards over the run folder (``judge <run-id>``).
        conn: an open connection to reuse (the runner passes one); opened otherwise.
        ocean_override: replaces the contact's OCEAN profile for the faithfulness
            metric's mirrored run; never used by a normal generation.
        brief: a brief that is not a database row (text typed into the demo page);
            when given, ``brief_id`` is not looked up.
    """
    lvl = (
        level if isinstance(level, levels.Level) else levels.LEVELS[str(level).lower().lstrip("l")]
    )
    own = conn is None
    conn = conn or data.connect()
    try:
        contact = data.load_contact(conn, contact_id)
        if brief is None:
            brief = data.load_brief(conn, brief_id)
        enrichment = data.load_enrichment(conn, contact)
        if ocean_override is not None:
            enrichment = data.Enrichment(**{**asdict(enrichment), "ocean": ocean_override})
    finally:
        if own:
            conn.close()

    # Provenance: the run records the concrete id and tier the adapter will use
    # (default -> "gpt-5.5", alias "sonnet" -> "claude-sonnet-5"), never the raw
    # argument. A value outside the generated menu is an error row, not a crash.
    resolved_model = resolved_tier = None
    resolve_error: str | None = None
    if lvl.uses_model:
        try:
            resolved_model = resolve_model(provider, model)
            resolved_tier = resolve_tier(provider, tier, model)
        except ValueError as exc:
            resolve_error = f"{type(exc).__name__}: {exc}"
            resolved_model, resolved_tier = (str(model) if model is not None else None), tier

    gen = Generation(
        contact_id=contact.id,
        brief_id=brief.id,
        level=lvl.id,
        level_name=lvl.name,
        created_at=_now(),
        text=None,
        used_model=lvl.uses_model,
        provider=provider if lvl.uses_model else None,
        model=resolved_model,
        tier=resolved_tier,
        prompt_version=prompts.PROMPT_VERSION,
        slots=list(lvl.slots),
        system_prompt=None,
        user_prompt=None,
        gender=contact.gender,
        formal=contact.formal,
        gender_paired=contact.gender_paired,
        ocean_source=contact.ocean_source,
        lifecycle_stage=contact.lifecycle_stage,
    )

    missing = lvl.missing(contact, enrichment)
    if missing:
        gen.skipped = missing
        return gen
    if resolve_error is not None:
        gen.error = resolve_error
        return gen

    started = time.monotonic()
    if lvl.id == "0":
        gen.text = levels.generic(brief)
    elif lvl.id == "1":
        gen.text = levels.merge(brief, contact)
    else:
        system, user = levels.build_prompt(lvl, contact, brief, enrichment)
        gen.system_prompt, gen.user_prompt = system, user
        if reuse is not None and reusable(reuse, gen):
            gen.text = reuse["text"]
            gen.seconds = float(reuse.get("seconds") or 0.0)
            gen.reused_from = str(reuse.get("run_id") or "reused")
            if "rules" in judges:
                gen.rules = validate_rules(
                    gen.text,
                    contact,
                    pricing=enrichment.pricing if "pricing" in lvl.slots else None,
                ).to_dict()
            return gen
        from utils.generation import generate_text

        try:
            gen.text = (
                await generate_text(
                    user,
                    provider=provider,
                    system_prompt=system,
                    model=model,
                    tier=tier,
                    timeout=DISPATCH_TIMEOUT,
                )
            ).strip()
        except Exception as exc:  # noqa: BLE001 - every provider failure is recorded, not raised
            gen.error = f"{type(exc).__name__}: {exc}"
            gen.seconds = round(time.monotonic() - started, 2)
            return gen
    gen.seconds = round(time.monotonic() - started, 2)

    if "rules" in judges:
        verdict: RulesVerdict = validate_rules(
            gen.text,
            contact,
            pricing=enrichment.pricing if "pricing" in lvl.slots else None,
        )
        gen.rules = verdict.to_dict()
    return gen


def generate_sync(*args: Any, **kwargs: Any) -> Generation:
    """``generate()`` for callers without an event loop (the CLI)."""
    return asyncio.run(generate(*args, **kwargs))
