"""Provenance trace: where do the "bad characters" come from, stage by stage.

Streams the two compressed Amazon dumps (byte-identical to the public SNAP
files, see fetch_and_filter.py), keeps the 500 stratified reviewers and the
19 243 catalog products, and counts every anomaly class of
utils.text_hygiene at three stages:

    RAW        the string exactly as stored in the dump (HTML entities intact)
    UNESCAPED  after html.unescape, i.e. what the pre-2026-09-02 step 0c produced
    CLEANED    after utils.text_hygiene.clean_text (the chain since 2026-09-02)

Then the Czech side: zero-width characters in the frozen translation input
vs. output. Writes provenance-trace.md next to this script.

Run from the project root:
    python substrate/snapshots/provenance/pre-clean-2026-09-02/trace_bad_chars.py
"""
from __future__ import annotations

import ast
import csv
import gzip
import html
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent          # snapshots/provenance/pre-clean-2026-09-02
THESIS = HERE.parents[3]                          # repository root
sys.path.insert(0, str(THESIS))
from utils.text_hygiene import CRITICAL_CLASSES, clean_text, scan_text  # noqa: E402

RAW = THESIS / "substrate/pipeline/data_acquisition/downloaded"  # renamed raw/ -> downloaded/ 2026-09-03
REVIEWS_GZ = RAW / "reviews_Electronics_5.json.gz"
META_GZ = RAW / "meta_Electronics.json.gz"
STRAT = THESIS / "substrate/pipeline/data_acquisition/stratified_500_users.json"
CATALOG = THESIS / "substrate/snapshots/amazon/amazon-catalog-en.json"
STAGE1 = THESIS / "substrate/snapshots/provenance/translation/stage1-translate.json"
MORNING_CSV = HERE / "audit-counts-before-rebuild.csv"
OUT = HERE / "provenance-trace.md"

ZW = re.compile("[​-‏⁠-⁤﻿]")


def esc(s: str) -> str:
    """Make a snippet printable without hiding anything.

    Every character that would be invisible or ambiguous on screen (control
    characters, zero-width, NBSP, private-use glyphs, the replacement character)
    is written as its code point, e.g. ``\\u200b``. Everything else stays as is.
    """
    return "".join(c if 32 <= ord(c) < 127 or (ord(c) > 159 and c.isprintable() and ord(c) not in (0xA0, 0xFFFD)) else "\\u%04x" % ord(c) for c in s)


def agg(counter: Counter, s: str) -> None:
    """Add the anomaly counts of one string to a running total (class -> count)."""
    for k, v in scan_text(s).items():
        counter[k] += v


def parse(line: str):
    """Parse one line of an Amazon dump.

    Review lines are strict JSON; metadata lines are Python dict literals
    (single quotes), so fall back to ``ast.literal_eval`` for those.
    """
    try:
        return json.loads(line)
    except json.JSONDecodeError:
        return ast.literal_eval(line)


def load_scope() -> tuple[set[str], set[str]]:
    """Which reviewers and products the trace looks at.

    Reviewer ids come from the stratified selection (the 500 users of the
    substrate), product ids from the current catalog snapshot (19 243 asins).
    Everything else in the dumps is skipped.
    """
    ids = {u["reviewerID"] for u in json.loads(STRAT.read_text(encoding="utf-8"))}
    asins = {p["asin"] for p in json.loads(CATALOG.read_text(encoding="utf-8"))}
    return ids, asins


def three_stages(s: str, *, strip_tags: bool) -> tuple[str, str, str]:
    """Return the same text in its three states: RAW, UNESCAPED, CLEANED.

    RAW is the string exactly as stored in the dump (HTML entities intact).
    UNESCAPED is ``html.unescape`` applied once, which is all the pre-2026-09-02
    step did. CLEANED is ``utils.text_hygiene.clean_text``; for product
    descriptions HTML tags are stripped too, as the catalog builder does.
    """
    return s, html.unescape(s), clean_text(s, strip_html_tags=strip_tags) or ""


def example_for(where: str, key: str, s: str, u: str, *, strip_tags: bool) -> dict | None:
    """Build one printable example when the decoded text carries a critical class.

    Returns ``None`` when there is nothing critical in the unescaped text. The
    window is centred on the first anomalous character so the reader sees the
    same passage in all three states.
    """
    crit = {k: v for k, v in scan_text(u).items() if k in CRITICAL_CLASSES}
    if not crit:
        return None
    pos = next(i for i, ch in enumerate(u) if scan_text(ch))
    ent = html.escape(u[pos])
    raw_pos = max(0, s.find(ent) if ent in s else s.find(u[pos]))
    window_u = u[max(0, pos - 50):pos + 60]
    return {
        "where": where,
        "key": key,
        "classes": crit,
        "raw": esc(s[max(0, raw_pos - 50):raw_pos + 60]),
        "unescaped": esc(window_u),
        "cleaned": esc(clean_text(window_u, strip_html_tags=strip_tags) or ""),
    }


