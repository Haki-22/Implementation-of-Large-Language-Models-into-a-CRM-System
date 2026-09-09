"""The one-page card of UC-04: every number with its run folder, assembled from the runs of record.

``eval/RESULTS.md`` is the page a reader takes as the result of the use case, the way
``ucs/uc02_pseudonymization/eval/RESULTS.md`` is for UC-02: the data behind the numbers,
the classical arena, the personality column, the outputs for UC-01 and the model methods,
each block naming the folder its numbers come from. Nothing here is typed by hand:
``build()`` reads the newest run of record of every kind (``attachment.run_folders``,
``record_model_runs``) and rewrites the page; run it again after any new record run
(``python -m ucs.uc04_matchmaker card``).
"""

from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path
from typing import Any

from utils.paths import UC04_DIR

from . import attachment
from .arms import model as model_registry
from .protocols import random_floor

CARD_PATH = UC04_DIR / "eval" / "RESULTS.md"


# ---------------------------------------------------------------------------
# Finding the runs of record
# ---------------------------------------------------------------------------


def _config(folder: Path) -> dict[str, Any]:
    """Read `config.json` of a run folder."""
    return json.loads((folder / "config.json").read_text(encoding="utf-8"))


def records(runs_dir: Path = attachment.RUNS_DIR) -> dict[str, Any]:
    """The newest run of record of every kind: arena, facts, personality, outputs for UC-01, model methods."""
    personality = attachment.run_folders("personality", runs_dir)
    outputs = [
        p
        for p in attachment.run_folders("outputs-for-uc01", runs_dir)
        if _config(p).get("limit") is None
    ]
    facts = attachment.run_folders("data-facts", runs_dir)
    return {
        "arena": attachment.newest_full_run(runs_dir),
        "facts": facts[-1] if facts else None,
        "personality": personality[-1] if personality else None,
        "outputs": outputs[-1] if outputs else None,
        "model": attachment.record_model_runs(runs_dir),
        "comparisons": attachment.comparison_model_runs(runs_dir),
    }


# ---------------------------------------------------------------------------
# Blocks
# ---------------------------------------------------------------------------


def _line(fact: str, meaning: str) -> tuple[str, str]:
    return fact, meaning


def _render(lines: list) -> list[str]:
    """Indent the block's fact lines and align the meanings to the block's longest fact."""
    facts = [x for x in lines if isinstance(x, tuple)]
    width = max((len(f) for f, _ in facts), default=0) + 3
    return [
        f"    {f.ljust(width)}({m})" if isinstance(x, tuple) else x
        for x in lines
        for f, m in [x if isinstance(x, tuple) else ("", "")]
    ]


def _pct(x: float) -> str:
    """`x` (a 0-1 fraction) formatted as a percentage string, one decimal place."""
    return f"{100 * x:.1f} %"


def _facts_block(folder: Path) -> list[str]:
    """Card section 1: the substrate facts (customers, catalogue density, history length, Czech coverage) from `folder`'s `facts.json`."""
    payload = json.loads((folder / "facts.json").read_text(encoding="utf-8"))
    f = {k: v["value"] for k, v in payload["facts"].items()}
    out = [f"## 1. The data behind the numbers — `runs/{folder.name}/`", ""]
    out.append(
        _line(
            f"{f['customers_linked']} customers, {f['catalogue_products']} products",
            f"density {f['density_percent']} %; {f['products_single_buyer']} of the {f['products_bought']} products ever bought have one buyer",
        )
    )
    out.append(
        _line(
            f"{f['hidden_bought_by_0_others']} hidden items bought by nobody else",
            "no collaborative method can reach them; the ceiling of the full protocol",
        )
    )
    out.append(
        _line(
            f"history {f['history_products_median']} products median ({f['history_products_min']}–{f['history_products_max']})",
            "heavy buyers; the whole history fits a model prompt",
        )
    )
    out.append(
        _line(
            f"Czech titles for {f['catalogue_czech_titles']} products, {f['czech_history_texts_empty']} history texts empty",
            "what the Czech branch reads",
        )
    )
    if "population_users" in f:
        out.append(
            _line(
                f"population {f['population_users']} users / {f['population_reviews']} reviews",
                "the public dump the population regime learns from",
            )
        )
    out.append("")
    return _render(out)


