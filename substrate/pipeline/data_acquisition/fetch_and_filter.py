"""The ``amazon`` step of the substrate chain: verify the raw Amazon dumps and stratify 425 reviewers.

Source dataset: Amazon product reviews, "Electronics" 5-core split, 2014
release by McAuley et al. (SNAP, https://snap.stanford.edu/data/web-Amazon.html).
The two files are pinned by size and md5 below. ``--download`` fetches them
into ``downloaded/`` and ``--verify-only`` checks what is on disk. ``downloaded/`` is
gitignored, so a fresh clone has to fetch the dumps (~680 MB) before a full
rebuild. Only the snapshots derived from them are committed, and the md5 pins
make the provenance reproducible from the public source.

Stratification (deterministic by sorted keys; revised 2026-09-03):

    A = 300 reviewers with the most distinct products (>= 5 products)
    B = 50 remaining reviewers with the most words (>= 5 products, > 100 words)
    C = 75 remaining reviewers with the FEWEST distinct products

425 reviewers, not 500. The substrate's remaining 75 contacts are deliberately
left **without an Amazon link at all** (see ``substrate/generators/__main__.py``):
no reviewer, no orders, no review text. Every real CRM holds contacts nobody has
ever sold to — leads, event signups, imported lists — and they are the only way
to get a true cold-start customer here.

Why C changed. It used to take the 150 *longest remaining texts* and was
commented "Complex/Noisy", but measured, that produced a median of 62 distinct
products against A's 113: three tiers of heavy buyers differing by a factor of
two, mostly in how much they *wrote*. Selecting the fewest distinct products
instead makes the tiers a real difficulty gradient, which is what UC-04's
leave-one-out metric is sensitive to, and it is the property its per-group HR@K
breakdown was always reporting against.

**The candidate pool is pinned by the frozen translation.** The English->Czech
run happened once, on a paid API whose credit is gone, so Czech review text
exists for exactly the reviewers listed in
``snapshots/provenance/translation/frozen-reviewers.json``. Selecting outside
that set would produce contacts with no Czech text at all, which is the one
thing a Czech CRM cannot have, so the stratification draws only from it. That
also caps how sparse group C can be: within the pinned pool the thinnest
histories run to about 12 distinct products, not the 5-core floor of 5.

A contact with no reviewer at all is how the substrate reaches zero, and it is
not capped by any of this.

Run:
    python -m substrate.pipeline.data_acquisition.fetch_and_filter --download   # fetch + verify raw/
    python -m substrate.pipeline.data_acquisition.fetch_and_filter --verify-only
    python -m substrate.pipeline.data_acquisition.fetch_and_filter --force      # rewrite stratified_500_users.json
"""

from __future__ import annotations

import argparse
import ast
import gzip
import json
import sys
from collections import defaultdict
from pathlib import Path

from substrate.pipeline.data_acquisition import _pinned
from utils.paths import PROVENANCE_DIR, DOWNLOADS_DIR, STRATIFIED_500_USERS

_SNAP = "https://snap.stanford.edu/data/amazon/productGraph/categoryFiles/"
SOURCES: dict[str, dict] = {
    "reviews_Electronics_5.json.gz": {
        "url": _SNAP + "reviews_Electronics_5.json.gz",
        "size": 495854086,
        "md5": "e4524af6c644cd044b1969bac7b62b2a",
    },
    "meta_Electronics.json.gz": {
        "url": _SNAP + "meta_Electronics.json.gz",
        "size": 186594679,
        "md5": "b39b77b4c980cca078ec2b93dfcba786",
    },
}
DATA_DIR = DOWNLOADS_DIR
REVIEWS_PATH = DATA_DIR / "reviews_Electronics_5.json.gz"
META_PATH = DATA_DIR / "meta_Electronics.json.gz"
OUT_PATH = STRATIFIED_500_USERS

# Group sizes. The substrate has 500 contacts; only these 425 carry an Amazon
# link, and the remaining 75 are prospects with no purchase history at all.
GROUP_A_SIZE = 300
GROUP_B_SIZE = 50
GROUP_C_SIZE = 75
STRATIFIED_TOTAL = GROUP_A_SIZE + GROUP_B_SIZE + GROUP_C_SIZE

# The reviewers the one-time paid translation covers; nothing may be selected
# outside this set (see the module docstring).
FROZEN_REVIEWERS = PROVENANCE_DIR / "translation" / "frozen-reviewers.json"


# ---------------------------------------------------------------------------
# Pinned sources
# ---------------------------------------------------------------------------


def verify(raw_dir: Path) -> dict[str, str]:
    """Return per-file status against the pins in ``SOURCES``."""
    return _pinned.verify(SOURCES, raw_dir)


def download(raw_dir: Path, *, force: bool = False) -> dict[str, str]:
    """Fetch whatever is missing from ``SOURCES``; return the verify status."""
    return _pinned.download(SOURCES, raw_dir, force=force)


# ---------------------------------------------------------------------------
# Raw dump reading
# ---------------------------------------------------------------------------


def load_json_gz(path):
    """Yield one parsed record per line of a gzipped JSON-lines dump (tolerates Python-literal lines)."""
    if not path.exists():
        return
    with gzip.open(path, "rt", encoding="utf-8") as f:
        for line in f:
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError:
                # Amazon metadata snapshots are Python-literal dict lines
                # rather than strict JSON.  Keep the parser structured instead
                # of using ad-hoc string manipulation.
                try:
                    yield ast.literal_eval(stripped)
                except (SyntaxError, ValueError):
                    continue