def scan_reviews(ids: set[str], stages: dict, examples: list) -> int:
    """Stream the compressed reviews dump and count all three stages per review field.

    Only lines whose reviewerID is in ``ids`` are parsed (a cheap regex
    pre-filter avoids parsing the other ~1.6 million lines). Fields scanned:
    summary, reviewText, reviewerName. Returns the number of reviews kept.
    """
    rid_rx = re.compile(r'"reviewerID":\s*"([^"]+)"')
    n = 0
    with gzip.open(REVIEWS_GZ, "rt", encoding="utf-8") as fh:
        for line in fh:
            m = rid_rx.search(line)
            if not m or m.group(1) not in ids:
                continue
            rec = parse(line.strip())
            n += 1
            for field in ("summary", "reviewText", "reviewerName"):
                s = rec.get(field) or ""
                if not isinstance(s, str):
                    continue
                raw, u, c = three_stages(s, strip_tags=False)
                agg(stages["RAW"], raw)
                agg(stages["UNESCAPED"], u)
                agg(stages["CLEANED"], c)
                if len([e for e in examples if e["where"] == "review"]) < 10:
                    ex = example_for("review", f"{rec['reviewerID']} / {rec.get('asin')} / {field}", s, u, strip_tags=False)
                    if ex:
                        examples.append(ex)
    return n


