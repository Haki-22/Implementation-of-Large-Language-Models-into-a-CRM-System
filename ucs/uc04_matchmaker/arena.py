"""The arena runner: arms x languages x data regimes x protocols into one run folder.

``run()`` loads the arena from ``substrate.db`` (``data.py``), asks every requested
arm for its score matrix, applies both protocols (``protocols.py``) and writes a
run folder under ``eval/runs/<date>-arena-...`` with ``config.json`` (what ran on
what), ``scores/<regime>-<arm>-<lang>.json`` (numbers plus per-customer ranks and
top-10 lists), ``TABLE.md`` (the generated comparison tables) and ``RESULTS.md``
(the one-page card). A run folder is the provenance of a number and is never
edited; ``report()`` re-renders the two markdown files from the JSONs.

Regimes: ``crm`` = the arms learn only from the shop's 425 customers; ``population``
= the collaborative arms learn from the whole public dump (``population.py``).
Results of different regimes are never put in one table.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import logging
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.eval.runs import (
    code_identity,
    format_duration,
    new_run_dir,
    write_card,
    write_json,
)
from utils.paths import SUBSTRATE_DB, UC04_DIR

from . import arms as arm_registry
from .data import Arena, load_arena
from .population import Population, load_population, raw_reviews_path
from .protocols import (
    evaluate_full,
    evaluate_sampled,
    random_floor,
    sample_candidates,
)

RUNS_DIR = UC04_DIR / "eval" / "runs"
REGIMES = ("crm", "population")
PROTOCOLS = ("full", "sampled")
RUN_ROLES = ("record", "comparison")
PACKAGES = (
    "implicit",
    "scipy",
    "scikit-learn",
    "lightgbm",
    "mlxtend",
    "rank_bm25",
    "sentence_transformers",
    "transformers",
    "torch",
    "simplemma",
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Identity of the inputs
# ---------------------------------------------------------------------------


def _file_digest(path: Path, *, limit_mb: int = 512) -> str:
    """SHA-256 of a file (skipped for very large files, where the pin is the identity)."""
    if path.stat().st_size > limit_mb * 1024 * 1024:
        return "skipped (large file; see pin)"
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def database_identity(arena: Arena, db_path: Path = SUBSTRATE_DB) -> dict[str, Any]:
    """The database a run read: path, size, digest and row counts, so a number can name its input."""
    return {
        "file": str(db_path.relative_to(UC04_DIR.parents[1]))
        if db_path.is_relative_to(UC04_DIR.parents[1])
        else str(db_path),
        "sha256": _file_digest(db_path),
        "customers": arena.n_customers,
        "groups": {
            g: sum(1 for c in arena.customers if c.group == g)
            for g in sorted({c.group for c in arena.customers})
        },
        "catalogue_items": arena.n_items,
        "reviews_in_histories": sum(len(c.history) for c in arena.customers),
    }


def population_identity(pop: Population) -> dict[str, Any]:
    """The public review dump the population regime learned from: file, pins and counts."""
    from substrate.pipeline.data_acquisition import fetch_and_filter as raw

    spec = raw.SOURCES.get(raw_reviews_path().name, {})
    return {
        "file": raw_reviews_path().name,
        "md5_pin": spec.get("md5"),
        "size_pin": spec.get("size"),
        "users": pop.matrix.shape[0],
        "items": pop.matrix.shape[1],
        "reviews": pop.n_reviews,
        "load_seconds": round(pop.seconds, 1),
    }


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def _tag(arm_names: list[str], langs: list[str], regimes: list[str], n_customers: int) -> str:
    """Default run-folder label summarising the regimes, arm count, languages and customer count."""
    return (
        f"arena-{'-'.join(regimes)}-{len(arm_names)}-arms-{'-'.join(langs)}-{n_customers}-customers"
    )


def run(
    *,
    arms: str | list[str] = "fast",
    langs: list[str] = ("en", "cs"),
    regimes: list[str] = ("crm",),
    protocols: list[str] = PROTOCOLS,
    n_neg: int = 100,
    seed: int = 42,
    db_path: Path = SUBSTRATE_DB,
    base_dir: Path = RUNS_DIR,
    label: str | None = None,
    attachments_dir: Path | None = None,
    progress: Callable[[int, int], None] | None = None,
    role: str = "record",
) -> Path:
    """Run the requested arms, write a run folder and refresh the thesis attachments; returns the folder.

    ``attachments_dir`` defaults to ``<project_root>/attachments/`` (``None`` = the default);
    pass a scratch path in tests. Only a run that covers every registered arm rewrites
    the appendix files, and it does so from its own folder. ``progress(done, total)``
    is called after every arm x branch x regime (the demo page shows it). ``role`` is
    ``record`` from the command line and ``comparison`` from the demo page: a comparison
    folder is kept beside the records and never selected as the run of record, however
    many arms it covers.
    """
    if role not in RUN_ROLES:
        raise ValueError(f"role must be one of {RUN_ROLES}, got {role!r}")
    arm_names = arm_registry.resolve(arms) if isinstance(arms, str) else list(arms)
    langs, regimes, protocols = list(langs), list(regimes), list(protocols)
    for r in regimes:
        if r not in REGIMES:
            raise ValueError(f"unknown regime {r}; known: {REGIMES}")
    t_start = time.time()
    arenas = {lang: load_arena(lang, db_path) for lang in langs}
    first = arenas[langs[0]]
    run_dir = new_run_dir(
        label or _tag(arm_names, langs, regimes, first.n_customers), base=base_dir
    )
    (run_dir / "scores").mkdir()
    candidates = (
        {lang: sample_candidates(a, n_neg=n_neg, seed=seed) for lang, a in arenas.items()}
        if "sampled" in protocols
        else {}
    )
    population = load_population(first) if "population" in regimes else None

    config: dict[str, Any] = {
        "run_dir": run_dir.name,
        "date": _dt.date.today().isoformat(),
        "arms": {
            n: {
                "title": arm_registry.ARMS[n].TITLE,
                "description": arm_registry.ARMS[n].DESCRIPTION,
                "family": arm_registry.ARMS[n].FAMILY,
            }
            for n in arm_names
        },
        "languages": langs,
        "regimes": regimes,
        "protocols": protocols,
        "role": role,
        "sampled_negatives": n_neg,
        "seed": seed,
        "leave_one_out": "last review by date, ties on the last day broken by the lowest review id",
        "czech_branch": "same customers, histories and hidden items; review text, headline and product title in Czech (title for 16 067 of 18 213 products, empty text for 3 207 untranslated reviews); descriptions stay English (D-UC04-D)",
        "database": database_identity(first, db_path),
        "population": population_identity(population) if population else None,
        "code": code_identity(PACKAGES),
    }
    write_json(run_dir / "config.json", config)

    results: dict[str, dict[str, Any]] = {}
    total_steps = sum(
        len(langs)
        for regime in regimes
        for name in arm_names
        if regime != "population" or arm_registry.ARMS[name].SUPPORTS_POPULATION
    )
    done_steps = 0
    for regime in regimes:
        pop = population if regime == "population" else None
        for name in arm_names:
            module = arm_registry.ARMS[name]
            if pop is not None and not module.SUPPORTS_POPULATION:
                continue
            for lang in langs:
                arena = arenas[lang]
                key = f"{regime}-{name}-{lang}"
                logger.info("=== %s ===", key)
                t0 = time.time()
                done_steps += 1
                try:
                    scores = module.score(arena, population=pop)
                except Exception as exc:  # noqa: BLE001 - a failed arm must not stop the sweep
                    logger.exception("arm %s failed: %s", key, exc)
                    results[key] = {"regime": regime, "arm": name, "lang": lang, "error": repr(exc)}
                    write_json(run_dir / "scores" / f"{key}.json", results[key])
                    if progress is not None:
                        progress(done_steps, total_steps)
                    continue
                wall = time.time() - t0
                entry: dict[str, Any] = {
                    "regime": regime,
                    "arm": name,
                    "lang": lang,
                    "wall_seconds": round(wall, 1),
                    "protocols": {},
                }
                detail: dict[str, Any] = {}
                if "full" in protocols:
                    full = evaluate_full(scores, arena, seed=seed)
                    entry["protocols"]["full"] = full.as_dict()
                    detail["full"] = full.per_customer
                if "sampled" in protocols:
                    sampled = evaluate_sampled(scores, arena, candidates[lang], seed=seed)
                    entry["protocols"]["sampled"] = sampled.as_dict()
                    detail["sampled"] = sampled.per_customer
                logger.info("  %s: %s  (%s)", key, _oneline(entry), format_duration(wall))
                results[key] = entry
                write_json(run_dir / "scores" / f"{key}.json", {**entry, "per_customer": detail})
                if progress is not None:
                    progress(done_steps, total_steps)
    config["total_seconds"] = round(time.time() - t_start, 1)
    write_json(run_dir / "config.json", config)
    report(run_dir)
    _append_runs_readme(run_dir, config)
    refresh_attachments(run_dir, attachments_dir)
    return run_dir


def refresh_attachments(run_dir: Path, attachments_dir: Path | None) -> list[Path]:
    """After a full run (every registered arm) rewrite the appendix files from this folder; a partial run keeps its own tables only."""
    from . import attachment  # local import: attachment reads run folders this module writes

    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    if not attachment.is_full_run(config):
        logger.info(
            "  partial run (%d of %d arms): appendix files unchanged; this folder's TABLE.md and RESULTS.md are its readable output",
            len(config.get("arms", {})),
            len(arm_registry.ARMS),
        )
        return []
    out = attachments_dir or attachment.ATTACHMENTS_DIR
    written = attachment.build(run_dir=run_dir, out_dir=out)
    for path in written:
        logger.info("  appendix file refreshed from this run: %s", path)
    return written


def _oneline(entry: dict[str, Any]) -> str:
    """One `hits@10` summary per protocol in `entry`, joined for a log line."""
    bits = []
    for proto, res in entry.get("protocols", {}).items():
        bits.append(f"{proto} hits@10 {res['hits']['10']}/{res['n_customers']}")
    return " · ".join(bits)


# ---------------------------------------------------------------------------
# Reporting: TABLE.md + RESULTS.md from the scores JSONs
# ---------------------------------------------------------------------------


def _load_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Read `config.json` and every `scores/*.json` of `run_dir` (per-customer detail stripped) for reporting."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    results = {}
    for path in sorted((run_dir / "scores").glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        entry.pop("per_customer", None)
        results[path.stem] = entry
    return config, results


def _pct(x: float) -> str:
    """`x` (a 0-1 fraction) formatted as a percentage string, one decimal place."""
    return f"{100 * x:.1f} %"


def report(run_dir: Path) -> None:
    """Write ``TABLE.md`` and ``RESULTS.md`` from what the run folder holds."""
    config, results = _load_run(run_dir)
    langs, regimes, protocols = config["languages"], config["regimes"], config["protocols"]
    n_items = config["database"]["catalogue_items"]
    n_neg = config["sampled_negatives"]
    lines = [f"# UC-04 arena — {run_dir.name}", ""]
    lines.append(
        f"Customers {config['database']['customers']} (groups {config['database']['groups']}), catalogue {n_items} products, "
        f"seed {config['seed']}. Full protocol: the hidden last purchase ranked against the whole catalogue, guessing scores "
        f"{_pct(random_floor('full', n_items, n_neg))} at top 10. Sampled protocol: ranked against {n_neg} random unbought products, "
        f"the same list for every arm, guessing scores {_pct(random_floor('sampled', n_items, n_neg))}. The sampled protocol is an easier task "
        "and its numbers are not comparable with the full one; it is the protocol of the recommender literature."
    )
    lines.append("")
    blocks: list[dict[str, Any]] = []
    for regime in regimes:
        for proto in protocols:
            lines.append(f"## Regime `{regime}` · protocol `{proto}`")
            lines.append("")
            head = "| arm | what it does |" + "".join(
                f" {lang}: hits / n | {lang}: HR@10 (95 % CI) | {lang}: NDCG@10 |" for lang in langs
            )
            if proto == "full":
                head += "".join(f" {lang}: hidden in top 30 / 200 |" for lang in langs)
            lines.append(head)
            lines.append("|" + " --- |" * (head.count("|") - 1))
            block_lines: list[tuple[str, str]] = []
            for name, meta in config["arms"].items():
                cells = [f"`{name}`", meta["title"]]
                reach_cells = []
                any_row = False
                for lang in langs:
                    entry = results.get(f"{regime}-{name}-{lang}")
                    res = (entry or {}).get("protocols", {}).get(proto)
                    if res is None:
                        cells += ["—", "—", "—"]
                        reach_cells.append("—")
                        continue
                    any_row = True
                    lo, hi = res["wilson95_hr10"]
                    cells += [
                        f"{res['hits']['10']} / {res['n_customers']}",
                        f"{_pct(res['hr']['10'])} ({_pct(lo)}–{_pct(hi)})",
                        f"{res['ndcg@10']:.4f}",
                    ]
                    reach_cells.append(
                        f"{res.get('reach', {}).get('30', '—')} / {res.get('reach', {}).get('200', '—')}"
                    )
                    block_lines.append(
                        (
                            f"{name} {lang}: {res['hits']['10']}/{res['n_customers']} hits@10, HR {_pct(res['hr']['10'])}",
                            f"{meta['title']}; 95 % CI {_pct(lo)}–{_pct(hi)}; NDCG@10 {res['ndcg@10']:.3f}; {entry['wall_seconds']} s",
                        )
                    )
                if not any_row:
                    continue
                if proto == "full":
                    cells += reach_cells
                lines.append("| " + " | ".join(cells) + " |")
            floor = random_floor(proto, n_items, n_neg)
            lines.append(
                "| _guessing_ | random top 10 |"
                + "".join(f" — | {_pct(floor)} | — |" for _ in langs)
                + ("".join(" — |" for _ in langs) if proto == "full" else "")
            )
            lines.append("")
            blocks.append(
                {
                    "name": f"regime {regime}, protocol {proto} (guessing {_pct(floor)})",
                    "lines": block_lines or [("no arm ran", "")],
                }
            )
    lines.append(
        "Per-customer ranks and top-10 lists: `scores/<regime>-<arm>-<lang>.json`. Configuration and input identity: `config.json`."
    )
    (run_dir / "TABLE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    header = [
        (
            "Ran on",
            f"`substrate.db` (sha256 {config['database']['sha256'][:12]}…), {config['database']['customers']} linked customers, {n_items} products",
        ),
        (
            "Regimes",
            ", ".join(regimes)
            + (
                f"; population = {config['population']['users']} users / {config['population']['reviews']} reviews from `{config['population']['file']}`"
                if config.get("population")
                else ""
            ),
        ),
        ("Protocols", ", ".join(protocols) + f"; sampled negatives {n_neg}; seed {config['seed']}"),
        ("When", f"{config['date']}, {format_duration(config.get('total_seconds', 0))} in total"),
        ("Czech branch", config.get("czech_branch", "")),
        ("Model calls", "none (classical arms only)"),
    ]
    sentence = _closing_sentence(config, results)
    write_card(
        run_dir,
        title=f"UC-04 arena results — {run_dir.name}",
        header=header,
        blocks=blocks,
        sentence=sentence,
    )


def _closing_sentence(config: dict[str, Any], results: dict[str, dict[str, Any]]) -> str:
    """One prose sentence per regime x protocol naming the best-hitting arm, for the results card."""
    parts = []
    n_items = config["database"]["catalogue_items"]
    n_neg = config["sampled_negatives"]
    for regime in config["regimes"]:
        for proto in config["protocols"]:
            best = None
            for key, entry in results.items():
                res = entry.get("protocols", {}).get(proto)
                if (
                    res is None
                    or entry["regime"] != regime
                    or entry["lang"] != config["languages"][0]
                ):
                    continue
                if best is None or res["hits"]["10"] > best[1]:
                    best = (entry["arm"], res["hits"]["10"], res["n_customers"])
            if best:
                floor = random_floor(proto, n_items, n_neg) * best[2]
                parts.append(
                    f"under `{proto}` in regime `{regime}` the best arm was `{best[0]}` with {best[1]} of {best[2]} hits at top 10 against {floor:.1f} expected by guessing"
                )
    return (
        ("Read the two protocols apart: " + "; ".join(parts) + ".")
        if parts
        else "No arm produced a result."
    )


def _append_runs_readme(run_dir: Path, config: dict[str, Any]) -> None:
    """Append one summary line for `run_dir` to `README.md` in the runs folder, creating it if needed."""
    readme = run_dir.parent / "README.md"
    line = f"- `{run_dir.name}` — {len(config['arms'])} arms, regimes {'+'.join(config['regimes'])}, protocols {'+'.join(config['protocols'])}, languages {'+'.join(config['languages'])}, {config['database']['customers']} customers; no model calls.\n"
    if not readme.exists():
        readme.write_text(
            "# UC-04 run folders\n\nOne line per folder; each folder is the provenance of the numbers it holds and is never edited.\n\n",
            encoding="utf-8",
        )
    with open(readme, "a", encoding="utf-8") as fh:
        fh.write(line)


__all__ = ["PROTOCOLS", "REGIMES", "RUNS_DIR", "refresh_attachments", "report", "run"]
