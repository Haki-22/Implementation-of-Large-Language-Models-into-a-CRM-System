"""Shared batching + IO logic for Stage 3 (Gemini) and Stage 4 (Sonnet) judges.

Both judges:
- read `stage1-translate.json`
- judge items in batches of N (default 15)
- return a JSON object `{"verdicts": [...]}` per the v2 contract
  documented in `prompts_translation.TRANSLATION_JUDGE_PROMPT`
- write a CSV with one row per item

Per the v2 contract (2026-05-28), each verdict carries:
  - item_id
  - verdict: "VALID" | "INVALID"
  - fixes:   list of {replace, with, why} entries — empty when VALID

The `fixes` array is JSON-encoded into a single CSV column `fixes_json` so
the snapshot stays a flat CSV; Stage 5 parses it back to a list during
assembly.
"""

from __future__ import annotations

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from substrate.pipeline.translation_pipeline.io_utils import (
    chunked,
    load_stage1,
    read_csv,
    write_csv,
)

# v2 CSV schema: fixes serialised as JSON in one column.
CSV_FIELDNAMES = ["item_id", "verdict", "fixes_json"]

# Type alias: (batch of items, timeout_s) -> list of verdict dicts
JudgeCall = Callable[[list[dict], int], Awaitable[list[dict]]]


def format_batch_prompt(items: list[dict]) -> str:
    """Render the user-prompt body — same for both providers."""
    payload = [{"item_id": it["item_id"], "en": it["en"], "cz": it["cz_raw"]} for it in items]
    return "Polozky k posouzeni:\n" + json.dumps(payload, ensure_ascii=False, indent=2)


def select_queue(
    stage1: dict[str, dict],
    existing: dict[str, dict],
    redo_invalid: bool,
    limit: int | None,
) -> list[dict]:
    """Build the list of stage1 records that still need judging."""
    queue: list[dict] = []
    for _item_id, rec in stage1.items():
        if not rec.get("cz_raw") or rec.get("error"):
            continue
        prev = existing.get(rec["item_id"])
        if prev:
            if prev.get("verdict") == "VALID":
                continue
            if prev.get("verdict") == "INVALID" and not redo_invalid:
                continue
        queue.append(rec)
        if limit and len(queue) >= limit:
            break
    return queue


def normalize_verdicts(raw: object) -> list[dict]:
    """Normalise provider response into a list of verdict dicts.

    Accepts:
      - {"verdicts": [...]} (canonical v2 shape)
      - raw [...] (top-level array — Vertex sometimes returns this)
      - single {item_id, ...} dict (last resort)
    """
    if isinstance(raw, list):
        return raw
    if isinstance(raw, dict):
        for key in ("verdicts", "items", "results", "data"):
            v = raw.get(key)
            if isinstance(v, list):
                return v
        if "item_id" in raw:
            return [raw]
    return []


def _coerce_fixes(raw: object) -> list[dict]:
    """Defensive coercion of the model's `fixes` field into a list of dicts.

    Tolerates:
      - missing field (returns [])
      - string with JSON-encoded array
      - already-a-list
      - single dict (wraps into list)
    Each fix dict is normalised to keys {replace, with, why} with empty
    string fallbacks so the CSV row never carries None.
    """
    if raw is None or raw == "":
        return []
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except json.JSONDecodeError:
            return []
    if isinstance(raw, dict):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    out: list[dict] = []
    for f in raw:
        if not isinstance(f, dict):
            continue
        out.append(
            {
                "replace": (f.get("replace") or "").strip(),
                "with": (f.get("with") or "").strip(),
                "why": (f.get("why") or "").strip(),
            }
        )
    return out


def _row_invalid(item_id: str, reason_tag: str) -> dict:
    """CSV row builder for control-plane INVALIDs (errors, missing, duplicates).

    Encodes the reason as a single fix with `replace=""` so a HITL consumer
    seeing this row knows the verdict came from the pipeline itself, not
    from a real judgment over the translation content.
    """
    return {
        "item_id": item_id,
        "verdict": "INVALID",
        "fixes_json": json.dumps(
            [{"replace": "", "with": "", "why": reason_tag}], ensure_ascii=False
        ),
    }


