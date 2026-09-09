"""Rebuild the whole substrate with one command.

The chain is a sequence of small scripts, each reading committed snapshots and
writing the next one. Running them by hand means copying the eight commands
below (``STEPS``) in the right order with the right flags; this runs them in
that order, stops at the first failure, ends with the text-hygiene audit gate
and prints a manifest of what was produced.

    python -m substrate.pipeline.build_all --verify   # read-only preflight, seconds
    python -m substrate.pipeline.build_all --force    # full rebuild from the raw dumps, minutes

A full rebuild fetches any raw input that is missing by itself (the two Amazon
dumps, ~680 MB, and the ČSÚ + Czech Post files, ~885 MB; every file md5-pinned,
see ``data_acquisition/inputs.py``), so "start here" is one command on a fresh
clone. ``--verify`` never downloads. Both modes first unpack the large snapshots
git ships compressed (``packing.py``), which is all a fresh clone needs for
``--from database``.

The translation is never part of a rebuild: it ran once on 2026-05-29, cost
money, and is frozen evidence the chain joins against by item id. See
``pipeline/translation_pipeline/README.md``.

For day-to-day work none of this is needed -- the committed JSON snapshots are
enough and only the database step has to run (``--from database``, ~45 s).

Freshness is judged by file time: a step is STALE when one of its inputs is
newer than its output. A byte-identical regeneration of a snapshot therefore
still makes the steps derived from it report STALE; re-run those steps, they
are cheap.
"""

from __future__ import annotations

import argparse
import subprocess
import sqlite3
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from substrate.constants import REVIEWS_FTS_TABLE
from substrate.pipeline import packing
from substrate.pipeline.data_acquisition.inputs import download_size_mb, ensure_raw_inputs
from utils.file_safety import file_md5
from utils.paths import (
    AMAZON_EN_INTERMEDIATE,
    BRIEFS_SNAPSHOT,
    CATALOG_EN,
    CATALOG_TITLES_CS,
    COMPANIES_SNAPSHOT,
    CONTACTS_SNAPSHOT,
    ENGLISH_ITEMS,
    NOTES_SNAPSHOT,
    OCEAN_SYNTHETIC_SNAPSHOT,
    REVIEWER_GENDER_SNAPSHOT,
    REVIEWERS_CZ_SNAPSHOT,
    REVIEWERS_EN_SNAPSHOT,
    STAGE1_TRANSLATE,
    STRATIFIED_500_USERS,
    SUBSTRATE_DB,
    THESIS_ROOT,
    UC04_HANDOFF,
)

# Critical text-hygiene hits the audit gate is allowed to report. Empty since
# 2026-09-04: the last exception (a UC-01 derivation with one U+FFFD) was deleted
# with the old UC-01 pipeline.
KNOWN_AUDIT_EXCEPTIONS: frozenset[str] = frozenset()

AUDIT_PATHS = (
    "substrate/snapshots",
    "ucs/uc01_personalization/snapshots",
    "ucs/uc02_pseudonymization/snapshots",
)


# ---------------------------------------------------------------------------
# The chain
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Step:
    """One command in the chain."""

    name: str
    what: str
    module: str
    args: tuple[str, ...] = ()
    verify_args: tuple[str, ...] | None = None  # read-only form, when one exists
    produces: tuple[Path, ...] = field(default_factory=tuple)
    derives_from: tuple[Path, ...] = field(default_factory=tuple)


