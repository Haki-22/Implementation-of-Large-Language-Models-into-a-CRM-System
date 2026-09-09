"""Data facts behind the arena's numbers, printed by a run of their own.

``python -m ucs.uc04_matchmaker facts [--population]`` measures, from the same
database the arena reads, everything the chapter needs to explain why the hit
rates look the way they do: how sparse the customer x product matrix is, how many
hidden items were bought by nobody else (unreachable for any behavioural method),
how long a purchase history is, how many customers tie on their last day, how much
Czech text is missing, and, with ``--population``, how the same collaborative
filtering scores on ordinary Amazon reviewers so the shop's customers can be placed
against them. The numbers go into a run folder (``facts.json``, ``facts.csv``,
``RESULTS.md``) so that a figure quoted in the thesis always points at the run that
produced it; nothing here is copied from a scratch script.
"""

from __future__ import annotations

import csv
import datetime as _dt
import statistics
import time
from collections import Counter
from pathlib import Path
from typing import Any

import numpy as np

from ucs.uc02_pseudonymization.eval.runs import (
    code_identity,
    format_duration,
    new_run_dir,
    write_card,
    write_json,
)
from utils.paths import SUBSTRATE_DB

from .arena import PACKAGES, RUNS_DIR, database_identity, population_identity
from .data import Arena, connect, load_arena
from .population import Population, load_population
from .protocols import random_floor

Fact = tuple[str, Any, str]  # key, value, what it means


# ---------------------------------------------------------------------------
# Measurements
# ---------------------------------------------------------------------------


def customer_facts(arena: Arena, cs: Arena, db_path: Path) -> list[Fact]:
    """Population, catalogue, sparsity, reachability, ties, history length, Czech coverage."""
    conn = connect(db_path)
    try:
        prospects = conn.execute(
            "SELECT COUNT(*) FROM uc_contacts WHERE reviewer_id IS NULL"
        ).fetchone()[0]
        cz_titles = conn.execute(
            "SELECT COUNT(*) FROM uc_products WHERE name_cs IS NOT NULL AND name_cs <> ''"
        ).fetchone()[0]
    finally:
        conn.close()
    n, m = arena.n_customers, arena.n_items
    interactions = sum(len(c.history) for c in arena.customers)
    buyers: Counter[str] = Counter()
    for c in arena.customers:
        buyers.update(c.history_asins)
    bought = len(buyers)
    single = sum(1 for v in buyers.values() if v == 1)
    others = [buyers.get(c.held_out.asin, 0) for c in arena.customers]
    bucket = Counter(
        "0" if k == 0 else "1" if k == 1 else "2-4" if k <= 4 else "5+" for k in others
    )
    ties = sum(
        1
        for c in arena.customers
        if sum(1 for it in [*c.history, c.held_out] if it.date == c.held_out.date) > 1
    )
    hist_len = [len(c.history) for c in arena.customers]
    title_words = [
        sum(len((arena.catalog.get(it.asin, {}).get("title") or "").split()) for it in c.history)
        for c in arena.customers
    ]
    review_words = [sum(len(it.text.split()) for it in c.history) for c in arena.customers]
    cs_empty = sum(1 for c in cs.customers for it in c.history if not it.text)
    groups = Counter(c.group for c in arena.customers)
    facts: list[Fact] = [
        (
            "customers_linked",
            n,
            "contacts with an Amazon reviewer, i.e. with purchases; the arena's population",
        ),
        (
            "customers_prospects",
            prospects,
            "contacts without a reviewer: no purchases, out of leave-one-out by construction",
        ),
        ("groups", dict(sorted(groups.items())), "stratum sizes A / B / C"),
        ("catalogue_products", m, "products in the shop catalogue = the ranking universe"),
        (
            "catalogue_czech_titles",
            cz_titles,
            "products with a Czech title (the Czech branch reads it)",
        ),
        ("interactions", interactions, "purchases in the histories (hidden items excluded)"),
        (
            "density_percent",
            round(100 * interactions / (n * m), 3),
            "share of the customer x product matrix that is filled",
        ),
        ("products_bought", bought, "products bought by at least one customer in the histories"),
        ("products_single_buyer", single, "of those, bought by exactly one customer"),
        (
            "median_buyers_per_bought_product",
            statistics.median(buyers.values()),
            "median number of customers per bought product",
        ),
        (
            "hidden_bought_by_0_others",
            bucket["0"],
            "hidden items nobody else bought: unreachable for any behavioural method",
        ),
        ("hidden_bought_by_1_other", bucket["1"], "hidden items bought by one other customer"),
        (
            "hidden_bought_by_2_to_4_others",
            bucket["2-4"],
            "hidden items bought by two to four other customers",
        ),
        (
            "hidden_bought_by_5_plus_others",
            bucket["5+"],
            "hidden items bought by five or more other customers",
        ),
        (
            "last_day_ties",
            ties,
            "customers with two or more reviews on their final day (tie broken by review id)",
        ),
        (
            "history_products_median",
            statistics.median(hist_len),
            "median purchases per customer in the history",
        ),
        ("history_products_min", min(hist_len), "shortest history"),
        ("history_products_max", max(hist_len), "longest history"),
        (
            "history_title_words_median",
            statistics.median(title_words),
            "median words if every bought title is written out (a prompt's history block)",
        ),
        ("history_title_words_max", max(title_words), "longest such history in words"),
        (
            "review_words_per_customer_median",
            statistics.median(review_words),
            "median words of English review text per customer",
        ),
        (
            "review_words_per_customer_max",
            max(review_words),
            "most review text a single customer wrote",
        ),
        (
            "czech_history_texts_empty",
            cs_empty,
            "history reviews with no Czech text in the Czech branch (dropped by the May translation run)",
        ),
        (
            "random_floor_full_top10",
            round(random_floor("full", m, 100), 5),
            "hit rate of guessing under the full protocol at top 10",
        ),
        (
            "random_floor_sampled_top10",
            round(random_floor("sampled", m, 100), 4),
            "hit rate of guessing under the sampled protocol (100 negatives) at top 10",
        ),
    ]
    return facts


