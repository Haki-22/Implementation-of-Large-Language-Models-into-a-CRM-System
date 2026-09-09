"""Every name used in the project's code must be defined or imported (ruff F821).

Why this exists: in June 2026 a cleanup pass removed eleven imports from
``substrate/generators/__main__.py`` and deleted its test. The
documented-entry-point smoke test kept passing because ``--help`` runs before
the broken code, and the script stayed unrunnable for three months. A static
undefined-name check catches that class of breakage regardless of which code
path a test happens to execute.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[1]


def _ruff() -> str | None:
    venv_ruff = Path(sys.executable).with_name("ruff")
    if venv_ruff.exists():
        return str(venv_ruff)
    return shutil.which("ruff")


def test_no_undefined_names_in_thesis_code():
    ruff = _ruff()
    if ruff is None:
        pytest.skip("ruff not installed (requirements.txt pins it)")
    proc = subprocess.run(
        [
            ruff,
            "check",
            "--select",
            "F821",
            # ``--extend-exclude`` keeps ruff's default excludes (``.venv``, ``venv``,
            # ``site-packages``, ...); a plain ``--exclude`` would replace them and lint
            # the environment the README tells the reader to create inside the repository.
            "--extend-exclude",
            "_external,node_modules",
            "--output-format",
            "concise",
            ".",
        ],
        cwd=_ROOT,
        capture_output=True,
        text=True,
    )
    assert proc.returncode == 0, "undefined names in thesis code:\n" + proc.stdout + proc.stderr
