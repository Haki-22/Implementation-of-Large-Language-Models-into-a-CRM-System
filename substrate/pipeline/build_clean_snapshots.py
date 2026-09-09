"""Build clean review snapshots + an English product catalogue.

- **Czech reviews** — they drive the behavioural analysis (OCEAN inference,
  frequent-word lexicons, UC-01's prior-interaction text), so the review text
  must be Czech.
- an **English product catalogue** — the recommendation arms are
  language-agnostic for the headline LLM-vs-classical result, and the secondary
  "does language matter" comparison is dropped (its Czech catalogue would have
  untranslated descriptions). No Czech catalogue is built and nothing extra is
  translated here.

Outputs (in ``snapshots/amazon/``)
----------------------------------
- ``amazon-original-en.json`` — users + their reviews, English text (cleaned).
- ``amazon-translated-cz.json`` — users + their reviews, Czech text from the frozen
  stage-1 translation. Reviews without any Czech translation are dropped rather
  than left as English contamination; a review with only one half translated
  keeps the other field empty.
- ``amazon-catalog-en.json`` — catalogue: asin, title, category, price, description
  (mojibake repaired, HTML entities unescaped, HTML tags stripped).
- ``translation-coverage.json`` — per-reviewer count of English vs. Czech reviews
  (input for the cohort decision; documents translation loss).

All text passes through ``utils.text_hygiene.clean_text`` — the same rules the
English layer was cleaned with in ``build_english_snapshot.py``.

Field sources
-------------
- Bilingual review text + product titles -> ``stage1-translate.json``.
- Review numeric metadata (rating, helpful, timestamp) -> ``english-amazon.json``.
- Product category / price / description -> raw ``meta_Electronics.json.gz``.

Run:
    python -m substrate.pipeline.build_clean_snapshots --force   # build_all step ``clean``
"""

from __future__ import annotations

import argparse
import json
from typing import Any

from substrate.pipeline import packing
from substrate.pipeline.data_acquisition.fetch_and_filter import load_json_gz
from utils.paths import (
    AMAZON_EN_INTERMEDIATE as ENGLISH_AMAZON,
    DOWNLOADS_DIR as RAW,
    REVIEWERS_CZ_SNAPSHOT as OUT_REV_CZ,
    REVIEWERS_EN_SNAPSHOT as OUT_REV_EN,
    SNAPSHOTS_DIR,
    STAGE1_TRANSLATE as STAGE1,
    CATALOG_EN as OUT_ITEMS_EN,
    CATALOG_TITLES_CS,
    TRANSLATION_COVERAGE,
)
from utils.text_hygiene import clean_text

META = RAW / "meta_Electronics.json.gz"
OUT_DIR_AMAZON = SNAPSHOTS_DIR / "amazon"


# ---------------------------------------------------------------------------
# Frozen translation
# ---------------------------------------------------------------------------


def _load_stage1() -> tuple[dict, dict, dict]:
    """Parse the flat translation table into join-ready maps.

    Returns:
        rev_cz: (reviewerID, asin, unixtime_str) -> {"summary": cz, "text": cz}
        title_en: asin -> English product title
        title_cs: asin -> Czech product title (the translator ran over the
            titles too; descriptions were never translated, which is why no
            Czech catalogue is built -- only this title map)
    """
    data = json.loads(STAGE1.read_text(encoding="utf-8"))
    rev_cz: dict[tuple[str, str, str], dict[str, str]] = {}
    title_en: dict[str, str] = {}
    title_cs: dict[str, str] = {}
    for key, value in data.items():
        kind = value.get("kind")
        cz = (value.get("cz_raw") or "").strip()
        en = (value.get("en") or "").strip()
        if kind == "product_title":
            if en:
                title_en[value.get("asin")] = en
            if cz:
                title_cs[value.get("asin")] = cz
            continue
        parts = key.split("::")
        if len(parts) != 4:
            continue
        _, user, kasin, ktime = parts
        slot = "summary" if kind == "review_summary" else "text"
        rev_cz.setdefault((user, kasin, ktime), {})[slot] = cz
    return rev_cz, title_en, title_cs


