"""Run every generator in this package and write its committed snapshot.

The only entry point in this package. One command, one coordinated seed: it
writes all three snapshots together so they cannot disagree about which contacts
they describe, refreshes the OCEAN projection derived from them, and loads the
result into ``substrate.db``. Every other module here is import-only.

Inputs
------
- ``substrate/snapshots/intermediate/english-amazon.json`` (the 425 stratified
  reviewers, cleaned by the ``english`` step of ``build_all``). Only ``reviewerID``
  and ``group`` are used here.
- ``substrate/snapshots/amazon/reviewer-gender.json`` (the ``reviewer_gender`` step):
  the inferred gender of each reviewer, which decides the pairing below.

Outputs (committed snapshots, all required by ``build_substrate_db.py``)
------------------------------------------------------------------------
- ``contacts/contacts.json`` -- 500 deterministic Czech identities (``contacts/``,
  seed 42); named for the layer, not for a use case: every UC and the frontend build on it.
  The first 425 contacts are paired with the stratified reviewers **inside each
  group** (the reviewers are ordered A (300), B (50), C (75)) so that a contact's
  gender matches its reviewer's wherever the reviewer's gender is known
  (``pair_by_gender``): the contact carries ``reviewer_id`` + ``amazon_group`` +
  ``reviewer_gender`` + ``gender_paired``. ``build_contacts`` first reorders the
  generated contacts to clean (375), defective (50), clean (75), so every
  defective contact sits inside group C and the 75 unlinked prospects at the
  tail are all clean. Until 2026-09-04 the join was positional; that put a man's
  history behind about half of the women (145 of the 293 pairs with a known
  reviewer gender). Pairing brings it down to the leftover male reviewers (54),
  and never gives a man a woman's history, without regenerating a single identity.
- ``contacts/notes.json`` -- 80 seeded Czech CRM notes
  (``notes/``, fixed ``NOTES_ANCHOR``).
- ``contacts/companies.json`` -- the 8 partner companies the contacts
  affiliate with, with seeded registry fields (``companies.py``).
- ``ocean/ocean_synthetic_500.json`` -- the projection of the sampled OCEAN profiles,
  re-derived so it can never describe an older cohort than the contacts do.
- ``substrate.db`` -- the CRM database, reassembled from the snapshots above plus the
  Amazon layer (unless ``--snapshots-only``).

No free text is written here: ``prior_interactions`` and ``frequent_words`` are
filled by the assembler from the translated reviews.

Run:
    python -m substrate.generators --force                   # snapshots -> DB
    python -m substrate.generators --force --snapshots-only  # stop at the snapshots

``substrate.pipeline.build_all`` calls the ``--snapshots-only`` form as its
``contacts`` step, because it runs the projection and the database as steps of
its own and reports each separately.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from substrate.generators.companies import (
    generate_companies,
    save_snapshot as save_companies_snapshot,
)
from substrate.generators.contacts import generate_contacts, save_snapshot
from substrate.generators.notes import (
    NOTES_ANCHOR,
    generate_notes,
    save_snapshot as save_notes_snapshot,
)
from substrate.pipeline.build_reviewer_gender import load_reviewer_gender
from utils.file_safety import require_can_write
from utils.paths import (
    THESIS_ROOT,
    AMAZON_EN_INTERMEDIATE,
    COMPANIES_SNAPSHOT,
    CONTACTS_SNAPSHOT,
    NOTES_SNAPSHOT,
    REVIEWER_GENDER_SNAPSHOT,
)

# The substrate holds this many contacts regardless of how many reviewers the
# stratification yields; the difference becomes unlinked prospects.
TOTAL_CONTACTS = 500

DEFAULT_AMAZON = AMAZON_EN_INTERMEDIATE
DEFAULT_CONTACTS = CONTACTS_SNAPSHOT
DEFAULT_NOTES = NOTES_SNAPSHOT
DEFAULT_COMPANIES = COMPANIES_SNAPSHOT


# ---------------------------------------------------------------------------
# Inputs
# ---------------------------------------------------------------------------


def _load_amazon(path: Path) -> list[dict[str, Any]]:
    """Read the stratified reviewer wrappers; only ``reviewerID`` and ``group`` are used."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise TypeError(f"{path} must contain a JSON list")
    return data


