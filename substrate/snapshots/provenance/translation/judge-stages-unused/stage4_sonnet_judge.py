"""Stage 4 — Sonnet 4.6 JSON judge over the shared translation-judge prompt.

Mirrors Stage 3 but routes through the local Claude headless wrapper. Reads the
shared `TRANSLATION_JUDGE_PROMPT` from the catalog — Stages 3 and 4 are now two
independent verifiers of the same VALID/INVALID question.

Sonnet's structured-output mode chokes on long batches
(`error_max_structured_output_retries`), so we use plain `generate_text` and
parse the response manually; `normalize_verdicts` tolerates the
`{"verdicts": [...]}` wrapping the catalog prompt enforces by instruction.

Counts against the Claude weekly subscription quota, NOT the Vertex trial.

Run from the project root:

    python -m substrate.pipeline.translation_pipeline.stage4_sonnet_judge \
        [--batch-size 5] [--concurrency 3] [--limit N]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re

from utils.generation.claude import generate_text as claude_text
from utils.llm_switch import add_force_llm_argument, apply_force_llm
from substrate.pipeline.translation_pipeline._judge_common import (
    format_batch_prompt,
    normalize_verdicts,
    run_batched,
)
from substrate.pipeline.translation_pipeline.io_utils import STAGE4_PATH
from substrate.pipeline.translation_pipeline.prompts_translation import (
    TRANSLATION_JUDGE_PROMPT,
)

MODEL = "claude-sonnet-4-6"
# Empirical batch limit timeline (2026-05-28):
#   batch=30 + generate_json strict schema → error_max_structured_output_retries
#   batch=10 + generate_text + old prompt (with quotes) → 2/3 ValueError parse fails
#   batch=5  + generate_text + new prompt (apostrophes only) → 6/6 clean
#   batch=15 + generate_text + new prompt → 1/1 clean (post-prompt-fix re-test)
# Going with 15 as the conservative-but-fast default.
DEFAULT_BATCH = 15
DEFAULT_CONCURRENCY = 3

SYSTEM_PROMPT = TRANSLATION_JUDGE_PROMPT.system_instruction


def _parse_response(text: str) -> object:
    """Extract a JSON object/array from the model's text response.

    Tolerant of ```json fences and surrounding prose.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass
    for pattern in (r"\{.*\}", r"\[.*\]"):
        m = re.search(pattern, cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                continue
    raise ValueError(f"Could not parse JSON from Sonnet response: {text[:300]!r}")


async def _judge_call(batch: list[dict], timeout: int) -> list[dict]:
    """Send one batch to the Claude judge, parse its free-text response, and normalise it into verdict dicts."""
    prompt = format_batch_prompt(batch)
    text = await claude_text(
        prompt,
        system_prompt=SYSTEM_PROMPT,
        model=MODEL,
        timeout=timeout,
    )
    raw = _parse_response(text)
    return normalize_verdicts(raw)


async def run(
    batch_size: int = DEFAULT_BATCH,
    concurrency: int = DEFAULT_CONCURRENCY,
    limit: int | None = None,
    timeout: int = 900,
    redo_invalid: bool = False,
) -> dict:
    """Ask the Claude judge for a verdict on each translation pair (paid; never ran on the full corpus)."""
    return await run_batched(
        judge_call=_judge_call,
        csv_path=STAGE4_PATH,
        judge_label=f"4 (sonnet-4-6 / prompt={TRANSLATION_JUDGE_PROMPT.prompt_id} v{TRANSLATION_JUDGE_PROMPT.version})",
        batch_size=batch_size,
        concurrency=concurrency,
        timeout=timeout,
        limit=limit,
        redo_invalid=redo_invalid,
    )


def main() -> None:
    """CLI entry point of stage 4."""
    parser = argparse.ArgumentParser(description=__doc__)
    add_force_llm_argument(parser)
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH)
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--timeout", type=int, default=900)
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
