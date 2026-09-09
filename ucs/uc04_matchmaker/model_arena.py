"""The run of the model methods: sample × branches × methods with one provider into one run folder.

``run()`` loads the fixed sample (``eval/samples/``), both language arenas from
``substrate.db``, the seeded ALS and popularity scores the methods build on and
compare against, then asks every requested method for its score matrix over its
customers (the sample of 100, or the customers whose hidden item ALS placed within its
top 200) and applies the protocols the method declares (``protocols.py``, unchanged
from the classical arena). The folder under ``eval/runs/<date>-model-methods-…/``
holds ``config.json`` (methods, prompt version and full prompt texts, schemas, sample,
branches, seed, provider with its resolved model, tier and CLI version, database and
package identity, which profile fields each customer had, the reachable customers),
``sample.json`` (a copy), ``calls/<method>-<lang>-<provider>/<contact_id>.json``
(every call verbatim), ``scores/<method>-<lang>.json`` and
``scores/reference-<arm>-<subset>.json`` (numbers plus per-customer ranks; the
references are ALS and popularity scored on exactly the same customers and candidate
lists), ``pairs.json`` (per-customer paired differences with the sign test),
``TABLE.md`` and ``RESULTS.md``. A run over every method and the whole sample with a
real provider rewrites ``<project_root>/attachments/uc04-model-methods.{csv,md}`` and
``uc04-arms.md``; a smoke (``--limit``) or a mock run keeps its own tables only.
Nothing is called without ``--force-llm`` (the adapters fail closed); ``--reuse
<run>`` takes over identical calls from an earlier folder instead of paying again.
"""

from __future__ import annotations

import asyncio
import datetime as _dt
import json
import logging
import statistics
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
from utils.generation import cli_version, resolve_model, resolve_tier
from utils.paths import SUBSTRATE_DB, UC04_SAMPLES_DIR

from .arena import PACKAGES, RUNS_DIR, database_identity
from .arms import als_cf, popularity
from .arms import model as model_registry
from .arms.model import _prompts
from .arms.model._calls import CONCURRENCY, Inputs, MethodOutput, subset_arena
from .data import Arena, load_arena
from .outputs_for_uc01.calls import Provider
from .personality import paired
from .protocols import (
    Result,
    evaluate_full,
    evaluate_sampled,
    random_floor,
    sample_candidates,
)
from .sample import DEFAULT_SAMPLE, load_sample

logger = logging.getLogger(__name__)

REFERENCE_ARMS = {"als_cf": als_cf, "popularity": popularity}
# What each method is paired against, per protocol: a reference arm on the same customers
# and candidate lists, or another model method of the same run and branch (design §7).
PAIRS: dict[str, list[tuple[str, str]]] = {
    "rank_candidates": [("als_cf", "sampled"), ("popularity", "sampled")],
    "describe_and_retrieve": [
        ("als_cf", "full"),
        ("popularity", "full"),
        ("als_cf", "sampled"),
        ("popularity", "sampled"),
    ],
    "rerank_als": [("als_cf", "sampled")],
    "rerank_als_with_profile": [("als_cf", "sampled"), ("rerank_als", "sampled")],
    "rerank_als_top200": [("als_cf", "full")],
}


# ---------------------------------------------------------------------------
# Running
# ---------------------------------------------------------------------------


def _tag(names: list[str], prov: Provider, langs: list[str], n: int) -> str:
    """Default run-folder label summarising the method count, provider/model/tier, languages and customer count."""
    return (
        f"model-methods-{len(names)}-methods-{prov.name}-{prov.resolved_model}-"
        f"{prov.resolved_tier or 'notier'}-{'-'.join(langs)}-{n}-customers"
    )


