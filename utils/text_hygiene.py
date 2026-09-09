"""Shared text hygiene: one definition of "unusual character", two operations.

``scan_text`` counts anomaly classes without changing anything; ``clean_text``
removes them. Every substrate build step imports ``clean_text`` so the raw
Amazon layer, the frozen Czech translations and the product catalog are
cleaned by the same rules, and the ``audit`` CLI re-checks the outputs with
the same rules.

Classes (name: what it matches):
    ZW       zero-width space/joiner/non-joiner, word joiner, BOM (U+200B-200F, 2060-2064, FEFF)
    BIDI     bidirectional embedding/override/isolate marks (U+202A-202E, 2066-2069)
    C0       ASCII control characters except TAB/LF/CR
    C1       U+0080-009F
    NBSP     U+00A0
    LSEP     U+2028/2029 line and paragraph separators, U+0085 NEL
    SHY      U+00AD soft hyphen
    PUA      private-use areas (leaked Wingdings/Symbol glyphs)
    VS       variation selectors
    TAGS     U+E0000-E007F tag characters
    FFFD     U+FFFD replacement character
    NONCHAR  U+FFF0-FFF8, FFFE, FFFF
    MOJI     UTF-8 read as Latin-1/cp1252 mojibake (\u00c3\u00a9 for \u00e9, \u00e2\u20ac\u201c for \u2013)
    HTMLENT  HTML entities ("&amp;", "&#34;")
    ESCSEQ_X000D  Excel/Amazon "_x000D_" carriage-return marker
    HTMLTAG  HTML/XML tags ("<br>", "<p>")
    CYR / CJK / RTL  foreign scripts (informational, never removed)
    DBLSP    runs of two or more spaces (informational)
    WS_EDGE  leading/trailing whitespace (informational)

Run an audit:

    python -m utils.text_hygiene audit substrate/snapshots ucs --exclude intermediate/ --exclude provenance/ --fail-on-critical
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import ftfy

# --- class definitions ------------------------------------------------------

_RX: dict[str, re.Pattern[str]] = {
    # Code points are written numerically so this source file stays free of
    # invisible characters itself (same convention as the retired cleaner).
    "ZW": re.compile("[\u200B-\u200F\u2060-\u2064\uFEFF]"),
    "BIDI": re.compile("[\u202A-\u202E\u2066-\u2069]"),
    "C0": re.compile("[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]"),
    "C1": re.compile("[\x80-\x9F]"),
    "NBSP": re.compile("\u00A0"),
    "LSEP": re.compile("[\u2028\u2029\u0085]"),
    "SHY": re.compile("\u00AD"),
    "PUA": re.compile("[\uE000-\uF8FF\U000F0000-\U0010FFFF]"),
    "VS": re.compile("[\uFE00-\uFE0F\U000E0100-\U000E01EF]"),
    "TAGS": re.compile("[\U000E0000-\U000E007F]"),
    "FFFD": re.compile("\uFFFD"),
    "NONCHAR": re.compile("[\uFFF0-\uFFF8\uFFFE\uFFFF]"),
    "MOJI": re.compile(
        "(?:[\u00C3\u00C2\u00C4\u00C5][\x80-\xBF\u0152-\u0192\u2013-\u203A\u02C6\u02DC\u2122\u20AC]"
        "|\u00E2\u20AC|\u00EF\u00BF\u00BD)"
    ),
    "HTMLENT": re.compile(r"&(?:[a-zA-Z]{2,8}|#\d{2,6}|#x[0-9a-fA-F]{2,5});"),
    "ESCSEQ_X000D": re.compile("_x000D_"),
    "HTMLTAG": re.compile(r"</?[a-zA-Z][a-zA-Z0-9:]{0,20}(?:\s[^<>]{0,200})?/?>"),
    "CYR": re.compile("[\u0400-\u04FF]"),
    "CJK": re.compile("[\u3040-\u30FF\u3400-\u4DBF\u4E00-\u9FFF\uAC00-\uD7AF]"),
    "RTL": re.compile("[\u0590-\u06FF\u0E00-\u0E7F]"),
    "DBLSP": re.compile(" {2,}"),
    "WS_EDGE": re.compile(r"^\s|\s$"),
}

CRITICAL_CLASSES: frozenset[str] = frozenset(
    {"ZW", "BIDI", "C0", "C1", "PUA", "VS", "TAGS", "NONCHAR", "FFFD", "MOJI", "ESCSEQ_X000D"}
)

# Characters deleted outright. VT (\x0B), FF (\x0C) and NEL (\x85) are NOT here:
# they are whitespace and become a single space in _TO_SPACE below.
_STRIP = re.compile(
    "[\u200B-\u200F\u2060-\u2064\uFEFF\u202A-\u202E\u2066-\u2069"
    "\x00-\x08\x0E-\x1F\x7F\x80-\x84\x86-\x9F\u00AD"
    "\uE000-\uF8FF\U000F0000-\U0010FFFF\uFE00-\uFE0F\U000E0000-\U000E01EF"
    "\uFFFD\uFFF0-\uFFF8\uFFFE\uFFFF]"
)
_TO_SPACE = re.compile("_x000D_|[\u00A0\u2028\u2029\u0085\x0B\x0C\t\r]")
_SPACE_RUN = re.compile(" {2,}")
_SCRIPT_BLOCK = re.compile(r"<(script|style)\b[^>]*>.*?</\1\s*>", re.IGNORECASE | re.DOTALL)
_TAG = _RX["HTMLTAG"]

# Mojibake that no decoder can invert because the source already dropped a byte.
# Amazon meta encodes such titles as HTML entities and omits C1 bytes, e.g. the
# trademark sign arrives as "&Atilde;&cent;&Acirc;&Acirc;&cent;". Keys are the
# text AFTER entity unescaping; extend only with sequences verified in the raw dump.
_KNOWN_BROKEN: dict[str, str] = {
    "\u00c3\u00a2\u00c2\u00c2\u00a2": "™",
}

# ftfy: repair encoding + unescape entities only. Quotes, ligatures, widths and
# Unicode normalisation stay as the author wrote them (Czech „quotes“ must survive).
_FTFY = ftfy.TextFixerConfig(
    unescape_html=True,
    remove_terminal_escapes=True,
    fix_encoding=True,
    restore_byte_a0=True,
    replace_lossy_sequences=True,
    decode_inconsistent_utf8=True,
    fix_c1_controls=True,
    fix_latin_ligatures=False,
    fix_character_width=False,
    uncurl_quotes=False,
    fix_line_breaks=False,
    fix_surrogates=True,
    remove_control_chars=False,
    normalization=None,
)


def _unescape_fixpoint(text: str, limit: int = 4) -> str:
    """Unescape HTML entities repeatedly until stable (or ``limit`` rounds), catching double-encoding."""
    for _ in range(limit):
        nxt = html.unescape(text)
        if nxt == text:
            return text
        text = nxt
    return text


def clean_text(text: str | None, *, strip_html_tags: bool = False) -> str | None:
    """Return ``text`` with every critical class removed and whitespace tidied.

    Order matters: entities are unescaped first (they may hide control characters),
    known undecodable sequences are mapped by table, then ftfy repairs decodable
    mojibake (it may produce entities again, hence the fixpoint loop), invisible
    characters are stripped third, whitespace last. Returns ``None`` when nothing
    readable is left.
    """
    if text is None:
        return None
    if not isinstance(text, str):
        return text
    out = _unescape_fixpoint(text)
    for broken, fixed in _KNOWN_BROKEN.items():
        out = out.replace(broken, fixed)
    out = ftfy.fix_text(out, config=_FTFY)
    out = _unescape_fixpoint(out)
    if strip_html_tags:
        out = _SCRIPT_BLOCK.sub(" ", out)
        out = _TAG.sub(" ", out)
    out = _STRIP.sub("", out)
    out = _TO_SPACE.sub(" ", out)
    out = _SPACE_RUN.sub(" ", out).strip()
    return out or None


def clean_json(obj: Any, *, strip_html_tags: bool = False) -> Any:
    """Recursively ``clean_text`` every string value; dict keys are left alone."""
    if isinstance(obj, str):
        return clean_text(obj, strip_html_tags=strip_html_tags)
    if isinstance(obj, list):
        return [clean_json(v, strip_html_tags=strip_html_tags) for v in obj]
    if isinstance(obj, dict):
        return {k: clean_json(v, strip_html_tags=strip_html_tags) for k, v in obj.items()}
    return obj


def scan_text(text: str) -> dict[str, int]:
    """Count occurrences of every class in ``text``; only non-zero classes are returned."""
    counts: dict[str, int] = {}
    for name, rx in _RX.items():
        n = len(rx.findall(text))
        if n:
            counts[name] = n
    return counts


# --- audit over files -------------------------------------------------------

def _iter_strings(obj: Any):
    """Yield every string value nested inside ``obj`` (dicts, lists, or a bare string)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from _iter_strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_strings(v)