STEPS: tuple[Step, ...] = (
    Step(
        name="amazon",
        what="Verify the raw Amazon dumps against the pinned size + md5",
        module="substrate.pipeline.data_acquisition.fetch_and_filter",
        args=("--force",),
        verify_args=("--verify-only",),
    ),
    Step(
        name="csu",
        what="Verify / rebuild the reduced ČSÚ + Czech Post demographic tables",
        module="substrate.pipeline.data_acquisition.fetch_csu",
        args=("--force",),
        verify_args=("--verify-only",),
    ),
    Step(
        name="english",
        what="Clean the English text and rebuild the translation queue",
        module="substrate.pipeline.build_english_snapshot",
        args=("--force", "--check-against-frozen"),
        # No read-only form: --check-against-frozen still rebuilds the queue first,
        # so the preflight only checks that the queue is on disk.
        produces=(AMAZON_EN_INTERMEDIATE, ENGLISH_ITEMS),
        derives_from=(STRATIFIED_500_USERS,),
    ),
    Step(
        name="clean",
        what="Join the frozen Czech text with the English layer and the catalogue",
        module="substrate.pipeline.build_clean_snapshots",
        args=("--force",),
        produces=(REVIEWERS_CZ_SNAPSHOT, REVIEWERS_EN_SNAPSHOT, CATALOG_TITLES_CS),
        derives_from=(AMAZON_EN_INTERMEDIATE, STAGE1_TRANSLATE),
    ),
    Step(
        name="reviewer_gender",
        what="Infer each reviewer's gender from their Amazon name + English self-references",
        module="substrate.pipeline.build_reviewer_gender",
        args=("--force",),
        produces=(REVIEWER_GENDER_SNAPSHOT,),
        derives_from=(AMAZON_EN_INTERMEDIATE,),
    ),
    Step(
        name="contacts",
        what="Generate the 500 Czech identities (paired with reviewers by gender), 80 notes and 8 partner companies",
        module="substrate.generators",
        args=("--force", "--snapshots-only"),
        produces=(CONTACTS_SNAPSHOT, NOTES_SNAPSHOT, COMPANIES_SNAPSHOT),
        derives_from=(REVIEWER_GENDER_SNAPSHOT,),
    ),
    Step(
        name="ocean",
        what="Re-derive the OCEAN projection report from the contacts snapshot",
        module="substrate.pipeline.build_ocean_synthetic",
        produces=(OCEAN_SYNTHETIC_SNAPSHOT,),
        derives_from=(CONTACTS_SNAPSHOT,),
    ),
    Step(
        name="database",
        what="Assemble substrate.db from the committed snapshots",
        module="substrate.pipeline.build_substrate_db",
        args=("--force",),
        produces=(SUBSTRATE_DB,),
        derives_from=(
            CONTACTS_SNAPSHOT,
            NOTES_SNAPSHOT,
            COMPANIES_SNAPSHOT,
            BRIEFS_SNAPSHOT,
            REVIEWERS_EN_SNAPSHOT,
            REVIEWERS_CZ_SNAPSHOT,
            CATALOG_EN,
            CATALOG_TITLES_CS,
            UC04_HANDOFF,  # UC-04's committed results: rerun UC-04, then --from database
        ),
    ),
)

STEP_NAMES = tuple(step.name for step in STEPS)


# ---------------------------------------------------------------------------
# Step execution
# ---------------------------------------------------------------------------


def _run(module: str, args: tuple[str, ...]) -> int:
    """Run one chain module as a subprocess, streaming its output."""
    cmd = [sys.executable, "-m", module, *args]
    print(f"\n$ {' '.join(cmd[2:])}", flush=True)
    return subprocess.run(cmd, cwd=THESIS_ROOT).returncode


def _audit() -> tuple[int, list[str]]:
    """Run the text-hygiene audit; return (unexpected critical count, offending files)."""
    cmd = [
        sys.executable,
        "-m",
        "utils.text_hygiene",
        "audit",
        *AUDIT_PATHS,
        "--exclude",
        "intermediate/",
        "--exclude",
        "provenance/",
        "--exclude",
        "pre-backfill",
    ]
    print(f"\n$ {' '.join(cmd[2:])}", flush=True)
    proc = subprocess.run(cmd, cwd=THESIS_ROOT, capture_output=True, text=True)
    print(proc.stdout, end="")

    unexpected = [
        line.split()[1]
        for line in proc.stdout.splitlines()
        if line.startswith("CRITICAL") and line.split()[1] not in KNOWN_AUDIT_EXCEPTIONS
    ]
    return len(unexpected), unexpected


# ---------------------------------------------------------------------------
# Preflight checks
# ---------------------------------------------------------------------------


def _outputs_problems(step: Step) -> list[str]:
    """Report a step's outputs as missing or stale.

    Stale means an input is newer than an output: the step has not been re-run
    since whatever it derives from last changed. Catching that is the whole
    point of a preflight — a snapshot that merely *exists* can still describe a
    substrate two regenerations old.
    """
    problems = [f"MISSING {path}" for path in step.produces if not path.exists()]
    if problems:
        return problems

    for output in step.produces:
        for source in step.derives_from:
            if source.exists() and source.stat().st_mtime > output.stat().st_mtime:
                problems.append(
                    f"STALE {output.relative_to(THESIS_ROOT)} is older than "
                    f"{source.relative_to(THESIS_ROOT)} — re-run with "
                    f"--force --from {step.name}"
                )
    return problems


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------


