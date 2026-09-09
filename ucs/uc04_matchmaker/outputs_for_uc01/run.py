"""The run: who by rule, the classical fields, the model calls, the checks, the handoff, the card, the appendix pair.

``run`` writes ``eval/runs/<date>-outputs-for-uc01-<provider>-<model>-<tier>-<N>-contacts/``:
``config.json`` (the rule, the pick, the prompt version and texts, the provider with
its resolved model, tier and CLI version, the database hash), ``pick.json``, ``calls/``
(one file per call), ``topics.json``, ``handoff.json`` (what ``freeze`` copies to the
file of record), ``summary.json`` and ``RESULTS.md``; a run over the whole pick also rewrites
``<project_root>/attachments/uc04-outputs-for-uc01.{csv,md}`` from its own folder (the Příloha A
pattern), a smoke (``--limit N``, the first N prose contacts) keeps its card only;
``--top-k`` sets the recommendations per contact.
"""

from __future__ import annotations

import asyncio
import csv
import datetime as _dt
import statistics
import time
from pathlib import Path
from typing import Any

from ucs.uc01_personalization import picker
from ucs.uc02_pseudonymization.eval.runs import (
    code_identity,
    format_duration,
    new_run_dir,
    write_card,
    write_json,
)
from utils.generation import cli_version, resolve_model, resolve_tier
from utils.paths import SUBSTRATE_DB

from ..arena import PACKAGES, RUNS_DIR, database_identity
from ..data import connect, load_arena
from . import aspects as aspects_mod
from . import handoff as handoff_mod
from . import inputs, persona, prompts, reasons
from . import topics as topics_mod
from .calls import CONCURRENCY, Provider

RULE = (
    "model-written prose (recommendation reasons, persona, aspects) for the linked contacts of "
    "UC-01's pick PICK, in contact-id order; classical fields (interest topics, lifecycle stage) "
    "for every linked contact; recommendations = ALS collaborative filtering over the whole "
    "purchase history, top K unbought products"
)


def prose_contacts(pick: dict[str, Any]) -> list[int]:
    """The pick's contacts that own a reviewer (prospects have no history), by contact id."""
    return sorted(int(cid) for cid, f in pick.get("contacts", {}).items() if f.get("amazon_group"))


def run(
    *,
    provider: str,
    model: str | None = None,
    tier: str | None = None,
    pick_name: str = picker.DEFAULT_PICK,
    limit: int | None = None,
    top_k: int = 5,
    concurrency: int = CONCURRENCY,
    db_path: Path = SUBSTRATE_DB,
    base_dir: Path = RUNS_DIR,
    label: str | None = None,
    attachments_dir: Path | None = None,
) -> Path:
    """Produce the outputs for UC-01 into a new run folder; returns the folder."""
    t_start = time.time()
    pick = picker.load_pick(pick_name)
    prose = prose_contacts(pick)
    if limit is not None:
        prose = prose[:limit]
    arena = load_arena("en", db_path, hold_out=False)
    prov = Provider(
        provider, model, tier, resolve_model(provider, model), resolve_tier(provider, tier, model)
    )
    run_dir = new_run_dir(
        label
        or f"outputs-for-uc01-{provider}-{prov.resolved_model}-{prov.resolved_tier or 'notier'}-{len(prose)}-contacts",
        base=base_dir,
    )
    config: dict[str, Any] = {
        "run_dir": run_dir.name,
        "date": _dt.date.today().isoformat(),
        "rule": RULE.replace("PICK", pick_name),
        "pick": pick_name,
        "prose_contacts": prose,
        "limit": limit,
        "top_k": top_k,
        "provider": provider,
        "model": prov.resolved_model,
        "tier": prov.resolved_tier,
        "provider_cli_version": cli_version(provider),
        "concurrency": concurrency,
        "prompt_version": prompts.PROMPT_VERSION,
        "prompts": {
            "reasons": prompts.REASON_SYSTEM,
            "persona": prompts.PERSONA_SYSTEM,
            "aspects": prompts.ASPECTS_SYSTEM,
        },
        "schemas": {
            "reasons": prompts.REASON_SCHEMA,
            "persona": prompts.PERSONA_SCHEMA,
            "aspects": prompts.ASPECTS_SCHEMA,
        },
        "caps": {
            "history_purchases": prompts.HISTORY_CAP,
            "review_chars": prompts.REVIEW_CHARS_CAP,
            "persona_reviews": prompts.PERSONA_REVIEWS,
        },
        "topics": {
            "method": "lda",
            "n_topics": topics_mod.N_TOPICS,
            "per_customer": topics_mod.TOP_TOPICS,
        },
        "database": database_identity(arena, db_path),
        "code": code_identity(PACKAGES),
    }
    write_json(run_dir / "config.json", config)
    write_json(run_dir / "pick.json", pick)

    conn = connect(db_path)
    try:
        # classical fields for everyone
        doc_topic, labels = topics_mod.fit(arena)
        topics = topics_mod.per_customer(arena, doc_topic, labels)
        write_json(run_dir / "topics.json", {str(k): v for k, v in topics.items()})
        all_ids = [c.contact_id for c in arena.customers]
        lifecycle = inputs.lifecycle_labels(conn, all_ids)
        reviewer_of = {c.contact_id: c.reviewer_id for c in arena.customers}

        # model-written prose for the pick
        async def prose_all() -> tuple[Any, Any, Any]:
            """Run the reasons, persona and aspects generators concurrently for the pick's prose contacts."""
            return await asyncio.gather(
                reasons.generate(
                    conn,
                    arena,
                    prose,
                    top_k=top_k,
                    provider=prov,
                    run_dir=run_dir,
                    concurrency=concurrency,
                ),
                persona.generate(
                    conn,
                    arena,
                    prose,
                    topics,
                    provider=prov,
                    run_dir=run_dir,
                    concurrency=concurrency,
                ),
                aspects_mod.generate(
                    conn, prose, provider=prov, run_dir=run_dir, concurrency=concurrency
                ),
            )

        reason_rows, personas, aspect_rows = asyncio.run(prose_all())
    finally:
        conn.close()

    summary = _summary(reason_rows, personas, aspect_rows, topics, time.time() - t_start)
    payload = handoff_mod.assemble(
        reviewer_of=reviewer_of,
        reasons=reason_rows,
        personas=personas,
        aspects=aspect_rows,
        topics=topics,
        lifecycle=lifecycle,
        meta={
            "run": run_dir.name,
            "date": config["date"],
            "rule": config["rule"],
            "prompt_version": prompts.PROMPT_VERSION,
            "provider": f"{provider} / {prov.resolved_model} / {prov.resolved_tier}",
            "provider_cli_version": config["provider_cli_version"],
            "counts": summary["counts"],
        },
    )
    handoff_mod.write(run_dir, payload)
    write_json(run_dir / "summary.json", summary)
    _write_card(run_dir, config, summary)
    _append_readme(run_dir, config, summary)
    # a smoke keeps its card; only a run over the whole pick rewrites the appendix
    if limit is None:
        _write_attachment(
            run_dir, config, summary, reason_rows, personas, aspect_rows, arena, attachments_dir
        )
    return run_dir


