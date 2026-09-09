"""Stage 3 — Gemini 2.5 Pro JSON judge over the shared translation-judge prompt.

Thin wrapper around `_judge_common.run_batched`. Stage-specific bits: model,
JSON-schema dialect (Vertex uppercase types), output CSV path. The system
prompt itself comes from `prompts_translation.TRANSLATION_JUDGE_PROMPT` and is
shared with Stage 4 (Sonnet), so the two judges are independent verifiers of
the same VALID/INVALID question.

Run from the project root after loading the Vertex environment:

    # historical (2026-05): Vertex credentials came from the environment; stage is frozen
        python -m substrate.pipeline.translation_pipeline.stage3_gemini_judge \
            [--batch-size 30] [--concurrency 4] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from utils.generation.api.vertex.gemini import generate_json as vertex_json
from utils.llm_switch import add_force_llm_argument, apply_force_llm
from substrate.pipeline.translation_pipeline._judge_common import (
    format_batch_prompt,
    normalize_verdicts,
    run_batched,
)
from substrate.pipeline.translation_pipeline.io_utils import STAGE3_PATH
from substrate.pipeline.translation_pipeline.prompts_translation import (
    TRANSLATION_JUDGE_PROMPT,
)

MODEL = "gemini-2.5-pro"
# v2 schema (2026-05-28) — batch=15 empirically clean with apostrophe-only
# prompt. Higher untested; safe to push later if needed.
DEFAULT_BATCH = 15
DEFAULT_CONCURRENCY = 4

SYSTEM_PROMPT = TRANSLATION_JUDGE_PROMPT.system_instruction


# Vertex GenAI schema dialect uses uppercase type names; convert from the
# catalog's lowercase JSON-Schema by recursively uppercasing `type` values.
def _to_vertex_schema(schema: dict) -> dict:
    """Recursively uppercase every `"type"` value in a JSON-Schema dict for the Vertex GenAI dialect."""
    out: dict[str, Any] = {}
    for k, v in schema.items():
        if k == "type" and isinstance(v, str):
            out[k] = v.upper()
        elif isinstance(v, dict):
            out[k] = _to_vertex_schema(v)
        elif isinstance(v, list):
            out[k] = [_to_vertex_schema(x) if isinstance(x, dict) else x for x in v]
        else:
            out[k] = v
    return out


VERTEX_SCHEMA: dict[str, Any] = _to_vertex_schema(TRANSLATION_JUDGE_PROMPT.json_schema)


async def _judge_call(batch: list[dict], timeout: int) -> list[dict]:
    """Send one batch to the Vertex Gemini judge and normalise its response into verdict dicts."""
    prompt = format_batch_prompt(batch)
    raw = await vertex_json(
        prompt,
        VERTEX_SCHEMA,
        system_prompt=SYSTEM_PROMPT,
        model=MODEL,
        timeout=timeout,
    )
    return normalize_verdicts(raw)


async def run(
    batch_size: int = DEFAULT_BATCH,
    concurrency: int = DEFAULT_CONCURRENCY,
    limit: int | None = None,
    timeout: int = 600,
    redo_invalid: bool = False,
) -> dict:
    """Ask the Gemini judge for a verdict on each translation pair (paid; never ran on the full corpus)."""
    return await run_batched(
        judge_call=_judge_call,
        csv_path=STAGE3_PATH,
        judge_label=f"3 (gemini-2.5-pro / prompt={TRANSLATION_JUDGE_PROMPT.prompt_id} v{TRANSLATION_JUDGE_PROMPT.version})",
        batch_size=batch_size,
        concurrency=concurrency,
        timeout=timeout,
        limit=limit,
        redo_invalid=redo_invalid,
    )


def main() -> None:
    """CLI entry point of stage 3."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_force_llm_argument(parser)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=600)
    parser.add_argument("--redo-invalid", action="store_true")
    args = parser.parse_args()
    apply_force_llm(args)
    stats = asyncio.run(
        run(
            batch_size=args.batch_size,
            concurrency=args.concurrency,
            limit=args.limit,
            timeout=args.timeout,
            redo_invalid=args.redo_invalid,
        )
    )
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
