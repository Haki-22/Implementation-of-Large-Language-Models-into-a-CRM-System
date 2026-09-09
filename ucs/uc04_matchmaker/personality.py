"""Does a Big Five profile help a classical recommender? The paired personality-feature comparison of UC-04.

Chapter 9.1 promised that UC-04 compares a personality profile derived from behaviour
with a purely synthetic one. The feature arms dropped the profile on 2026-09-06 because
an inferred one existed for 62 customers only; since the same evening every linked
customer carries a profile inferred from their English reviews, and 271 of them also
carry the generator's sampled profile, so the comparison can be measured. This module
runs the two feature arms (LightGBM, linear SVM) in three variants on the same
customers, the same candidate lists and the same seeds:

* ``none`` -- the recorded arms, no personality columns;
* ``inferred`` -- five columns from the model-inferred profile (``uc_contacts.ocean``
  where ``ocean_source = 'inferred'``);
* ``sampled`` -- the same columns from the generator's sampled profile
  (``substrate/snapshots/ocean/ocean_synthetic_500.json``); a customer without one gets
  the missing value (NaN for LightGBM, the scale midpoint for the SVM).

Evaluation is paired: per customer, whether the hidden item sits in the top 10 under
each variant. The card reports the hits per variant, the discordant pairs (a hit under
one variant only) and the two-sided sign test on them; pairs that involve the sampled
profile are counted on the customers who have both profiles. LightGBM moves by a few
hits between runs even with pinned threads (measured 2026-09-06), so a difference of
that size is noise, which the card says. For the linear SVM the columns cannot change
anything by construction: a customer-level feature adds the same term to every product
of that customer, so the ranking inside a customer is unchanged and the discordant count
is zero; only a model with interactions (the trees) can use a personality column at all,
which the card states rather than leaving the reader to think the SVM ignored it.

Run (no model calls; a few minutes of CPU):
    python -m ucs.uc04_matchmaker personality
"""

from __future__ import annotations

import csv
import datetime as _dt
import json
import logging
import time
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.eval.runs import (
    code_identity,
    format_duration,
    new_run_dir,
    write_card,
    write_json,
)
from utils.paths import OCEAN_SYNTHETIC_SNAPSHOT, SUBSTRATE_DB

from . import arms as arm_registry
from .arena import PACKAGES, RUNS_DIR, database_identity
from .arms._features import TRAITS
from .data import Arena, connect, load_arena
from .protocols import (
    Result,
    evaluate_full,
    evaluate_sampled,
    random_floor,
    sample_candidates,
)

logger = logging.getLogger(__name__)

VARIANTS = ("none", "inferred", "sampled")
FEATURE_ARMS = ("lightgbm_features", "svm_features")
PAIRS = (("inferred", "none"), ("sampled", "none"), ("inferred", "sampled"))
TOP_K = 10
VARIANT_CS = {
    "none": "bez profilu",
    "inferred": "odvozený profil",
    "sampled": "vzorkovaný profil",
}
PROTOCOL_CS = {"full": "úplný katalog", "sampled": "vzorkovaný (1 + 100)"}
LANG_CS = {"en": "anglická větev", "cs": "česká větev"}


# ---------------------------------------------------------------------------
# The two profile sources
# ---------------------------------------------------------------------------


def load_profiles(
    db_path: Path = SUBSTRATE_DB, synthetic_path: Path = OCEAN_SYNTHETIC_SNAPSHOT
) -> dict[str, dict[int, dict[str, float]]]:
    """Contact id -> Big Five profile, for ``inferred`` (the database) and ``sampled`` (the generator's snapshot)."""
    inferred: dict[int, dict[str, float]] = {}
    conn = connect(db_path)
    try:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(uc_contacts)")}
        if {"ocean", "ocean_source"} <= columns:
            for row in conn.execute(
                "SELECT id, ocean FROM uc_contacts WHERE ocean_source = 'inferred' AND ocean IS NOT NULL"
            ):
                profile = row["ocean"]
                if isinstance(profile, str):
                    profile = json.loads(profile)
                inferred[int(row["id"])] = {t: float(profile[t]) for t in TRAITS}
    finally:
        conn.close()
    sampled: dict[int, dict[str, float]] = {}
    if Path(synthetic_path).exists():
        payload = json.loads(Path(synthetic_path).read_text(encoding="utf-8"))
        for row in payload.get("rows", []):
            if row.get("ocean"):
                sampled[int(row["contact_id"])] = {t: float(row["ocean"][t]) for t in TRAITS}
    return {"inferred": inferred, "sampled": sampled}


# ---------------------------------------------------------------------------
# Paired comparison
# ---------------------------------------------------------------------------


