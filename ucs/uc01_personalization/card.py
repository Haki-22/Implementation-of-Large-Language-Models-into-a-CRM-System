"""The one-page card of UC-01 (`eval/RESULTS.md`) and the appendix files, generated from the runs of record.

Same shape as UC-02 and UC-04: ran on / who / model / when, then the numbers with
their meaning, then a closing sentence, every number naming its run folder. The
runs of record are found by rule, never named by hand: the newest ladder run that
covers every level of the ladder for the whole pick with a real provider, the
newest faithfulness run with a real provider, and the judge folders under that
ladder run (none yet). Regenerate after any new record run:

    python -m ucs.uc01_personalization card        # eval/RESULTS.md + <project_root>/attachments/uc01-*.{csv,md}
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import levels
from utils.paths import THESIS_ROOT, UC01_DIR, UC01_RUNS_DIR

CARD_PATH = UC01_DIR / "eval" / "RESULTS.md"
ATTACHMENTS_DIR = THESIS_ROOT / "attachments"

LEVEL_CS = {
    "0": "obecný brief",
    "1": "mail merge",
    "2": "morfologie",
    "3a": "vlastní slova",
    "3b": "nákupy",
    "3c": "recenze",
    "3d": "role",
    "3": "chování",
    "4": "aspekty",
    "5": "profil OCEAN",
    "6a": "doporučení",
    "6b": "témata",
    "6c": "fáze vztahu",
    "6d": "cena",
    "6": "hyperpersonalizace",
}


# ---------------------------------------------------------------------------
# Finding the runs of record
# ---------------------------------------------------------------------------


def _config(folder: Path) -> dict[str, Any]:
    """A run (or judge) folder's ``config.json``, parsed."""
    return json.loads((folder / "config.json").read_text(encoding="utf-8"))


def _json(path: Path) -> Any:
    """``path`` parsed as JSON, or ``None`` when it does not exist."""
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def ladder_runs(runs_dir: Path = UC01_RUNS_DIR, *, allow_mock: bool = False) -> list[Path]:
    """Run folders that ran every level of the ladder on the whole pick, oldest first."""
    out: list[Path] = []
    if not runs_dir.exists():
        return out
    for folder in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        if not (folder / "config.json").exists() or not (folder / "summary.json").exists():
            continue
        cfg = _config(folder)
        if cfg.get("kind") == "faithfulness" or "levels" not in cfg:
            continue
        if cfg.get("provider") == "mock" and not allow_mock:
            continue
        if set(cfg["levels"]) != set(levels.LADDER):
            continue
        pick = _json(folder / "pick.json") or {}
        whole = set(pick.get("reading_set", [])) | {
            i for ids in pick.get("strata", {}).values() for i in ids
        }
        if whole and set(cfg.get("contacts", [])) != whole:
            continue
        out.append(folder)
    return out


def faithfulness_runs(runs_dir: Path = UC01_RUNS_DIR, *, allow_mock: bool = False) -> list[Path]:
    """Faithfulness folders (config.json with kind 'faithfulness'), oldest first."""
    out: list[Path] = []
    if not runs_dir.exists():
        return out
    for folder in sorted(p for p in runs_dir.iterdir() if p.is_dir()):
        if not (folder / "config.json").exists() or not (folder / "faithfulness.json").exists():
            continue
        cfg = _config(folder)
        if cfg.get("kind") != "faithfulness":
            continue
        if cfg.get("provider") == "mock" and not allow_mock:
            continue
        out.append(folder)
    return out


def records(runs_dir: Path = UC01_RUNS_DIR, *, allow_mock: bool = False) -> dict[str, Any]:
    """The runs of record: the newest ladder run, its judge folders, the newest faithfulness run."""
    ladders = ladder_runs(runs_dir, allow_mock=allow_mock)
    ladder = ladders[-1] if ladders else None
    faith = faithfulness_runs(runs_dir, allow_mock=allow_mock)
    judges = sorted(p for p in ladder.glob("judge-*") if p.is_dir()) if ladder else []
    return {"ladder": ladder, "judges": judges, "faithfulness": faith[-1] if faith else None}


# ---------------------------------------------------------------------------
# Rows
# ---------------------------------------------------------------------------


