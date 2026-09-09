"""The one-time translation must not be re-run by accident."""

from __future__ import annotations

import subprocess
import sys


def test_stage1_refuses_to_run_without_unfreeze():
    proc = subprocess.run(
        [sys.executable, "-m", "substrate.pipeline.translation_pipeline.stage1_translate", "--limit", "1"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3
    assert "FROZEN" in proc.stderr


def test_stage1_help_still_works():
    proc = subprocess.run(
        [sys.executable, "-m", "substrate.pipeline.translation_pipeline.stage1_translate", "--help"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0
