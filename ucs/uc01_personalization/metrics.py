"""Intrinsic metrics over a run: style match, vocabulary reuse, and OCEAN faithfulness.

None of these say whether a recipient would prefer the message (there are no
recipients). They say whether the generator *did* what a level asked:

- **Language Style Matching** (Gonzales et al. 2010): for each function-word
  class the match is ``1 - |p1 - p2| / (p1 + p2)``, averaged over classes, where
  p is the class's share of tokens. Computed between the message and **all** of
  the contact's Czech reviews (not the 600-character prompt sample), so the
  reference has enough tokens for proportions. The classes are a pragmatic
  Czech adaptation of the LIWC categories; treat absolute values as indicative
  and the ordering across levels as the signal.
- **Lexical overlap**: the share of the contact's ``frequent_words`` that appear
  verbatim in the message. L3a should raise it if the lexicon was used.
- **Faithfulness** (EGISES-style counterfactual): the same message generated
  twice, from the real OCEAN profile and from its mirror across the midpoint;
  responsiveness = 1 - Jaccard(tokens). It measures *how much* the profile
  changes the text, not in which direction. Two model calls per
  contact; behind the switch.
"""

from __future__ import annotations

import asyncio
import csv
import json
import re
import sqlite3
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterable

from ucs.uc01_personalization import data, levels
from ucs.uc01_personalization.generate import generate

# ---------------------------------------------------------------------------
# Czech function-word classes (pragmatic LIWC adaptation)
# ---------------------------------------------------------------------------

CATEGORIES: dict[str, frozenset[str]] = {
    "pronouns": frozenset(
        "já ty on ona ono my vy oni ony mě mně mi tě ti tebe tobě ho mu jej jí ji nás vás nám vám je jich "
        "jim se si svůj svá své svého můj má mé tvůj náš váš jeho její jejich ten ta to tento tato toto "
        "který která které jenž kdo co tom tím této toho".split()
    ),
    "prepositions": frozenset(
        "v ve na do z ze s se o od u k ke ku za po při pro před nad pod mezi bez podle kvůli během kromě "
        "vedle okolo díky skrz proti vůči".split()
    ),
    "conjunctions": frozenset(
        "a i ale nebo že když protože aby jako však tedy proto neboť ani jelikož zatímco takže či pokud "
        "jakmile přestože avšak".split()
    ),
    "auxiliary": frozenset(
        "je jsou jsem jsi jsme jste byl byla bylo byli byly být bude budou budu budeš budeme budete má máte "
        "máme mít mám máš mají měl měla by bych bys bychom byste".split()
    ),
    "negations": frozenset("ne ani nikdy nic nikdo žádný žádná žádné ničeho".split()),
    "adverbs": frozenset(
        "už ještě také taky velmi jen jenom právě tak jak kde tady zde nyní teď vždy často více méně stále "
        "tam kdy proč navíc zcela dokonce".split()
    ),
    "quantifiers": frozenset(
        "všechny všechno všichni každý každá mnoho několik hodně málo pár většina celý celá oba obě".split()
    ),
}

_TOKEN = re.compile(r"[a-záčďéěíňóřšťúůýž]+", re.IGNORECASE)
_TOKEN_ANY = re.compile(r"[a-zá-ž0-9]+", re.IGNORECASE)


def _tokens(text: str) -> list[str]:
    """Lowercased Czech-letter tokens of ``text`` (diacritics-aware; punctuation and digits dropped)."""
    return _TOKEN.findall((text or "").lower())


def _proportions(tokens: list[str]) -> dict[str, float]:
    """Each ``CATEGORIES`` class's share of ``tokens`` (0.0 for every class when ``tokens`` is empty)."""
    n = len(tokens)
    if n == 0:
        return {c: 0.0 for c in CATEGORIES}
    counts: dict[str, int] = defaultdict(int)
    for tok in tokens:
        for cat, words in CATEGORIES.items():
            if tok in words:
                counts[cat] += 1
    return {c: counts[c] / n for c in CATEGORIES}


def lsm_index(text_a: str, text_b: str) -> float:
    """Language Style Matching between two texts, 0-1, higher = more style coordination."""
    pa, pb = _proportions(_tokens(text_a)), _proportions(_tokens(text_b))
    per_cat = []
    for c in CATEGORIES:
        denom = pa[c] + pb[c]
        per_cat.append(1.0 if denom == 0 else 1.0 - abs(pa[c] - pb[c]) / denom)
    return sum(per_cat) / len(per_cat)


def overlap_rate(message: str, frequent_words: Iterable[str]) -> float | None:
    """Share of the contact's frequent words that appear verbatim in the message; None without a list."""
    words = [str(w).lower() for w in frequent_words if str(w).strip()]
    if not words:
        return None
    toks = {t.lower() for t in _TOKEN_ANY.findall(message or "")}
    return sum(1 for w in words if w in toks) / len(words)