def ladder_rows(folder: Path) -> list[dict[str, Any]]:
    """One row per level: counts, the rules judge, the two cheap metrics."""
    summary = _json(folder / "summary.json") or {}
    metrics = _json(folder / "metrics-summary.json") or {}
    rows: list[dict[str, Any]] = []
    for level in levels.LADDER:
        s = summary.get(level)
        if not s:
            continue
        m = metrics.get(level, {})
        skipped = sum(s.get("skipped", {}).values())
        rows.append(
            {
                "level": level,
                "name": s["name"],
                "name_cs": LEVEL_CS.get(level, s["name"]),
                "uses_model": int(levels.LEVELS[level].uses_model),
                "requested": s["requested"],
                "generated": s["generated"],
                "skipped": skipped,
                "errors": s.get("errors", 0),
                "reused": s.get("reused", 0),
                "rules_accepted": s.get("rules_accepted"),
                "rules_rate": s.get("rules_rate"),
                "rules_failures": ";".join(
                    f"{k}={v}" for k, v in sorted(s.get("rules_failures", {}).items())
                ),
                "rules_unchecked": ";".join(
                    f"{k}={v}" for k, v in sorted(s.get("rules_unchecked", {}).items())
                ),
                "lsm_mean": m.get("lsm_mean"),
                "overlap_mean": m.get("overlap_mean"),
                "chars_mean": m.get("chars_mean"),
                "run": folder.name,
            }
        )
    return rows


def faithfulness_rows(folder: Path) -> list[dict[str, Any]]:
    """One row per contact of a faithfulness run: the responsiveness and both profiles."""
    rows = _json(folder / "faithfulness.json") or []
    pick = _json(folder.parent / ".." / "picks" / f"{_config(folder).get('pick')}.json")
    facts = (pick or {}).get("contacts", {})
    out: list[dict[str, Any]] = []
    for r in rows:
        f = facts.get(str(r.get("contact_id")), {})
        out.append(
            {
                "contact_id": r.get("contact_id"),
                "tier": f.get("tier"),
                "gender": f.get("gender"),
                "formal": f.get("formal"),
                "skipped": r.get("skipped", ""),
                "responsiveness": r.get("responsiveness"),
                "ocean": json.dumps(r.get("ocean"), ensure_ascii=False) if r.get("ocean") else "",
                "mirrored": json.dumps(r.get("mirrored"), ensure_ascii=False)
                if r.get("mirrored")
                else "",
                "run": folder.name,
            }
        )
    return out


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt(x: Any, digits: int = 3) -> str:
    """``x`` rendered for the card: an em dash when missing, a float to ``digits`` places, else ``str(x)``."""
    if x is None or x == "":
        return "—"
    if isinstance(x, float):
        return f"{x:.{digits}f}"
    return str(x)


def _pct(x: float | None) -> str:
    """``x`` as a whole-number percentage, or an em dash when ``x`` is ``None``."""
    return "—" if x is None else f"{100 * x:.0f} %"


def _line(fact: str, meaning: str) -> tuple[str, str]:
    """Marker pair for a `(fact, meaning)` display row, aligned by ``_render``."""
    return (fact, meaning)


def _render(lines: list) -> list[str]:
    """Render a mix of plain strings and ``_line`` tuples, aligning the tuples' facts into one column."""
    facts = [item for item in lines if isinstance(item, tuple)]
    width = max((len(f) for f, _ in facts), default=0)
    out: list[str] = []
    for item in lines:
        if isinstance(item, tuple):
            fact, meaning = item
            out.append(f"    {fact.ljust(width)}   ({meaning})")
        else:
            out.append(item)
    return out