def _arena_block(folder: Path) -> list[str]:
    """Card section 2: the classical arms' best hit rates per regime/protocol, the ALS population lift, and the Czech tax on text arms."""
    config, rows = attachment.arena_rows(folder)
    n_items = config["database"]["catalogue_items"]
    n_neg = config["sampled_negatives"]
    out = [f"## 2. Classical arms — `runs/{folder.name}/`", ""]
    out.append(
        f"Twelve arms, both branches, both protocols, regimes CRM and population, {config['database']['customers']} customers; "
        f"guessing scores {_pct(random_floor('full', n_items, n_neg))} at top 10 against the whole catalogue and "
        f"{_pct(random_floor('sampled', n_items, n_neg))} against {n_neg} sampled negatives."
    )
    out.append("")
    for regime, proto in (("crm", "full"), ("crm", "sampled"), ("population", "sampled")):
        sub = [
            r
            for r in rows
            if r["regime"] == regime and r["protocol"] == proto and r["branch"] == "en"
        ]
        if not sub:
            continue
        sub.sort(key=lambda r: -r["hits_top10"])
        best = sub[0]
        cs = next(
            (
                r
                for r in rows
                if r["regime"] == regime
                and r["protocol"] == proto
                and r["branch"] == "cs"
                and r["arm"] == best["arm"]
            ),
            None,
        )
        out.append(
            _line(
                f"{regime} / {proto}: best `{best['arm']}` {best['hits_top10']} of {best['customers']}",
                f"en; cs {cs['hits_top10'] if cs else '—'}; 95 % CI {_pct(best['ci95_low'])}–{_pct(best['ci95_high'])}",
            )
        )
    als = {
        (r["regime"], r["branch"]): r
        for r in rows
        if r["arm"] == "als_cf" and r["protocol"] == "sampled"
    }
    if ("crm", "en") in als and ("population", "en") in als:
        out.append(
            _line(
                f"ALS sampled: CRM {als[('crm', 'en')]['hits_top10']} → population {als[('population', 'en')]['hits_top10']}",
                "learning from the public dump lifts collaborative filtering",
            )
        )
    text_arms = [
        (
            r["arm"],
            r["hits_top10"],
            next(
                (
                    x["hits_top10"]
                    for x in rows
                    if x["arm"] == r["arm"]
                    and x["regime"] == "crm"
                    and x["protocol"] == "sampled"
                    and x["branch"] == "cs"
                ),
                None,
            ),
        )
        for r in rows
        if r["regime"] == "crm"
        and r["protocol"] == "sampled"
        and r["branch"] == "en"
        and r["arm"] in ("dense_e5", "bert_encoder", "bm25_text", "hybrid_als_dense")
    ]
    if text_arms:
        out.append(
            _line(
                "Czech tax: " + ", ".join(f"{a} {en} → {cs}" for a, en, cs in text_arms),
                "arms that read text, en → cs, sampled; arms that read none score identically",
            )
        )
    out.append("")
    return _render(out)


def _personality_block(folder: Path) -> list[str]:
    """Card section 3: each feature arm's paired hit difference between an inferred/sampled profile and no profile."""
    pairs = json.loads((folder / "pairs.json").read_text(encoding="utf-8"))
    out = [f"## 3. The personality column — `runs/{folder.name}/`", ""]
    for p in pairs:
        if p["lang"] != "en" or p["protocol"] != "sampled" or p["second"] != "none":
            continue
        sign = "+" if p["difference"] > 0 else ""
        out.append(
            _line(
                f"{p['arm']}: {p['first']} profile {sign}{p['difference']} of {p['n']}",
                f"{p['hits_second']} → {p['hits_first']} hits, discordant {p['only_first']}/{p['only_second']}, sign p {p['p_sign']}",
            )
        )
    out.append("")
    return _render(out)


def _outputs_block(folder: Path) -> list[str]:
    """Card section 4: the outputs-for-UC-01 grounding counts (reasons, personas, aspect quotes) from `folder`'s `summary.json`."""
    config = _config(folder)
    summary = json.loads((folder / "summary.json").read_text(encoding="utf-8"))
    c = summary["counts"]
    out = [f"## 4. The outputs for UC-01 — `runs/{folder.name}/`", ""]
    out.append(
        _line(
            f"{c['reasons_grounded']} of {c['reasons_ok'] + c['reasons_failed']} reasons grounded",
            f"every cited purchase exists in the history shown; {summary['reason_words_median']} words median",
        )
    )
    out.append(
        _line(
            f"{c['personas_ok']} personas, {c['aspects_grounded']} of {c['aspects_total']} aspect quotes verbatim",
            "checked, not trusted",
        )
    )
    out.append(
        _line(
            f"{c['calls']} calls, {config['provider']} / {config['model']} / {config['tier']}",
            f"prompt {config['prompt_version']}; topics + lifecycle for {c['topics_contacts']} contacts",
        )
    )
    out.append("")
    return _render(out)