def _entry(output: MethodOutput, protocols: tuple[str, ...], seed: int) -> tuple[dict, dict]:
    """The numbers of one method × branch under its protocols, and the per-customer detail."""
    entry: dict[str, Any] = {"protocols": {}, "calls": output.call_counts()}
    seconds = [c.seconds for c in output.calls if not c.reused_from]
    entry["median_call_seconds"] = round(statistics.median(seconds), 1) if seconds else None
    detail: dict[str, Any] = {}
    for proto in protocols:
        if proto == "full":
            res = evaluate_full(output.scores, output.arena, seed=seed)
        else:
            if output.candidates is None:
                raise ValueError("the sampled protocol needs the candidate lists")
            res = evaluate_sampled(output.scores, output.arena, output.candidates, seed=seed)
        entry["protocols"][proto] = res.as_dict()
        detail[proto] = res.per_customer
    return entry, detail


def _reference(
    arm: str, scores_all, arena_all: Arena, ids: list[int], *, n_neg: int, seed: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    """ALS or popularity scored on ``ids`` only, under both protocols, on the same candidate lists."""
    sub = subset_arena(arena_all, ids)
    rows = [
        next(u for u, c in enumerate(arena_all.customers) if c.contact_id == cid) for cid in ids
    ]
    scores = scores_all[rows]
    full: Result = evaluate_full(scores, sub, seed=seed)
    sampled: Result = evaluate_sampled(
        scores, sub, sample_candidates(sub, n_neg=n_neg, seed=seed), seed=seed
    )
    entry = {
        "arm": arm,
        "customers": ids,
        "protocols": {"full": full.as_dict(), "sampled": sampled.as_dict()},
    }
    return entry, {"full": full.per_customer, "sampled": sampled.per_customer}


def run(
    *,
    methods: str | list[str] = "all",
    sample_name: str = DEFAULT_SAMPLE,
    langs: list[str] = ("en", "cs"),
    provider: str = "agy",
    model: str | None = None,
    tier: str | None = None,
    limit: int | None = None,
    reuse: Path | None = None,
    concurrency: int = CONCURRENCY,
    n_neg: int = 100,
    seed: int = 42,
    db_path: Path = SUBSTRATE_DB,
    base_dir: Path = RUNS_DIR,
    samples_dir: Path = UC04_SAMPLES_DIR,
    label: str | None = None,
    attachments_dir: Path | None = None,
    role: str = "record",
) -> Path:
    """Run the requested model methods with one provider into a new run folder; returns the folder."""
    if role not in RUN_ROLES:
        raise ValueError(f"role must be one of {RUN_ROLES}, got {role!r}")
    names = model_registry.resolve(methods) if isinstance(methods, str) else list(methods)
    langs = list(langs)
    t_start = time.time()
    sample = load_sample(sample_name, samples_dir)
    target_ids = list(sample["contact_ids"])
    if limit is not None:
        target_ids = target_ids[:limit]
    arenas = {lang: load_arena(lang, db_path) for lang in langs}
    if "en" not in arenas:
        arenas["en"] = load_arena("en", db_path)  # the classical scores are language-agnostic
    en = arenas["en"]
    logger.info(
        "fitting the classical references (ALS, popularity) on %d customers", en.n_customers
    )
    als_scores = als_cf.score(en)
    pop_scores = popularity.score(en)
    prov = Provider(
        provider, model, tier, resolve_model(provider, model), resolve_tier(provider, tier, model)
    )
    run_dir = new_run_dir(label or _tag(names, prov, langs, len(target_ids)), base=base_dir)
    (run_dir / "scores").mkdir()
    db_identity = database_identity(en, db_path)
    inputs = Inputs(
        arenas=arenas,
        target_ids=target_ids,
        als_scores=als_scores,
        pop_scores=pop_scores,
        provider=prov,
        run_dir=run_dir,
        n_neg=n_neg,
        seed=seed,
        concurrency=concurrency,
        reuse_dir=Path(reuse) if reuse else None,
        db_sha256=db_identity["sha256"],
        db_path=db_path,
        provider_cli_version=cli_version(provider),
        limit=limit,
    )
    config: dict[str, Any] = {
        "run_dir": run_dir.name,
        "date": _dt.date.today().isoformat(),
        "methods": {
            n: {
                "title": model_registry.MODEL_ARMS[n].TITLE,
                "description": model_registry.MODEL_ARMS[n].DESCRIPTION,
                "family": model_registry.MODEL_ARMS[n].FAMILY,
                "ml_input": model_registry.MODEL_ARMS[n].ML_INPUT,
                "protocols": list(model_registry.MODEL_ARMS[n].PROTOCOLS),
                "subset": model_registry.MODEL_ARMS[n].SUBSET,
            }
            for n in names
        },
        "sample": {
            "name": sample["name"],
            "rule": sample["rule"],
            "seed": sample.get("seed"),
            "customers": target_ids,
            "limit": limit,
        },
        "limit": limit,
        "languages": langs,
        "czech_branch": (
            "Czech instruction and Czech product titles (16 067 of 18 213; English title "
            "otherwise); persona and aspects in the profile are Czech in both branches (D-UC04-D, "
            "design §8.1)"
        ),
        "sampled_negatives": n_neg,
        "seed": seed,
        "candidate_shuffle": "numpy default_rng([seed, contact_id, 7]) per customer (method 1)",
        "title_chars": _prompts.TITLE_CHARS,
        "provider": provider,
        "model": prov.resolved_model,
        "tier": prov.resolved_tier,
        "provider_cli_version": inputs.provider_cli_version,
        "concurrency": concurrency,
        "reuse": Path(reuse).name if reuse else None,
        "role": role,
        "prompt_version": _prompts.PROMPT_VERSION,
        "prompts": {
            "ranking_system": _prompts.RANKING_SYSTEM,
            "als_order_addendum": _prompts.ALS_ORDER_ADDENDUM,
            "profile_addendum": _prompts.PROFILE_ADDENDUM,
            "describe_system": _prompts.DESCRIBE_SYSTEM,
            "no_tools": _prompts.NO_TOOLS,
        },
        "schemas": {
            "ranking": _prompts.ranking_schema(n_neg + 1),
            "ranking_top200": _prompts.ranking_schema(200),
            "describe": _prompts.DESCRIBE_SCHEMA,
        },
        "database": db_identity,
        "code": code_identity(PACKAGES),
    }
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "sample.json", sample)

    details: dict[str, dict[str, Any]] = {}  # "<method>-<lang>" -> protocol -> per_customer
    subsets: dict[str, list[int]] = {"sample": target_ids}
    for name in names:
        module = model_registry.MODEL_ARMS[name]
        for lang in langs:
            key = f"{name}-{lang}"
            logger.info("=== %s ===", key)
            t0 = time.time()
            output = asyncio.run(module.score(inputs, lang))
            wall = time.time() - t0
            entry, detail = _entry(output, module.PROTOCOLS, seed)
            entry.update(
                {
                    "method": name,
                    "lang": lang,
                    "customers": [c.contact_id for c in output.arena.customers],
                    "wall_seconds": round(wall, 1),
                    "extras": output.extras,
                }
            )
            if module.SUBSET == "reachable":
                subsets["reachable"] = [c.contact_id for c in output.arena.customers]
            details[key] = detail
            write_json(run_dir / "scores" / f"{key}.json", {**entry, "per_customer": detail})
            logger.info(
                "  %s: %s · calls %s  (%s)",
                key,
                _oneline(entry),
                entry["calls"],
                format_duration(wall),
            )
            for field in ("profile_fields", "ocean_sources", "reachable", "hidden_position_in_als"):
                if field in output.extras:
                    config["methods"][name].setdefault("extras", {})[field] = output.extras[field]
    for subset, ids in subsets.items():
        if not ids:
            continue
        for arm, module in REFERENCE_ARMS.items():
            scores_all = als_scores if arm == "als_cf" else pop_scores
            entry, detail = _reference(arm, scores_all, en, ids, n_neg=n_neg, seed=seed)
            details[f"reference-{arm}-{subset}"] = detail
            write_json(
                run_dir / "scores" / f"reference-{arm}-{subset}.json",
                {**entry, "subset": subset, "per_customer": detail},
            )
    pairs = _pairs(names, langs, details)
    write_json(run_dir / "pairs.json", pairs)
    config["total_seconds"] = round(time.time() - t_start, 1)
    write_json(run_dir / "config.json", config)
    report(run_dir)
    if provider != "mock":
        _append_runs_readme(run_dir, config)
        refresh_attachments(run_dir, attachments_dir)
    return run_dir


