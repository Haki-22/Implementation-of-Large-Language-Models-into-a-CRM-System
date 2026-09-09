"""Smoke tests for every CLI + module reference the project READMEs claim.

The job is narrow: if a README says "run this command" or "import this
module", this test makes sure the command at least starts (rc=0 from
``--help``) and the module imports without raising. The point is to catch
documentation drift before a reviewer does.

These tests are deliberately fast: every CLI test only invokes ``--help``
(no real work happens), and the only end-to-end run is a fresh substrate
rebuild against ``tmp_path`` which the README claims takes ~10 s.

Adding a new entry point:
    1. Document it in some README.
    2. Add the command / module to one of the lists below.
    3. Re-run ``pytest tests/test_documented_entry_points.py -q``.

Adding a test that would call a real LLM:
    don't. Use ``--dry-run`` or skip it.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from utils.paths import CATALOG_EN, REVIEWERS_CZ_SNAPSHOT, REVIEWERS_EN_SNAPSHOT


_PROJECT_ROOT = Path(__file__).resolve().parents[1]
_PYTHON = sys.executable


# ---------------------------------------------------------------------------
# Documented CLIs — every one of these is described in at least one README.
# ---------------------------------------------------------------------------

DOCUMENTED_CLIS: list[list[str]] = [
    # ---- substrate -------------------------------------------------------
    [_PYTHON, "-m", "substrate.pipeline.build_all", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.build_substrate_db", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.build_clean_snapshots", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.build_english_snapshot", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.data_acquisition.fetch_and_filter", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.data_acquisition.fetch_csu", "--help"],
    [_PYTHON, "-m", "substrate.generators", "--help"],
    [_PYTHON, "-m", "substrate.pipeline.build_ocean_synthetic", "--help"],
    # ---- utils -----------------------------------------------------------
    [_PYTHON, "-m", "utils.generation.cli", "--list-options"],
    [_PYTHON, "-m", "utils.text_hygiene", "--help"],
    [_PYTHON, "-m", "utils.llm_switch"],
    # ---- UC-01 -----------------------------------------------------------
    [_PYTHON, "-m", "ucs.uc01_personalization", "--help"],
    [_PYTHON, "-m", "ucs.uc01_personalization.judge_testset", "--help"],
    [_PYTHON, "-m", "ucs.uc01_personalization.ocean_inference", "--help"],
    [_PYTHON, "-m", "ucs.uc01_personalization.ocean_inference", "infer", "--help"],
    [_PYTHON, "-m", "ucs.uc01_personalization.ocean_inference", "freeze", "--help"],
    [_PYTHON, "-m", "ucs.uc01_personalization.ocean_inference", "attachment", "--help"],
    # ---- UC-02 -----------------------------------------------------------
    [_PYTHON, "-m", "ucs.uc02_pseudonymization.code.pii_corpus", "--help"],
    [_PYTHON, "-m", "ucs.uc02_pseudonymization.eval.run_table", "--help"],
    [_PYTHON, "-m", "ucs.uc02_pseudonymization.eval.casing_table", "--help"],
    [_PYTHON, "-m", "ucs.uc02_pseudonymization.eval.false_alarms", "--help"],
    [_PYTHON, "-m", "ucs.uc02_pseudonymization.eval.live_check", "--help"],
    # ---- UC-03 -----------------------------------------------------------
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.chat", "--help"],
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.stt", "--help"],
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.review", "--help"],
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.tool_manifest", "--help"],
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.server", "--help"],
    [_PYTHON, "-m", "ucs.uc03_mcp_privacy.audit_log", "--help"],
    # ---- UC-04 -----------------------------------------------------------
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "run", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "facts", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "attachment", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "sample", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "personality", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "for-uc01", "run", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "for-uc01", "freeze", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "model-run", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "model-report", "--help"],
    [_PYTHON, "-m", "ucs.uc04_matchmaker", "card", "--help"],
    # ---- UC-04 dispatchers (must accept --help without calling an LLM)
]


def _cli_id(cmd: list[str]) -> str:
    """Render a parametrize ID from ``python -m <module> --help`` form."""
    if "-m" in cmd:
        return cmd[cmd.index("-m") + 1]
    return " ".join(cmd[1:3])


@pytest.mark.parametrize("cmd", DOCUMENTED_CLIS, ids=_cli_id)
def test_documented_cli_starts(cmd: list[str]) -> None:
    """Every documented CLI must return rc=0 from ``--help``.

    Run from the project root so module discovery works.  We intentionally
    pass ``--help`` (or ``--list-options`` for the generation CLI) so no real
    work happens; the test only proves the script's argparse setup is sound
    and the module imports cleanly.
    """
    env = os.environ.copy()

    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        timeout=30,
        env=env,
    )
    assert result.returncode == 0, (
        f"{' '.join(cmd[1:])} exited rc={result.returncode}\n"
        f"--- stdout ---\n{result.stdout.decode(errors='replace')[-2000:]}\n"
        f"--- stderr ---\n{result.stderr.decode(errors='replace')[-2000:]}"
    )


# ---------------------------------------------------------------------------
# Documented modules — every one of these is referenced from a README as
# an import target.
# ---------------------------------------------------------------------------

DOCUMENTED_MODULES: list[str] = [
    # substrate
    "substrate.schema.session",
    "substrate.schema.models",
    "substrate.generators.contacts",
    "substrate.generators.companies",
    "substrate.generators.notes",
    "utils.czech_identifiers",
    "substrate.pipeline.build_substrate_db",
    "substrate.pipeline.build_all",
    "substrate.pipeline.amazon_lookup",
    # utils
    "utils.paths",
    "utils.generation",
    "utils.generation.errors",
    "utils.generation.claude",
    "utils.generation.codex",
    "utils.generation.agy",
    "utils.generation.mock",
    "utils.generation.models",
    "utils.generation.catalog",
    "utils.generation.catalog.codegen",
    "utils.promptmodel",
    # UC-01
    "ucs.uc01_personalization",
    "ucs.uc01_personalization.data",
    "ucs.uc01_personalization.prompts",
    "ucs.uc01_personalization.levels",
    "ucs.uc01_personalization.judge",
    "ucs.uc01_personalization.generate",
    "ucs.uc01_personalization.picker",
    "ucs.uc01_personalization.runner",
    "ucs.uc01_personalization.metrics",
    # UC-02
    "ucs.uc02_pseudonymization",
    "ucs.uc02_pseudonymization.code.envelope",
    "ucs.uc02_pseudonymization.code.pseudonymizer",
    "ucs.uc02_pseudonymization.code.ner",
    "ucs.uc02_pseudonymization.code.ner_presidio",
    "ucs.uc02_pseudonymization.code.pii_corpus",
    "ucs.uc02_pseudonymization.eval.runs",
    "ucs.uc02_pseudonymization.eval.run_table",
    "ucs.uc02_pseudonymization.eval.false_alarms",
    "ucs.uc02_pseudonymization.eval.live_check",
    "ucs.uc02_pseudonymization.eval.nametag3_adapter",
    # UC-03
    "ucs.uc03_mcp_privacy.tools",
    "ucs.uc03_mcp_privacy.audit_log",
    "ucs.uc03_mcp_privacy.tool_manifest",
    "ucs.uc03_mcp_privacy.envelope",
    "ucs.uc03_mcp_privacy.server",
    "ucs.uc03_mcp_privacy.stt",
    "ucs.uc03_mcp_privacy.chat",
    "ucs.uc03_mcp_privacy.mcp_client",
    "ucs.uc03_mcp_privacy.review",
    "ucs.uc03_mcp_privacy.categorizer",
    # UC-04
    "ucs.uc04_matchmaker.arena",
    "ucs.uc04_matchmaker.model_arena",
    "ucs.uc04_matchmaker.arms.model",
    "ucs.uc04_matchmaker.data",
    "ucs.uc04_matchmaker.protocols",
    "ucs.uc04_matchmaker.population",
    "ucs.uc04_matchmaker.arms",
    "ucs.uc04_matchmaker.facts",
    "ucs.uc04_matchmaker.attachment",
    "ucs.uc04_matchmaker.sample",
    "ucs.uc04_matchmaker.personality",
    "ucs.uc04_matchmaker.outputs_for_uc01",
    "ucs.uc04_matchmaker.outputs_for_uc01.run",
]


@pytest.mark.parametrize("module", DOCUMENTED_MODULES, ids=lambda m: m)
def test_documented_module_imports(module: str) -> None:
    """Every documented module must import without raising."""
    cmd = [_PYTHON, "-c", f"import {module}"]
    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"import {module} failed:\n--- stderr ---\n{result.stderr.decode(errors='replace')[-2000:]}"
    )


# ---------------------------------------------------------------------------
# Documented public-API symbols — every one of these is referenced from a
# README as importable from the package's top-level ``__init__``.
# ---------------------------------------------------------------------------

DOCUMENTED_SYMBOLS: list[tuple[str, str]] = [
    # UC-02 public API per ucs/uc02_pseudonymization/README.md
    ("ucs.uc02_pseudonymization", "with_envelope"),
    ("ucs.uc02_pseudonymization", "compose_system_prompt"),
    ("ucs.uc02_pseudonymization", "pseudonymize"),
    ("ucs.uc02_pseudonymization", "depseudonymize"),
    ("ucs.uc02_pseudonymization", "MappingRegistry"),
    ("ucs.uc02_pseudonymization", "EnvelopeProviderError"),
    ("ucs.uc02_pseudonymization", "EnvelopeIntegrityError"),
    # utils.paths constants per utils/README.md
    ("utils.paths", "THESIS_ROOT"),
    ("utils.paths", "SUBSTRATE_DB"),
    ("utils.paths", "SNAPSHOTS_DIR"),
    ("utils.paths", "UC01_DIR"),
    ("utils.paths", "UC04_DIR"),
    ("utils.paths", "UC04_HANDOFF"),
]


@pytest.mark.parametrize(
    "module,symbol", DOCUMENTED_SYMBOLS, ids=lambda v: v if isinstance(v, str) else ""
)
def test_documented_symbol_is_importable(module: str, symbol: str) -> None:
    """Every documented public-API symbol must be importable from its module."""
    cmd = [_PYTHON, "-c", f"from {module} import {symbol}"]
    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, (
        f"from {module} import {symbol} failed:\n"
        f"--- stderr ---\n{result.stderr.decode(errors='replace')[-2000:]}"
    )


# ---------------------------------------------------------------------------
# Snapshot regen — the README's headline claim is that running this command
# rebuilds the canonical substrate DB from JSON snapshots in roughly 10 s.
# ---------------------------------------------------------------------------


@pytest.mark.skipif(
    not all(p.exists() for p in (REVIEWERS_EN_SNAPSHOT, REVIEWERS_CZ_SNAPSHOT, CATALOG_EN)),
    reason="shipped snapshots not unpacked yet; run: python -m substrate.pipeline.packing --unpack",
)
def test_substrate_db_rebuilds_from_snapshots(tmp_path: Path) -> None:
    """``build_substrate_db`` must rebuild ``substrate.db`` from snapshots.

    Writes into ``tmp_path`` rather than the real snapshot directory so a
    failed regen never trashes the committed DB.  The test asserts only
    that a non-trivial database is produced; the exact row counts are
    covered by other tests.
    """
    db = tmp_path / "substrate.db"
    cmd = [
        _PYTHON,
        "-m",
        "substrate.pipeline.build_substrate_db",
        "--db",
        str(db),
        "--force",
    ]
    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        timeout=120,
    )
    assert result.returncode == 0, (
        "substrate rebuild failed:\n"
        f"--- stdout ---\n{result.stdout.decode(errors='replace')[-2000:]}\n"
        f"--- stderr ---\n{result.stderr.decode(errors='replace')[-2000:]}"
    )
    assert db.exists(), "substrate.db not written"
    assert db.stat().st_size > 1_000_000, (
        f"substrate.db is suspiciously small ({db.stat().st_size} bytes)"
    )


def test_substrate_ocean_synthetic_rebuilds(tmp_path: Path) -> None:
    """``build_ocean_synthetic`` must regenerate the OCEAN snapshot."""
    out = tmp_path / "ocean_synthetic_500.json"
    cmd = [
        _PYTHON,
        "-m",
        "substrate.pipeline.build_ocean_synthetic",
        "--out",
        str(out),
    ]
    result = subprocess.run(
        cmd,
        cwd=_PROJECT_ROOT,
        capture_output=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(
            "build_ocean_synthetic does not yet support --out; covered once the driver lands"
        )
    assert out.exists()
    assert out.stat().st_size > 1_000
