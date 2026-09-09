"""Alias-map extraction from the installed Claude Code binary.

Claude Code compiles its alias -> model map (opus/sonnet/haiku/fable -> concrete
ids, plus the `best` alias) into the distributed binary and exposes no command
that prints it. The payload is machine-readable in place, so the updater reads
the installed binary as CLI-distributed truth — never touching the user's
personal settings. Extraction is best-effort by design: if the payload shape
changes in a future release, this reader reports SKIP with a warning and the
curated overlay aliases take over as fallback.

The binary is large (hundreds of MB), so it is scanned in streamed chunks with
an overlap window instead of being loaded into memory. Matches are counted and
the most common value wins, which tolerates duplicate embedded payloads.
"""

from __future__ import annotations

import logging
import re
import shutil
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger("catalog.claude")

_FAMILY = re.compile(rb'(opus|sonnet|haiku|fable)\s*:\s*\{\s*default\s*:\s*"([a-z0-9.\-\[\]]+)"')
_BEST = re.compile(rb'best\s*:\s*"([a-z]+)"')
CHUNK = 8 * 1024 * 1024
OVERLAP = 4096


@dataclass
class ClaudeAliases:
    """One extraction outcome: the alias map found, or ``SKIP`` with why extraction failed."""

    status: str
    message: str
    aliases: dict = field(default_factory=dict)


def read(binary: str = "claude", path: str | Path | None = None) -> ClaudeAliases:
    """Extract the alias -> model map from the installed Claude Code binary.

    Args:
        binary: The executable name to locate on ``PATH`` when ``path`` is not given.
        path: An explicit path to the binary, mainly for tests.

    Returns:
        A ``ClaudeAliases`` with ``status`` ``"OK"`` and the extracted aliases, or
        ``"SKIP"`` (with a message) when the binary is missing, unreadable, or its
        payload shape does not match what this reader expects.
    """
    if path is None:
        found = shutil.which(binary)
        if found is None:
            log.info("`%s` not found on PATH (maybe installed differently) -> overlay alias fallback", binary)
            return ClaudeAliases("SKIP", "claude binary not on PATH")
        path = Path(found).resolve()
    path = Path(path)

    family_counts: dict[bytes, Counter] = {}
    best_counts: Counter = Counter()
    try:
        with path.open("rb") as fh:
            prev = b""
            while True:
                chunk = fh.read(CHUNK)
                if not chunk:
                    break
                buf = prev + chunk
                for match in _FAMILY.finditer(buf):
                    family_counts.setdefault(match.group(1), Counter())[match.group(2)] += 1
                for match in _BEST.finditer(buf):
                    best_counts[match.group(1)] += 1
                prev = buf[-OVERLAP:]
    except OSError as exc:
        log.warning("cannot read claude binary %s (%s) -> overlay alias fallback", path, exc)
        return ClaudeAliases("SKIP", f"unreadable: {exc}")

    aliases = {family.decode(): counts.most_common(1)[0][0].decode() for family, counts in family_counts.items()}
    if best_counts:
        aliases["best"] = best_counts.most_common(1)[0][0].decode()
    if {"opus", "sonnet", "haiku"} - set(aliases):
        log.warning("claude alias payload not found in %s (binary format changed?) -> overlay alias fallback", path)
        return ClaudeAliases("SKIP", "alias payload not found (binary format changed?)")
    return ClaudeAliases("OK", f"alias map extracted from installed binary ({len(aliases)} aliases)", aliases)