def _jaccard(a: str, b: str) -> float:
    """Jaccard similarity of ``a`` and ``b``'s token sets; 1.0 when both are empty."""
    ta = {t.lower() for t in _TOKEN_ANY.findall(a or "")}
    tb = {t.lower() for t in _TOKEN_ANY.findall(b or "")}
    return len(ta & tb) / len(ta | tb) if (ta | tb) else 1.0


def flip_ocean(ocean: dict[str, float]) -> dict[str, float]:
    """Mirror each Big Five score across the 1-5 midpoint."""
    return {k: round(6 - v, 2) for k, v in ocean.items() if k in "OCEAN"}


# ---------------------------------------------------------------------------
# Over a run folder
# ---------------------------------------------------------------------------


def evaluate(run_folder: Path) -> Path:
    """LSM and overlap for every generated message of a run; writes ``metrics.csv`` and ``metrics-summary.json``."""
    conn = data.connect()
    cache_text: dict[int, str] = {}
    cache_words: dict[int, list[str]] = {}
    rows: list[dict[str, Any]] = []
    try:
        with (run_folder / "messages.jsonl").open(encoding="utf-8") as fh:
            for line in fh:
                g = json.loads(line)
                if not g.get("ok"):
                    continue
                cid = g["contact_id"]
                if cid not in cache_text:
                    cache_text[cid] = data.czech_review_text(conn, cid)
                    cache_words[cid] = data.load_contact(conn, cid).frequent_words
                ref = cache_text[cid]
                rows.append(
                    {
                        "contact_id": cid,
                        "brief_id": g["brief_id"],
                        "level": g["level"],
                        "lsm": round(lsm_index(g["text"], ref), 4) if ref else "",
                        "overlap": (
                            round(overlap_rate(g["text"], cache_words[cid]), 4)
                            if cache_words[cid]
                            else ""
                        ),
                        "chars": len(g["text"]),
                    }
                )
    finally:
        conn.close()

    out = run_folder / "metrics.csv"
    with out.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(
            fh, fieldnames=("contact_id", "brief_id", "level", "lsm", "overlap", "chars")
        )
        writer.writeheader()
        writer.writerows(rows)

    summary: dict[str, Any] = {}
    for level in sorted({r["level"] for r in rows}, key=levels.LADDER.index):
        mine = [r for r in rows if r["level"] == level]
        lsm = [r["lsm"] for r in mine if r["lsm"] != ""]
        ov = [r["overlap"] for r in mine if r["overlap"] != ""]
        summary[level] = {
            "n": len(mine),
            "lsm_mean": round(sum(lsm) / len(lsm), 4) if lsm else None,
            "overlap_mean": round(sum(ov) / len(ov), 4) if ov else None,
            "chars_mean": round(sum(r["chars"] for r in mine) / len(mine), 1),
        }
    (run_folder / "metrics-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    return out


async def faithfulness(
    contact_ids: list[int],
    brief_id: int,
    *,
    provider: str,
    model: str | None,
    tier: str | None,
    level: str = "5",
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Responsiveness of the psychographic level to the OCEAN profile, per contact (two calls each)."""
    own = conn is None
    conn = conn or data.connect()
    rows: list[dict[str, Any]] = []
    try:
        for cid in contact_ids:
            contact = data.load_contact(conn, cid)
            if not contact.ocean:
                rows.append({"contact_id": cid, "skipped": "ocean"})
                continue
            real = await generate(
                cid,
                brief_id,
                level,
                provider=provider,
                model=model,
                tier=tier,
                judges=(),
                conn=conn,
            )
            mirrored = await generate(
                cid,
                brief_id,
                level,
                provider=provider,
                model=model,
                tier=tier,
                judges=(),
                conn=conn,
                ocean_override=flip_ocean(contact.ocean),
            )
            if not (real.ok and mirrored.ok):
                rows.append(
                    {
                        "contact_id": cid,
                        "skipped": ",".join(real.skipped + mirrored.skipped),
                        "error": real.error or mirrored.error,
                    }
                )
                continue
            rows.append(
                {
                    "contact_id": cid,
                    "ocean": contact.ocean,
                    "mirrored": flip_ocean(contact.ocean),
                    "responsiveness": round(1 - _jaccard(real.text, mirrored.text), 4),
                    "real": real.text,
                    "mirrored_text": mirrored.text,
                    # the two calls verbatim: prompts, resolved model and tier, prompt version
                    "real_generation": real.to_dict(),
                    "mirrored_generation": mirrored.to_dict(),
                }
            )
    finally:
        if own:
            conn.close()
    return rows


def faithfulness_sync(*args: Any, **kwargs: Any) -> list[dict[str, Any]]:
    """``faithfulness()`` for callers without an event loop (the CLI)."""
    return asyncio.run(faithfulness(*args, **kwargs))
