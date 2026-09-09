"""The thesis attachment for UC-04, generated from one run folder.

Flow (user 2026-09-06): a run saves its numbers into its dated run folder and the readable
markdown is generated from those saved numbers, no manual step. Every run folder carries
its own ``TABLE.md`` and ``RESULTS.md``; the **appendix files** in ``<project_root>/attachments/``
(``uc04-arena-results.csv`` / ``.md``, ``uc04-data-facts.csv`` / ``.md``) are built from
**one** run folder, the run of record, never stitched from several. Every arm is seeded, but LightGBM can still vary
between processes; a table that mixes folders would lose the provenance of which
code and which database it describes. ``arena.run`` rewrites the
arena attachment when the run covers every registered arm (a full run); a partial run
(``run --arms als_cf``) keeps its own tables and leaves the appendix alone. ``facts.run``
rewrites the facts attachment; ``model_arena.run`` rewrites ``uc04-model-methods.{csv,md}``
after a full run of the model methods; ``uc04-arms.md`` (the single table of every method,
classical and model) is generated from the two registries by every ``build``.
``python -m ucs.uc04_matchmaker attachment --run <folder>`` does the same by hand for a
chosen folder. The pattern is the one of
``attachments/tokenizer_fertility.py`` behind Příloha A: the appendix quotes a generated
file, never a typed number. The tables are wide; the appendix page renders landscape.
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
from pathlib import Path
from typing import Any

from utils.paths import THESIS_ROOT, UC04_DIR

from . import arms as arm_registry
from .arms import model as model_registry
from .protocols import random_floor

RUNS_DIR = UC04_DIR / "eval" / "runs"
ATTACHMENTS_DIR = THESIS_ROOT / "attachments"
REGIME_CS = {
    "crm": "režim CRM (učení jen ze zákazníků obchodu)",
    "population": "režim populace (učení z celého veřejného datasetu)",
}
PROTOCOL_CS = {
    "full": "úplný katalog",
    "sampled": "vzorkovaný (1 skrytý + 100 náhodných nekoupených)",
}
LANG_CS = {"en": "anglická větev", "cs": "česká větev"}
FIELDS = [
    "run",
    "regime",
    "protocol",
    "arm",
    "title",
    "branch",
    "customers",
    "hits_top5",
    "hits_top10",
    "hr_top10",
    "ci95_low",
    "ci95_high",
    "ndcg10",
    "mrr10",
    "hidden_in_top30",
    "hidden_in_top200",
    "seconds",
]
MODEL_FIELDS = [
    "run",
    "provider",
    "model",
    "tier",
    "prompt_version",
    "method",
    "title",
    "branch",
    "protocol",
    "customers",
    "calls_ok",
    "calls_partial",
    "calls_failed",
    "calls_reused",
    "hidden_dropped",
    "hits_top5",
    "hits_top10",
    "hr_top10",
    "ci95_low",
    "ci95_high",
    "ndcg10",
    "mrr10",
    "median_call_seconds",
    "versus",
    "versus_hits_top10",
    "difference",
    "only_method",
    "only_versus",
    "p_sign",
]


# ---------------------------------------------------------------------------
# Reading run folders
# ---------------------------------------------------------------------------


def run_folders(kind: str, base: Path = RUNS_DIR) -> list[Path]:
    """Run folders of one kind, told apart by their files, oldest first: ``arena`` (config.json + scores/, no pairs.json), ``data-facts`` (facts.json), ``model-methods`` (pairs.json + scores/ + sample.json), ``personality`` (pairs.json + scores/, no sample.json), ``outputs-for-uc01`` (handoff.json)."""
    if not base.exists():
        return []
    found = []
    for p in base.iterdir():
        if not p.is_dir():
            continue
        if (
            kind == "arena"
            and (p / "config.json").exists()
            and (p / "scores").is_dir()
            and not (p / "pairs.json").exists()
        ):
            found.append(p)
        elif kind == "data-facts" and (p / "facts.json").exists():
            found.append(p)
        elif (
            kind == "model-methods"
            and (p / "pairs.json").exists()
            and (p / "scores").is_dir()
            and (p / "sample.json").exists()
        ):
            found.append(p)
        elif (
            kind == "personality"
            and (p / "pairs.json").exists()
            and (p / "scores").is_dir()
            and not (p / "sample.json").exists()
        ):
            found.append(p)
        elif kind == "outputs-for-uc01" and (p / "handoff.json").exists():
            found.append(p)
    return sorted(found, key=lambda p: (p.name[:10], p.stat().st_mtime, p.name))


def _load_arena_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]]]:
    """Read `config.json` and every `scores/*.json` of an arena run folder (per-customer detail stripped)."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    results = {}
    for path in sorted((run_dir / "scores").glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        entry.pop("per_customer", None)
        results[path.stem] = entry
    return config, results


def arena_rows(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Flatten one arena run into rows, one per regime x protocol x arm x branch."""
    config, results = _load_arena_run(run_dir)
    rows: list[dict[str, Any]] = []
    for key in sorted(results):
        entry = results[key]
        for proto, res in entry.get("protocols", {}).items():
            lo, hi = res["wilson95_hr10"]
            rows.append(
                {
                    "run": run_dir.name,
                    "regime": entry["regime"],
                    "protocol": proto,
                    "arm": entry["arm"],
                    "title": config["arms"][entry["arm"]]["title"],
                    "branch": entry["lang"],
                    "customers": res["n_customers"],
                    "hits_top5": res["hits"]["5"],
                    "hits_top10": res["hits"]["10"],
                    "hr_top10": round(res["hr"]["10"], 4),
                    "ci95_low": round(lo, 4),
                    "ci95_high": round(hi, 4),
                    "ndcg10": round(res["ndcg@10"], 4),
                    "mrr10": round(res["mrr@10"], 4),
                    "hidden_in_top30": res.get("reach", {}).get("30", ""),
                    "hidden_in_top200": res.get("reach", {}).get("200", ""),
                    "seconds": entry["wall_seconds"],
                }
            )
    return config, rows


def is_full_run(config: dict[str, Any]) -> bool:
    """A record run that covers every registered arm may stand as the run of record.

    A folder launched as a comparison (the demo page, ``role="comparison"``) never does,
    however complete it is; a folder without the field predates the role and is a record.
    """
    return (
        set(config.get("arms", {})) >= set(arm_registry.ARMS)
        and config.get("role", "record") == "record"
    )


def newest_full_run(base: Path = RUNS_DIR) -> Path | None:
    """The newest arena folder that covers every registered arm, or None."""
    for folder in reversed(run_folders("arena", base)):
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        if is_full_run(config):
            return folder
    return None


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _pct(x: float) -> str:
    """`x` (a 0-1 fraction) as a Czech-locale percentage string (comma decimal separator), one decimal place."""
    return f"{100 * x:.1f} %".replace(".", ",")


def arena_markdown(config: dict[str, Any], rows: list[dict[str, Any]], run_dir: Path) -> str:
    """Czech-captioned tables from one run folder, one per regime x protocol, branches side by side."""
    n_items = config["database"]["catalogue_items"]
    n_neg = config["sampled_negatives"]
    out = [
        "# Výsledky arény UC-04 (příloha, generováno)",
        "",
        f"Vygenerováno ze složky běhu `ucs/uc04_matchmaker/eval/runs/{run_dir.name}/` (běh ze dne {config['date']}, "
        f"{config.get('total_seconds', 0):.0f} s). Databáze `substrate.db` (sha256 {config['database']['sha256'][:12]}…), "
        f"{config['database']['customers']} zákazníků, {n_items} produktů, seed {config['seed']}. Bez volání jazykového modelu. "
        "Všechna ramena jsou nasazená se semínkem a opakovaný běh nad touž databází dává tatáž čísla; jedinou výjimkou je LightGBM, které se mezi běhy liší o jednotky zásahů uvnitř svého intervalu spolehlivosti. "
        "Tabulky jsou široké; stránka přílohy se sází na šířku.",
        "",
        f"Skrytou položkou je chronologicky poslední nákup zákazníka. Úplný katalog: skrytá položka se řadí proti všem {n_items} produktům, "
        f"náhodný tip dává v top 10 {_pct(random_floor('full', n_items, n_neg))}. Vzorkovaný protokol: skrytá položka se řadí proti "
        f"{n_neg} náhodným nekoupeným produktům, stejným pro všechna ramena, náhodný tip dává {_pct(random_floor('sampled', n_items, n_neg))}. "
        "Vzorkovaný protokol je snazší úloha a jeho čísla nejsou srovnatelná s úplným katalogem; slouží ke srovnání metod mezi sebou, ne k odhadu, co by viděl obchod. "
        f"Česká větev: {config.get('czech_branch', '')}.",
        "",
    ]
    langs = ["en", "cs"] if any(r["branch"] == "cs" for r in rows) else ["en"]
    regimes = [r for r in ("crm", "population") if any(x["regime"] == r for x in rows)]
    protocols = [p for p in ("full", "sampled") if any(x["protocol"] == p for x in rows)]
    t = 1
    for regime in regimes:
        for proto in protocols:
            sub = [r for r in rows if r["regime"] == regime and r["protocol"] == proto]
            if not sub:
                continue
            out.append(
                f"Tabulka {t} – Zásahy v top 10 z {sub[0]['customers']} zákazníků, {PROTOCOL_CS[proto]}, {REGIME_CS[regime]}"
            )
            out.append("")
            head = "| rameno | metoda |" + "".join(
                f" {LANG_CS[lang]}: zásahy | {LANG_CS[lang]}: HR@10 (95% IS) |" for lang in langs
            )
            if proto == "full":
                head += "".join(f" {LANG_CS[lang]}: skrytá v top 30 / 200 |" for lang in langs)
            out.append(head)
            out.append("|" + " --- |" * (head.count("|") - 1))
            arms_here = []
            for r in sub:
                if r["arm"] not in arms_here:
                    arms_here.append(r["arm"])
            for arm in arms_here:
                title = next(r["title"] for r in sub if r["arm"] == arm)
                cells = [f"`{arm}`", title]
                reach = []
                for lang in langs:
                    r = next((x for x in sub if x["arm"] == arm and x["branch"] == lang), None)
                    if r is None:
                        cells += ["—", "—"]
                        reach.append("—")
                        continue
                    cells += [
                        f"{r['hits_top10']} / {r['customers']}",
                        f"{_pct(r['hr_top10'])} ({_pct(r['ci95_low'])}–{_pct(r['ci95_high'])})",
                    ]
                    reach.append(f"{r['hidden_in_top30']} / {r['hidden_in_top200']}")
                if proto == "full":
                    cells += reach
                out.append("| " + " | ".join(cells) + " |")
            floor = random_floor(proto, n_items, n_neg)
            out.append(
                "| _náhodný tip_ | top 10 náhodně |"
                + "".join(f" — | {_pct(floor)} |" for _ in langs)
                + ("".join(" — |" for _ in langs) if proto == "full" else "")
            )
            out.append("")
            t += 1
    out.append(
        "Zdrojová data po řádcích: `attachments/uc04-arena-results.csv`; pořadí a top 10 každého zákazníka: `scores/` ve složce běhu."
    )
    return "\n".join(out) + "\n"


def facts_rows(facts_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Flatten a data-facts run's `facts.json` into `(payload, rows)`, one row per fact key."""
    payload = json.loads((facts_dir / "facts.json").read_text(encoding="utf-8"))
    rows = [
        {"run": facts_dir.name, "key": k, "value": v["value"], "meaning": v["meaning"]}
        for k, v in payload["facts"].items()
    ]
    return payload, rows


def facts_markdown(payload: dict[str, Any], rows: list[dict[str, Any]], facts_dir: Path) -> str:
    """Czech-captioned data-facts appendix table from `facts_rows`' output."""
    out = [
        "# Datová fakta za arénou UC-04 (příloha, generováno)",
        "",
        f"Vygenerováno dne {_dt.date.today().isoformat()} ze složky běhu `ucs/uc04_matchmaker/eval/runs/{facts_dir.name}/` "
        f"(databáze `substrate.db`, sha256 {payload['database']['sha256'][:12]}…). Bez volání jazykového modelu.",
        "",
        "Tabulka – Vlastnosti datové základny, které určují dosažitelné hodnoty HR@K",
        "",
        "| klíč | hodnota | význam |",
        "| --- | --- | --- |",
    ]
    for r in rows:
        out.append(f"| `{r['key']}` | {r['value']} | {r['meaning']} |")
    out.append("")
    out.append("Zdrojová data: `attachments/uc04-data-facts.csv`.")
    return "\n".join(out) + "\n"


# ---------------------------------------------------------------------------
# Building
# ---------------------------------------------------------------------------


def build(
    *,
    run_dir: Path | None = None,
    facts_dir: Path | None = None,
    model_run_dirs: list[Path] | None = None,
    out_dir: Path = ATTACHMENTS_DIR,
) -> list[Path]:
    """Write the attachment files from one arena run (default: the newest full run), one facts run (default: the newest), the model-methods folders of record (default: the newest complete folder per method) and the registries."""
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    run_dir = run_dir or newest_full_run()
    if run_dir is not None:
        config, rows = arena_rows(run_dir)
        csv_path = out_dir / "uc04-arena-results.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            w.writerows(rows)
        written.append(csv_path)
        md_path = out_dir / "uc04-arena-results.md"
        md_path.write_text(arena_markdown(config, rows, run_dir), encoding="utf-8")
        written.append(md_path)
    facts = run_folders("data-facts", RUNS_DIR) if facts_dir is None else [facts_dir]
    if facts:
        payload, frows = facts_rows(facts[-1])
        fcsv = out_dir / "uc04-data-facts.csv"
        with open(fcsv, "w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=["run", "key", "value", "meaning"])
            w.writeheader()
            w.writerows(frows)
        written.append(fcsv)
        fmd = out_dir / "uc04-data-facts.md"
        fmd.write_text(facts_markdown(payload, frows, facts[-1]), encoding="utf-8")
        written.append(fmd)
    written += build_model_methods(run_dirs=model_run_dirs, out_dir=out_dir)
    written.append(write_arms_table(out_dir))
    return written


# ---------------------------------------------------------------------------
# The single methods table (the arms are described once, from the registries)
# ---------------------------------------------------------------------------


def arms_table_markdown() -> str:
    """One table of every method of the arena, classical and model, from the two registries."""
    out = [
        "# Metody arény UC-04 (příloha, generováno z registrů)",
        "",
        f"Vygenerováno dne {_dt.date.today().isoformat()} z `arms/__init__.py` ({len(arm_registry.ARMS)} klasických metod) "
        f"a `arms/model/__init__.py` ({len(model_registry.MODEL_ARMS)} metod s jazykovým modelem). Toto je jediný popis metod "
        "v práci; text kapitoly na tuto tabulku odkazuje a metody znovu nepopisuje. Klasické metody se hodnotí pod oběma "
        "protokoly na všech 425 zákaznících; metody s modelem pod protokolem, který je u nich uveden, na pevném vzorku "
        "100 zákazníků (metoda nad ALS top 200 na zákaznících, jimž ALS dostalo skrytý nákup do prvních dvou set).",
        "",
        "Tabulka – Metody arény: jméno v kódu, co metoda dělá, rodina, vstup z klasického modelu, protokol",
        "",
        "| metoda | co to je | rodina | vstup z ML | protokol |",
        "| --- | --- | --- | --- | --- |",
    ]
    for name, m in arm_registry.ARMS.items():
        out.append(
            f"| `{name}` | {m.TITLE}: {m.DESCRIPTION} | {m.FAMILY} | — | úplný katalog i vzorkovaný |"
        )
    for name, m in model_registry.MODEL_ARMS.items():
        protocols = ", ".join(PROTOCOL_CS[p] for p in m.PROTOCOLS)
        out.append(
            f"| `{name}` | {m.TITLE}: {m.DESCRIPTION} | {m.FAMILY} | {m.ML_INPUT} | {protocols} |"
        )
    out.append("")
    return "\n".join(out) + "\n"


def write_arms_table(out_dir: Path = ATTACHMENTS_DIR) -> Path:
    """Write ``uc04-arms.md`` from the registries."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "uc04-arms.md"
    path.write_text(arms_table_markdown(), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# The model methods: results, paired differences, the model's lines
# ---------------------------------------------------------------------------


def record_model_runs(base: Path = RUNS_DIR) -> dict[str, Path]:
    """Method name -> the newest run folder that holds it on the whole sample with a real provider.

    The model methods may be run one provider at a time (decided 2026-09-07: methods 1, 2
    and 5 on agy, 3 and 4 on Codex), so the run of record of the appendix is one folder
    per method, never a folder stitched from reruns of the same method: for every method
    exactly one folder, the newest complete one, and every row of the appendix names it.
    """
    from .model_arena import is_record_run

    found: dict[str, Path] = {}
    for folder in run_folders("model-methods", base):
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        if not is_record_run(config):
            continue
        for name in config.get("methods", {}):
            if any((folder / "scores").glob(f"{name}-*.json")):
                found[name] = folder
    return found


def comparison_model_runs(base: Path = RUNS_DIR) -> list[Path]:
    """The complete model-methods folders launched as a provider comparison (``--role comparison``), oldest first.

    A comparison runs the same method on the whole sample with a second provider or model
    (2026-09-07). It is kept beside the record and never replaces it
    (``model_arena.is_record_run``); the card lists every one of them next to the record
    of the same method.
    """
    out: list[Path] = []
    for folder in run_folders("model-methods", base):
        config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
        if (
            config.get("role") == "comparison"
            and config.get("limit") is None
            and config.get("provider") != "mock"
        ):
            out.append(folder)
    return out


def assign_methods(run_dirs: list[Path]) -> dict[str, Path]:
    """Method name -> the folder that stands for it among ``run_dirs``: the last one (by name) that holds it.

    The same rule as ``record_model_runs`` applied to a chosen list: a method present in
    two folders takes the newer folder, never both.
    """
    assignment: dict[str, Path] = {}
    for run_dir in sorted(run_dirs, key=lambda p: p.name):
        config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
        for name in config.get("methods", {}):
            if any((run_dir / "scores").glob(f"{name}-*.json")):
                assignment[name] = run_dir
    return assignment


def model_methods_rows(
    assignment: dict[str, Path],
) -> tuple[list[tuple[Path, dict[str, Any], list[str]]], list[dict[str, Any]], list[dict]]:
    """Flatten the assigned folders: one row per method × branch × protocol × paired reference.

    ``assignment`` is method -> folder (``record_model_runs`` or ``assign_methods``); a
    folder contributes only the methods assigned to it. Returns the distinct folders with
    their configs and assigned methods, the rows and the pairs of the assigned methods.
    """
    from .model_arena import load_run

    folders: list[tuple[Path, dict[str, Any], list[str]]] = []
    rows: list[dict[str, Any]] = []
    all_pairs: list[dict] = []
    by_folder: dict[Path, list[str]] = {}
    for name, run_dir in assignment.items():
        by_folder.setdefault(run_dir, []).append(name)
    for run_dir in sorted(by_folder, key=lambda p: p.name):
        config, results, pairs = load_run(run_dir)
        names = [n for n in config["methods"] if n in by_folder[run_dir]]
        folders.append((run_dir, config, names))
        all_pairs += [p for p in pairs if p["method"] in names]
        for name in names:
            _method_rows(rows, run_dir, config, results, pairs, name, config["methods"][name])
    return folders, rows, all_pairs


def _method_rows(rows, run_dir, config, results, pairs, name, meta) -> None:
    """Append one row per branch x protocol x paired reference for method `name` to `rows` (in place)."""
    for lang in config["languages"]:
        entry = results.get(f"{name}-{lang}")
        if entry is None:
            continue
        for proto, res in entry["protocols"].items():
            lo, hi = res["wilson95_hr10"]
            base = {
                "run": run_dir.name,
                "provider": config["provider"],
                "model": config["model"],
                "tier": config["tier"],
                "prompt_version": config["prompt_version"],
                "method": name,
                "title": meta["title"],
                "branch": lang,
                "protocol": proto,
                "customers": res["n_customers"],
                "calls_ok": entry["calls"]["ok"],
                "calls_partial": entry["calls"]["partial"],
                "calls_failed": entry["calls"]["failed"],
                "calls_reused": entry["calls"].get("reused", 0),
                "hidden_dropped": entry["calls"].get("hidden_dropped", 0),
                "hits_top5": res["hits"]["5"],
                "hits_top10": res["hits"]["10"],
                "hr_top10": round(res["hr"]["10"], 4),
                "ci95_low": round(lo, 4),
                "ci95_high": round(hi, 4),
                "ndcg10": round(res["ndcg@10"], 4),
                "mrr10": round(res["mrr@10"], 4),
                "median_call_seconds": entry.get("median_call_seconds"),
            }
            own = [
                p
                for p in pairs
                if p["method"] == name and p["lang"] == lang and p["protocol"] == proto
            ]
            if not own:
                rows.append(
                    {
                        **base,
                        "versus": "",
                        "versus_hits_top10": "",
                        "difference": "",
                        "only_method": "",
                        "only_versus": "",
                        "p_sign": "",
                    }
                )
            for p in own:
                rows.append(
                    {
                        **base,
                        "versus": p["versus"],
                        "versus_hits_top10": p["hits_second"],
                        "difference": p["difference"],
                        "only_method": p["only_first"],
                        "only_versus": p["only_second"],
                        "p_sign": p["p_sign"],
                    }
                )


def model_methods_markdown(
    folders: list[tuple[Path, dict[str, Any], list[str]]], rows: list[dict[str, Any]]
) -> str:
    """Czech-captioned tables from the run folders of record: results per method and branch, paired differences, the model's lines."""
    first = folders[0][1]
    n_items = first["database"]["catalogue_items"]
    n_neg = first["sampled_negatives"]
    n_sample = len(first["sample"]["customers"])
    provenance = "; ".join(
        f"`{run_dir.name}` ({', '.join(names)}: {cfg['provider']} / {cfg['model']} / {cfg['tier']}, "
        f"CLI {cfg['provider_cli_version']}, prompt {cfg['prompt_version']}, běh ze dne {cfg['date']}, "
        f"{cfg.get('total_seconds', 0):.0f} s)"
        for run_dir, cfg, names in folders
    )
    out = [
        "# Metody s jazykovým modelem v aréně UC-04 (příloha, generováno)",
        "",
        f"Vygenerováno ze složek běhů pod `ucs/uc04_matchmaker/eval/runs/`, jedna složka na metodu: {provenance}. "
        f"Databáze `substrate.db` (sha256 {first['database']['sha256'][:12]}…); vzorek `{first['sample']['name']}` "
        f"({n_sample} zákazníků, pravidlo ve složce běhu), metoda nad ALS top 200 na zákaznících, jimž ALS dostalo skrytý nákup "
        "do prvních dvou set. Metody běžely po poskytovatelích (rozhodnutí 2026-09-07); dvojice metoda 3 × metoda 4 je uvnitř jedné "
        "složky, ostatní dvojice jsou proti klasickým referencím na týchž listinách. Anglická větev: anglická instrukce "
        "a anglické názvy; česká větev: česká instrukce a české názvy (kde jsou), persona a aspekty v profilu jsou české v obou větvích.",
        "",
        f"Vzorkovaný protokol: skrytý poslední nákup proti {n_neg} náhodným nekoupeným produktům, stejným jako u klasických metod, "
        f"náhodný tip {_pct(random_floor('sampled', n_items, n_neg))} v top 10. Úplný katalog: proti všem {n_items} produktům, náhodný tip "
        f"{_pct(random_floor('full', n_items, n_neg))}. Referenční metody `als_cf` a `popularity` jsou spočítány na týchž zákaznících "
        "a týchž listinách. Volání: ok = každý identifikátor právě jednou; partial = chybějící identifikátory doplněny na konec v pořadí "
        "promptu; failed = neznámý nebo opakovaný identifikátor, chyba poskytovatele nebo časový limit (zákazník bez odpovědi se řadí náhodně).",
        "",
        "Tabulka 1 – Zásahy v top 10, metoda × větev × protokol, s referencí na týchž listinách",
        "",
        "| metoda | poskytovatel / model / úroveň | větev | protokol | zákazníků | volání ok / partial / failed (skrytý mezi vynechanými) | zásahy | HR@10 (95% IS) | NDCG@10 | reference `als_cf` | reference `popularity` |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    seen: set[tuple[str, str, str]] = set()
    by_ref: dict[tuple[str, str, str, str], Any] = {
        (r["method"], r["branch"], r["protocol"], r["versus"]): r["versus_hits_top10"]
        for r in rows
        if r["versus"]
    }
    for r in rows:
        key = (r["method"], r["branch"], r["protocol"])
        if key in seen:
            continue
        seen.add(key)
        als = by_ref.get((*key, "als_cf"), "—")
        pop = by_ref.get((*key, "popularity"), "—")
        out.append(
            f"| `{r['method']}` | {r['provider']} / {r['model']} / {r['tier']} | {LANG_CS[r['branch']]} | {PROTOCOL_CS[r['protocol']]} | {r['customers']} | "
            f"{r['calls_ok']} / {r['calls_partial']} / {r['calls_failed']} ({r['hidden_dropped']}) | {r['hits_top10']} / {r['customers']} | "
            f"{_pct(r['hr_top10'])} ({_pct(r['ci95_low'])}–{_pct(r['ci95_high'])}) | {str(r['ndcg10']).replace('.', ',')} | {als} | {pop} |"
        )
    out += [
        "",
        "Tabulka 2 – Párové rozdíly na týchž zákaznících (zásah v top 10; oboustranný znaménkový test nad neshodnými páry)",
        "",
        "| metoda | větev | protokol | proti | zásahy proti | zásahy metoda | rozdíl | jen metoda | jen proti | p (znaménkový) |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        if not r["versus"]:
            continue
        out.append(
            f"| `{r['method']}` | {LANG_CS[r['branch']]} | {PROTOCOL_CS[r['protocol']]} | `{r['versus']}` | {r['versus_hits_top10']} | "
            f"{r['hits_top10']} | {r['difference']:+d} | {r['only_method']} | {r['only_versus']} | {str(r['p_sign']).replace('.', ',')} |"
        )
    out.append("")
    examples: list[str] = []
    for run_dir, cfg, names in folders:
        if "describe_and_retrieve" in names:
            examples = _model_lines_examples(run_dir, cfg)
            break
    if examples:
        out += [
            "Tabulka 3 – Co model napsal jako příští nákup vedle toho, co zákazník skutečně koupil (metoda popíše a katalog najde; první zákazníci každé větve)",
            "",
            "| větev | zákazník | skutečný příští nákup | tři řádky modelu |",
            "| --- | --- | --- | --- |",
            *examples,
            "",
        ]
    out.append(
        "Zdrojová data po řádcích: `attachments/uc04-model-methods.csv`; každé volání doslova: `calls/` ve složce běhu."
    )
    return "\n".join(out) + "\n"


def _model_lines_examples(run_dir: Path, config: dict[str, Any], n: int = 3) -> list[str]:
    """Markdown table rows pairing `describe_and_retrieve`'s written lines with the real hidden purchase, first `n` customers per branch."""
    from .data import load_catalog, connect

    rows: list[str] = []
    titles: dict[str, dict[str, Any]] = {}
    db = Path(config["database"]["file"])
    db = db if db.is_absolute() else THESIS_ROOT / db
    if db.exists():
        conn = connect(db)
        try:
            titles = load_catalog(conn)
        finally:
            conn.close()
    for lang in config["languages"]:
        folder = run_dir / "calls" / f"describe_and_retrieve-{lang}-{config['provider']}"
        if not folder.is_dir():
            continue
        for path in sorted(folder.glob("*.json"), key=lambda p: int(p.stem))[:n]:
            call = json.loads(path.read_text(encoding="utf-8"))
            lines = (call.get("parsed") or {}).get("next_purchases") or []
            asin = call.get("held_out", "")
            meta = titles.get(asin, {})
            title = (meta.get("title_cs") if lang == "cs" else None) or meta.get("title") or asin
            rows.append(
                f"| {LANG_CS[lang]} | {path.stem} | {str(title)[:90]} | {' · '.join(s[:90] for s in lines) or '(selhalo)'} |"
            )
    return rows


def build_model_methods(
    *,
    record: dict[str, Path] | None = None,
    run_dirs: list[Path] | None = None,
    out_dir: Path = ATTACHMENTS_DIR,
) -> list[Path]:
    """Write ``uc04-model-methods.{csv,md}`` from one folder per method.

    ``record`` is method -> folder; ``run_dirs`` a list the same rule is applied to
    (``assign_methods``); neither = the newest complete folder of every method.
    """
    out_dir.mkdir(parents=True, exist_ok=True)
    if record is None:
        record = assign_methods(list(run_dirs)) if run_dirs else record_model_runs()
    if not record:
        return []
    folders, rows, _ = model_methods_rows(record)
    csv_path = out_dir / "uc04-model-methods.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=MODEL_FIELDS)
        w.writeheader()
        w.writerows(rows)
    md_path = out_dir / "uc04-model-methods.md"
    md_path.write_text(model_methods_markdown(folders, rows), encoding="utf-8")
    return [csv_path, md_path]


__all__ = [
    "ATTACHMENTS_DIR",
    "MODEL_FIELDS",
    "RUNS_DIR",
    "arena_rows",
    "arms_table_markdown",
    "assign_methods",
    "build",
    "build_model_methods",
    "facts_rows",
    "is_full_run",
    "model_methods_markdown",
    "model_methods_rows",
    "record_model_runs",
    "comparison_model_runs",
    "newest_full_run",
    "run_folders",
    "write_arms_table",
]