def _pairs(names: list[str], langs: list[str], details: dict[str, dict[str, Any]]) -> list[dict]:
    """Per-customer paired comparisons of every method against its `PAIRS` opponents, one entry per method x lang x protocol x opponent."""
    out: list[dict[str, Any]] = []
    for name in names:
        subset = model_registry.MODEL_ARMS[name].SUBSET
        for lang in langs:
            for versus, proto in PAIRS.get(name, []):
                first = details.get(f"{name}-{lang}", {}).get(proto)
                if versus in REFERENCE_ARMS:
                    second = details.get(f"reference-{versus}-{subset}", {}).get(proto)
                else:
                    second = details.get(f"{versus}-{lang}", {}).get(proto)
                if not first or not second:
                    continue
                out.append(
                    {
                        "method": name,
                        "lang": lang,
                        "protocol": proto,
                        "versus": versus,
                        **paired(first, second),
                    }
                )
    return out


def _oneline(entry: dict[str, Any]) -> str:
    """One `hits@10` summary per protocol in `entry`, joined for a log line."""
    return " · ".join(
        f"{proto} hits@10 {res['hits']['10']}/{res['n_customers']}"
        for proto, res in entry.get("protocols", {}).items()
    )


RUN_ROLES: tuple[str, ...] = ("record", "comparison")


