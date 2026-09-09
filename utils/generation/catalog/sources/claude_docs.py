"""Vendor-disclosed Claude Code default model, from the official docs.

Anthropic publishes what the `default` model setting resolves to per account
type at code.claude.com/docs/en/model-config.md — a deliberate raw-markdown
endpoint (the docs site serves `.md` versions and an llms.txt index).
Combined with the account type from `claude auth status` (local, read-only,
no model tokens) this yields the vendor default for THIS machine. Best-effort
by design: any fetch, parse, or mapping failure returns SKIP and the curated
overlay default takes over. Organization-admin defaults and
ANTHROPIC_DEFAULT_MODEL overrides deliberately stay out of the parse —
personal settings never enter the catalog.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import requests

DOCS_URL = "https://code.claude.com/docs/en/model-config.md"

_SECTION_RE = re.compile(r"###\s+`default`\s+model\s+setting\n(.*?)(?=\n###\s|\Z)", re.DOTALL)
_BULLET_RE = re.compile(
    r"^\*\s+\*\*(?P<accounts>.+?)\*\*:\s*defaults to\s+(?P<display>[A-Za-z]+ [\d.]+)\s*$", re.MULTILINE
)
_UPGRADE_RE = re.compile(r"On Max, Team, and Enterprise plans[^.]*Opus is automatically upgraded to 1M context")

# `claude auth status` subscriptionType -> the phrase identifying its bullet.
# Values that match zero or several bullets (e.g. "enterprise", which appears
# in both a pay-as-you-go and a seats bullet) resolve to SKIP, never a guess.
_SUBSCRIPTION_PHRASE = {
    "max": "Max",
    "pro": "Pro",
    "team": "Team Standard",
    "team_premium": "Team Premium",
    "enterprise": "Enterprise",
}
# Plans named by the docs' automatic Opus -> 1M upgrade sentence.
_UPGRADE_PLANS = {"max", "team", "team_premium", "enterprise"}


@dataclass
class ClaudeDefault:
    """One lookup outcome: the vendor default model for this account type, or ``SKIP`` with why."""

    status: str
    message: str
    model_id: str | None = None
    fetched_at: str | None = None


def read(binary: str = "claude", cache_dir: str | Path = ".cache/model-catalog", timeout: int = 30) -> ClaudeDefault:
    """Resolve the vendor-disclosed default model for the locally authenticated account type.

    Args:
        binary: The ``claude`` executable used to read the local account type.
        cache_dir: Where the fetched docs page is cached between runs (etag-conditional).
        timeout: Seconds allowed for the subprocess call and the HTTP request.

    Returns:
        A ``ClaudeDefault`` with ``status`` ``"OK"`` and ``model_id`` set, or
        ``"SKIP"`` (with a message) when the account type, the docs page, or an
        unambiguous match for that account type could not be obtained.
    """
    subscription = _subscription_type(binary, timeout)
    if not subscription:
        return ClaudeDefault("SKIP", "account type unavailable (`claude auth status`) -> overlay default")
    text, fetched_at, how = _fetch_docs(Path(cache_dir), timeout)
    if text is None:
        return ClaudeDefault("SKIP", f"model-config docs unavailable ({how}) -> overlay default")
    model_id = _resolve(text, subscription)
    if model_id is None:
        return ClaudeDefault(
            "SKIP", f"docs parse found no unambiguous default for account type {subscription!r} -> overlay default"
        )
    return ClaudeDefault(
        "OK", f"vendor default {model_id} for account type {subscription!r} ({how})", model_id, fetched_at
    )


def _resolve(text: str, subscription: str) -> str | None:
    """Find the one unambiguous default-model bullet for ``subscription`` in the docs text."""
    phrase = _SUBSCRIPTION_PHRASE.get(subscription)
    if phrase is None:
        return None
    section = _SECTION_RE.search(text)
    if not section:
        return None
    matches = [
        m for m in _BULLET_RE.finditer(section.group(1)) if re.search(rf"\b{re.escape(phrase)}\b", m["accounts"])
    ]
    if len(matches) != 1:
        return None
    family, _, version = matches[0]["display"].rpartition(" ")
    model_id = f"claude-{family.lower()}-{version.replace('.', '-')}"
    if family.lower() == "opus" and subscription in _UPGRADE_PLANS and _UPGRADE_RE.search(text):
        model_id += "[1m]"
    return model_id


def _subscription_type(binary: str, timeout: int) -> str | None:
    """The logged-in account's subscription type from ``claude auth status``, or None."""
    try:
        proc = subprocess.run([binary, "auth", "status"], capture_output=True, text=True, timeout=timeout, check=False)
        data = json.loads(proc.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if not isinstance(data, dict) or not data.get("loggedIn"):
        return None
    value = data.get("subscriptionType")
    return str(value) if value else None


def _fetch_docs(cache: Path, timeout: int) -> tuple[str | None, str | None, str]:
    """Fetch the model-config docs page (etag-conditional), falling back to the cache on any failure."""
    cache.mkdir(parents=True, exist_ok=True)
    body_path = cache / "claude-model-config.md"
    meta_path = cache / "claude-model-config.meta.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    try:
        cached = body_path.read_text(encoding="utf-8")
    except OSError:
        cached = None
    headers = {"If-None-Match": meta["etag"]} if meta.get("etag") and cached is not None else {}
    try:
        resp = requests.get(DOCS_URL, headers=headers, timeout=timeout)
        if resp.status_code == 304 and cached is not None:
            return cached, meta.get("fetched_at"), "304 not-modified"
        resp.raise_for_status()
        text = resp.text
        _write_atomic(body_path, text)
        fetched_at = _utc_now()
        new_meta = {"etag": resp.headers.get("ETag"), "fetched_at": fetched_at}
        _write_atomic(meta_path, json.dumps(new_meta, indent=2, sort_keys=True) + "\n")
        return text, fetched_at, "fetched"
    except Exception as exc:  # noqa: BLE001 - any failure means "try the cache, else SKIP"
        if cached is not None:
            return cached, meta.get("fetched_at"), f"stale cache ({exc.__class__.__name__})"
        return None, None, exc.__class__.__name__


def _write_atomic(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via a temp file plus rename, so a crash never leaves a partial file."""
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        tmp.write_text(text, encoding="utf-8")
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _utc_now() -> str:
    """Current UTC time as a second-precision ISO 8601 string with a ``Z`` suffix."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
