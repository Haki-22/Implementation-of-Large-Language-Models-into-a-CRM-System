"""Centralised project paths for the technical prototype.

This module provides a single source of truth for common directories and files,
eliminating the need for fragile ``Path(__file__).parents[N]`` logic across
multiple scripts. All paths are absolute and resolved.
"""

from pathlib import Path


# Project root for this repository.
THESIS_ROOT = Path(__file__).resolve().parents[1]

# Major subdirectories
SUBSTRATE_DIR = THESIS_ROOT / "substrate"
# Committed inputs the substrate is built with (reduced ČSÚ tables, the vendored stop-list).
SUBSTRATE_DATA_DIR = SUBSTRATE_DIR / "data"
UCS_DIR = THESIS_ROOT / "ucs"
UTILS_DIR = THESIS_ROOT / "utils"

# Pipeline internals
PIPELINE_DIR = SUBSTRATE_DIR / "pipeline"
DOWNLOADS_DIR = (
    PIPELINE_DIR / "data_acquisition" / "downloaded"
)  # every pinned public download lands here
STRATIFIED_500_USERS = PIPELINE_DIR / "data_acquisition" / "stratified_500_users.json"

# Specific data paths
SNAPSHOTS_DIR = SUBSTRATE_DIR / "snapshots"
INTERMEDIATE_DIR = SNAPSHOTS_DIR / "intermediate"
PROVENANCE_DIR = SNAPSHOTS_DIR / "provenance"  # frozen evidence, never regenerated
SUBSTRATE_DB = SNAPSHOTS_DIR / "substrate.db"
CATALOG_EN = SNAPSHOTS_DIR / "amazon" / "amazon-catalog-en.json"
CATALOG_TITLES_CS = SNAPSHOTS_DIR / "amazon" / "amazon-catalog-titles-cs.json"

# UC-specific roots (convenience)
UC01_DIR = UCS_DIR / "uc01_personalization"
UC02_DIR = UCS_DIR / "uc02_pseudonymization"
UC03_DIR = UCS_DIR / "uc03_mcp_privacy"
UC04_DIR = UCS_DIR / "uc04_matchmaker"

# Canonical snapshots
CONTACTS_SNAPSHOT = SNAPSHOTS_DIR / "contacts" / "contacts.json"
NOTES_SNAPSHOT = SNAPSHOTS_DIR / "contacts" / "notes.json"
COMPANIES_SNAPSHOT = SNAPSHOTS_DIR / "contacts" / "companies.json"
OCEAN_INFERRED_SNAPSHOT = UC01_DIR / "snapshots" / "ocean_inferred.json"
JUDGE_TESTSET_SNAPSHOT = UC01_DIR / "snapshots" / "uc01-judge-testset.json"
UC01_PICKS_DIR = UC01_DIR / "snapshots" / "picks"  # who the reported runs are for (picker.py)
UC01_RUNS_DIR = UC01_DIR / "snapshots" / "runs"  # one folder per run (runner.py)
REVIEWERS_CZ_SNAPSHOT = SNAPSHOTS_DIR / "amazon" / "amazon-translated-cz.json"
REVIEWERS_EN_SNAPSHOT = SNAPSHOTS_DIR / "amazon" / "amazon-original-en.json"
TRANSLATION_COVERAGE = SNAPSHOTS_DIR / "amazon" / "translation-coverage.json"
REVIEWER_GENDER_SNAPSHOT = SNAPSHOTS_DIR / "amazon" / "reviewer-gender.json"
BRIEFS_SNAPSHOT = SNAPSHOTS_DIR / "briefs" / "message_briefs.json"
OCEAN_SYNTHETIC_SNAPSHOT = SNAPSHOTS_DIR / "ocean" / "ocean_synthetic_500.json"

# UC-02-local PII corpus + gold-label sidecar (UC-02's own snapshots,
# distinct from the substrate-level PII corpus above).
UC02_PII_CORPUS_SNAPSHOT = UC02_DIR / "snapshots" / "uc02-pii-corpus.json"
UC02_PII_GOLD_SNAPSHOT = UC02_DIR / "snapshots" / "uc02-pii-gold.jsonl"

# Intermediate and Bridge artifacts
AMAZON_EN_INTERMEDIATE = INTERMEDIATE_DIR / "english-amazon.json"
ENGLISH_ITEMS = INTERMEDIATE_DIR / "english-items.jsonl"
STAGE1_TRANSLATE = (
    PROVENANCE_DIR / "translation" / "stage1-translate.json"
)  # FROZEN, one-time run 2026-05-29

# Integration points
UC04_HANDOFF = UC04_DIR / "results" / "uc04_to_uc01_handoff.json"
UC04_SAMPLES_DIR = UC04_DIR / "eval" / "samples"  # the fixed customer sample of the model arms (sample.py)

# Frozen evidence kept from before the 2026-09-02 cleaning (the contacts as the May
# results read them, with the unrecorded OCEAN backfill; irreproducible).
PRECLEAN_DIR = PROVENANCE_DIR / "pre-clean-2026-09-02"
PRECLEAN_CONTACTS = PRECLEAN_DIR / "uc01-contacts-english-mapped-snapshot.json"