def is_record_run(config: dict[str, Any]) -> bool:
    """The whole sample with a real provider, launched as a record: the folder may stand as the run of record of its methods.

    A run launched with ``--role comparison`` (the same method on a second provider, on
    identical inputs; 2026-09-07) is kept beside the record and never replaces it, however
    new or complete it is. A folder without the field predates the role and is a record.
    """
    return (
        config.get("limit") is None
        and config.get("provider") != "mock"
        and config.get("role", "record") == "record"
    )


def refresh_attachments(run_dir: Path, attachments_dir: Path | None) -> list[Path]:
    """After a record run rewrite the appendix pair and the methods table, once every method has a record folder.

    The methods may run one provider at a time, so the appendix is built from the newest
    complete folder of every method (``attachment.record_model_runs``); until all five have
    one, the folders keep their own tables and the appendix is left alone.
    """
    from . import attachment  # local import: attachment reads run folders this module writes

    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    out = attachments_dir or attachment.ATTACHMENTS_DIR
    if not is_record_run(config):
        logger.info(
            "  partial or mock run: appendix files unchanged; TABLE.md and RESULTS.md are its output"
        )
        return []
    record = attachment.record_model_runs(run_dir.parent)
    missing = [n for n in model_registry.MODEL_ARMS if n not in record]
    if missing:
        logger.info(
            "  no record folder yet for %s: appendix files unchanged; this folder's TABLE.md and RESULTS.md are its output",
            ", ".join(missing),
        )
        return []
    folders = sorted({p.name for p in record.values()})
    written = attachment.build_model_methods(record=record, out_dir=out)
    written.append(attachment.write_arms_table(out))
    for path in written:
        logger.info("  appendix file refreshed from %s: %s", ", ".join(folders), path)
    return written


# ---------------------------------------------------------------------------
# Reporting: TABLE.md + RESULTS.md from the folder
# ---------------------------------------------------------------------------


def load_run(run_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], list[dict]]:
    """``(config, scores without per-customer detail, pairs)`` of a run folder."""
    config = json.loads((run_dir / "config.json").read_text(encoding="utf-8"))
    results: dict[str, dict[str, Any]] = {}
    for path in sorted((run_dir / "scores").glob("*.json")):
        entry = json.loads(path.read_text(encoding="utf-8"))
        entry.pop("per_customer", None)
        results[path.stem] = entry
    pairs_path = run_dir / "pairs.json"
    pairs = json.loads(pairs_path.read_text(encoding="utf-8")) if pairs_path.exists() else []
    return config, results, pairs