def _english_title_fallback() -> dict[str, str]:
    """asin -> English title from the per-user ``products`` lists (fallback)."""
    titles: dict[str, str] = {}
    for user in json.loads(ENGLISH_AMAZON.read_text(encoding="utf-8")):
        for product in user.get("products", []):
            asin = product.get("asin")
            title = (product.get("title") or "").strip()
            if asin and title and asin not in titles:
                titles[asin] = title
    return titles


# ---------------------------------------------------------------------------
# Product metadata
# ---------------------------------------------------------------------------


def _load_meta(needed: set[str]) -> dict[str, dict[str, Any]]:
    """Stream the raw Amazon metadata, keep only the needed asins.

    Returns asin -> {"category", "price", "description"}.  ``category`` is the
    second level of the first category path (a readable mid-level label),
    falling back to the most specific level.  ``description`` is returned raw;
    ``catalog_entry`` cleans it.
    """
    meta: dict[str, dict[str, Any]] = {}
    for rec in load_json_gz(META):  # same line parser the stratification uses
        asin = rec.get("asin")
        if asin not in needed:
            continue
        cats = rec.get("categories") or []
        category = None
        if cats and isinstance(cats[0], list) and cats[0]:
            path = cats[0]
            category = path[1] if len(path) > 1 else path[-1]
        meta[asin] = {
            "category": category,
            "price": rec.get("price"),
            "description": rec.get("description"),
        }
        if len(meta) == len(needed):
            break
    return meta


def catalog_entry(asin: str, title: str | None, info: dict[str, Any]) -> dict[str, Any]:
    """One product row: title/description cleaned, HTML stripped from the description."""
    return {
        "asin": asin,
        "title": clean_text(title) or asin,
        "category": info.get("category"),
        "price": info.get("price"),
        "description": clean_text(info.get("description"), strip_html_tags=True),
    }


# ---------------------------------------------------------------------------
# Translation coverage
# ---------------------------------------------------------------------------