# ---------------------------------------------------------------------------
# Summary, card, attachment
# ---------------------------------------------------------------------------


def _summary(
    reason_rows: dict[int, list[dict[str, Any]]],
    personas: dict[int, dict[str, Any]],
    aspect_rows: dict[int, dict[str, Any]],
    topics: dict[int, list[dict[str, Any]]],
    seconds: float,
) -> dict[str, Any]:
    """Aggregate the run's counts (reasons, personas, aspects, topics, calls) and timing into the `summary.json` payload."""
    reasons_all = [r for rows in reason_rows.values() for r in rows]
    aspects_all = [a for rows in aspect_rows.values() for a in rows.get("aspects", [])]
    call_seconds = (
        [r["seconds"] for r in reasons_all]
        + [p["seconds"] for p in personas.values() if p.get("status") != "skipped"]
        + [a["seconds"] for a in aspect_rows.values() if a.get("status") != "skipped"]
    )
    words = [len(r["reason"].split()) for r in reasons_all if r.get("reason")]
    return {
        "counts": {
            "prose_contacts": len(reason_rows),
            "reasons_ok": sum(r["status"] == "ok" for r in reasons_all),
            "reasons_failed": sum(r["status"] == "failed" for r in reasons_all),
            "reasons_grounded": sum(bool(r["grounded"]) for r in reasons_all),
            "personas_ok": sum(p.get("status") == "ok" for p in personas.values()),
            "personas_failed": sum(p.get("status") == "failed" for p in personas.values()),
            "aspects_contacts_ok": sum(a.get("status") == "ok" for a in aspect_rows.values()),
            "aspects_contacts_failed": sum(
                a.get("status") == "failed" for a in aspect_rows.values()
            ),
            "aspects_contacts_skipped": sum(
                a.get("status") == "skipped" for a in aspect_rows.values()
            ),
            "aspects_total": len(aspects_all),
            "aspects_grounded": sum(bool(a["grounded"]) for a in aspects_all),
            "topics_contacts": sum(1 for rows in topics.values() if rows),
            "calls": len(reasons_all)
            + sum(p.get("status") != "skipped" for p in personas.values())
            + sum(a.get("status") != "skipped" for a in aspect_rows.values()),
        },
        "reason_words_median": statistics.median(words) if words else None,
        "reason_words_max": max(words) if words else None,
        "median_call_seconds": round(statistics.median(call_seconds), 1) if call_seconds else None,
        "wall_seconds": round(seconds, 1),
    }