def _pct(x: float) -> str:
    """`x` (a 0-1 fraction) formatted as a percentage string, one decimal place."""
    return f"{100 * x:.1f} %"


def _calls_cell(calls: dict[str, int]) -> str:
    """The `ok / partial / failed` call-status cell for a table row, with reused and hidden-dropped counts appended when non-zero."""
    cell = f"{calls['ok']} / {calls['partial']} / {calls['failed']}"
    if calls.get("reused"):
        cell += f" ({calls['reused']} reused)"
    if calls.get("hidden_dropped"):
        cell += f"; hidden item among the dropped ids {calls['hidden_dropped']}×"
    return cell


def _seconds_cell(entry: dict[str, Any]) -> str:
    """`entry`'s median call seconds as a table cell, or `"—"` when there were no timed calls."""
    s = entry.get("median_call_seconds")
    return "—" if s is None else f"{s}"


def _pair_text(p: dict[str, Any]) -> str:
    """One-line paired-comparison summary (hits, difference, sign-test p) for the results card."""
    sign = "+" if p["difference"] > 0 else ""
    return (
        f"vs `{p['versus']}` {p['hits_second']} → {p['hits_first']} ({sign}{p['difference']}; "
        f"only method {p['only_first']}, only {p['versus']} {p['only_second']}; sign p {p['p_sign']})"
    )


