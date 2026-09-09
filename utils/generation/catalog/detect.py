"""Detect which provider CLIs are actually installed on the local machine.

The catalog's value is *local* detection: codex and claude expose their model
lists through on-disk caches/config, so a provider is only worth surfacing if
its CLI is present on this machine. An absent CLI means there is no local
information to offer (and the user cannot run that provider anyway), so the
provider is dropped from the catalog rather than shown as a dead option.

Used in two places:
  * the updater, when (re)generating the catalog -- build only installed
    providers and log what was detected/skipped;
  * the serving layer, to hide providers whose CLI is not on PATH even if a
    pre-built catalog shipped with them.
"""

from __future__ import annotations

import shutil


def is_cli_installed(binary: str | None) -> bool:
    """True if ``binary`` resolves to an executable on PATH."""
    return bool(binary) and shutil.which(binary) is not None


def detect_installed_providers(providers: dict) -> dict[str, bool]:
    """Map each provider name -> whether its CLI binary is on PATH.

    ``providers`` is a provider config table -- either the overlay's
    ``[providers]`` section or a built catalog's ``providers`` dict; both carry
    a ``binary`` (falling back to ``cli`` / the provider name).
    """
    detected: dict[str, bool] = {}
    for name, cfg in (providers or {}).items():
        cfg = cfg or {}
        binary = cfg.get("binary") or cfg.get("cli") or name
        detected[name] = is_cli_installed(binary)
    return detected