def scan_catalog(asins: set[str], stages: dict, examples: list) -> int:
    """Stream the compressed metadata dump and count all three stages for title + description.

    Descriptions are cleaned with HTML tags stripped, exactly as
    ``build_clean_snapshots.catalog_entry`` does. Returns the number of products kept.
    """
    n = 0
    with gzip.open(META_GZ, "rt", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rec = parse(line)
            if rec.get("asin") not in asins:
                continue
            n += 1
            for field in ("title", "description"):
                s = rec.get(field) or ""
                if not isinstance(s, str):
                    continue
                strip = field == "description"
                raw, u, c = three_stages(s, strip_tags=strip)
                agg(stages["RAW"], raw)
                agg(stages["UNESCAPED"], u)
                agg(stages["CLEANED"], c)
                if len([e for e in examples if e["where"] == "catalog"]) < 8:
                    ex = example_for("catalog", f"{rec['asin']} / {field}", s, u, strip_tags=strip)
                    if ex:
                        if field == "title":
                            ex["raw"] = esc(s[:140])
                        examples.append(ex)
    return n


def czech_side() -> dict:
    """Show that the zero-width characters on the Czech side came from the translator.

    Counts zero-width characters in the frozen translation's English input
    (``en``) and Czech output (``cz_raw``), and after cleaning the output; collects
    four items where the input had none and the output has them.
    """
    st1 = json.loads(STAGE1.read_text(encoding="utf-8"))
    out = {
        "items": len(st1),
        "en_zw": sum(len(ZW.findall(v.get("en") or "")) for v in st1.values()),
        "cz_zw": sum(len(ZW.findall(v.get("cz_raw") or "")) for v in st1.values()),
        "cz_items": sum(1 for v in st1.values() if ZW.search(v.get("cz_raw") or "")),
        "cz_clean_zw": sum(len(ZW.findall(clean_text(v.get("cz_raw")) or "")) for v in st1.values()),
        "examples": [],
    }
    for v in st1.values():
        if ZW.search(v.get("cz_raw") or "") and not ZW.search(v.get("en") or ""):
            cz = v["cz_raw"]
            pos = ZW.search(cz).start()
            out["examples"].append({
                "item": v["item_id"],
                "en": esc((v["en"] or "")[:120]),
                "cz_raw": esc(cz[max(0, pos - 60):pos + 60]),
                "cleaned": esc(clean_text(cz[max(0, pos - 60):pos + 60]) or ""),
            })
            if len(out["examples"]) >= 4:
                break
    return out


def before_rebuild_audit() -> dict[str, dict[str, int]]:
    """Read the per-file audit of the whole tree taken before the rebuild.

    Gives the counts found in the snapshots that were in use at the time, so the
    UNESCAPED column can be checked against what those files really contained.
    """
    morning: dict[str, dict[str, int]] = {}
    if MORNING_CSV.exists():
        for row in csv.DictReader(MORNING_CSV.open(encoding="utf-8")):
            if row["file"] in (
                "substrate/snapshots/intermediate/english-amazon.json",
                "substrate/snapshots/amazon/amazon-items-en.json",
                "substrate/snapshots/amazon/500-reviewers-en.json",
            ):
                morning[row["file"]] = {k: int(v) for k, v in row.items() if k not in ("file", "strings", "chars") and v and int(v)}
    return morning


def stage_table(block: dict[str, Counter], classes: list[str]) -> str:
    """Render one RAW / UNESCAPED / CLEANED table in Markdown, skipping all-zero classes."""
    rows = ["| class | RAW (as stored in the dump) | UNESCAPED (old step 0c) | CLEANED (new step 0c) |", "|---|--:|--:|--:|"]
    for c in classes:
        r, u, k = block["RAW"].get(c, 0), block["UNESCAPED"].get(c, 0), block["CLEANED"].get(c, 0)
        if r or u or k:
            rows.append(f"| {c} | {r} | {u} | {k} |")
    return "\n".join(rows)


CLASSES = ["ZW", "BIDI", "C0", "C1", "NBSP", "LSEP", "SHY", "PUA", "VS", "FFFD", "NONCHAR",
           "MOJI", "HTMLENT", "ESCSEQ_X000D", "HTMLTAG"]


def write_report(n_rev: int, n_prod: int, stages: dict, examples: list, cz: dict, morning: dict, seconds: float) -> None:
    """Assemble ``provenance-trace.md``: the two three-stage tables, the audit of the
    snapshots before the rebuild, the literal dump lines, and the Czech-side table."""
    md = [f"# Provenance trace: where the bad characters come from — {time.strftime('%Y-%m-%d %H:%M')}", "",
          "Source: `reviews_Electronics_5.json.gz` + `meta_Electronics.json.gz` (md5 identical to the public SNAP files), streamed;",
          f"kept {n_rev} reviews of the 500 stratified reviewers and {n_prod} catalog products. Script: `trace_bad_chars.py`.", "",
          "Three states of the same text: **RAW** = the string exactly as stored in the dump (an HTML entity such as `&#65533;` is 8 ASCII characters);",
          "**UNESCAPED** = after `html.unescape`, i.e. what the original step 0c produced (and what",
          "`intermediate/english-amazon.json` contained until 2026-09-02); **CLEANED** = after `utils.text_hygiene.clean_text`.", "",
          "## Reviews (summary + reviewText + reviewerName)", "", stage_table(stages["reviews"], CLASSES), "",
          "## Catalog (title + description)", "", stage_table(stages["catalog"], CLASSES), "",
          "How to read the tables: in RAW the hidden characters are almost absent and HTML entities number in the tens of thousands; decoding the entities reveals",
          "U+FFFD, NBSP, PUA (Wingdings) and mojibake, exactly the counts the pre-rebuild audit found in the",
          "`english-amazon.json` of that time (below). The new step removes them.", "",
          "## Audit of the snapshots before the rebuild (`audit-counts-before-rebuild.csv`)", ""]
    for f, counts in morning.items():
        md.append(f"- `{f}`: {counts}")
    for where, title in (("review", "reviews"), ("catalog", "catalog")):
        md += ["", f"## Literal dump lines ({title})", ""]
        for e in [e for e in examples if e["where"] == where]:
            md += [f"- **{e['key']}** — classes after decoding: {e['classes']}",
                   f"  - RAW: `{e['raw']}`", f"  - UNESCAPED: `{e['unescaped']}`", f"  - CLEANED: `{e['cleaned']}`"]
    md += ["", "## Czech side: the zero-width characters were inserted by the translator", "",
           "| where | zero-width characters |", "|---|--:|",
           f"| translator input (`en` in stage1-translate.json, {cz['items']} items) | {cz['en_zw']} |",
           f"| translator output (`cz_raw`) | {cz['cz_zw']} (in {cz['cz_items']} items) |",
           f"| `cz_raw` after `clean_text` | {cz['cz_clean_zw']} |", ""]
    for e in cz["examples"]:
        md += [f"- **{e['item']}**", f"  - EN input: `{e['en']}`", f"  - CZ output (raw): `{e['cz_raw']}`", f"  - CZ after cleaning: `{e['cleaned']}`"]
    md += ["", f"Run time: {seconds:.0f} s."]
    OUT.write_text("\n".join(md) + "\n", encoding="utf-8")


def main() -> None:
    """Run the whole trace: scope -> reviews dump -> metadata dump -> Czech side -> report."""
    t0 = time.time()
    ids, asins = load_scope()
    stages = {"reviews": {"RAW": Counter(), "UNESCAPED": Counter(), "CLEANED": Counter()},
              "catalog": {"RAW": Counter(), "UNESCAPED": Counter(), "CLEANED": Counter()}}
    examples: list[dict] = []
    n_rev = scan_reviews(ids, stages["reviews"], examples)
    n_prod = scan_catalog(asins, stages["catalog"], examples)
    cz = czech_side()
    morning = before_rebuild_audit()
    write_report(n_rev, n_prod, stages, examples, cz, morning, time.time() - t0)
    print(f"wrote {OUT} in {time.time() - t0:.0f}s; reviews {n_rev}, products {n_prod}")


if __name__ == "__main__":
    main()