# ---------------------------------------------------------------------------
# Stratification
# ---------------------------------------------------------------------------


def stratify() -> None:
    """Select the 425 reviewers (A/B/C) from the raw dumps and write stratified_500_users.json."""
    print("Loading Electronics data for stratified selection...")

    user_reviews = defaultdict(list)
    product_meta = {}

    # 1. Load Reviews
    print("Processing reviews...")
    for rev in load_json_gz(REVIEWS_PATH):
        user_reviews[rev["reviewerID"]].append(rev)

    # 2. Load Metadata
    print("Processing metadata...")
    for meta in load_json_gz(META_PATH):
        product_meta[meta["asin"]] = meta

    # 3. Stratification Logic
    print(f"Performing stratified selection of {STRATIFIED_TOTAL} users...")

    eligible = set(json.loads(FROZEN_REVIEWERS.read_text(encoding="utf-8"))["reviewer_ids"])
    print(f"Restricting to the {len(eligible)} reviewers the frozen translation covers...")

    user_stats = []
    for uid, reviews in user_reviews.items():
        if uid not in eligible:
            continue
        unique_asins = set(r["asin"] for r in reviews)
        total_words = sum(len(r.get("reviewText", "").split()) for r in reviews)
        user_stats.append(
            {"uid": uid, "count": len(unique_asins), "words": total_words, "reviews": reviews}
        )

    # Group A: most distinct products (at least 5).
    group_a = sorted(
        [u for u in user_stats if u["count"] >= 5],
        key=lambda x: (-x["count"], x["uid"]),
    )[:GROUP_A_SIZE]

    # Group B: of the rest, the most words among reviewers with >= 5 products.
    group_a_ids = {u["uid"] for u in group_a}
    remaining = [u for u in user_stats if u["uid"] not in group_a_ids]
    group_b = sorted(
        [u for u in remaining if u["count"] >= 5 and u["words"] > 100],
        key=lambda x: (-x["words"], x["uid"]),
    )[:GROUP_B_SIZE]

    # Group C: the FEWEST distinct products, i.e. the sparsest histories the
    # 5-core dump allows. This is the tier UC-04's leave-one-out metric finds
    # hard, and the step below the two dense tiers on the way to the contacts
    # that carry no Amazon link at all.
    group_b_ids = {u["uid"] for u in group_b}
    remaining = [u for u in remaining if u["uid"] not in group_b_ids]
    group_c = sorted(remaining, key=lambda x: (x["count"], x["uid"]))[:GROUP_C_SIZE]

    selected = group_a + group_b + group_c

    # Filler if any group is too small. Never fires on the 5-core Electronics
    # dump (A+B+C reach the target exactly); kept so a smaller input still fills.
    if len(selected) < STRATIFIED_TOTAL:
        already_selected = {u["uid"] for u in selected}
        filler = sorted(
            [u for u in user_stats if u["uid"] not in already_selected],
            key=lambda x: (-x["words"], x["uid"]),
        )[: STRATIFIED_TOTAL - len(selected)]
        selected += filler

    print(f"Selection complete. Total: {len(selected)} users selected.")

    # 4. Save
    final_output = []
    group_lookup = {
        **{u["uid"]: "A" for u in group_a},
        **{u["uid"]: "B" for u in group_b},
        **{u["uid"]: "C" for u in group_c},
    }
    for user in selected:
        asins = sorted({r["asin"] for r in user["reviews"]})
        final_output.append(
            {
                "reviewerID": user["uid"],
                "group": group_lookup.get(user["uid"], "C"),
                "reviews": sorted(
                    user["reviews"],
                    key=lambda r: (r.get("asin", ""), r.get("unixReviewTime", 0)),
                ),
                "products": [
                    product_meta.get(asin, {"asin": asin, "title": "Unknown Product"})
                    for asin in asins
                ],
            }
        )

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2, ensure_ascii=False)

    print(f"Saved {len(final_output)} stratified Electronics users to {OUT_PATH}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: verify or download the raw dumps, or write the stratified 500-reviewer file."""
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="fetch missing/invalid raw files from SNAP, then verify",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="only check raw/ against the pinned sizes and md5s",
    )
    parser.add_argument(
        "--force", action="store_true", help="rewrite stratified_500_users.json (tracked, ~250 MB)"
    )
    args = parser.parse_args(argv)
    if args.download:
        print(json.dumps(download(DATA_DIR), indent=2))
        return 0
    if args.verify_only:
        status = verify(DATA_DIR)
        print(json.dumps(status, indent=2))
        return 0 if all(v == "ok" for v in status.values()) else 1
    if OUT_PATH.exists() and not args.force:
        print("stratified_500_users.json exists; pass --force to rewrite it.", file=sys.stderr)
        return 2
    bad = {k: v for k, v in verify(DATA_DIR).items() if v != "ok"}
    if bad:
        print(f"raw files not verified: {bad}. Run with --download first.", file=sys.stderr)
        return 1
    stratify()
    return 0


if __name__ == "__main__":
    sys.exit(main())
