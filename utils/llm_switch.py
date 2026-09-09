"""One switch for every paid or external model call in the prototype.

Nothing in this repository may call a language model, a cloud translator or a
cloud speech recogniser unless the switch is on. The switch is off by default so
a rerun, a test session or a demo can never spend quota by accident.

Setting it
----------
- ``THESIS_LLM_CALLS=TRUE`` or ``FALSE`` in ``.env`` at the thesis root
  (``env.example`` is the template; ``.env`` itself is git-ignored), or
- the same variable in the process environment, which overrides the file, or
- ``--force-llm`` on any CLI that can dispatch a model, which sets the process
  environment to ``TRUE`` for that run only, or
- the ON/OFF toggle in the demo frontend, which does the same for the bridge process.

Enforcement
-----------
The provider adapters in ``utils/generation/`` call ``require_llm_calls`` right
before they start the CLI subprocess, so a direct import of a provider module
cannot bypass the switch. The ``mock`` provider is always allowed. The Google
speech backends in UC-03 and the frozen translation stage are gated the same way.

    python -m utils.llm_switch        # print the current state and where it comes from
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from utils.paths import THESIS_ROOT

ENV_VAR = "THESIS_LLM_CALLS"
DOTENV_PATH = THESIS_ROOT / ".env"

_TRUE = {"true", "1", "yes", "on"}
_FALSE = {"false", "0", "no", "off", ""}


def _parse_flag(raw: str | None) -> bool | None:
    """Map a raw setting to True/False, or None when it is unset or unrecognised."""
    if raw is None:
        return None
    value = raw.strip().strip('"').strip("'").lower()
    if value in _TRUE:
        return True
    if value in _FALSE:
        return False
    return None


def read_dotenv(path: Path = DOTENV_PATH) -> dict[str, str]:
    """Read ``KEY=VALUE`` lines from a ``.env`` file (no dependency on python-dotenv).

    Blank lines and ``#`` comments are skipped; surrounding quotes are stripped.
    A missing file yields an empty dict.
    """
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values


def llm_calls_source(dotenv_path: Path = DOTENV_PATH) -> tuple[bool, str]:
    """Return ``(enabled, source)`` where source is ``"env"``, ``".env"`` or ``"default"``."""
    from_env = _parse_flag(os.environ.get(ENV_VAR))
    if from_env is not None:
        return from_env, "env"
    from_file = _parse_flag(read_dotenv(dotenv_path).get(ENV_VAR))
    if from_file is not None:
        return from_file, ".env"
    return False, "default"


def llm_calls_enabled(dotenv_path: Path = DOTENV_PATH) -> bool:
    """True when model calls are allowed for this process."""
    return llm_calls_source(dotenv_path)[0]


def require_llm_calls(provider: str, dotenv_path: Path = DOTENV_PATH) -> None:
    """Raise ``LLMCallsDisabledError`` unless the switch is on.

    Called by every provider adapter before it spends anything. ``mock`` never
    needs the switch and is not gated.
    """
    if provider == "mock":
        return
    enabled, source = llm_calls_source(dotenv_path)
    if enabled:
        return
    from utils.generation.errors import LLMCallsDisabledError

    raise LLMCallsDisabledError(
        provider,
        f"model calls are switched off ({ENV_VAR} is FALSE, source: {source}).",
        hint=(
            f"Set {ENV_VAR}=TRUE in {dotenv_path.name} at the thesis root, export it in the shell, "
            "pass --force-llm to the CLI, or switch LLM calls on in the demo settings."
        ),
    )


def enable_llm_calls_for_process() -> None:
    """Switch model calls on for the current process only (does not touch ``.env``)."""
    os.environ[ENV_VAR] = "TRUE"


def disable_llm_calls_for_process() -> None:
    """Switch model calls off for the current process only (does not touch ``.env``)."""
    os.environ[ENV_VAR] = "FALSE"


def add_force_llm_argument(parser: argparse.ArgumentParser) -> None:
    """Add the uniform ``--force-llm`` flag to a CLI parser."""
    parser.add_argument(
        "--force-llm",
        action="store_true",
        help=(
            f"Allow model calls for this run (sets {ENV_VAR}=TRUE for the process). "
            "Without it, and without the switch in .env, every provider call fails closed."
        ),
    )


def apply_force_llm(args: argparse.Namespace) -> bool:
    """Honour ``--force-llm`` if present; return whether model calls are enabled now."""
    if getattr(args, "force_llm", False):
        enable_llm_calls_for_process()
    return llm_calls_enabled()


def main(argv: list[str] | None = None) -> int:
    """CLI entry point: print the current switch state and where it comes from."""
    parser = argparse.ArgumentParser(description="Show whether model calls are switched on.")
    parser.parse_args(argv)
    enabled, source = llm_calls_source()
    state = "ON" if enabled else "OFF"
    print(f"LLM calls: {state} (source: {source}; variable {ENV_VAR}; file {DOTENV_PATH})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