def population_facts(
    arena: Arena, pop: Population, *, sanity_users: int = 2000, seed: int = 42
) -> list[Fact]:
    """How the shop's customers sit inside the public population, and how ALS scores on ordinary reviewers."""
    from implicit.als import AlternatingLeastSquares

    item_buyers = np.asarray((pop.matrix > 0).sum(axis=0)).ravel()
    others = [
        int(item_buyers[pop.item_index[c.held_out.asin]])
        if c.held_out.asin in pop.item_index
        else 0
        for c in arena.customers
    ]
    bucket = Counter("0" if k == 0 else "1-4" if k < 5 else "5+" for k in others)
    # leave-one-out on ordinary reviewers: hide the last-added interaction of a random sample and retrain
    rng = np.random.default_rng(seed)
    ours = {c.reviewer_id for c in arena.customers}
    rows_by_user = pop.matrix.tolil(copy=False).rows
    eligible = [
        u for uid, u in pop.user_index.items() if uid not in ours and len(rows_by_user[u]) >= 5
    ]
    sample = rng.choice(eligible, size=min(sanity_users, len(eligible)), replace=False)
    hidden = {int(u): pop.last_item[int(u)] for u in sample}  # the last column stored for the user
    mat = pop.matrix.tolil(copy=True)
    for u, j in hidden.items():
        mat[u, j] = 0
    mat = mat.tocsr()
    mat.eliminate_zeros()
    t0 = time.time()
    model = AlternatingLeastSquares(
        factors=64, iterations=20, regularization=0.01, use_gpu=False, random_state=seed
    )
    model.fit(mat, show_progress=False)
    item_f = np.asarray(model.item_factors)
    user_f = np.asarray(model.user_factors)
    hits = 0
    for u, j in hidden.items():
        scores = item_f @ user_f[u]
        scores[mat[u].indices] = -np.inf
        top = np.argpartition(-scores, 10)[:10]
        hits += j in set(top.tolist())
    return [
        (
            "population_users",
            pop.matrix.shape[0],
            "reviewers in the public Amazon Electronics 5-core dump",
        ),
        ("population_items", pop.matrix.shape[1], "products in the dump"),
        ("population_reviews", pop.n_reviews, "reviews in the dump"),
        (
            "hidden_bought_by_0_others_in_population",
            bucket["0"],
            "our hidden items nobody in the population bought",
        ),
        (
            "hidden_bought_by_1_to_4_others_in_population",
            bucket["1-4"],
            "our hidden items bought by one to four other reviewers in the population",
        ),
        (
            "hidden_bought_by_5_plus_others_in_population",
            bucket["5+"],
            "our hidden items bought by five or more other reviewers in the population",
        ),
        (
            "sanity_users",
            len(hidden),
            "random ordinary reviewers (not ours, >= 5 reviews) scored with the population ALS, their chronologically last review hidden, as in the arena",
        ),
        (
            "sanity_hits_top10",
            hits,
            "of them, hidden interaction in the ALS top 10 over the full population catalogue",
        ),
        (
            "sanity_hr10_percent",
            round(100 * hits / max(len(hidden), 1), 2),
            "the population model's hit rate on ordinary reviewers, the yardstick for the shop's heavy buyers",
        ),
        (
            "sanity_seconds",
            round(time.time() - t0, 1),
            "training + scoring time of the sanity check",
        ),
    ]


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------


