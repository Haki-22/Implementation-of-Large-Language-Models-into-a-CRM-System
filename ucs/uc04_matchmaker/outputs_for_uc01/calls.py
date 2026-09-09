"""One recorded model call: the prompt goes in, the answer and its provenance land in the run folder.

Every call writes ``calls/<kind>/<key>.json`` as soon as it returns: the verbatim
prompt and system prompt, the raw answer, the parsed object (or the error), the status,
the seconds the call itself took, the resolved model and tier. A failed call is a row,
never a crash; the run's card counts them. The model switch is enforced by the
adapters (``THESIS_LLM_CALLS`` / ``--force-llm``); the mock provider is exempt.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.eval.runs import write_json
from utils.generation import generate_json

TIMEOUT_SECONDS = 180
CONCURRENCY = 4


@dataclass
class Call:
    """What one call produced."""

    kind: str  # reasons | persona | aspects
    key: str  # e.g. "2" (contact) or "2-3" (contact-rank)
    status: str  # ok | failed
    seconds: float
    error: str
    parsed: dict[str, Any] | None


@dataclass(frozen=True)
class Provider:
    """The provider a run calls, with the resolved model and tier recorded once."""

    name: str
    model: str | None  # the argument; the resolved id lives in the run config
    tier: str | None
    resolved_model: str
    resolved_tier: str | None


async def call_json(
    *,
    kind: str,
    key: str,
    prompt: str,
    system_prompt: str,
    schema: dict[str, Any],
    provider: Provider,
    run_dir: Path,
    sem: asyncio.Semaphore,
    validate=None,
) -> Call:
    """One schema-enforced call, recorded under ``calls/<kind>/<key>.json``.

    ``validate(parsed) -> parsed`` may raise ``ValueError`` to turn a schema-valid but
    wrong answer into a failed call (an evidence id outside the history, for instance).
    """
    raw: Any = None
    parsed: dict[str, Any] | None = None
    error = ""
    async with sem:
        t0 = time.perf_counter()
        try:
            raw = await generate_json(
                prompt,
                schema,
                provider=provider.name,
                system_prompt=system_prompt,
                model=provider.model,
                tier=provider.tier,
                timeout=TIMEOUT_SECONDS,
            )
            parsed = validate(raw) if validate else dict(raw)
        except Exception as exc:  # noqa: BLE001 - one failed call is a row, not a crash
            error = f"{type(exc).__name__}: {exc}"[:500]
        seconds = round(time.perf_counter() - t0, 2)
    record = Call(kind, key, "ok" if parsed is not None else "failed", seconds, error, parsed)
    folder = run_dir / "calls" / kind
    folder.mkdir(parents=True, exist_ok=True)
    write_json(
        folder / f"{key}.json",
        {
            **asdict(record),
            "provider": provider.name,
            "model": provider.resolved_model,
            "tier": provider.resolved_tier,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "raw": raw,
        },
    )
    return record


__all__ = ["CONCURRENCY", "TIMEOUT_SECONDS", "Call", "Provider", "call_json"]