def _hit(row: dict[str, Any], k: int = TOP_K) -> bool:
    """Whether a `per_customer` row's hidden item landed in the top `k`."""
    return row["rank"] is not None and row["rank"] <= k


def paired(
    first: list[dict[str, Any]], second: list[dict[str, Any]], subset: set[int] | None = None
) -> dict[str, Any]:
    """Hits of two variants on the same customers, the discordant pairs and the two-sided sign test.

    ``first`` and ``second`` are the ``per_customer`` lists of two results in the same
    customer order; ``subset`` restricts the pairing to those contact ids.
    """
    from scipy.stats import binomtest

    n = hits_a = hits_b = only_a = only_b = 0
    for a, b in zip(first, second, strict=True):
        if a["contact_id"] != b["contact_id"]:
            raise ValueError("per-customer lists are not aligned")
        if subset is not None and a["contact_id"] not in subset:
            continue
        n += 1
        ha, hb = _hit(a), _hit(b)
        hits_a += ha
        hits_b += hb
        only_a += ha and not hb
        only_b += hb and not ha
    discordant = only_a + only_b
    p_value = binomtest(only_a, discordant, 0.5).pvalue if discordant else 1.0
    return {
        "n": n,
        "hits_first": hits_a,
        "hits_second": hits_b,
        "difference": hits_a - hits_b,
        "only_first": only_a,
        "only_second": only_b,
        "p_sign": round(float(p_value), 3),
    }


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def _tag(arm_names: list[str], langs: list[str], n_customers: int) -> str:
    """Default run-folder label summarising the arm count, languages and customer count."""
    return f"personality-feature-{len(arm_names)}-arms-3-variants-{'-'.join(langs)}-{n_customers}-customers"


def run(
    *,
    arms: tuple[str, ...] | list[str] = FEATURE_ARMS,
    langs: tuple[str, ...] | list[str] = ("en", "cs"),
    protocols: tuple[str, ...] | list[str] = ("full", "sampled"),
    n_neg: int = 100,
    seed: int = 42,
    db_path: Path = SUBSTRATE_DB,
    synthetic_path: Path = OCEAN_SYNTHETIC_SNAPSHOT,
    base_dir: Path = RUNS_DIR,
    label: str | None = None,
    attachments_dir: Path | None = None,
) -> Path:
    """Run the feature arms in the three variants, pair them, write the run folder and the attachment; returns the folder."""
    arm_names = list(arms)
    for name in arm_names:
        if name not in FEATURE_ARMS:
            raise ValueError(f"{name} is not a feature arm; known: {FEATURE_ARMS}")
    langs, protocols = list(langs), list(protocols)
    t_start = time.time()
    arenas = {lang: load_arena(lang, db_path) for lang in langs}
    first = arenas[langs[0]]
    profiles = load_profiles(db_path, synthetic_path)
    customers = {c.contact_id for c in first.customers}
    coverage = {v: len(customers & set(profiles[v])) for v in ("inferred", "sampled")}
    candidates = (
        {lang: sample_candidates(a, n_neg=n_neg, seed=seed) for lang, a in arenas.items()}
        if "sampled" in protocols
        else {}
    )
    run_dir = new_run_dir(label or _tag(arm_names, langs, first.n_customers), base=base_dir)
    (run_dir / "scores").mkdir()

    config: dict[str, Any] = {
        "run_dir": run_dir.name,
        "date": _dt.date.today().isoformat(),
        "arms": {
            n: {
                "title": arm_registry.ARMS[n].TITLE,
                "description": arm_registry.ARMS[n].DESCRIPTION,
            }
            for n in arm_names
        },
        "variants": {
            "none": "no personality columns (the recorded arms)",
            "inferred": f"five columns from the model-inferred profile; {coverage['inferred']} of {first.n_customers} customers",
            "sampled": f"five columns from the generator's sampled profile; {coverage['sampled']} of {first.n_customers} customers, the rest missing",
        },
        "missing_value": "NaN for LightGBM (native handling), the scale midpoint 3.0 for the SVM",
        "pairing": "per customer, hit = hidden item in the top 10; pairs with the sampled profile are counted on the customers who have both profiles",
        "languages": langs,
        "protocols": protocols,
        "sampled_negatives": n_neg,
        "seed": seed,
        "database": database_identity(first, db_path),
        "synthetic_profiles": str(synthetic_path.name),
        "code": code_identity(PACKAGES),
    }
    write_json(run_dir / "config.json", config)

    results: dict[str, dict[str, Any]] = {}
    detail: dict[str, dict[str, list[dict[str, Any]]]] = {}
    for name in arm_names:
        module = arm_registry.ARMS[name]
        for variant in VARIANTS:
            mapping = None if variant == "none" else profiles[variant]
            for lang in langs:
                arena = arenas[lang]
                key = f"{name}-{variant}-{lang}"
                logger.info("=== %s ===", key)
                t0 = time.time()
                scores = module.score(arena, personality=mapping)
                entry: dict[str, Any] = {
                    "arm": name,
                    "variant": variant,
                    "lang": lang,
                    "wall_seconds": round(time.time() - t0, 1),
                    "protocols": {},
                }
                per_customer: dict[str, list[dict[str, Any]]] = {}
                if "full" in protocols:
                    full: Result = evaluate_full(scores, arena, seed=seed)
                    entry["protocols"]["full"] = full.as_dict()
                    per_customer["full"] = full.per_customer
                if "sampled" in protocols:
                    sampled: Result = evaluate_sampled(scores, arena, candidates[lang], seed=seed)
                    entry["protocols"]["sampled"] = sampled.as_dict()
                    per_customer["sampled"] = sampled.per_customer
                results[key] = entry
                detail[key] = per_customer
                write_json(
                    run_dir / "scores" / f"{key}.json", {**entry, "per_customer": per_customer}
                )

    both = customers & set(profiles["inferred"]) & set(profiles["sampled"])
    pairs: list[dict[str, Any]] = []
    for name in arm_names:
        for lang in langs:
            for protocol in protocols:
                for first_v, second_v in PAIRS:
                    subset = both if "sampled" in (first_v, second_v) else None
                    stats = paired(
                        detail[f"{name}-{first_v}-{lang}"][protocol],
                        detail[f"{name}-{second_v}-{lang}"][protocol],
                        subset,
                    )
                    pairs.append(
                        {
                            "arm": name,
                            "lang": lang,
                            "protocol": protocol,
                            "first": first_v,
                            "second": second_v,
                            **stats,
                        }
                    )
    write_json(run_dir / "pairs.json", pairs)
    config["total_seconds"] = round(time.time() - t_start, 1)
    write_json(run_dir / "config.json", config)

    _write_table(run_dir, config, results, pairs, first)
    _write_card(run_dir, config, results, pairs, first)
    _append_readme(run_dir, config)
    _write_attachment(run_dir, config, results, pairs, first, attachments_dir)
    return run_dir