def coverage(
    rev_en_out: list[dict[str, Any]], rev_cz_out: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Per-reviewer translation coverage: how many English reviews survived into Czech."""
    cz_counts = {u["reviewerID"]: len(u["reviews"]) for u in rev_cz_out}
    rows = []
    for u in rev_en_out:
        en_n = len(u["reviews"])
        cz_n = cz_counts.get(u["reviewerID"], 0)
        rows.append(
            {
                "reviewerID": u["reviewerID"],
                "group": u["group"],
                "en_reviews": en_n,
                "cz_reviews": cz_n,
                "lost": en_n - cz_n,
                "loss_ratio": round((en_n - cz_n) / en_n, 4) if en_n else 0.0,
            }
        )
    return sorted(rows, key=lambda r: (-r["loss_ratio"], r["reviewerID"]))


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """CLI entry point: join the frozen Czech text with the cleaned English layer and the catalog (build_all step ``clean``)."""
    parser = argparse.ArgumentParser(
        description=(
            "Join stage1-translate.json + raw English Amazon + product metadata "
            "into the clean substrate/snapshots/amazon/*.json snapshots. "
            "Writes amazon-original-en.json, amazon-translated-cz.json, amazon-catalog-en.json "
            "and translation-coverage.json. "
            "Run with --force to actually overwrite the committed snapshots."
        )
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the committed amazon/*.json snapshots in place.",
    )
    args = parser.parse_args()
    if not args.force:
        parser.error(
            "build_clean_snapshots writes large snapshots in place; pass --force to confirm."
        )

    users = json.loads(ENGLISH_AMAZON.read_text(encoding="utf-8"))
    rev_cz, title_en_s1, title_cs_s1 = _load_stage1()
    title_en_fb = _english_title_fallback()

    needed: set[str] = set()
    for user in users:
        for review in user.get("reviews", []):
            needed.add(review.get("asin"))
        for product in user.get("products", []):
            needed.add(product.get("asin"))
    needed.discard(None)
    meta = _load_meta(needed)

    # ---- reviewers (en keeps all; cz keeps only genuinely-translated reviews) ----
    rev_en_out: list[dict[str, Any]] = []
    rev_cz_out: list[dict[str, Any]] = []
    cz_hits = cz_miss = 0
    for user in users:
        rid = user["reviewerID"]
        group = user.get("group")
        en_reviews: list[dict[str, Any]] = []
        cz_reviews: list[dict[str, Any]] = []
        for review in user.get("reviews", []):
            asin = review.get("asin")
            ktime = str(review.get("unixReviewTime"))
            base = {
                "asin": asin,
                "overall": review.get("overall"),
                "helpful": review.get("helpful"),
                "unixReviewTime": review.get("unixReviewTime"),
            }
            en_reviews.append(
                {
                    **base,
                    "summary": clean_text(review.get("summary")) or "",
                    "reviewText": clean_text(review.get("reviewText")) or "",
                }
            )
            translated = rev_cz.get((rid, asin, ktime), {})
            if translated.get("summary") or translated.get("text"):
                cz_hits += 1
                cz_reviews.append(
                    {
                        **base,
                        "summary": clean_text(translated.get("summary")) or "",
                        "reviewText": clean_text(translated.get("text")) or "",
                    }
                )
            else:
                cz_miss += 1
        rev_en_out.append({"reviewerID": rid, "group": group, "reviews": en_reviews})
        rev_cz_out.append({"reviewerID": rid, "group": group, "reviews": cz_reviews})

    # ---- catalogue (English) + the Czech titles the translator produced ----
    items_en: list[dict[str, Any]] = []
    for asin in sorted(needed):
        items_en.append(
            catalog_entry(asin, title_en_s1.get(asin) or title_en_fb.get(asin), meta.get(asin, {}))
        )
    # asin -> Czech title, cleaned like every other translated text (158 titles
    # carry zero-width characters); only the products of this catalogue, no
    # entry for a product the translator never saw. The assembler puts these
    # into Product.name_cs; a missing title stays NULL there.
    titles_cs = {
        asin: title for asin in sorted(needed) if (title := clean_text(title_cs_s1.get(asin)))
    }

    OUT_DIR_AMAZON.mkdir(parents=True, exist_ok=True)
    for path, obj in [
        (OUT_REV_EN, rev_en_out),
        (OUT_REV_CZ, rev_cz_out),
        (OUT_ITEMS_EN, items_en),
    ]:
        path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
        packing.pack(path)  # git ships the .gz; the .json stays for the readers
    CATALOG_TITLES_CS.write_text(
        json.dumps(titles_cs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    cov = coverage(rev_en_out, rev_cz_out)
    TRANSLATION_COVERAGE.write_text(
        json.dumps(
            {"_schema": {"version": "1.0", "source": "build_clean_snapshots.py"}, "rows": cov},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    total_reviews = sum(len(u["reviews"]) for u in rev_en_out)
    with_cat = sum(1 for item in items_en if item["category"])
    with_price = sum(1 for item in items_en if item["price"] not in (None, ""))
    print(f"reviewers: {len(rev_en_out)} users, {total_reviews} reviews (en)")
    print(f"  cz reviews kept: {cz_hits}  dropped (untranslated): {cz_miss}")
    print(f"items (en catalogue): {len(items_en)} products")
    print(f"  with meta category: {with_cat}  with meta price: {with_price}")
    print(f"  with a Czech title from the frozen translation: {len(titles_cs)}")
    zero_cz = sum(1 for r in cov if r["cz_reviews"] == 0)
    heavy = sum(1 for r in cov if r["cz_reviews"] > 0 and r["loss_ratio"] >= 0.75)
    print(f"coverage: reviewers with 0 cz reviews: {zero_cz}, with >=75% lost: {heavy}")
    for path in (OUT_REV_EN, OUT_REV_CZ, OUT_ITEMS_EN, CATALOG_TITLES_CS, TRANSLATION_COVERAGE):
        print(f"  wrote {path.name}")


if __name__ == "__main__":
    main()
