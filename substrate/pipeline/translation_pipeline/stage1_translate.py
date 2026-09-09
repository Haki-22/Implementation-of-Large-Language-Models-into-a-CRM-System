"""Stage 1 — Google Cloud Translation v3 (EN -> CS).

Reads ``snapshots/intermediate/english-items.jsonl``, translates each ``en``
string and writes ``snapshots/intermediate/stage1-translate.json`` keyed by
``item_id``. The frozen result of the one-time run lives under
``snapshots/provenance/translation/`` and is never written to.

Resumable: items the frozen file already holds with a non-empty ``cz_raw`` are
skipped, so a re-run only translates what is missing.

Run from the project root:

    python -m substrate.pipeline.translation_pipeline.stage1_translate \
        [--limit N] [--user REVIEWERID] [--concurrency K]
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time

from google.cloud import translate_v3

from substrate.pipeline.translation_pipeline.io_utils import (
    ENGLISH_ITEMS_PATH,
    load_stage1,
    read_jsonl,
    save_stage1,
)

LOCATION = "global"


# ---------------------------------------------------------------------------
# Google Cloud client
# ---------------------------------------------------------------------------


def _project_id() -> str:
    """Google Cloud project id from the environment only; no file lookup on disk."""
    project = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise SystemExit(
            "GOOGLE_CLOUD_PROJECT is not set. This stage is frozen; if you really re-run it, "
            "export GOOGLE_CLOUD_PROJECT and GOOGLE_APPLICATION_CREDENTIALS yourself."
        )
    return project


_PROJECT_ID: str | None = None
_CLIENT: translate_v3.TranslationServiceClient | None = None


def _get_project_id() -> str:
    """Return the memoized Google Cloud project id, resolving it from the environment on first call."""
    global _PROJECT_ID
    if _PROJECT_ID is None:
        _PROJECT_ID = _project_id()
    return _PROJECT_ID


def _client() -> translate_v3.TranslationServiceClient:
    """Return the memoized `TranslationServiceClient`, constructing it on first call."""
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = translate_v3.TranslationServiceClient()
    return _CLIENT


async def translate_batch(texts: list[str], target: str = "cs") -> list[str]:
    """Translate one batch with Google Cloud Translation v3 (paid; production output is frozen)."""
    if not texts:
        return []
    project_id = _get_project_id()
    parent = f"projects/{project_id}/locations/{LOCATION}"
    loop = asyncio.get_running_loop()

    def _call() -> list[str]:
        """Make the synchronous `translate_text` request; run via `run_in_executor` below."""
        resp = _client().translate_text(
            request={
                "parent": parent,
                "contents": texts,
                "mime_type": "text/plain",
                "source_language_code": "en-US",
                "target_language_code": target,
            }
        )
        return [t.translated_text for t in resp.translations]

    return await loop.run_in_executor(None, _call)


async def _translate_one(
    item: dict, sem: asyncio.Semaphore, prev_attempts: int = 0
) -> tuple[str, dict]:
    """Single-item translate with semaphore + error capture.

    `prev_attempts` is the attempt count already recorded on disk for this
    `item_id`; it is passed in explicitly so a resumed run correctly increments
    rather than resetting to 1.
    """
    async with sem:
        try:
            cz = (await translate_batch([item["en"]]))[0]
            return item["item_id"], {
                **item,
                "cz_raw": cz,
                "attempts": prev_attempts + 1,
                "error": None,
            }
        except Exception as exc:  # noqa: BLE001
            return item["item_id"], {
                **item,
                "cz_raw": "",
                "attempts": prev_attempts + 1,
                "error": f"{type(exc).__name__}: {exc}",
            }


async def run(
    limit: int | None = None,
    user_filter: str | None = None,
    concurrency: int = 8,
    redo_ids: set[str] | None = None,
) -> dict:
    """Translate the queue items, optionally limited or filtered, persisting stage-1 results incrementally."""
    _get_project_id()  # fails loudly when GOOGLE_CLOUD_PROJECT is unset

    existing = load_stage1()
    queue: list[dict] = []
    for it in read_jsonl(ENGLISH_ITEMS_PATH):
        if user_filter and it.get("source_user_id") != user_filter:
            # product titles have source_user_id=null - keep them too when
            # filtering on a single user so we can translate their products.
            if not (
                it["kind"] == "product_title" and it["asin"]
                # too lax, acceptable for a smoke run
            ):
                continue
        prev = existing.get(it["item_id"])
        if prev and prev.get("cz_raw") and (not redo_ids or it["item_id"] not in redo_ids):
            continue
        queue.append(it)
        if limit and len(queue) >= limit:
            break

    print(f"stage1: {len(queue)} items to translate (concurrency={concurrency})")
    sem = asyncio.Semaphore(concurrency)
    start = time.time()
    done = 0
    tasks = [
        asyncio.create_task(
            _translate_one(
                it,
                sem,
                prev_attempts=int((existing.get(it["item_id"]) or {}).get("attempts") or 0),
            )
        )
        for it in queue
    ]
    for fut in asyncio.as_completed(tasks):
        item_id, rec = await fut
        existing[item_id] = rec
        done += 1
        if done % 100 == 0 or done == len(queue):
            elapsed = time.time() - start
            rate = done / elapsed if elapsed > 0 else 0.0
            print(f"  {done}/{len(queue)} ({rate:.1f}/s, {elapsed:.0f}s)")
            # Incremental checkpoint so a crash mid-run doesn't lose progress.
            save_stage1(existing)

    save_stage1(existing)
    elapsed = time.time() - start
    errors = sum(1 for r in existing.values() if r.get("error"))
    return {
        "translated_now": done,
        "total_in_stage1": len(existing),
        "errors_total": errors,
        "elapsed_seconds": round(elapsed, 1),
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point; refuses to run without ``--unfreeze`` and the model-call switch."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--user", type=str, default=None, help="reviewerID filter")
    parser.add_argument("--concurrency", type=int, default=8)
    parser.add_argument(
        "--unfreeze",
        action="store_true",
        help="acknowledge that stage 1 ran once on 2026-05-29 and that re-running costs API money",
    )
    args = parser.parse_args()
    if not args.unfreeze:
        print(
            "stage1 is FROZEN: the translation ran once on 2026-05-29 and its result is "
            "substrate/snapshots/provenance/translation/stage1-translate.json (see translation_pipeline/README.md). "
            "Pass --unfreeze only if you really intend to spend on the API again.",
            file=sys.stderr,
        )
        raise SystemExit(3)
    # The model-call switch must fail closed *before* anything is sent to the API.
    from utils.llm_switch import require_llm_calls

    require_llm_calls("google-translate")
    stats = asyncio.run(run(limit=args.limit, user_filter=args.user, concurrency=args.concurrency))
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