def _write_card(run_dir: Path, config: dict[str, Any], summary: dict[str, Any]) -> None:
    """Write `RESULTS.md`: header facts, per-block counts (reasons, persona, aspects, classical fields) and a closing sentence."""
    c = summary["counts"]
    header = [
        (
            "Ran on",
            f"`substrate.db` (sha256 {config['database']['sha256'][:12]}…), {config['database']['customers']} linked customers",
        ),
        (
            "Who",
            f"prose for {c['prose_contacts']} contacts of pick `{config['pick']}`"
            + (f" (limit {config['limit']})" if config["limit"] else "")
            + f"; topics + lifecycle for all {config['database']['customers']}",
        ),
        (
            "Provider / model / tier",
            f"{config['provider']} / {config['model']} / {config['tier']} (CLI {config['provider_cli_version']})",
        ),
        (
            "Prompts",
            f"version {config['prompt_version']}, Czech; reasons cite purchase ids, aspects quote verbatim",
        ),
        (
            "When",
            f"{config['date']}, {format_duration(summary['wall_seconds'])}, {c['calls']} model calls",
        ),
    ]
    blocks = [
        {
            "name": "Recommendation reasons (ALS top-k + one Czech sentence each)",
            "lines": [
                (
                    f"{c['reasons_ok']} of {c['reasons_ok'] + c['reasons_failed']} sentences",
                    "schema-valid, evidence ids inside the history shown, within the word rule",
                ),
                (
                    f"{c['reasons_grounded']} grounded",
                    "every cited purchase exists in the customer's history (checked, not trusted)",
                ),
                (
                    f"{summary['reason_words_median']} words median, {summary['reason_words_max']} max",
                    f"the rule says at most {reasons.MAX_WORDS}",
                ),
            ],
        },
        {
            "name": "Persona (two Czech sentences)",
            "lines": [
                (
                    f"{c['personas_ok']} of {c['personas_ok'] + c['personas_failed']}",
                    "schema-valid; not loaded into the database, kept in the handoff and the appendix",
                )
            ],
        },
        {
            "name": "Aspects (from the Czech reviews, verbatim quotes)",
            "lines": [
                (
                    f"{c['aspects_contacts_ok']} contacts ok, {c['aspects_contacts_failed']} failed, {c['aspects_contacts_skipped']} without Czech reviews",
                    "one call per contact",
                ),
                (
                    f"{c['aspects_grounded']} of {c['aspects_total']} quotes found verbatim",
                    "whitespace and case aside; a paraphrase counts as not grounded",
                ),
            ],
        },
        {
            "name": "Classical fields",
            "lines": [
                (
                    f"topics for {c['topics_contacts']} contacts",
                    f"LDA, {config['topics']['n_topics']} topics over the catalogue titles, top {config['topics']['per_customer']} per contact; lifecycle from the substrate's rule",
                )
            ],
        },
    ]
    if summary["median_call_seconds"] is not None:
        blocks[0]["lines"].append(
            (f"{summary['median_call_seconds']} s median per call", "the call itself")
        )
    total_prose = c["reasons_ok"] + c["reasons_failed"]
    sentence = (
        f"{c['reasons_grounded']} of {total_prose} recommendation sentences cite only purchases the customer made and "
        f"{c['aspects_grounded']} of {c['aspects_total']} aspect quotes are verbatim in the reviews; these are the "
        "checks the thesis reports, because nobody receives these texts and nothing else about them can be measured here. "
        "Whether they help a message is judged in UC-01, where the texts are read."
    )
    write_card(
        run_dir,
        title=f"UC-04 outputs for UC-01 — {run_dir.name}",
        header=header,
        blocks=blocks,
        sentence=sentence,
    )


def _append_readme(run_dir: Path, config: dict[str, Any], summary: dict[str, Any]) -> None:
    """Append one summary line for `run_dir` to `README.md` in the runs folder, creating it if needed."""
    readme = run_dir.parent / "README.md"
    if not readme.exists():
        readme.write_text(
            "# UC-04 run folders\n\nOne line per folder; each folder is the provenance of the numbers it holds and is never edited.\n\n",
            encoding="utf-8",
        )
    c = summary["counts"]
    with open(readme, "a", encoding="utf-8") as fh:
        fh.write(
            f"- `{run_dir.name}` — outputs for UC-01: reasons, persona, aspects for {c['prose_contacts']} contacts of the pick "
            f"({config['provider']} / {config['model']} / {config['tier']}, {c['calls']} calls), topics + lifecycle for all; prompt {config['prompt_version']}.\n"
        )