# ---------------------------------------------------------------------------
# Tables, card, attachment
# ---------------------------------------------------------------------------


def _hits(entry: dict[str, Any], protocol: str) -> tuple[int, tuple[float, float]]:
    """`(hits@TOP_K, Wilson 95% CI)` for one arm/variant/lang result entry under `protocol`."""
    block = entry["protocols"][protocol]
    return int(block["hits"][str(TOP_K)]), tuple(block["wilson95_hr10"])


def _pair_line(p: dict[str, Any]) -> str:
    """One-line paired-comparison summary (hits, difference, discordant counts, sign-test p) for the results card."""
    return (
        f"{p['first']} vs {p['second']}, {p['lang']}, {p['protocol']}: {p['hits_first']} vs {p['hits_second']} "
        f"({p['difference']:+d}) on {p['n']}; only {p['first']} {p['only_first']}, only {p['second']} {p['only_second']}; sign p {p['p_sign']}"
    )


def _write_table(
    run_dir: Path,
    config: dict[str, Any],
    results: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    arena: Arena,
) -> None:
    """Write `TABLE.md`: per-arm/protocol hit tables across the three variants, plus the paired-difference table."""
    lines = [f"# Personality feature: {run_dir.name}", ""]
    for name in config["arms"]:
        for protocol in config["protocols"]:
            floor = random_floor(protocol, arena.n_items, config["sampled_negatives"])
            lines += [
                f"## {config['arms'][name]['title']}, protocol {protocol} (hits in the top {TOP_K} of {arena.n_customers}; guessing {floor * arena.n_customers:.1f})",
                "",
                "| variant | "
                + " | ".join(f"{lang} hits (95 % CI of HR@10)" for lang in config["languages"])
                + " |",
                "| --- | " + " | ".join("---" for _ in config["languages"]) + " |",
            ]
            for variant in VARIANTS:
                cells = []
                for lang in config["languages"]:
                    hits, ci = _hits(results[f"{name}-{variant}-{lang}"], protocol)
                    cells.append(f"{hits} ({ci[0] * 100:.1f}–{ci[1] * 100:.1f} %)")
                lines.append(f"| {variant} | " + " | ".join(cells) + " |")
            lines.append("")
    lines += [
        "## Paired differences (hit = hidden item in the top 10 under a variant)",
        "",
        "| arm | branch | protocol | pair | n | hits | difference | discordant (first / second) | sign test p |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in pairs:
        lines.append(
            f"| {p['arm']} | {p['lang']} | {p['protocol']} | {p['first']} vs {p['second']} | {p['n']} | "
            f"{p['hits_first']} vs {p['hits_second']} | {p['difference']:+d} | {p['only_first']} / {p['only_second']} | {p['p_sign']} |"
        )
    lines.append("")
    (run_dir / "TABLE.md").write_text("\n".join(lines), encoding="utf-8")


def _write_card(
    run_dir: Path,
    config: dict[str, Any],
    results: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    arena: Arena,
) -> None:
    """Write `RESULTS.md`: header facts, per-arm variant/pair blocks and a closing sentence naming the largest paired difference."""
    header = [
        (
            "Ran on",
            f"`substrate.db` (sha256 {config['database']['sha256'][:12]}…), {arena.n_customers} linked customers, {arena.n_items} products",
        ),
        ("When", f"{config['date']}, {format_duration(config['total_seconds'])}"),
        ("Model calls", "none"),
        ("Variants", "; ".join(f"{k} = {v}" for k, v in config["variants"].items())),
        ("Missing profile", config["missing_value"]),
        (
            "Protocols",
            f"{', '.join(config['protocols'])}; sampled negatives {config['sampled_negatives']}; seed {config['seed']}",
        ),
    ]
    blocks = []
    for name in config["arms"]:
        lines = []
        for protocol in config["protocols"]:
            for lang in config["languages"]:
                cells = ", ".join(
                    f"{variant} {_hits(results[f'{name}-{variant}-{lang}'], protocol)[0]}"
                    for variant in VARIANTS
                )
                lines.append(
                    (
                        f"{protocol}, {lang}: {cells}",
                        f"hits in the top {TOP_K} of {arena.n_customers}",
                    )
                )
        for p in pairs:
            if p["arm"] == name:
                lines.append((_pair_line(p), "paired on the same customers and candidate lists"))
        if name == "svm_features":
            lines.append(
                (
                    "identical rankings by construction",
                    "a linear model adds the same term to every product of a customer for a customer-level column, so the order inside a customer cannot change; zero discordant pairs is the expected outcome and the check that the pairing works",
                )
            )
        blocks.append({"name": config["arms"][name]["title"], "lines": lines})
    biggest = max(pairs, key=lambda p: abs(p["difference"])) if pairs else None
    significant = [p for p in pairs if p["p_sign"] < 0.05]
    sentence = (
        f"The largest paired difference is {biggest['difference']:+d} hits of {biggest['n']} "
        f"({biggest['arm']}, {biggest['first']} vs {biggest['second']}, {biggest['lang']}, {biggest['protocol']}); "
        + (
            f"{len(significant)} of {len(pairs)} pairs pass the sign test at 5 %."
            if significant
            else "no pair passes the sign test at 5 %, so on this data a Big Five profile, inferred or sampled, adds nothing measurable to a classical recommender."
        )
        + " LightGBM moves by a few hits between runs even with pinned threads, so differences of that size are noise; the linear SVM cannot react to a customer-level column at all (identical rankings by construction)."
        if biggest
        else "No pairs."
    )
    write_card(
        run_dir,
        title=f"UC-04 personality feature — {run_dir.name}",
        header=header,
        blocks=blocks,
        sentence=sentence,
    )


def _append_readme(run_dir: Path, config: dict[str, Any]) -> None:
    """Append one summary line for `run_dir` to `README.md` in the runs folder, creating it if needed."""
    readme = run_dir.parent / "README.md"
    if not readme.exists():
        readme.write_text(
            "# UC-04 run folders\n\nOne line per folder; each folder is the provenance of the numbers it holds and is never edited.\n\n",
            encoding="utf-8",
        )
    with open(readme, "a", encoding="utf-8") as fh:
        fh.write(
            f"- `{run_dir.name}` — the personality-feature comparison: {len(config['arms'])} feature arms × 3 variants (none / inferred / sampled), "
            f"languages {'+'.join(config['languages'])}, protocols {'+'.join(config['protocols'])}, paired sign tests; no model calls.\n"
        )


def _write_attachment(
    run_dir: Path,
    config: dict[str, Any],
    results: dict[str, dict[str, Any]],
    pairs: list[dict[str, Any]],
    arena: Arena,
    attachments_dir: Path | None,
) -> list[Path]:
    """Rewrite ``<project_root>/attachments/uc04-personality-feature.{csv,md}`` from this run (the Příloha A pattern)."""
    from .attachment import ATTACHMENTS_DIR

    out = attachments_dir or ATTACHMENTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for key, entry in results.items():
        for protocol in config["protocols"]:
            hits, ci = _hits(entry, protocol)
            rows.append(
                {
                    "kind": "variant",
                    "run": run_dir.name,
                    "arm": entry["arm"],
                    "variant": entry["variant"],
                    "branch": entry["lang"],
                    "protocol": protocol,
                    "customers": arena.n_customers,
                    "hits_top10": hits,
                    "hr_top10": round(hits / arena.n_customers, 4),
                    "ci95_low": round(ci[0], 4),
                    "ci95_high": round(ci[1], 4),
                }
            )
    for p in pairs:
        rows.append(
            {
                "kind": "pair",
                "run": run_dir.name,
                "arm": p["arm"],
                "variant": f"{p['first']} vs {p['second']}",
                "branch": p["lang"],
                "protocol": p["protocol"],
                "customers": p["n"],
                "hits_top10": f"{p['hits_first']} vs {p['hits_second']}",
                "difference": p["difference"],
                "only_first": p["only_first"],
                "only_second": p["only_second"],
                "p_sign": p["p_sign"],
            }
        )
    fields = [
        "kind",
        "run",
        "arm",
        "variant",
        "branch",
        "protocol",
        "customers",
        "hits_top10",
        "hr_top10",
        "ci95_low",
        "ci95_high",
        "difference",
        "only_first",
        "only_second",
        "p_sign",
    ]
    csv_path = out / "uc04-personality-feature.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)

    lines = [
        "# Sloupec osobnosti v klasickém rameni UC-04 (příloha, generováno)",
        "",
        f"Vygenerováno ze složky běhu `ucs/uc04_matchmaker/eval/runs/{run_dir.name}/` (běh ze dne {config['date']}, "
        f"databáze `substrate.db`, sha256 {config['database']['sha256'][:12]}…). Bez volání jazykového modelu. "
        "Tři varianty téhož ramene na týchž zákaznících, kandidátních listinách a seedech: bez profilu, "
        f"s odvozeným profilem ({config['variants']['inferred'].split(';')[1].strip()}), se vzorkovaným profilem "
        f"({config['variants']['sampled'].split(';')[1].strip()}). Chybějící profil: {config['missing_value']}. "
        "U lineárního SVM se pořadí uvnitř zákazníka změnit nemůže: sloupec na úrovni zákazníka přičte "
        "každému jeho produktu tentýž člen, takže nula diskordantních párů je očekávaný výsledek a zároveň "
        "kontrola párování; sloupec osobnosti může využít jen model s interakcemi (stromy).",
        "",
    ]
    t = 0
    for name in config["arms"]:
        for protocol in config["protocols"]:
            t += 1
            lines += [
                f"Tabulka {t} – {config['arms'][name]['title']}, {PROTOCOL_CS[protocol]}: zásahy v top {TOP_K} z {arena.n_customers} zákazníků podle varianty",
                "",
                "| varianta | " + " | ".join(LANG_CS[lang] for lang in config["languages"]) + " |",
                "| --- | " + " | ".join("---" for _ in config["languages"]) + " |",
            ]
            for variant in VARIANTS:
                cells = []
                for lang in config["languages"]:
                    hits, ci = _hits(results[f"{name}-{variant}-{lang}"], protocol)
                    cells.append(f"{hits} ({ci[0] * 100:.1f} až {ci[1] * 100:.1f} %)")
                lines.append(f"| {VARIANT_CS[variant]} | " + " | ".join(cells) + " |")
            lines.append("")
    t += 1
    lines += [
        f"Tabulka {t} – Párové rozdíly (zásah = skrytý produkt v top {TOP_K}; diskordantní páry a znaménkový test)",
        "",
        "| rameno | větev | protokol | dvojice | n | zásahy | rozdíl | jen první / jen druhá | p |",
        "| --- | --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for p in pairs:
        lines.append(
            f"| `{p['arm']}` | {LANG_CS[p['lang']]} | {PROTOCOL_CS[p['protocol']]} | {VARIANT_CS[p['first']]} vs {VARIANT_CS[p['second']]} | {p['n']} | "
            f"{p['hits_first']} vs {p['hits_second']} | {p['difference']:+d} | {p['only_first']} / {p['only_second']} | {p['p_sign']} |"
        )
    lines.append("")
    md_path = out / "uc04-personality-feature.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [csv_path, md_path]


__all__ = ["FEATURE_ARMS", "PAIRS", "VARIANTS", "load_profiles", "paired", "run"]