def report(run_dir: Path) -> None:
    """Write ``TABLE.md`` and ``RESULTS.md`` from what the run folder holds."""
    config, results, pairs = load_run(run_dir)
    langs = config["languages"]
    n_items = config["database"]["catalogue_items"]
    n_neg = config["sampled_negatives"]
    floors = {p: random_floor(p, n_items, n_neg) for p in ("full", "sampled")}
    lines = [f"# UC-04 model methods — {run_dir.name}", ""]
    lines.append(
        f"Sample `{config['sample']['name']}`: {len(config['sample']['customers'])} customers"
        + (f" (limit {config['limit']})" if config.get("limit") else "")
        + f"; provider {config['provider']} / {config['model']} / {config['tier']} (CLI {config['provider_cli_version']}); "
        f"prompt version {config['prompt_version']}; seed {config['seed']}. Guessing scores "
        f"{_pct(floors['sampled'])} at top 10 under the sampled protocol (1 hidden + {n_neg} unbought) and "
        f"{_pct(floors['full'])} under the full catalogue ({n_items} products). The references `als_cf` and "
        "`popularity` are scored on exactly the same customers and candidate lists (`scores/reference-*.json`). "
        "Calls: ok = every id once; partial = ids left out and appended in prompt order; failed = unknown or "
        "repeated id, provider error or timeout (a failed customer keeps no opinion and is ranked at random). "
        "'Hidden item among the dropped ids' counts the partial calls whose left-out ids include the right "
        "answer, which then lands at the end of the list."
    )
    lines.append("")
    blocks: list[dict[str, Any]] = []
    for name, meta in config["methods"].items():
        lines.append(f"## `{name}` — {meta['title']}")
        lines.append("")
        lines.append(f"{meta['description']}. ML input: {meta['ml_input']}.")
        lines.append("")
        lines.append(
            "| branch | protocol | customers | calls ok / partial / failed | hits@10 / n | HR@10 (95 % CI) "
            "| NDCG@10 | MRR@10 | median s per call | reference `als_cf` | reference `popularity` |"
        )
        lines.append("|" + " --- |" * 11)
        block_lines: list[tuple[str, str]] = []
        for lang in langs:
            entry = results.get(f"{name}-{lang}")
            if entry is None:
                continue
            for proto in meta["protocols"]:
                res = entry["protocols"].get(proto)
                if res is None:
                    continue
                lo, hi = res["wilson95_hr10"]
                refs = []
                for arm in ("als_cf", "popularity"):
                    ref = (
                        results.get(f"reference-{arm}-{meta['subset']}", {})
                        .get("protocols", {})
                        .get(proto)
                    )
                    refs.append(f"{ref['hits']['10']} / {ref['n_customers']}" if ref else "—")
                # A branch whose every call failed has no opinion of the model in it: its
                # hits are the seeded random order (2026-09-07: a run of 400 failed calls
                # printed 9/100 as if it were a result). Say so in front of the number.
                calls = entry["calls"]
                answered = calls["ok"] + calls["partial"]
                dead = answered == 0 and calls["failed"] > 0
                dead_note = "NO RESULT (every call failed; random order scored): " if dead else ""
                lines.append(
                    f"| {lang} | {proto} | {res['n_customers']} | {_calls_cell(entry['calls'])} | "
                    f"{dead_note}{res['hits']['10']} / {res['n_customers']} | {_pct(res['hr']['10'])} ({_pct(lo)}–{_pct(hi)}) | "
                    f"{res['ndcg@10']:.4f} | {res['mrr@10']:.4f} | {_seconds_cell(entry)} | "
                    f"{refs[0]} | {refs[1]} |"
                )
                own_pairs = [
                    p
                    for p in pairs
                    if p["method"] == name and p["lang"] == lang and p["protocol"] == proto
                ]
                block_lines.append(
                    (
                        f"{lang} {proto}: {dead_note}{res['hits']['10']}/{res['n_customers']} hits@10, HR {_pct(res['hr']['10'])}",
                        f"95 % CI {_pct(lo)}–{_pct(hi)}; NDCG@10 {res['ndcg@10']:.3f}; calls {_calls_cell(entry['calls'])}"
                        + ("; " + "; ".join(_pair_text(p) for p in own_pairs) if own_pairs else ""),
                    )
                )
        lines.append("")
        own = [p for p in pairs if p["method"] == name]
        if own:
            lines.append(
                "Paired per customer (hits in the top 10; two-sided sign test on the discordant pairs):"
            )
            lines.append("")
            lines.append(
                "| branch | protocol | versus | hits versus | hits method | difference | only method | only versus | sign p |"
            )
            lines.append("|" + " --- |" * 9)
            for p in own:
                lines.append(
                    f"| {p['lang']} | {p['protocol']} | `{p['versus']}` | {p['hits_second']} | {p['hits_first']} | "
                    f"{p['difference']:+d} | {p['only_first']} | {p['only_second']} | {p['p_sign']} |"
                )
            lines.append("")
        if name == "describe_and_retrieve":
            lines += _sentence_examples(run_dir, config, results, langs)
        blocks.append(
            {"name": f"{meta['title']} (`{name}`)", "lines": block_lines or [("no branch ran", "")]}
        )
    lines.append(
        "Per-customer ranks and top-10 lists: `scores/<method>-<lang>.json`; every call verbatim: "
        "`calls/<method>-<lang>-<provider>/<contact_id>.json`; paired differences: `pairs.json`."
    )
    (run_dir / "TABLE.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    total_calls = sum(
        sum(e["calls"][k] for k in ("ok", "partial", "failed"))
        for e in results.values()
        if "calls" in e
    )
    reused = sum(e["calls"].get("reused", 0) for e in results.values() if "calls" in e)
    header = [
        (
            "Ran on",
            f"`substrate.db` (sha256 {config['database']['sha256'][:12]}…), {config['database']['customers']} linked customers, {n_items} products",
        ),
        (
            "Who",
            f"sample `{config['sample']['name']}`, {len(config['sample']['customers'])} customers"
            + (f" (limit {config['limit']})" if config.get("limit") else "")
            + "; the top-200 method on the customers whose hidden item ALS placed within its top 200",
        ),
        (
            "Provider / model / tier",
            f"{config['provider']} / {config['model']} / {config['tier']} (CLI {config['provider_cli_version']})",
        ),
        (
            "Prompts",
            f"version {config['prompt_version']}; English branch in English, Czech branch in Czech",
        ),
        (
            "Protocols",
            f"sampled (1 hidden + {n_neg} unbought, guessing {_pct(floors['sampled'])}) and full "
            f"(the whole catalogue, guessing {_pct(floors['full'])}); seed {config['seed']}",
        ),
        (
            "When",
            f"{config['date']}, {format_duration(config.get('total_seconds', 0))}, {total_calls} model calls"
            + (f" ({reused} reused from `{config['reuse']}`)" if reused else ""),
        ),
        ("Czech branch", config.get("czech_branch", "")),
    ]
    write_card(
        run_dir,
        title=f"UC-04 model methods — {run_dir.name}",
        header=header,
        blocks=blocks,
        sentence=_closing_sentence(config, results, pairs),
    )