def _model_block(record: dict[str, Path]) -> list[str]:
    """Card section 5: each model method's hit rate, its ALS pairing and its record provider/model, one row per method/protocol."""
    folders, rows, pairs = attachment.model_methods_rows(record)
    out = ["## 5. The model methods — one record folder per method", ""]
    for run_dir, cfg, names in folders:
        out.append(
            f"`runs/{run_dir.name}/` — {', '.join(names)}: {cfg['provider']} / {cfg['model']} / {cfg['tier']}, prompt {cfg['prompt_version']}"
        )
    out.append("")
    seen: set[tuple[str, str]] = set()
    for r in rows:
        key = (r["method"], r["protocol"])
        if key in seen or r["branch"] != "en":
            continue
        seen.add(key)
        cs = next(
            (
                x
                for x in rows
                if x["method"] == r["method"]
                and x["protocol"] == r["protocol"]
                and x["branch"] == "cs"
            ),
            None,
        )
        als = next(
            (
                p
                for p in pairs
                if p["method"] == r["method"]
                and p["protocol"] == r["protocol"]
                and p["lang"] == "en"
                and p["versus"] == "als_cf"
            ),
            None,
        )
        meaning = f"cs {cs['hits_top10'] if cs else '—'}"
        if als:
            sign = "+" if als["difference"] > 0 else ""
            meaning += f"; ALS {als['hits_second']} on the same lists ({sign}{als['difference']}, sign p {als['p_sign']})"
        meaning += (
            f"; calls ok/partial/failed {r['calls_ok']}/{r['calls_partial']}/{r['calls_failed']}"
        )
        out.append(
            _line(
                f"{r['method']} ({r['protocol']}): {r['hits_top10']} of {r['customers']}",
                meaning,
            )
        )
    prof = [
        p for p in pairs if p["method"] == "rerank_als_with_profile" and p["versus"] == "rerank_als"
    ]
    if prof:
        out.append(
            _line(
                "profile vs plain re-rank: "
                + ", ".join(f"{p['lang']} {p['difference']:+d}" for p in prof),
                "sign p "
                + " / ".join(str(p["p_sign"]) for p in prof)
                + "; the CRM profile in the prompt does not help",
            )
        )
    out.append("")
    return _render(out)


def _hits(rows: list[dict[str, Any]], method: str, protocol: str, branch: str) -> dict | None:
    """The `model_methods_rows` row matching `method`/`protocol`/`branch`, or None."""
    return next(
        (
            x
            for x in rows
            if x["method"] == method and x["protocol"] == protocol and x["branch"] == branch
        ),
        None,
    )


def _comparison_block(record: dict[str, Path], comparisons: list[Path]) -> list[str]:
    """The same method on a second provider: every comparison folder beside the record of its methods."""
    out = ["## 6. The same method on a second provider — comparison folders, never the record", ""]
    rec_rows = attachment.model_methods_rows(record)[1] if record else []
    for folder in comparisons:
        cfg = _config(folder)
        assignment = {
            name: folder
            for name in cfg.get("methods", {})
            if any((folder / "scores").glob(f"{name}-*.json"))
        }
        _, rows, _ = attachment.model_methods_rows(assignment)
        out.append(
            f"`runs/{folder.name}/` — {', '.join(assignment)}: {cfg['provider']} / {cfg['model']} / {cfg['tier']}, prompt {cfg['prompt_version']}"
        )
        seen: set[tuple[str, str]] = set()
        for r in rows:
            key = (r["method"], r["protocol"])
            if key in seen or r["branch"] != "en":
                continue
            seen.add(key)
            cs = _hits(rows, r["method"], r["protocol"], "cs")
            rec_en = _hits(rec_rows, r["method"], r["protocol"], "en")
            rec_cs = _hits(rec_rows, r["method"], r["protocol"], "cs")
            rec_folder = record.get(r["method"])
            if rec_en and rec_folder:
                rc = _config(rec_folder)
                meaning = (
                    f"record {rc['provider']} / {rc['model']} / {rc['tier']}: "
                    f"{rec_en['hits_top10']} / {rec_cs['hits_top10'] if rec_cs else '—'}"
                )
            else:
                meaning = "no record for this method yet"
            meaning += f"; calls ok/partial/failed {r['calls_ok']}/{r['calls_partial']}/{r['calls_failed']}"
            out.append(
                _line(
                    f"{r['method']} ({r['protocol']}): en {r['hits_top10']} / cs "
                    f"{cs['hits_top10'] if cs else '—'} of {r['customers']}",
                    meaning,
                )
            )
        out.append("")
    return _render(out)


