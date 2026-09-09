"""Stage 5 — HITL queue + czech-amazon.json assembly.

Joins the four per-stage snapshots into the final outputs:

    stage5-hitl-queue.jsonl  -- one row per item where the pipeline did NOT
                                 unanimously accept the translation. Schema
                                 per row (v2, 2026-05-28):
        {
          "item_id", "kind", "source_user_id", "asin",
          "en", "cz_raw",
          "comet_score", "comet_status",
          "gemini_verdict", "gemini_fixes": [{replace, with, why}, ...],
          "sonnet_verdict", "sonnet_fixes": [{replace, with, why}, ...],
          "final_cz": null,           # to be filled by human
          "hitl_reason": "<+-joined bitmask of failures>"
        }
        Both judges emit `fixes` arrays per the v2 contract documented in
        prompts_translation.TRANSLATION_JUDGE_PROMPT. A human reviewer can
        accept the gemini fixes, the sonnet fixes, both, neither, or write
        a final string from scratch.

    czech-amazon.json        -- mirrors english-amazon.json's per-user shape
                                 (`reviewerID`, `group`, `reviews`, `products`)
                                 but with every text field replaced by its
                                 final Czech value (or null for HITL-pending).

Acceptance rule:
    final_cz = cz_raw    iff comet_status == "PASS"
                          AND gemini_verdict == "VALID"
                          AND sonnet_verdict == "VALID"
    otherwise final_cz = null and the item enters the HITL queue.

Run from the project root:

    python -m substrate.pipeline.translation_pipeline.stage5_assemble
"""

from __future__ import annotations

import argparse
import json
import time

from substrate.pipeline.translation_pipeline.io_utils import (
    CZECH_USERS_PATH,
    ENGLISH_USERS_PATH,
    STAGE2_PATH,
    STAGE3_PATH,
    STAGE4_PATH,
    STAGE5_HITL_PATH,
    load_stage1,
    read_csv,
    write_jsonl,
)


def _parse_fixes(raw: str | None) -> list[dict]:
    """Decode the `fixes_json` CSV column into a list of fix dicts."""
    if not raw:
        return []
    try:
        v = json.loads(raw)
    except json.JSONDecodeError:
        return []
    return v if isinstance(v, list) else []


def _decide_final(
    comet_row: dict | None, g_row: dict | None, s_row: dict | None
) -> tuple[str | None, list[str]]:
    """Return (final_cz_or_None, list_of_hitl_reasons)."""
    reasons: list[str] = []
    if not comet_row:
        reasons.append("COMET_MISSING")
    elif comet_row.get("status") != "PASS":
        reasons.append(f"COMET_{comet_row.get('status', 'UNKNOWN')}")

    if not g_row:
        reasons.append("GEMINI_MISSING")
    elif g_row.get("verdict") != "VALID":
        reasons.append(f"GEMINI_{g_row.get('verdict', 'UNKNOWN')}")

    if not s_row:
        reasons.append("SONNET_MISSING")
    elif s_row.get("verdict") != "VALID":
        reasons.append(f"SONNET_{s_row.get('verdict', 'UNKNOWN')}")

    return (None, reasons) if reasons else ("__USE_CZ_RAW__", reasons)


def assemble() -> dict:
    """Merge the stage 1-4 outputs into the final per-item verdicts and the review queue; return the assembled dict."""
    stage1 = load_stage1()
    if not stage1:
        raise RuntimeError("stage1-translate.json missing — run Stage 1 first.")
    comet = read_csv(STAGE2_PATH)
    gemini = read_csv(STAGE3_PATH)
    sonnet = read_csv(STAGE4_PATH)

    final_by_id: dict[str, str | None] = {}
    hitl_rows: list[dict] = []
    stats: dict = {
        "total_items": len(stage1),
        "accepted": 0,
        "hitl": 0,
        "by_reason": {},
    }

    for item_id, rec in stage1.items():
        c_row = comet.get(item_id)
        g_row = gemini.get(item_id)
        s_row = sonnet.get(item_id)
        outcome, reasons = _decide_final(c_row, g_row, s_row)

        if outcome == "__USE_CZ_RAW__":
            final_by_id[item_id] = rec.get("cz_raw") or None
            stats["accepted"] += 1
        else:
            final_by_id[item_id] = None
            stats["hitl"] += 1
            for r in reasons:
                stats["by_reason"][r] = stats["by_reason"].get(r, 0) + 1
            hitl_rows.append(
                {
                    "item_id": item_id,
                    "kind": rec.get("kind"),
                    "source_user_id": rec.get("source_user_id"),
                    "asin": rec.get("asin"),
                    "en": rec.get("en"),
                    "cz_raw": rec.get("cz_raw"),
                    "comet_score": (c_row or {}).get("comet_score"),
                    "comet_status": (c_row or {}).get("status"),
                    "gemini_verdict": (g_row or {}).get("verdict"),
                    "gemini_fixes": _parse_fixes((g_row or {}).get("fixes_json")),
                    "sonnet_verdict": (s_row or {}).get("verdict"),
                    "sonnet_fixes": _parse_fixes((s_row or {}).get("fixes_json")),
                    "final_cz": None,
                    "hitl_reason": "+".join(reasons),
                }
            )

    write_jsonl(STAGE5_HITL_PATH, hitl_rows)

    en_users = json.loads(ENGLISH_USERS_PATH.read_text(encoding="utf-8"))
    cz_users: list[dict] = []
    for u in en_users:
        cz_reviews = []
        for r in u["reviews"]:
            rid = r["review_id"]
            cz_reviews.append(
                {
                    "review_id": rid,
                    "asin": r["asin"],
                    "summary": final_by_id.get(f"rs::{rid}"),
                    "reviewText": final_by_id.get(f"rt::{rid}"),
                    "overall": r.get("overall"),
                    "helpful": r.get("helpful"),
                    "unixReviewTime": r.get("unixReviewTime"),
                    "reviewerName": r.get("reviewerName"),
                }
            )
        cz_products = []
        for p in u["products"]:
            cz_products.append(
                {
                    "asin": p["asin"],
                    "title": final_by_id.get(f"pt::{p['asin']}"),
                }
            )
        cz_users.append(
            {
                "reviewerID": u["reviewerID"],
                "group": u["group"],
                "reviews": cz_reviews,
                "products": cz_products,
            }
        )

    CZECH_USERS_PATH.write_text(
        json.dumps(cz_users, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    stats["out_czech_users"] = str(CZECH_USERS_PATH)
    stats["out_hitl"] = str(STAGE5_HITL_PATH)
    return stats


def main() -> None:
    """CLI entry point of stage 5."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args()
    start = time.time()
    stats = assemble()
    stats["elapsed_seconds"] = round(time.time() - start, 2)
    print(json.dumps(stats, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