async def run_batched(
    *,
    judge_call: JudgeCall,
    csv_path: Path,
    judge_label: str,
    batch_size: int,
    concurrency: int,
    timeout: int,
    limit: int | None,
    redo_invalid: bool,
) -> dict:
    """Generic batched judging loop used by both Stage 3 and Stage 4."""
    stage1 = load_stage1()
    if not stage1:
        raise RuntimeError("stage1-translate.json missing — run Stage 1 first.")

    existing = read_csv(csv_path)
    queue = select_queue(stage1, existing, redo_invalid, limit)
    total_batches = (len(queue) + batch_size - 1) // batch_size
    print(
        f"stage {judge_label}: judging {len(queue)} items "
        f"(batch_size={batch_size}, concurrency={concurrency}, batches={total_batches})"
    )
    if not queue:
        return {"judged": 0, "total_in_csv": len(existing)}

    new_rows: dict[str, dict] = dict(existing)
    sem = asyncio.Semaphore(concurrency)
    start = time.time()
    completed = 0
    batch_errors: list[dict] = []

    async def _do(batch: list[dict], idx: int) -> None:
        """Judge one batch under the semaphore, writing its rows (or control-plane INVALIDs on failure) into `new_rows`."""
        nonlocal completed
        async with sem:
            try:
                verdicts = await judge_call(batch, timeout)
            except Exception as exc:  # noqa: BLE001
                batch_errors.append({"batch_idx": idx, "error": f"{type(exc).__name__}: {exc}"})
                for it in batch:
                    new_rows[it["item_id"]] = _row_invalid(
                        it["item_id"], f"JUDGE_ERROR: {type(exc).__name__}"
                    )
                completed += len(batch)
                return

            by_id: dict[str, dict] = {}
            duplicate_ids: set[str] = set()
            for v in verdicts:
                returned_id = v.get("item_id")
                if not returned_id:
                    continue
                if returned_id in by_id:
                    duplicate_ids.add(returned_id)
                else:
                    by_id[returned_id] = v
            for it in batch:
                if it["item_id"] in duplicate_ids:
                    new_rows[it["item_id"]] = _row_invalid(it["item_id"], "JUDGE_DUPLICATE_ITEM")
                    continue
                v = by_id.get(it["item_id"])
                if not v:
                    new_rows[it["item_id"]] = _row_invalid(it["item_id"], "JUDGE_MISSING_ITEM")
                    continue
                verdict = v.get("verdict", "INVALID")
                fixes = _coerce_fixes(v.get("fixes"))
                # VALID rows carry empty fixes list. INVALID rows must carry
                # at least one fix — if the model emitted INVALID with empty
                # fixes, downgrade the row to a control-plane INVALID so
                # downstream HITL knows the judge was incoherent.
                if verdict == "INVALID" and not fixes:
                    new_rows[it["item_id"]] = _row_invalid(
                        it["item_id"], "JUDGE_INVALID_WITHOUT_FIXES"
                    )
                    continue
                if verdict == "VALID":
                    fixes = []  # ignore any spurious fixes on a VALID verdict
                new_rows[it["item_id"]] = {
                    "item_id": it["item_id"],
                    "verdict": verdict,
                    "fixes_json": json.dumps(fixes, ensure_ascii=False),
                }
            completed += len(batch)

    tasks = [
        asyncio.create_task(_do(batch, idx)) for idx, batch in enumerate(chunked(queue, batch_size))
    ]
    flush_every = max(1, total_batches // 20)
    for done_idx, fut in enumerate(asyncio.as_completed(tasks), start=1):
        await fut
        if done_idx % flush_every == 0 or done_idx == total_batches:
            write_csv(csv_path, new_rows.values(), CSV_FIELDNAMES)
            elapsed = time.time() - start
            rate = completed / elapsed if elapsed > 0 else 0.0
            print(
                f"  judged {completed}/{len(queue)} "
                f"({rate:.1f}/s, batches {done_idx}/{total_batches})"
            )

    write_csv(csv_path, new_rows.values(), CSV_FIELDNAMES)

    by_verdict = {"VALID": 0, "INVALID": 0}
    for r in new_rows.values():
        by_verdict[r["verdict"]] = by_verdict.get(r["verdict"], 0) + 1
    return {
        "judged": completed,
        "total_in_csv": len(new_rows),
        "by_verdict": by_verdict,
        "batch_errors": len(batch_errors),
        "elapsed_seconds": round(time.time() - start, 1),
    }