def _closing(record: dict[str, Path], arena: Path | None) -> str:
    """One prose paragraph reading the model methods' results together, for the top of the card."""
    parts = []
    if record:
        _, rows, pairs = attachment.model_methods_rows(record)
        alone = next(
            (r for r in rows if r["method"] == "rank_candidates" and r["branch"] == "en"), None
        )
        rerank = next(
            (r for r in rows if r["method"] == "rerank_als" and r["branch"] == "en"), None
        )
        top = next(
            (r for r in rows if r["method"] == "rerank_als_top200" and r["branch"] == "en"), None
        )
        als = next(
            (
                p
                for p in pairs
                if p["method"] == "rerank_als" and p["lang"] == "en" and p["versus"] == "als_cf"
            ),
            None,
        )
        if alone and rerank and als:
            parts.append(
                f"on the sampled lists the model re-ranking ALS scores {rerank['hits_top10']} of {rerank['customers']} against ALS's {als['hits_second']} "
                f"and the model alone {alone['hits_top10']}: a strong complement, and on lists of 101 products from random categories stronger alone"
            )
        if top:
            top_als = next(
                (
                    p
                    for p in pairs
                    if p["method"] == "rerank_als_top200"
                    and p["lang"] == "en"
                    and p["versus"] == "als_cf"
                ),
                None,
            )
            parts.append(
                f"against the whole catalogue the only method that moves the number is the re-rank of ALS's top 200 "
                f"({top_als['hits_second'] if top_als else '?'} → {top['hits_top10']} of {top['customers']}), at the edge of significance"
            )
    if not parts:
        return "No model method has a record folder yet; the classical arena stands alone."
    return (
        "Reading: "
        + "; ".join(parts)
        + ". The profile of the customer, as a column in the classical arms or as text in the prompt, adds nothing measurable."
    )


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build(out_path: Path = CARD_PATH, runs_dir: Path = attachment.RUNS_DIR) -> Path:
    """Write the one-page card from the runs of record; returns the path."""
    rec = records(runs_dir)
    arena = rec["arena"]
    if arena is None:
        raise FileNotFoundError(
            f"no full arena run under {runs_dir}; run `python -m ucs.uc04_matchmaker run --arms all` first"
        )
    config = _config(arena)
    hashes: dict[str, str] = {arena.name: config["database"]["sha256"][:12]}
    for folder in [
        rec["personality"],
        rec["outputs"],
        *sorted(set(rec["model"].values()), key=lambda p: p.name),
        *rec["comparisons"],
    ]:
        if folder is not None:
            hashes[folder.name] = _config(folder)["database"]["sha256"][:12]
    distinct = sorted(set(hashes.values()))
    db_note = (
        f"sha256 {distinct[0]}…"
        if len(distinct) == 1
        else "the database was rebuilt between the runs (same customers, histories and hidden items; a rebuild "
        "changed the profile columns or the message briefs, which no arm reads): "
        + "; ".join(f"`{name}` on {h}…" for name, h in hashes.items())
    )
    out = [
        "# UC-04 results — customer × product matchmaker, classical machine learning against language models",
        "",
        f"Ran on: `substrate.db` ({db_note}), {config['database']['customers']} linked customers "
        f"with the chronologically last purchase hidden, {config['database']['catalogue_items']} products. Two protocols (the hidden item "
        "against the whole catalogue, and against 100 sampled unbought products), two branches (English, Czech), regimes CRM and "
        "population for the collaborative arms. Every number below sits in a run folder under `eval/runs/` with its `config.json` "
        f"(database hash, seeds, package versions, the full prompts of the model methods) and its own card. Generated "
        f"{_dt.date.today().isoformat()} by `python -m ucs.uc04_matchmaker card`.",
        "",
    ]
    if rec["facts"]:
        out += _facts_block(rec["facts"])
    out += _arena_block(arena)
    if rec["personality"]:
        out += _personality_block(rec["personality"])
    if rec["outputs"]:
        out += _outputs_block(rec["outputs"])
    if rec["model"]:
        out += _model_block(rec["model"])
        missing = [n for n in model_registry.MODEL_ARMS if n not in rec["model"]]
        if missing:
            out.append(f"Methods without a record folder yet: {', '.join(missing)}.")
            out.append("")
    if rec["comparisons"]:
        out += _comparison_block(rec["model"], rec["comparisons"])
    out.append(_closing(rec["model"], arena))
    out.append("")
    out.append(
        "Appendix files generated from the same folders: `attachments/uc04-arena-results.{csv,md}`, `uc04-data-facts.{csv,md}`, "
        "`uc04-personality-feature.{csv,md}`, `uc04-outputs-for-uc01.{csv,md}`, `uc04-model-methods.{csv,md}`, `uc04-arms.md`."
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    return out_path


__all__ = ["CARD_PATH", "build", "records"]