def _ladder_block(folder: Path) -> list[str]:
    """Card section 1: the ladder run's totals and its per-level table."""
    cfg = _config(folder)
    rows = ladder_rows(folder)
    model_rows = [r for r in rows if r["uses_model"]]
    calls = sum(r["generated"] for r in model_rows)
    reused = sum(r["reused"] for r in model_rows)
    accepted = sum(r["rules_accepted"] or 0 for r in model_rows)
    judged = sum(r["generated"] for r in model_rows if r["rules_rate"] is not None)
    out = [f"## 1. The ladder — `runs/{folder.name}/`", ""]
    out.append(
        _line(
            f"{sum(r['requested'] for r in rows)} messages requested, {sum(r['generated'] for r in rows)} generated",
            f"{len(cfg.get('contacts', []))} contacts of pick `{cfg.get('pick')}`, briefs {cfg.get('briefs')}, "
            f"{len(rows)} levels; the rest skipped for a missing input, never for a missing identity field",
        )
    )
    out.append(
        _line(
            f"{calls} model calls, {reused} reused, {sum(r['errors'] for r in rows)} errors",
            f"{cfg.get('provider')} / {cfg.get('model')} / {cfg.get('tier')}, prompt {cfg.get('prompt_version')}, "
            f"{cfg.get('seconds', 0):.0f} s",
        )
    )
    out.append(
        _line(
            f"rules judge {accepted} / {judged} on the model levels",
            "greeting, Ty/Vy, gender, no instruction bleed; at 6d also both prices, the discount and the disclosure sentence",
        )
    )
    out.append("")
    out.append(
        "| level | name | model | requested | generated | skipped | rules | LSM | overlap | chars |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in rows:
        out.append(
            f"| {r['level']} | {r['name']} ({r['name_cs']}) | {'yes' if r['uses_model'] else 'no'} | "
            f"{r['requested']} | {r['generated']} | {r['skipped']} | {_pct(r['rules_rate'])} | "
            f"{_fmt(r['lsm_mean'])} | {_fmt(r['overlap_mean'])} | {_fmt(r['chars_mean'], 0)} |"
        )
    out.append("")
    out.append(
        "LSM = language style matching between the message and the customer's own writing; overlap = share of the "
        "customer's frequent words in the message; L0 fails the greeting by design (the brief as written)."
    )
    out.append("")
    return _render(out)


def _judges_block(judges: list[Path]) -> list[str]:
    """Card section 2: one summary line per judge folder of the ladder run."""
    out = ["## 2. The model judges — one folder per judging of the ladder run", ""]
    for folder in judges:
        cfg = _json(folder / "config.json") or {}
        summary = _json(folder / "summary.json") or {}
        total = summary.get("total", summary)
        parts = ", ".join(f"{k} {v}" for k, v in total.items() if isinstance(v, (int, float)))
        out.append(
            _line(
                f"`{folder.name}`: {parts or 'see summary.json'}",
                f"level {cfg.get('level')}, judges {cfg.get('judges')}, arbiter {cfg.get('arbiter')}",
            )
        )
    out.append("")
    return _render(out)


def _faithfulness_block(folder: Path) -> list[str]:
    """Card section 3: the faithfulness run's mean responsiveness and its call/skip counts."""
    cfg = _config(folder)
    rows = [r for r in faithfulness_rows(folder) if r["responsiveness"] is not None]
    skipped = [r for r in faithfulness_rows(folder) if r["responsiveness"] is None]
    out = [f"## 3. Faithfulness to the profile — `runs/{folder.name}/`", ""]
    if rows:
        vals = sorted(r["responsiveness"] for r in rows)
        out.append(
            _line(
                f"mean responsiveness {sum(vals) / len(vals):.3f} over {len(rows)} contacts (min {vals[0]:.3f}, max {vals[-1]:.3f})",
                "1 − Jaccard of the L5 message with the real OCEAN profile against the same message with the profile "
                "mirrored around the scale's middle: the share of words that change when only the profile changes",
            )
        )
    out.append(
        _line(
            f"{cfg.get('calls')} calls, {len(skipped)} contacts skipped",
            f"{cfg.get('provider')} / {cfg.get('model')} / {cfg.get('tier')}, prompt {cfg.get('prompt_version')}, "
            f"brief {cfg.get('brief')}; skipped = no profile or no history (prospects)",
        )
    )
    out.append("")
    out.append(
        "The number says how much the text moves, not whether it moves the expected way; both texts sit side by side "
        "in `faithfulness.json` for the reading pass."
    )
    out.append("")
    return _render(out)


def _closing(rec: dict[str, Any]) -> str:
    """The card's closing sentence: rules acceptance, faithfulness (if run), and the reading-pass reminder."""
    ladder = rec["ladder"]
    if ladder is None:
        return "No ladder run of record yet."
    rows = ladder_rows(ladder)
    model_rows = [r for r in rows if r["uses_model"]]
    accepted = sum(r["rules_accepted"] or 0 for r in model_rows)
    judged = sum(r["generated"] for r in model_rows if r["rules_rate"] is not None)
    parts = [
        f"with explicit signals the model kept the greeting, the register and the gender in {accepted} of {judged} "
        "messages (the correctness claim, checked by rule, not by a model)"
    ]
    if rec["faithfulness"]:
        frows = [
            r for r in faithfulness_rows(rec["faithfulness"]) if r["responsiveness"] is not None
        ]
        if frows:
            mean = sum(r["responsiveness"] for r in frows) / len(frows)
            parts.append(
                f"mirroring the personality profile changes {100 * mean:.0f} % of the words of the L5 message on average "
                "(the profile is used, in which direction the reading pass says)"
            )
    parts.append(
        "the diff per rung (same person, same brief, one more field) is the evidence the chapter reads, not a rate"
    )
    return "Reading: " + "; ".join(parts) + "."


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def write_attachments(rec: dict[str, Any], out_dir: Path = ATTACHMENTS_DIR) -> list[Path]:
    """`uc01-ladder.{csv,md}` and `uc01-faithfulness.{csv,md}` from the runs of record."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    if rec["ladder"]:
        rows = ladder_rows(rec["ladder"])
        csv_path = out_dir / "uc01-ladder.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        md = [
            f"# UC-01 ladder — run of record `{rec['ladder'].name}`",
            "",
            "| level | name | model | requested | generated | skipped | rules judge | LSM | overlap | chars |",
            "|---|---|---|---|---|---|---|---|---|---|",
        ]
        for r in rows:
            md.append(
                f"| {r['level']} | {r['name_cs']} | {'ano' if r['uses_model'] else 'ne'} | {r['requested']} | "
                f"{r['generated']} | {r['skipped']} | {_pct(r['rules_rate'])} | {_fmt(r['lsm_mean'])} | "
                f"{_fmt(r['overlap_mean'])} | {_fmt(r['chars_mean'], 0)} |"
            )
        md.append("")
        (out_dir / "uc01-ladder.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        written += [csv_path, out_dir / "uc01-ladder.md"]
    if rec["faithfulness"]:
        rows = faithfulness_rows(rec["faithfulness"])
        csv_path = out_dir / "uc01-faithfulness.csv"
        with csv_path.open("w", encoding="utf-8", newline="") as fh:
            writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            writer.writeheader()
            writer.writerows(rows)
        md = [
            f"# UC-01 faithfulness — run of record `{rec['faithfulness'].name}`",
            "",
            "| contact | tier | gender | formal | responsiveness | skipped |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            md.append(
                f"| {r['contact_id']} | {r['tier']} | {r['gender']} | {r['formal']} | "
                f"{_fmt(r['responsiveness'])} | {r['skipped']} |"
            )
        md.append("")
        (out_dir / "uc01-faithfulness.md").write_text("\n".join(md) + "\n", encoding="utf-8")
        written += [csv_path, out_dir / "uc01-faithfulness.md"]
    return written


def build(
    out_path: Path = CARD_PATH,
    runs_dir: Path = UC01_RUNS_DIR,
    attachments_dir: Path | None = ATTACHMENTS_DIR,
    *,
    allow_mock: bool = False,
) -> Path:
    """Write the one-page card from the runs of record (and the appendix files); returns the card's path."""
    rec = records(runs_dir, allow_mock=allow_mock)
    ladder = rec["ladder"]
    if ladder is None:
        raise FileNotFoundError(
            f"no ladder run of record under {runs_dir}; run `python -m ucs.uc01_personalization run --levels all --provider codex --force-llm` first"
        )
    cfg = _config(ladder)
    db = cfg.get("database", {}).get("sha256", "")
    out = [
        "# UC-01 results — personalised Czech outreach, one message per level of the ladder",
        "",
        f"Ran on: `substrate.db` (sha256 {db[:12] + '…' if db else 'not recorded'}), pick `{cfg.get('pick')}` "
        f"({len(cfg.get('contacts', []))} contacts: 3 linked + 1 prospect per cell of formality × gender, 4 defective rows), "
        f"briefs {cfg.get('briefs')}. Every number below sits in a run folder under `snapshots/runs/` with its "
        f"`config.json` (provider, resolved model and tier, prompt version, database hash) and every message with its "
        f"prompts in `messages.jsonl`. Generated {_dt.date.today().isoformat()} by `python -m ucs.uc01_personalization card`.",
        "",
    ]
    out += _ladder_block(ladder)
    if rec["judges"]:
        out += _judges_block(rec["judges"])
    else:
        out += [
            "## 2. The model judges",
            "",
            "No judging of the ladder run yet (`judge <run-id>`).",
            "",
        ]
    if rec["faithfulness"]:
        out += _faithfulness_block(rec["faithfulness"])
    out.append(_closing(rec))
    out.append("")
    out.append(
        "Appendix files generated from the same folders: `attachments/uc01-ladder.{csv,md}`, "
        "`uc01-faithfulness.{csv,md}`."
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    if attachments_dir is not None:
        write_attachments(rec, attachments_dir)
    return out_path