def _sentence_examples(
    run_dir: Path,
    config: dict[str, Any],
    results: dict[str, dict[str, Any]],
    langs: list[str],
    n: int = 3,
) -> list[str]:
    """The model's three lines beside the real hidden purchase, first ``n`` customers per branch."""
    out = [
        "What the model wrote beside what the customer really bought next (first customers per branch):",
        "",
    ]
    for lang in langs:
        entry = results.get(f"describe_and_retrieve-{lang}")
        if not entry:
            continue
        sentences = entry.get("extras", {}).get("sentences", {})
        folder = run_dir / "calls" / f"describe_and_retrieve-{lang}-{config['provider']}"
        for cid in list(sentences)[:n]:
            call_path = folder / f"{cid}.json"
            hidden = ""
            if call_path.exists():
                hidden = json.loads(call_path.read_text(encoding="utf-8")).get("held_out", "")
            out.append(
                f"- {lang}, customer {cid}, bought next: `{hidden}` — model: "
                + " | ".join(sentences[cid])
            )
    out.append("")
    return out


def _closing_sentence(
    config: dict[str, Any], results: dict[str, dict[str, Any]], pairs: list[dict]
) -> str:
    """One prose sentence naming, for the first branch, every method's paired result against ALS, for the results card."""
    parts = []
    lang = config["languages"][0]
    for p in pairs:
        if p["lang"] != lang or p["versus"] != "als_cf":
            continue
        sign = "+" if p["difference"] > 0 else ""
        parts.append(
            f"`{p['method']}` {p['hits_first']} of {p['n']} against ALS's {p['hits_second']} under "
            f"`{p['protocol']}` ({sign}{p['difference']}, sign p {p['p_sign']})"
        )
    if not parts:
        return "No paired comparison was produced."
    return (
        f"In the {lang} branch: "
        + "; ".join(parts)
        + ". A difference whose sign test does not reach "
        "0.05 is inside what the customers' own variation explains; read the Czech branch against these rows for the Czech tax."
    )


def _append_runs_readme(run_dir: Path, config: dict[str, Any]) -> None:
    """Append one summary line for `run_dir` to `README.md` in the runs folder, creating it if needed."""
    readme = run_dir.parent / "README.md"
    if not readme.exists():
        readme.write_text(
            "# UC-04 run folders\n\nOne line per folder; each folder is the provenance of the numbers it holds and is never edited.\n\n",
            encoding="utf-8",
        )
    with open(readme, "a", encoding="utf-8") as fh:
        fh.write(
            f"- `{run_dir.name}` — model methods {', '.join(config['methods'])} on sample `{config['sample']['name']}` "
            f"({len(config['sample']['customers'])} customers{', limit ' + str(config['limit']) if config.get('limit') else ''}), "
            f"languages {'+'.join(config['languages'])}, {config['provider']} / {config['model']} / {config['tier']}; prompt {config['prompt_version']}.\n"
        )


__all__ = [
    "PAIRS",
    "REFERENCE_ARMS",
    "is_record_run",
    "load_run",
    "refresh_attachments",
    "report",
    "run",
]