# ---------------------------------------------------------------------------
# Contact / reviewer pairing
# ---------------------------------------------------------------------------


def _pair_block(
    block_contacts: list[dict[str, Any]],
    block_users: list[dict[str, Any]],
    reviewer_gender: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Pair one group's contacts with that group's reviewers, gender first.

    Three passes, each in position order so the result is deterministic:
    1. a contact takes a reviewer of its own gender while any is left;
    2. a still-unpaired contact takes a reviewer of unknown gender;
    3. whatever is left is handed out in order (the leftover male reviewers go
       to women, since the Amazon Electronics population is about 84 % male).
    Contacts without a gender (the defective rows) are served in passes 2 and 3.
    """
    pools: dict[str | None, list[dict[str, Any]]] = {"m": [], "f": [], None: []}
    for user in block_users:
        pools[reviewer_gender.get(user["reviewerID"])].append(user)

    paired: list[dict[str, Any] | None] = [None] * len(block_contacts)
    for i, contact in enumerate(block_contacts):
        gender = contact.get("gender")
        if gender in ("m", "f") and pools[gender]:
            paired[i] = pools[gender].pop(0)
    for i in range(len(block_contacts)):
        if paired[i] is None and pools[None]:
            paired[i] = pools[None].pop(0)
    leftover = pools["m"] + pools["f"]
    for i in range(len(block_contacts)):
        if paired[i] is None:
            paired[i] = leftover.pop(0)
    return paired  # type: ignore[return-value]


def pair_by_gender(
    contacts: list[dict[str, Any]],
    amazon_users: list[dict[str, Any]],
    reviewer_gender: dict[str, str | None],
) -> list[dict[str, Any]]:
    """Return ``amazon_users`` reordered so that ``contacts[i]`` pairs with the result's ``i``-th reviewer.

    The reviewers arrive in contiguous group blocks (A, then B, then C) and the
    contact at position *i* keeps the group of position *i*; pairing only permutes
    reviewers **within** a block, so group sizes, the defective rows' place inside
    group C and every reviewer's history are untouched. With no gender information
    (``reviewer_gender`` empty) every reviewer is "unknown" and the result is the
    original positional order.
    """
    paired: list[dict[str, Any]] = []
    seen_groups: set[str] = set()
    start = 0
    while start < len(amazon_users):
        group = amazon_users[start]["group"]
        if group in seen_groups:
            raise ValueError(
                f"reviewers must arrive in contiguous group blocks; group {group!r} reappears "
                f"at position {start}"
            )
        seen_groups.add(group)
        end = start
        while end < len(amazon_users) and amazon_users[end]["group"] == group:
            end += 1
        paired.extend(_pair_block(contacts[start:end], amazon_users[start:end], reviewer_gender))
        start = end
    return paired


def build_contacts(
    amazon_users: list[dict[str, Any]],
    *,
    seed: int,
    n_foreign: int,
    n_contacts: int = TOTAL_CONTACTS,
    n_clean: int | None = None,
    n_non_clean: int | None = None,
    reviewer_gender: dict[str, str | None] | None = None,
) -> list[dict[str, Any]]:
    """Generate the contacts and pair the first ones with Amazon reviewers, gender-matched inside each group.

    There are more contacts than reviewers on purpose. The reviewers supply the
    behavioural layer -- purchases and review text -- and the contacts left over
    are **prospects**: people in the CRM nobody has ever sold to. Every real CRM
    holds them (leads, event signups, imported lists), and they are the only way
    this substrate can offer a genuine cold-start customer, because the Amazon
    5-core source floors every reviewer at five reviews.

    The deliberately defective rows stay inside the linked block. A messy record
    in a real CRM still has order history, and keeping the two defects apart
    means a downstream failure can be attributed to one of them: a contact is
    either missing a field, or missing a history, not silently both.

    Args:
        amazon_users: Stratified reviewer wrappers (``reviewerID``, ``group``),
            in contiguous group blocks.
        seed: Generator seed.
        n_foreign: Foreign-origin contacts inside the clean subset.
        n_contacts: Total contacts to generate; the excess over ``amazon_users``
            becomes the unlinked prospects. Ignored when ``n_clean`` and
            ``n_non_clean`` are given, since those state the total themselves.
        n_clean / n_non_clean: Split of the contacts; default 90 % / 10 %.
        reviewer_gender: ``{reviewerID: 'm' | 'f' | None}`` from the
            ``reviewer_gender`` step (``build_reviewer_gender.load_reviewer_gender``).
            ``None`` or empty means no information: the pairing degenerates to
            the positional join.

    Returns:
        The contact dicts, the first ``len(amazon_users)`` of them carrying
        ``reviewer_id``, ``amazon_group``, ``reviewer_gender`` and
        ``gender_paired``; the prospects carry the blanks.
    """
    if n_clean is None and n_non_clean is None:
        n_clean = int(n_contacts * 0.90)
        n_non_clean = n_contacts - n_clean
    elif n_clean is None or n_non_clean is None:
        raise ValueError("n_clean and n_non_clean must be supplied together")
    else:
        # An explicit split states the total; n_contacts is only the default.
        n_contacts = n_clean + n_non_clean
    if len(amazon_users) > n_contacts:
        raise ValueError(
            f"{len(amazon_users)} reviewers for {n_contacts} contacts: "
            "there must be at least as many contacts as reviewers"
        )

    contacts = generate_contacts(
        seed=seed,
        n_clean=n_clean,
        n_non_clean=n_non_clean,
        n_foreign=min(n_foreign, n_clean),
    )

    # generate_contacts emits foreign, then clean, then the defective rows. Move
    # the defective block up so it lands inside the linked range and the tail of
    # unlinked prospects is entirely clean. A pure reordering: the same contacts
    # are generated either way, so the RNG stream is untouched.
    n_prospects = n_contacts - len(amazon_users)
    if n_prospects:
        defective = [c for c in contacts if not c["is_clean"]]
        clean = [c for c in contacts if c["is_clean"]]
        if len(clean) < n_prospects:
            raise ValueError(
                f"{n_prospects} prospects requested but only {len(clean)} clean contacts exist"
            )
        contacts = clean[: len(clean) - n_prospects] + defective + clean[len(clean) - n_prospects :]

    genders = reviewer_gender or {}
    for contact, user in zip(contacts, pair_by_gender(contacts, amazon_users, genders)):
        contact["reviewer_id"] = user["reviewerID"]
        contact["amazon_group"] = user["group"]
        contact["reviewer_gender"] = genders.get(user["reviewerID"])
        contact["gender_paired"] = bool(
            contact["reviewer_gender"] and contact["reviewer_gender"] == contact.get("gender")
        )
    return contacts


# ---------------------------------------------------------------------------
# Downstream steps
# ---------------------------------------------------------------------------


def _run_module(module: str, args: tuple[str, ...]) -> None:
    """Run a downstream chain module, failing loudly if it does.

    These live in ``substrate.pipeline``: a script orchestrating the steps after
    its own is fine, but importing them into the library modules of this package
    would invert the layering.
    """
    cmd = [sys.executable, "-m", module, *args]
    print(f"\n$ {' '.join(cmd[2:])}", flush=True)
    result = subprocess.run(cmd, cwd=THESIS_ROOT)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    """Write the snapshots, then refresh what is derived from them."""
    parser = argparse.ArgumentParser(
        prog="python -m substrate.generators",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--amazon",
        default=str(DEFAULT_AMAZON),
        help="Cleaned English Amazon snapshot (build_all step english).",
    )
    parser.add_argument(
        "--reviewer-gender",
        default=str(REVIEWER_GENDER_SNAPSHOT),
        help="Reviewer gender artifact (build_all step reviewer_gender); required.",
    )
    parser.add_argument(
        "--contacts", default=str(DEFAULT_CONTACTS), help="Output contact snapshot."
    )
    parser.add_argument("--notes", default=str(DEFAULT_NOTES), help="Output note snapshot.")
    parser.add_argument(
        "--companies", default=str(DEFAULT_COMPANIES), help="Output company snapshot."
    )
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--n-foreign", type=int, default=2)
    parser.add_argument("--n-notes", type=int, default=80)
    parser.add_argument("--note-pii-rate", type=float, default=0.30)
    parser.add_argument(
        "--notes-anchor",
        default=NOTES_ANCHOR.isoformat(),
        help="ISO timestamp the seeded note ages are subtracted from (default reproduces the committed snapshot).",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite the output snapshots.")
    parser.add_argument(
        "--snapshots-only",
        action="store_true",
        help="Stop after writing the snapshots; skip the OCEAN projection and the database.",
    )
    args = parser.parse_args()

    contacts_path = Path(args.contacts)
    notes_path = Path(args.notes)
    companies_path = Path(args.companies)
    for path in (contacts_path, notes_path, companies_path):
        require_can_write(path, overwrite=args.force, artifact="snapshot")

    amazon_users = _load_amazon(Path(args.amazon))
    gender_path = Path(args.reviewer_gender)
    if not gender_path.exists():
        # Pure assembly: never fall back to the positional join silently.
        raise SystemExit(
            f"reviewer gender artifact missing: {gender_path}. Run "
            "`python -m substrate.pipeline.build_reviewer_gender --force` first "
            "(build_all step reviewer_gender)."
        )
    reviewer_gender = load_reviewer_gender(gender_path)
    companies = generate_companies(seed=args.seed)
    contacts = build_contacts(
        amazon_users, seed=args.seed, n_foreign=args.n_foreign, reviewer_gender=reviewer_gender
    )
    notes = generate_notes(
        contacts,
        seed=args.seed,
        n=args.n_notes,
        pii_rate=args.note_pii_rate,
        today=datetime.fromisoformat(args.notes_anchor),
    )

    save_snapshot(contacts, contacts_path, overwrite=args.force)
    save_notes_snapshot(notes, notes_path, overwrite=args.force)
    save_companies_snapshot(companies, companies_path, overwrite=args.force)

    groups = Counter(user["group"] for user in amazon_users)
    n_prospects = len(contacts) - len(amazon_users)
    linked = contacts[: len(amazon_users)]
    known = sum(1 for c in linked if c["reviewer_gender"] and c.get("gender"))
    paired = sum(1 for c in linked if c["gender_paired"])
    print(f"Wrote contacts: {contacts_path} ({len(contacts)} rows)")
    print(f"Wrote notes: {notes_path} ({len(notes)} rows)")
    print(f"Wrote companies: {companies_path} ({len(companies)} rows)")
    print(f"Groups: {dict(groups)} + {n_prospects} prospects with no Amazon link")
    print(
        f"Gender pairing: {paired} of {known} pairs with a known reviewer gender match "
        f"({known - paired} mismatched, {len(linked) - known} unknown)"
    )

    if args.snapshots_only:
        return

    # Anything derived from the contacts is now out of date, so refresh it here
    # rather than leaving a snapshot that describes an older cohort.
    _run_module("substrate.pipeline.build_ocean_synthetic", ())
    _run_module("substrate.pipeline.build_substrate_db", ("--force",) if args.force else ())


if __name__ == "__main__":
    main()
