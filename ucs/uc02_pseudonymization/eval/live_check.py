"""Live check of the sandwich: real messages through a real model (Q5).

Runs the first N corpus messages through ``with_envelope`` with a fixed task and
one provider, and records per message what the contract saw: attempts, whether
the first response echoed the envelope id, tokens missing or invented per
attempt, and whether the restored text carries every original value and no token.
Nothing is trained; the model only does the task on masked text.

Every call is a model call: the run needs ``THESIS_LLM_CALLS=TRUE`` or
``--force-llm``. Run from the project root::

    python -m ucs.uc02_pseudonymization.eval.live_check --provider codex --n 20 --force-llm
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.code.envelope import (
    EnvelopeIntegrityError,
    EnvelopeProviderError,
    compose_system_prompt,
    with_envelope,
)
from ucs.uc02_pseudonymization.code.ner import DEFAULT_NER_BACKEND
from ucs.uc02_pseudonymization.code.pseudonymizer import TAG_PATTERN, load_gold
from ucs.uc02_pseudonymization.eval import runs
from utils.generation import DEFAULT_TIER, generate_text, resolve_model, resolve_tier
from utils.llm_switch import add_force_llm_argument, apply_force_llm
from utils.paths import UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT

TASKS = {
    "summarize": "Shrň následující zprávu ze CRM do tří vět. Drž věcný tón, nic nevymýšlej.",
    "reply": "Napiš krátkou zdvořilou odpověď zákazníkovi na následující zprávu (do pěti vět).",
}


# ---------------------------------------------------------------------------
# One message
# ---------------------------------------------------------------------------


async def check_message(
    message: dict[str, Any],
    gold_values: list[str],
    *,
    provider: str,
    model: str | None,
    tier: str | None,
    task: str,
    unify: str,
    timeout: float,
) -> dict[str, Any]:
    """Run one message through the envelope and record what happened."""
    system_prompt = compose_system_prompt(TASKS[task])
    attempts: list[dict[str, Any]] = []

    async def llm_call(prompt: str) -> str:
        """One model call through the thesis wrapper (the switch gates it)."""
        return await generate_text(
            prompt,
            provider=provider,
            system_prompt=system_prompt,
            model=model,
            tier=tier,
            timeout=timeout,
        )

    record: dict[str, Any] = {
        "message_id": message["message_id"],
        "attempts": attempts,
        "outcome": None,
        "final_text": None,
    }
    t0 = time.monotonic()
    try:
        final = await with_envelope(
            message["text"],
            llm_call,
            unify=unify,
            timeout_per_attempt=timeout,
            on_attempt=attempts.append,
        )
        record["outcome"] = "ok"
        record["final_text"] = final
        record["tokens_left_in_final"] = len(TAG_PATTERN.findall(final))
        record["gold_values_in_final"] = sum(1 for v in gold_values if v in final)
        record["gold_values"] = len(gold_values)
    except EnvelopeIntegrityError as exc:
        record["outcome"] = "integrity_error"
        record["error"] = str(exc)
    except EnvelopeProviderError as exc:
        record["outcome"] = "provider_error"
        record["error"] = str(exc)
    record["seconds"] = round(time.monotonic() - t0, 1)
    record["attempt_count"] = len(attempts)
    record["first_attempt_mid_ok"] = bool(attempts and attempts[0].get("mid_ok"))
    record["first_attempt_tokens_ok"] = bool(attempts and attempts[0].get("integrity_ok"))
    return record


# ---------------------------------------------------------------------------
# Run
# ---------------------------------------------------------------------------


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate the per-message records."""
    n = len(records)
    ok = [r for r in records if r["outcome"] == "ok"]
    return {
        "messages": n,
        "ok": len(ok),
        "integrity_errors": sum(1 for r in records if r["outcome"] == "integrity_error"),
        "provider_errors": sum(1 for r in records if r["outcome"] == "provider_error"),
        "first_attempt_mid_ok": sum(1 for r in records if r["first_attempt_mid_ok"]),
        "first_attempt_tokens_ok": sum(1 for r in records if r["first_attempt_tokens_ok"]),
        "attempts_total": sum(r["attempt_count"] for r in records),
        "attempts_mean": round(sum(r["attempt_count"] for r in records) / n, 2) if n else 0.0,
        "restored_without_tokens": sum(1 for r in ok if r.get("tokens_left_in_final") == 0),
        "gold_values_present": sum(r.get("gold_values_in_final", 0) for r in ok),
        "gold_values_total": sum(r.get("gold_values", 0) for r in ok),
        "seconds_total": round(sum(r["seconds"] for r in records), 1),
    }


