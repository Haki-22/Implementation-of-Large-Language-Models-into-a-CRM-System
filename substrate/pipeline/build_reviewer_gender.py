"""Infer the gender of each Amazon reviewer behind the substrate (build_all step ``reviewer_gender``).

Why this exists
---------------
The substrate joins a generated Czech identity to a real Amazon reviewer's
history. Until 2026-09-04 the join was positional, so about half of the
female contacts carried a man's purchase history and writing sample and vice
versa (measured: 145 of the 293 pairs whose reviewer gender is known were
mismatched). The Czech translation makes it worse: English first-person past
tense carries no gender and the translator renders it masculine by default, so
the Czech text speaks as a man for 377 of 410 reviewers regardless of who wrote
it. The reviewer's *actual* gender therefore has to come from the English side,
and this step records it so the generator can pair contacts and reviewers by
gender inside each stratification group (``substrate/generators/__main__.py``).

Method (deterministic, no model)
--------------------------------
Two independent signals per reviewer, both from the cleaned English layer
(``snapshots/intermediate/english-amazon.json``):

1. **Name.** The raw dump's ``reviewerName``; its first token is looked up in
   the English given-name lists that ship with Faker (``faker.providers.person.en_US``),
   names present in both lists (unisex) excluded. Handles and initials
   (``MagnumMan``, ``A. Dent``) yield nothing.
2. **Self-reference cues in the review text.** Phrases that name the writer's
   own sex or partner: ``my wife`` / ``my girlfriend`` / ``as a dad`` point to
   a man, ``my husband`` / ``my boyfriend`` / ``as a mom`` to a woman. The
   majority side wins; a tie yields nothing.

The final verdict is the name when it is known, otherwise the cue; when both
are known and disagree the reviewer stays *unknown* rather than guessed. On
the 425 stratified reviewers: 148 have a name verdict, 156 a cue verdict, and
where both exist they agree in 81 of 84 cases. 304 reviewers get a gender
(256 men, 48 women); 121 stay unknown. The population is Amazon Electronics,
so it is strongly male; the pairing step, not this one, decides what that means
for the 53.8 % female cohort.

Output
------
``substrate/snapshots/amazon/reviewer-gender.json`` (committed): per reviewer the
name, both verdicts, the cue counts and the final gender, plus a ``_meta`` block
with the counts above as measured at build time.

Run:
    python -m substrate.pipeline.build_reviewer_gender --force
"""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import faker
from faker.providers.person.en_US import Provider as _EnglishNames

from utils.file_safety import require_can_write
from utils.paths import AMAZON_EN_INTERMEDIATE, REVIEWER_GENDER_SNAPSHOT

# ---------------------------------------------------------------------------
# Signal 1: the reviewer's given name
# ---------------------------------------------------------------------------

_MALE_NAMES = frozenset(n.lower() for n in _EnglishNames.first_names_male)
_FEMALE_NAMES = frozenset(n.lower() for n in _EnglishNames.first_names_female)
_UNISEX = _MALE_NAMES & _FEMALE_NAMES
MALE_NAMES = _MALE_NAMES - _UNISEX
FEMALE_NAMES = _FEMALE_NAMES - _UNISEX

_NAME_TOKEN = re.compile(r"[A-Za-z]{2,}")


def name_gender(reviewer_name: str | None) -> str | None:
    """Gender of the first given-name token of ``reviewer_name``, or None.

    Only the first alphabetic token of at least two letters is consulted, so
    ``"Mary Jo Sminkey"`` -> f, ``"J. Haggard"`` -> None (initial), ``"Spudman"``
    -> None (not a given name), ``"Jordan Lee"`` -> None (unisex).
    """
    if not reviewer_name:
        return None
    match = _NAME_TOKEN.search(reviewer_name)
    if not match:
        return None
    token = match.group(0).lower()
    if token in MALE_NAMES:
        return "m"
    if token in FEMALE_NAMES:
        return "f"
    return None


# ---------------------------------------------------------------------------
# Signal 2: self-reference cues in the English review text
# ---------------------------------------------------------------------------