def _merge(into: dict[str, int], counts: dict[str, int]) -> None:
    """Add ``counts`` into ``into`` in place, key by key."""
    for k, v in counts.items():
        into[k] = into.get(k, 0) + v


def _scan_file(path: Path) -> dict[str, int]:
    """Scan one JSON, JSONL or SQLite file's string content and return the summed class counts."""
    totals: dict[str, int] = {}
    if path.suffix == ".json":
        for s in _iter_strings(json.loads(path.read_text(encoding="utf-8"))):
            _merge(totals, scan_text(s))
    elif path.suffix == ".jsonl":
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    for s in _iter_strings(json.loads(line)):
                        _merge(totals, scan_text(s))
    elif path.suffix in {".db", ".sqlite"}:
        con = sqlite3.connect(str(path))
        try:
            for (table,) in con.execute("select name from sqlite_master where type='table'"):
                for row in con.execute(f'select * from "{table}"'):
                    for v in row:
                        if isinstance(v, str):
                            _merge(totals, scan_text(v))
        finally:
            con.close()
    return totals


def audit_paths(paths: list[Path], *, exclude: list[str] | None = None) -> dict[str, dict[str, int]]:
    """Scan every JSON / JSONL / SQLite file under ``paths``; return file → class counts."""
    exclude = exclude or []
    report: dict[str, dict[str, int]] = {}
    for root in paths:
        files = [root] if root.is_file() else sorted(p for p in root.rglob("*") if p.is_file())
        for p in files:
            if p.suffix not in {".json", ".jsonl", ".db", ".sqlite"}:
                continue
            if any(sub in str(p) for sub in exclude):
                continue
            report[str(p)] = _scan_file(p)
    return report


def _main(argv: list[str] | None = None) -> int:
    """CLI entry point: run the ``audit`` subcommand and print a per-file class-count report."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit", help="scan JSON/JSONL/SQLite files for unusual characters")
    a.add_argument("paths", nargs="+", type=Path)
    a.add_argument("--exclude", action="append", default=[], help="substring of paths to skip (repeatable)")
    a.add_argument("--fail-on-critical", action="store_true", help="exit 1 if any critical class is present")
    args = parser.parse_args(argv)

    report = audit_paths(args.paths, exclude=args.exclude)
    critical_hits = 0
    for file, counts in report.items():
        crit = {k: v for k, v in counts.items() if k in CRITICAL_CLASSES}
        info = {k: v for k, v in counts.items() if k not in CRITICAL_CLASSES}
        critical_hits += sum(crit.values())
        flag = "CRITICAL" if crit else ("ok      " if not info else "info    ")
        print(f"{flag} {file}  {crit if crit else ''} {info if info else ''}".rstrip())
    print(f"\nfiles: {len(report)}  critical hits: {critical_hits}")
    return 1 if (args.fail_on_critical and critical_hits) else 0


if __name__ == "__main__":
    sys.exit(_main())
