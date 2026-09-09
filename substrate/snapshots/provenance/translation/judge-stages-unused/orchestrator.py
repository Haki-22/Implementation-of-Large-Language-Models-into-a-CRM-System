"""Entry point for the 5-stage Amazon Reviews translation pipeline.

FROZEN since 2026-05-29: stage 1 ran once, stages 2-5 never ran on the shipped
artifact; see README.md in this directory. Kept as documentation of the design
and for the bake-off provenance.

Each stage is independently runnable (its own module + `--limit`/`--user`
filters), but this orchestrator chains them so a smoke or full run is one
command.

The default behaviour is to:
    1. Translate every English item not yet present in stage1-translate.json
    2. COMET-score every (en, cz_raw) pair not yet in stage2-comet.csv
    3. Re-translate (Stage 1 retry) every item that returned RETRY from Stage 2
    4. COMET-rescore the retried items (--retry-only)
    5. Gemini judge every item not yet in stage3-gemini-judge.csv
    6. Sonnet judge every item not yet in stage4-sonnet-judge.csv
    7. Assemble czech-amazon.json + stage5-hitl-queue.jsonl

Filters:
    --user REVIEWERID   restrict Stage 1 (and downstream by construction) to a single user
    --limit N           cap Stage 1 queue to N items (smoke test)
    --skip-stage N      skip stage N (1..5); useful for re-running a single stage
    --only-stage N      run only stage N
    --no-judges         skip Stages 3 and 4 (for cheap iteration on Stage 2 alone)

Historical run command (2026-05-29; needs GOOGLE_APPLICATION_CREDENTIALS and
GOOGLE_CLOUD_PROJECT in the environment, stage 1 additionally --unfreeze):

    python -m substrate.pipeline.translation_pipeline.orchestrator \
            --user ADLVFFE4VBT8 --limit 60
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from typing import Any

from substrate.pipeline.translation_pipeline import (
    stage1_translate,
    stage2_comet,
    stage3_gemini_judge,
    stage4_sonnet_judge,
    stage5_assemble,
)


async def run_pipeline(
    *,
    user_filter: str | None,
    limit: int | None,
    translate_concurrency: int,
    judge_batch_size: int,
    judge_concurrency: int,
    comet_batch_size: int,
    use_gpu: bool,
    skip_stages: set[int],
    only_stage: int | None,
    no_judges: bool,
    no_retry: bool,
) -> dict:
    """Run the translation stages in sequence with the given filters and concurrency (stage 1 is frozen)."""
    results: dict[str, Any] = {}

    def _should_run(n: int) -> bool:
        """Return whether stage `n` should run, given `only_stage`, `skip_stages` and `no_judges`."""
        if only_stage is not None:
            return n == only_stage
        if n in skip_stages:
            return False
        if no_judges and n in (3, 4):
            return False
        return True

    overall_start = time.time()

    # --- Stage 1 ----------------------------------------------------------
    if _should_run(1):
        print("=== Stage 1: Google Cloud Translation v3 ===")
        results["stage1"] = await stage1_translate.run(
            limit=limit,
            user_filter=user_filter,
            concurrency=translate_concurrency,
        )
    # --- Stage 2 ----------------------------------------------------------
    if _should_run(2):
        print("=== Stage 2: COMET-Kiwi ===")
        results["stage2"] = stage2_comet.run(
            batch_size=comet_batch_size,
            use_gpu=use_gpu,
        )
        # Retry loop: if any item is RETRY, re-fire Stage 1 just for those,
        # then re-score Stage 2 with --retry-only.
        if not no_retry:
            retry_ids = {
                rid
                for rid, row in stage2_comet._load_existing_rows().items()
                if row.get("status") == "RETRY"
            }
            if retry_ids:
                print(f"=== Stage 1 retry: {len(retry_ids)} items ===")
                results["stage1_retry"] = await stage1_translate.run(
                    concurrency=translate_concurrency,
                    redo_ids=retry_ids,
                )
                print("=== Stage 2 retry-rescore ===")
                results["stage2_retry"] = stage2_comet.run(
                    batch_size=comet_batch_size,
                    use_gpu=use_gpu,
                    retry_only=True,
                )

    # --- Stage 3 ----------------------------------------------------------
    if _should_run(3):
        print("=== Stage 3: Gemini 2.5 Pro judge ===")
        results["stage3"] = await stage3_gemini_judge.run(
            batch_size=judge_batch_size,
            concurrency=judge_concurrency,
            limit=None,
        )
    # --- Stage 4 ----------------------------------------------------------
    if _should_run(4):
        print("=== Stage 4: Sonnet 4.6 judge ===")
        results["stage4"] = await stage4_sonnet_judge.run(
            batch_size=judge_batch_size,
            concurrency=max(1, judge_concurrency // 2),
            limit=None,
        )
    # --- Stage 5 ----------------------------------------------------------
    if _should_run(5):
        print("=== Stage 5: assemble + HITL queue ===")
        results["stage5"] = stage5_assemble.assemble()

    results["overall_elapsed_seconds"] = round(time.time() - overall_start, 1)
    return results


def main() -> None:
    """CLI entry point of the (frozen) translation pipeline."""
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--user", type=str, default=None)
    p.add_argument("--limit", type=int, default=None)
    p.add_argument("--translate-concurrency", type=int, default=8)
    p.add_argument("--judge-batch-size", type=int, default=30)
    p.add_argument("--judge-concurrency", type=int, default=4)
    p.add_argument("--comet-batch-size", type=int, default=16)
    p.add_argument("--gpu", action="store_true")
    p.add_argument("--skip-stage", type=int, action="append", default=[])
    p.add_argument("--only-stage", type=int, default=None)
    p.add_argument("--no-judges", action="store_true")
    p.add_argument("--no-retry", action="store_true")
    args = p.parse_args()
    stats = asyncio.run(
        run_pipeline(
            user_filter=args.user,
            limit=args.limit,
            translate_concurrency=args.translate_concurrency,
            judge_batch_size=args.judge_batch_size,
            judge_concurrency=args.judge_concurrency,
            comet_batch_size=args.comet_batch_size,
            use_gpu=args.gpu,
            skip_stages=set(args.skip_stage),
            only_stage=args.only_stage,
            no_judges=args.no_judges,
            no_retry=args.no_retry,
        )
    )
    print()
    print("=" * 60)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