def run(
    *,
    population: bool = False,
    sanity_users: int = 2000,
    seed: int = 42,
    db_path: Path = SUBSTRATE_DB,
    base_dir: Path = RUNS_DIR,
    label: str | None = None,
    attachments_dir: Path | None = None,
) -> Path:
    """Measure the facts and write them into a run folder; returns its path.

    Refreshes ``<project_root>/attachments/`` afterwards like ``arena.run`` (``attachments_dir`` overrides the target in tests).
    """
    t_start = time.time()
    arena = load_arena("en", db_path)
    cs = load_arena("cs", db_path)
    facts = customer_facts(arena, cs, db_path)
    pop = None
    if population:
        pop = load_population(arena)
        facts += population_facts(arena, pop, sanity_users=sanity_users, seed=seed)
    tag = label or f"data-facts-{arena.n_customers}-customers" + (
        "-population" if population else ""
    )
    run_dir = new_run_dir(tag, base=base_dir)
    payload = {
        "run_dir": run_dir.name,
        "date": _dt.date.today().isoformat(),
        "database": database_identity(arena, db_path),
        "population": population_identity(pop) if pop else None,
        "seed": seed,
        "code": code_identity(PACKAGES),
        "facts": {k: {"value": v, "meaning": d} for k, v, d in facts},
        "total_seconds": round(time.time() - t_start, 1),
    }
    write_json(run_dir / "facts.json", payload)
    with open(run_dir / "facts.csv", "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["key", "value", "meaning"])
        for k, v, d in facts:
            w.writerow([k, v, d])
    header = [
        (
            "Ran on",
            f"`substrate.db` (sha256 {payload['database']['sha256'][:12]}…), {arena.n_customers} linked customers, {arena.n_items} products",
        ),
        (
            "Population",
            f"{pop.matrix.shape[0]} users / {pop.n_reviews} reviews from the pinned dump"
            if pop
            else "not measured (run with --population)",
        ),
        ("When", f"{payload['date']}, {format_duration(payload['total_seconds'])}"),
        ("Model calls", "none"),
    ]
    lines = [(f"{k} = {v}", d) for k, v, d in facts]
    sentence = (
        f"The matrix is {dict(facts)['density_percent'] if False else [v for k, v, _ in facts if k == 'density_percent'][0]} % dense, "
        f"{[v for k, v, _ in facts if k == 'hidden_bought_by_0_others'][0]} of {arena.n_customers} hidden items were bought by nobody else, "
        "so single-digit hit counts against the whole catalogue are a property of the data, not of any method."
    )
    write_card(
        run_dir,
        title=f"UC-04 data facts — {run_dir.name}",
        header=header,
        blocks=[{"name": "facts", "lines": lines}],
        sentence=sentence,
    )
    _append_readme(run_dir, population)

    _write_facts_attachment(run_dir, attachments_dir)
    return run_dir


def _write_facts_attachment(run_dir: Path, attachments_dir: Path | None) -> list[Path]:
    """Rewrite ``uc04-data-facts.{csv,md}`` from this facts run; the arena attachment is left as it is."""
    from . import attachment

    out = attachments_dir or attachment.ATTACHMENTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    payload, rows = attachment.facts_rows(run_dir)
    fcsv = out / "uc04-data-facts.csv"
    with open(fcsv, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=["run", "key", "value", "meaning"])
        w.writeheader()
        w.writerows(rows)
    fmd = out / "uc04-data-facts.md"
    fmd.write_text(attachment.facts_markdown(payload, rows, run_dir), encoding="utf-8")
    return [fcsv, fmd]


def _append_readme(run_dir: Path, population: bool) -> None:
    """Append one summary line for `run_dir` to `README.md` in the runs folder, creating it if needed."""
    readme = run_dir.parent / "README.md"
    if not readme.exists():
        readme.write_text(
            "# UC-04 run folders\n\nOne line per folder; each folder is the provenance of the numbers it holds and is never edited.\n\n",
            encoding="utf-8",
        )
    with open(readme, "a", encoding="utf-8") as fh:
        fh.write(
            f"- `{run_dir.name}` — data facts behind the arena numbers{' incl. the population sanity check' if population else ''}; no model calls.\n"
        )


__all__ = ["customer_facts", "population_facts", "run"]
