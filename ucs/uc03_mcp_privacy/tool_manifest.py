"""Pin of the tool definitions the model reads, verified before the server serves.

Threat
------
Tool poisoning and rug pulls put instructions into the text the model reads
about a tool: its name, its description, its argument schema. A client that
approved a server once and binds to it by name will not notice a later change.
The pin therefore covers the whole payload the server advertises in
``tools/list`` for every tool (name, description, input schema, and any title,
output schema, annotations or metadata the SDK serialises), not the Python
source behind it.

Mechanism
---------
``advertised_tools(mcp)`` reads the live tool list from the FastMCP instance.
Each tool gets a SHA-256 over its canonical JSON; the whole manifest gets one
over the sorted list (``manifest_sha256``). The pin file is committed with the
code (``config.PIN_PATH``), so a fresh checkout verifies against what the
author pinned, not against whatever it finds on first start. In strict mode
(the default) any changed, missing **or new** tool stops the server before it
answers a single request; ``python -m ucs.uc03_mcp_privacy.tool_manifest pin``
re-pins after an intentional change, and the diff of the pin file is the
review artefact.

CLI
---
    python -m ucs.uc03_mcp_privacy.tool_manifest show
    python -m ucs.uc03_mcp_privacy.tool_manifest verify
    python -m ucs.uc03_mcp_privacy.tool_manifest pin
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import hashlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ucs.uc03_mcp_privacy import config

SCHEMA_VERSION = 3


def _utc_now() -> str:
    """Return the current UTC time as ``"YYYY-MM-DDTHH:MM:SSZ"``."""
    return _dt.datetime.now(tz=_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _canonical(obj: Any) -> bytes:
    """JSON-canonical bytes: sorted keys, no whitespace, UTF-8."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


# ---------------------------------------------------------------------------
# What is pinned
# ---------------------------------------------------------------------------


def advertised_tools(mcp: Any) -> list[dict[str, Any]]:
    """Return the ``tools/list`` payload of a FastMCP instance, one dict per tool.

    The dict is the SDK's own serialisation of the tool (``model_dump``, unset
    fields dropped) with ``description`` always present, so every field a host
    can show its model is part of the fingerprint.
    """
    tools = asyncio.run(mcp.list_tools())
    payloads = []
    for tool in tools:
        payload = tool.model_dump(mode="json", exclude_none=True)
        payload.setdefault("description", "")
        payloads.append(payload)
    return payloads


def fingerprint_tool(tool: dict[str, Any]) -> str:
    """SHA-256 of one advertised tool (canonical JSON of its whole payload)."""
    return hashlib.sha256(_canonical(tool)).hexdigest()


def manifest_sha256(tools: list[dict[str, Any]]) -> str:
    """SHA-256 of the whole advertised surface, order-independent."""
    digests = sorted(fingerprint_tool(tool) for tool in tools)
    return hashlib.sha256("|".join(digests).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


@dataclass
class ManifestReport:
    """Outcome of a verification: which tools matched, appeared, changed or vanished."""

    ok: list[str] = field(default_factory=list)
    new: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    missing: list[str] = field(default_factory=list)

    @property
    def is_clean(self) -> bool:
        """True when the advertised tools and the pin agree exactly."""
        return not (self.new or self.changed or self.missing)

    def as_dict(self) -> dict[str, list[str]]:
        """The four lists as a JSON-serialisable dict."""
        return {"ok": self.ok, "new": self.new, "changed": self.changed, "missing": self.missing}


class ToolManifestError(RuntimeError):
    """Raised in strict mode when the advertised tools differ from the pin."""


class ToolManifest:
    """The pin file: ``{"schema_version", "pinned_at", "manifest_sha256", "tools": {name: {sha256, payload}}}``."""

    def __init__(self, path: str | Path | None = None) -> None:
        """Point at `path` (default: `config.manifest_path()`); does not read it yet."""
        self.path = Path(path) if path is not None else config.manifest_path()

    def load(self) -> dict[str, dict[str, Any]]:
        """Return the pinned tools (name -> {sha256, payload}); empty if no file."""
        if not self.path.exists():
            return {}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return data.get("tools", {}) if isinstance(data, dict) else {}

    def save(self, tools: list[dict[str, Any]]) -> dict[str, Any]:
        """Write the pin for ``tools`` (an advertised list) and return the document."""
        doc = {
            "schema_version": SCHEMA_VERSION,
            "pinned_at": _utc_now(),
            "manifest_sha256": manifest_sha256(tools),
            "tools": {
                tool["name"]: {"sha256": fingerprint_tool(tool), "payload": tool} for tool in tools
            },
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(
            json.dumps(doc, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
        )
        return doc

    def verify(self, tools: list[dict[str, Any]], *, strict: bool = True) -> ManifestReport:
        """Compare the advertised ``tools`` with the pin.

        With ``strict`` any difference raises ``ToolManifestError``; nothing is
        written in either case. A missing pin file counts every tool as ``new``.
        """
        pinned = self.load()
        report = ManifestReport()
        live = {tool["name"]: fingerprint_tool(tool) for tool in tools}
        for name, digest in live.items():
            previous = pinned.get(name)
            if previous is None:
                report.new.append(name)
            elif previous.get("sha256") == digest:
                report.ok.append(name)
            else:
                report.changed.append(name)
        report.missing.extend(sorted(set(pinned) - set(live)))
        if strict and not report.is_clean:
            raise ToolManifestError(
                "tool manifest verification failed: "
                f"new={report.new} changed={report.changed} missing={report.missing} "
                f"(pin: {self.path}; re-pin with 'python -m ucs.uc03_mcp_privacy.tool_manifest pin' "
                "after an intentional change)"
            )
        return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _live_tools() -> list[dict[str, Any]]:
    """Build the server and return its currently advertised tools (see `advertised_tools`)."""
    # Local import: server imports this module.
    from ucs.uc03_mcp_privacy.server import build_mcp

    return advertised_tools(build_mcp())


def _cli(argv: list[str] | None = None) -> int:
    """Entry point for ``show`` / ``pin`` / ``verify``; return the process exit code."""
    parser = argparse.ArgumentParser(description="UC-03 tool manifest helper")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("show", help="Print the pin file")
    sub.add_parser("pin", help="(Re-)pin the advertised tools from the current code")
    sub.add_parser("verify", help="Compare the advertised tools with the pin (exit 1 on drift)")
    args = parser.parse_args(argv)

    manifest = ToolManifest()
    if args.cmd == "show":
        print(json.dumps({"path": str(manifest.path), "tools": manifest.load()}, indent=2))
        return 0
    if args.cmd == "pin":
        doc = manifest.save(_live_tools())
        print(
            f"Pinned {len(doc['tools'])} tools to {manifest.path} ({doc['manifest_sha256'][:12]}...)"
        )
        return 0
    report = manifest.verify(_live_tools(), strict=False)
    print(json.dumps(report.as_dict(), indent=2))
    return 0 if report.is_clean else 1


if __name__ == "__main__":
    sys.exit(_cli())
