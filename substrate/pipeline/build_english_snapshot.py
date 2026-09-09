"""The ``english`` step of the substrate chain: stratified Amazon users -> cleaned English snapshot.

Reads ``data_acquisition/stratified_500_users.json`` (the ``amazon`` step's output), cleans
every text field with ``utils.text_hygiene.clean_text`` (HTML entities,
mojibake, invisible characters, odd whitespace) and emits:

- ``snapshots/intermediate/english-amazon.json``   per-user canonical shape
- ``snapshots/intermediate/english-items.jsonl``   flat per-item translation queue

This is the point where the ORIGINAL Amazon text is cleaned. The translation
(stage 1) ran once on 2026-05-29 against the queue this script produced then;
``--check-against-frozen`` asserts that every item in the queue rebuilt today
has a translation in the frozen ``stage1-translate.json`` (the frozen run may
cover more), so the join in ``build_clean_snapshots.py`` stays valid.

item_id format:
  - review summary  : "rs::<reviewerID>::<asin>::<unixReviewTime>"
  - review text     : "rt::<reviewerID>::<asin>::<unixReviewTime>"
  - product title   : "pt::<asin>"

Run:
    python -m substrate.pipeline.build_english_snapshot --force --check-against-frozen
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from utils.file_safety import require_can_write
from utils.paths import (
    AMAZON_EN_INTERMEDIATE,
    ENGLISH_ITEMS,
    STAGE1_TRANSLATE,
    STRATIFIED_500_USERS,
)
from utils.text_hygiene import clean_text


# ---------------------------------------------------------------------------
# Item identity
# ---------------------------------------------------------------------------


def review_id(reviewer_id: str, asin: str, unix_time: int) -> str:
    """Stable per-review key ``reviewer::asin::unixtime`` that joins the queue to the frozen translation."""
    return f"{reviewer_id}::{asin}::{unix_time}"


# ---------------------------------------------------------------------------
# Cleaning and queue
# ---------------------------------------------------------------------------


def build(stratified: Path, out_users: Path, out_items: Path) -> dict:
    """Clean the stratified reviewers' text, write the English snapshot and the per-item translation queue; return counts."""
    raw = json.loads(stratified.read_text(encoding="utf-8"))
    out_users.parent.mkdir(parents=True, exist_ok=True)

    users_out: list[dict] = []
    items: list[dict] = []
    seen_product_asins: set[str] = set()

    for user in raw:
        rev_records = []
        for r in user["reviews"]:
            rid = review_id(user["reviewerID"], r["asin"], r.get("unixReviewTime", 0))
            summary = clean_text(r.get("summary")) or ""
            text = clean_text(r.get("reviewText")) or ""
            rev_records.append(
                {
                    "review_id": rid,
                    "asin": r["asin"],
                    "summary": summary,
                    "reviewText": text,
                    "overall": r.get("overall"),
                    "helpful": r.get("helpful"),
                    "unixReviewTime": r.get("unixReviewTime"),
                    "reviewerName": clean_text(r.get("reviewerName")),
                }
            )
            if summary:
                items.append(
                    {
                        "item_id": f"rs::{rid}",
                        "kind": "review_summary",
                        "source_user_id": user["reviewerID"],
                        "asin": r["asin"],
                        "en": summary,
                    }
                )
            if text:
                items.append(
                    {
                        "item_id": f"rt::{rid}",
                        "kind": "review_text",
                        "source_user_id": user["reviewerID"],
                        "asin": r["asin"],
                        "en": text,
                    }
                )

        prod_records = []
        for p in user["products"]:
            asin = p["asin"]
            title = clean_text(p.get("title")) or ""
            prod_records.append({"asin": asin, "title": title})
            if title and asin not in seen_product_asins:
                items.append(
                    {
                        "item_id": f"pt::{asin}",
                        "kind": "product_title",
                        "source_user_id": None,
                        "asin": asin,
                        "en": title,
                    }
                )
                seen_product_asins.add(asin)

        users_out.append(
            {
                "reviewerID": user["reviewerID"],
                "group": user["group"],
                "reviews": rev_records,
                "products": prod_records,
            }
        )

    out_users.write_text(json.dumps(users_out, indent=2, ensure_ascii=False), encoding="utf-8")
    with out_items.open("w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")

    by_kind: dict[str, int] = {}
    for it in items:
        by_kind[it["kind"]] = by_kind.get(it["kind"], 0) + 1
    return {
        "users": len(users_out),
        "items_total": len(items),
        "items_by_kind": by_kind,
        "unique_products": len(seen_product_asins),
        "out_users": str(out_users),
        "out_items": str(out_items),
    }


# ---------------------------------------------------------------------------
# Frozen-run check
# ---------------------------------------------------------------------------


def check_against_frozen(out_items: Path, stage1: Path) -> dict:
    """Assert every item in the rebuilt queue has a Czech translation.

    The condition that matters is one-directional: the join in
    ``build_clean_snapshots.py`` needs a translation for every item it queues, so
    ``missing_in_frozen`` must be zero. Items the frozen run translated but the
    current cohort no longer uses are expected and harmless -- the translation
    covers 500 reviewers and the stratification now links 425 of them, the rest
    of the substrate's contacts being prospects with no Amazon history. Those
    leftovers are reported, not enforced, because the frozen artifact cannot be
    trimmed: it is evidence of a paid run that cannot be repeated.
    """
    rebuilt = {
        json.loads(line)["item_id"]
        for line in out_items.read_text(encoding="utf-8").splitlines()
        if line.strip()
    }
    frozen_map = json.loads(stage1.read_text(encoding="utf-8"))
    frozen = set(frozen_map)
    users = {v.get("source_user_id") for v in frozen_map.values() if v.get("source_user_id")}
    result = {
        "items": len(rebuilt),
        "frozen": len(frozen),
        "missing_in_frozen": len(rebuilt - frozen),
        "extra_in_frozen": len(frozen - rebuilt),
        "users": len(users),
    }
    if result["missing_in_frozen"]:
        sample = sorted(rebuilt - frozen)[:5]
        raise RuntimeError(
            "rebuilt queue contains items the frozen translation does not cover, so they "
            f"would have no Czech text: missing_in_frozen={result['missing_in_frozen']} "
            f"sample={sample}. The stratification may only select reviewers listed in "
            "snapshots/provenance/translation/frozen-reviewers.json."
        )
    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point of the ``english`` step (``--check-against-frozen`` proves every queued item has a frozen translation)."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--force", action="store_true", help="overwrite the committed intermediate snapshots"
    )
    parser.add_argument(
        "--check-against-frozen",
        action="store_true",
        help="fail if any rebuilt queue item lacks a translation in stage1-translate.json",
    )
    args = parser.parse_args()
    require_can_write(AMAZON_EN_INTERMEDIATE, overwrite=args.force, artifact="english-amazon.json")
    require_can_write(ENGLISH_ITEMS, overwrite=args.force, artifact="english-items.jsonl")
    stats = build(STRATIFIED_500_USERS, AMAZON_EN_INTERMEDIATE, ENGLISH_ITEMS)
    if args.check_against_frozen:
        stats["frozen_check"] = check_against_frozen(ENGLISH_ITEMS, STAGE1_TRANSLATE)
    print(json.dumps(stats, indent=2))


if __name__ == "__main__":
    main()