MALE_CUES = re.compile(
    r"\bmy (?:wife|girlfriend|fiancee)\b"
    r"|\bas a (?:man|guy|dad|father|husband|grandpa|grandfather)\b"
    r"|\bi'?m a (?:man|guy|dad|father|husband)\b",
    re.IGNORECASE,
)
FEMALE_CUES = re.compile(
    r"\bmy (?:husband|boyfriend|fiance)\b"
    r"|\bas a (?:woman|girl|lady|mom|mother|wife|grandma|grandmother)\b"
    r"|\bi'?m a (?:woman|girl|lady|mom|mother|wife)\b",
    re.IGNORECASE,
)


def cue_counts(text: str) -> tuple[int, int]:
    """Return (male cues, female cues) found in ``text``."""
    return len(MALE_CUES.findall(text)), len(FEMALE_CUES.findall(text))


def cue_gender(male: int, female: int) -> str | None:
    """Majority verdict from the cue counts; a tie or no cue yields None."""
    if male > female:
        return "m"
    if female > male:
        return "f"
    return None


# ---------------------------------------------------------------------------
# Per-reviewer verdict + the artifact
# ---------------------------------------------------------------------------


def infer_reviewer(user: dict[str, Any]) -> dict[str, Any]:
    """Both signals and the final verdict for one stratified reviewer wrapper."""
    reviews = user.get("reviews", [])
    names = Counter(r.get("reviewerName") for r in reviews if r.get("reviewerName"))
    name = names.most_common(1)[0][0] if names else None
    by_name = name_gender(name)
    male, female = cue_counts(
        " ".join(f"{r.get('summary') or ''} {r.get('reviewText') or ''}" for r in reviews)
    )
    by_cue = cue_gender(male, female)
    conflict = bool(by_name and by_cue and by_name != by_cue)
    final = None if conflict else (by_name or by_cue)
    return {
        "name": name,
        "name_gender": by_name,
        "cue_male": male,
        "cue_female": female,
        "cue_gender": by_cue,
        "conflict": conflict,
        "gender": final,
    }


def build(users: list[dict[str, Any]]) -> dict[str, Any]:
    """The full artifact: per-reviewer verdicts plus the measured counts."""
    reviewers = {u["reviewerID"]: infer_reviewer(u) for u in users}
    both = [r for r in reviewers.values() if r["name_gender"] and r["cue_gender"]]
    meta = {
        "method": "first given-name token against Faker en_US name lists (unisex excluded) "
        "+ self-reference cues in the English reviews; name wins, a conflict stays unknown",
        "faker_version": faker.VERSION,
        "reviewers": len(reviewers),
        "with_name": sum(1 for r in reviewers.values() if r["name"]),
        "name_verdicts": sum(1 for r in reviewers.values() if r["name_gender"]),
        "cue_verdicts": sum(1 for r in reviewers.values() if r["cue_gender"]),
        "both_known": len(both),
        "both_agree": sum(1 for r in both if r["name_gender"] == r["cue_gender"]),
        "conflicts": sum(1 for r in reviewers.values() if r["conflict"]),
        "gender_counts": dict(Counter(r["gender"] or "unknown" for r in reviewers.values())),
    }
    return {"_meta": meta, "reviewers": dict(sorted(reviewers.items()))}


def load_reviewer_gender(path: Path = REVIEWER_GENDER_SNAPSHOT) -> dict[str, str | None]:
    """Read the artifact into ``{reviewerID: 'm' | 'f' | None}`` for the pairing step."""
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    return {rid: entry["gender"] for rid, entry in data["reviewers"].items()}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: read the cleaned English layer, write the reviewer-gender artifact."""
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--amazon", default=str(AMAZON_EN_INTERMEDIATE))
    parser.add_argument("--out", default=str(REVIEWER_GENDER_SNAPSHOT))
    parser.add_argument("--force", action="store_true", help="Overwrite the artifact.")
    args = parser.parse_args(argv)

    users = json.loads(Path(args.amazon).read_text(encoding="utf-8"))
    artifact = build(users)
    target = require_can_write(args.out, overwrite=args.force, artifact="reviewer gender")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(artifact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = artifact["_meta"]
    print(
        f"reviewers: {meta['reviewers']}  name verdicts: {meta['name_verdicts']}  "
        f"cue verdicts: {meta['cue_verdicts']}  agree: {meta['both_agree']}/{meta['both_known']}  "
        f"conflicts: {meta['conflicts']}  gender: {meta['gender_counts']}"
    )
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