def _manifest() -> None:
    """Print what the rebuild produced: table counts and snapshot fingerprints."""
    print("\n--- manifest -------------------------------------------------------")

    if SUBSTRATE_DB.exists():
        con = sqlite3.connect(SUBSTRATE_DB)
        try:
            tables = [
                row[0]
                for row in con.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                )
            ]
            # The FTS5 index and its shadow tables (_data, _idx, _docsize, _config)
            # are not entities; report the index once, by name.
            for table in tables:
                if table.startswith(REVIEWS_FTS_TABLE):
                    continue
                count = con.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                print(f"  {table:<22} {count:>8,d} rows")
            if REVIEWS_FTS_TABLE in tables:
                print(f"  {REVIEWS_FTS_TABLE:<22} full-text index over uc_reviews")
        finally:
            con.close()

    print()
    for path in (
        CATALOG_TITLES_CS,
        REVIEWER_GENDER_SNAPSHOT,
        CONTACTS_SNAPSHOT,
        NOTES_SNAPSHOT,
        COMPANIES_SNAPSHOT,
        BRIEFS_SNAPSHOT,
        OCEAN_SYNTHETIC_SNAPSHOT,
    ):
        if path.exists():
            print(f"  {path.relative_to(THESIS_ROOT)!s:<62} md5 {file_md5(path)}")
    for path in packing.PACKED[:4]:  # the shipped (compressed) form of the large snapshots
        gz_path = packing.packed_path(path)
        if gz_path.exists():
            print(f"  {gz_path.relative_to(THESIS_ROOT)!s:<62} md5 {file_md5(gz_path)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point: ``--verify`` (read-only preflight) or ``--force`` (rebuild), optionally ``--from <step>``."""
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--verify",
        action="store_true",
        help="Read-only preflight: check the pinned inputs and that every snapshot exists.",
    )
    mode.add_argument(
        "--force",
        action="store_true",
        help="Rebuild every step, overwriting the committed snapshots.",
    )
    parser.add_argument(
        "--from",
        dest="start",
        choices=STEP_NAMES,
        help="Start at this step instead of the first one.",
    )
    args = parser.parse_args()

    steps = list(STEPS)
    if args.start:
        steps = steps[STEP_NAMES.index(args.start) :]

    print("Substrate rebuild" if args.force else "Substrate preflight")
    print("The translation stays frozen; the chain joins against it by item id.")

    # Git ships the large snapshots compressed; the code reads the plain files.
    # Materialise whatever a fresh clone (or a newer .gz) has not unpacked yet.
    for path in packing.ensure_unpacked():
        print(f"  unpacked {path.relative_to(THESIS_ROOT)}")

    # The two acquisition steps need the raw dumps on disk. A rebuild fetches what is
    # missing (pinned, verified); the preflight only reports, through the steps below.
    if args.force and any(step.name in ("amazon", "csu") for step in steps):
        pending_mb = download_size_mb()
        if pending_mb:
            print(f"\nraw inputs missing: fetching {pending_mb:.0f} MB first", flush=True)
        ensure_raw_inputs()

    started = time.time()
    for index, step in enumerate(steps, start=1):
        if args.verify:
            if step.verify_args is None:
                problems = _outputs_problems(step)
                status = "\n    ".join(problems) if problems else "ok"
                print(f"\n[{index}/{len(steps)}] {step.name}: {step.what}\n    {status}")
                if problems:
                    return 1
                continue
            step_args = step.verify_args
        else:
            step_args = step.args

        print(f"\n[{index}/{len(steps)}] {step.name}: {step.what}")
        code = _run(step.module, step_args)
        if code != 0:
            print(f"\nFAILED at step '{step.name}' (exit {code}). Chain stopped.", file=sys.stderr)
            return code

    unexpected, offenders = _audit()
    if unexpected:
        print(f"\nFAILED: {unexpected} unexpected critical hit(s):", file=sys.stderr)
        for path in offenders:
            print(f"  {path}", file=sys.stderr)
        return 1

    _manifest()
    print(f"\nDone in {time.time() - started:.0f} s.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