def _write_attachment(
    run_dir: Path,
    config: dict[str, Any],
    summary: dict[str, Any],
    reason_rows: dict[int, list[dict[str, Any]]],
    personas: dict[int, dict[str, Any]],
    aspect_rows: dict[int, dict[str, Any]],
    arena: Any,
    attachments_dir: Path | None,
) -> list[Path]:
    """Rewrite ``<project_root>/attachments/uc04-outputs-for-uc01.{csv,md}``: counts, grounding, and examples."""
    from ..attachment import ATTACHMENTS_DIR

    out = attachments_dir or ATTACHMENTS_DIR
    out.mkdir(parents=True, exist_ok=True)
    c = summary["counts"]
    facts = [
        ("prose_contacts", c["prose_contacts"], "kontaktů z picku UC-01 s modelovou prózou"),
        (
            "reasons_ok",
            f"{c['reasons_ok']} / {c['reasons_ok'] + c['reasons_failed']}",
            "zdůvodnění platných podle schématu a pravidel",
        ),
        (
            "reasons_grounded",
            c["reasons_grounded"],
            "zdůvodnění, jejichž všechny citované nákupy v historii existují",
        ),
        (
            "reason_words_median",
            summary["reason_words_median"],
            f"medián slov ve větě (pravidlo nejvýš {reasons.MAX_WORDS})",
        ),
        (
            "personas_ok",
            f"{c['personas_ok']} / {c['personas_ok'] + c['personas_failed']}",
            "person platných podle schématu",
        ),
        (
            "aspects_grounded",
            f"{c['aspects_grounded']} / {c['aspects_total']}",
            "citací u aspektů nalezených doslova v recenzích",
        ),
        ("aspects_contacts_skipped", c["aspects_contacts_skipped"], "kontaktů bez českých recenzí"),
        ("topics_contacts", c["topics_contacts"], "kontaktů s tématy zájmu (LDA, klasika)"),
        ("calls", c["calls"], "volání modelu"),
        ("wall_seconds", summary["wall_seconds"], f"stěna při souběhu {config['concurrency']}"),
    ]
    csv_path = out / "uc04-outputs-for-uc01.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["run", "key", "value", "meaning"])
        for k, v, m in facts:
            w.writerow([run_dir.name, k, v, m])

    by_id = inputs.customers_by_id(arena)
    lines = [
        "# Slovní výstupy UC-04 pro UC-01: zdůvodnění, persona, aspekty (příloha, generováno)",
        "",
        f"Vygenerováno ze složky běhu `ucs/uc04_matchmaker/eval/runs/{run_dir.name}/` (běh ze dne {config['date']}, "
        f"{config['provider']} / {config['model']} / {config['tier']}, prompt {config['prompt_version']}, databáze `substrate.db`, "
        f"sha256 {config['database']['sha256'][:12]}…). Modelová próza pro kontakty z picku UC-01 (`{config['pick']}`), "
        "klasická pole pro všechny kontakty s historií. Doklad se ověřuje strojově: zdůvodnění cituje identifikátory nákupů, "
        "citace u aspektů se hledá doslova v textu recenzí.",
        "",
        "Tabulka 1 – Počty a doložitelnost",
        "",
        "| klíč | hodnota | význam |",
        "| --- | --- | --- |",
        *(f"| `{k}` | {v} | {m} |" for k, v, m in facts),
        "",
        "Tabulka 2 – Ukázky (první tři kontakty): poslední nákupy, doporučení se zdůvodněním, persona, aspekty",
        "",
    ]
    for cid in list(reason_rows)[:3]:
        customer = by_id.get(cid)
        recent = (
            ", ".join(
                inputs.title_of(arena.catalog, it.asin)[:50]
                for it in sorted(
                    customer.history, key=lambda i: (i.date, i.review_id), reverse=True
                )[:3]
            )
            if customer
            else ""
        )
        lines += [f"**Zákazník Z-{cid}**, poslední nákupy: {recent}", ""]
        for r in reason_rows.get(cid, []):
            if r["status"] == "ok":
                lines.append(
                    f"- {r['title'][:60]}: {r['reason']} (doklad: {', '.join(r['evidence_ids'])}{'' if r['grounded'] else ', NEDOLOŽENO'})"
                )
            else:
                lines.append(f"- {r['title'][:60]}: selhalo ({r['error'][:80]})")
        p = personas.get(cid) or {}
        if p.get("status") == "ok":
            lines.append(f"- persona `{p['label']}` ({p['price_segment']}): {p['narrative_cs']}")
        for a in (aspect_rows.get(cid) or {}).get("aspects", []):
            lines.append(
                f"- aspekt {a['aspect']} ({a['sentiment']}): „{a['evidence'][:120]}“{'' if a['grounded'] else ' NENALEZENO V RECENZÍCH'}"
            )
        lines.append("")
    md_path = out / "uc04-outputs-for-uc01.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return [csv_path, md_path]


__all__ = ["RULE", "prose_contacts", "run"]