def write_outputs(
    run_dir: Path, records: list[dict[str, Any]], args: argparse.Namespace, started: float
) -> None:
    """Write config.json, messages.jsonl, summary.json and RESULTS.md."""
    summary = summarize(records)
    resolved_model = resolve_model(args.provider, args.model)
    resolved_tier = resolve_tier(args.provider, args.tier, args.model)
    runs.write_json(
        run_dir / "config.json",
        {
            "run": run_dir.name,
            "kind": "live-check",
            "started": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(started)),
            "duration_seconds": round(time.monotonic() - args._t0, 1),
            "corpus": runs.corpus_identity(args.corpus, args.gold),
            "code": runs.code_identity(),
            "provider": args.provider,
            "model": resolved_model,
            "tier": resolved_tier,
            "requested": {"model": args.model, "tier": args.tier},
            "task": args.task,
            "task_prompt": TASKS[args.task],
            "unify": args.unify,
            "n": args.n,
            "timeout_per_attempt": args.timeout,
            "default_ner_backend": DEFAULT_NER_BACKEND,
        },
    )
    with (run_dir / "messages.jsonl").open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    runs.write_json(run_dir / "summary.json", summary)
    n = summary["messages"]
    sentence = (
        f"{args.provider} ({resolved_model}, {resolved_tier}) kept the envelope contract on the first attempt "
        f"for {summary['first_attempt_tokens_ok']} of {n} messages, {summary['ok']} of {n} came back restored, "
        f"and {summary['gold_values_present']} of {summary['gold_values_total']} original values reappeared in the restored text."
    )
    runs.write_card(
        run_dir,
        title=f"UC-02 live check — ran on: the first {n} corpus messages through the sandwich",
        header=[
            (
                "Model",
                f"{args.provider} {resolved_model} ({resolved_tier}); NER {DEFAULT_NER_BACKEND}; unify {args.unify}",
            ),
            ("Task", TASKS[args.task]),
            (
                "Ran",
                f"{time.strftime('%Y-%m-%d %H:%M', time.localtime(started))}, {runs.format_duration(time.monotonic() - args._t0)}",
            ),
        ],
        blocks=[
            {
                "name": f"{args.provider} {resolved_model}",
                "lines": [
                    (
                        f"{summary['first_attempt_mid_ok']} of {n} echoed the envelope id on the first attempt",
                        "the correlation wrapper the model must copy back",
                    ),
                    (
                        f"{summary['first_attempt_tokens_ok']} of {n} kept every token on the first attempt",
                        "no placeholder dropped or invented",
                    ),
                    (
                        f"{summary['attempts_total']} attempts for {n} messages",
                        f"mean {summary['attempts_mean']}; retries carry a reminder",
                    ),
                    (
                        f"{summary['ok']} of {n} restored, {summary['integrity_errors']} integrity errors, {summary['provider_errors']} provider errors",
                        "restored = every token replaced by its value",
                    ),
                    (
                        f"{summary['gold_values_present']} of {summary['gold_values_total']} original values in the restored text",
                        "values the model left out of its answer are not a leak, only absent",
                    ),
                ],
            }
        ],
        sentence=sentence,
    )


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(description="UC-02 live sandwich check.")
    add_force_llm_argument(parser)
    parser.add_argument("--provider", default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--tier", default=DEFAULT_TIER)
    parser.add_argument("--n", type=int, default=20)
    parser.add_argument("--task", choices=sorted(TASKS), default="summarize")
    parser.add_argument("--unify", default="none")
    parser.add_argument("--timeout", type=float, default=300.0)
    parser.add_argument("--corpus", type=Path, default=UC02_PII_CORPUS_SNAPSHOT)
    parser.add_argument("--gold", type=Path, default=UC02_PII_GOLD_SNAPSHOT)
    parser.add_argument("--tag", default=None)
    parser.add_argument("--runs-dir", type=Path, default=runs.RUNS_DIR)
    return parser


def main(argv: list[str] | None = None) -> Path:
    """Run the live check and return the run folder."""
    args = build_parser().parse_args(argv)
    apply_force_llm(args)
    args._t0 = time.monotonic()
    started = time.time()
    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))[: args.n]
    gold = load_gold(args.gold)

    async def _run() -> list[dict[str, Any]]:
        """Check every message in `corpus` in turn and return the per-message records."""
        out = []
        for message in corpus:
            values = [g["surface_form"] for g in gold.get(message["message_id"], [])]
            record = await check_message(
                message,
                values,
                provider=args.provider,
                model=args.model,
                tier=args.tier,
                task=args.task,
                unify=args.unify,
                timeout=args.timeout,
            )
            print(
                f"[live] {record['message_id']}: {record['outcome']} in {record['attempt_count']} attempt(s)"
            )
            out.append(record)
        return out

    records = asyncio.run(_run())
    run_dir = runs.new_run_dir(
        args.tag or f"sandwich-live-{args.provider}-{args.unify}-tokens-{len(records)}-messages",
        args.runs_dir,
    )
    write_outputs(run_dir, records, args, started)
    print(f"[live] wrote {run_dir}")
    return run_dir


if __name__ == "__main__":
    main()
