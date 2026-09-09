"""What every model method shares: the inputs of a run, prompt lines, the recorded call, the strict parser, the score matrix.

A method never sees an ASIN in its prompt: candidates are ``C001`` … ``C101`` (``C200``
for the top-200 method), the history is a list of dated, rated titles. One call is one
file ``calls/<method>-<lang>-<provider>/<contact_id>.json`` with the verbatim prompt and
system text, the raw answer, the parsed ranking, the status (``ok`` = every id exactly
once; ``partial`` = ids missing, appended in the order the prompt listed them; ``failed``
= an unknown or repeated id, a provider error, or a timeout), the seconds of the call
itself, the resolved model and tier, the provider CLI version, the prompt version and
the database hash. A failed call is a row, never a crash. ``--reuse <run>`` takes over a
record whose prompt version, model, tier, prompt and system text are identical and
writes where it came from.

The score of a method is produced the way the classical arms are scored: a matrix
customer × product over the whole catalogue, ``k − position`` for the candidates the
model ordered and ``-inf`` elsewhere, then ``protocols.evaluate_sampled`` /
``evaluate_full`` unchanged (design §3).
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

import numpy as np

from ucs.uc02_pseudonymization.eval.runs import write_json
from utils.generation import ProviderQuotaError, ProviderRateLimitError, generate_json

from ...data import Arena, Customer
from ...outputs_for_uc01.calls import Provider
from ...protocols import NEG_INF
from . import _prompts

TIMEOUT_SECONDS = 300
CONCURRENCY = 4
SHUFFLE_STREAM = 7  # third seed component: the candidate shuffle is not the sampler's stream
LIMIT_ERRORS_TO_STOP = 3  # rate-limit rejections in a row that end the sending (a usage window)


# ---------------------------------------------------------------------------
# The inputs of a run and the output of a method
# ---------------------------------------------------------------------------


@dataclass
class Inputs:
    """Everything a method reads: the arenas, the target customers, the classical scores, the provider, the folder."""

    arenas: dict[str, Arena]  # lang -> the whole arena (every linked customer)
    target_ids: list[int]  # the sample's contact ids (a --limit cuts the list)
    als_scores: np.ndarray  # [n_customers, n_items] over arenas["en"], language-agnostic
    pop_scores: np.ndarray  # same shape, the popularity arm
    provider: Provider
    run_dir: Path
    n_neg: int = 100
    seed: int = 42
    concurrency: int = CONCURRENCY
    reuse_dir: Path | None = None
    db_sha256: str = ""
    db_path: Path | None = None
    provider_cli_version: str | None = None
    limit: int | None = None  # a smoke: the first N customers of every subset
    quota_exhausted: bool = False  # set by the first quota error; later calls are skipped, not sent
    limit_errors_in_a_row: int = 0  # rate-limit rejections since the last good call

    def row_of(self, contact_id: int) -> int:
        """The row of a contact in the classical score matrices (``arenas["en"]`` order)."""
        if not hasattr(self, "_rows"):
            self._rows = {c.contact_id: u for u, c in enumerate(self.arenas["en"].customers)}
        return self._rows[contact_id]


@dataclass
class CallRecord:
    """What one recorded call produced, as the runner and the card see it."""

    contact_id: int
    status: str  # ok | partial | failed
    seconds: float
    error: str = ""
    ranking: list[str] | None = None  # candidate ids in the model's order (completed when partial)
    missing: int = 0
    reused_from: str | None = None
    parsed: dict[str, Any] | None = None
    hidden_dropped: bool = False  # partial call whose left-out ids include the hidden item


@dataclass
class MethodOutput:
    """What a method hands back: the sub-arena it scored, its score matrix, the candidate lists, the calls."""

    arena: Arena  # the target customers only, in contact-id order
    scores: np.ndarray  # [len(arena.customers), n_items]
    calls: list[CallRecord]
    candidates: list[list[int]] | None = None  # per customer, for the sampled protocol
    extras: dict[str, Any] = field(default_factory=dict)  # e.g. method 2's sentences

    def call_counts(self) -> dict[str, int]:
        """Tally `calls` by status (`ok`/`partial`/`failed`), plus how many were `reused` or `hidden_dropped`."""
        out = {"ok": 0, "partial": 0, "failed": 0, "reused": 0, "hidden_dropped": 0}
        for c in self.calls:
            out[c.status] += 1
            if c.reused_from:
                out["reused"] += 1
            if c.hidden_dropped:
                out["hidden_dropped"] += 1
        return out


# ---------------------------------------------------------------------------
# Prompt lines
# ---------------------------------------------------------------------------


def title_of(catalog: dict[str, dict[str, Any]], asin: str, lang: str) -> str:
    """The title in the branch language (Czech where the catalogue has one), cut to ``TITLE_CHARS``."""
    meta = catalog.get(asin) or {}
    title = (meta.get("title_cs") if lang == "cs" else None) or meta.get("title") or asin
    title = " ".join(str(title).split())
    return title[: _prompts.TITLE_CHARS]


def history_lines(customer: Customer, arena: Arena) -> list[str]:
    """``- <date> ★<rating> <title>``, oldest first (the arena keeps the history in date order)."""
    return [
        f"- {it.date} ★{int(round(it.rating))} {title_of(arena.catalog, it.asin, arena.lang)}"
        for it in customer.history
    ]


def candidate_ids(n: int) -> list[str]:
    """``C001`` … ``C<n>``."""
    if n > 999:
        raise ValueError("candidate ids have three digits")
    return [f"C{i:03d}" for i in range(1, n + 1)]


def candidate_lines(
    ids: list[str], item_idx: list[int], arena: Arena, scores: list[float] | None = None
) -> list[str]:
    """``C001  <title>`` (plus ``[ALS 0.831]`` when the method shows the classical score)."""
    lines = []
    for n, (cid, j) in enumerate(zip(ids, item_idx, strict=True)):
        line = f"{cid}  {title_of(arena.catalog, arena.all_asins[j], arena.lang)}"
        if scores is not None:
            line += f"  [ALS {scores[n]:.3f}]"
        lines.append(line)
    return lines


def shuffled(item_idx: list[int], *, seed: int, contact_id: int) -> list[int]:
    """The candidate list in a seeded random order per customer (design §8.4).

    The sampler appends the hidden item last; without the shuffle the right answer
    would always stand at the same position inside the prompt.
    """
    rng = np.random.default_rng([seed, contact_id, SHUFFLE_STREAM])
    order = rng.permutation(len(item_idx))
    return [item_idx[int(i)] for i in order]


# ---------------------------------------------------------------------------
# The strict parser
# ---------------------------------------------------------------------------


def parse_ranking(parsed: Any, ids: list[str]) -> tuple[list[str], str, list[str], str]:
    """Return ``(ranking, status, missing_ids, error)`` for a ranking answer over ``ids``.

    An unknown id or a repeated id fails the call (nothing is repaired silently);
    ids the model left out are appended in the order the prompt listed them and the
    call is ``partial``; ``missing_ids`` names them (a failed call lists every id).
    """
    if not isinstance(parsed, dict) or not isinstance(parsed.get("ranking"), list):
        return [], "failed", list(ids), "answer has no 'ranking' list"
    known = set(ids)
    seen: set[str] = set()
    ranking: list[str] = []
    for item in parsed["ranking"]:
        cid = str(item).strip()
        if cid not in known:
            return [], "failed", list(ids), f"unknown candidate id {cid!r}"
        if cid in seen:
            return [], "failed", list(ids), f"repeated candidate id {cid!r}"
        seen.add(cid)
        ranking.append(cid)
    missing = [cid for cid in ids if cid not in seen]
    if missing:
        return ranking + missing, "partial", missing, f"{len(missing)} ids missing"
    return ranking, "ok", [], ""


# ---------------------------------------------------------------------------
# One recorded call (with reuse)
# ---------------------------------------------------------------------------


def calls_folder(run_dir: Path, method: str, lang: str, provider: str) -> Path:
    """The per-(method, lang, provider) folder under `run_dir/calls/` that holds one JSON file per contact."""
    return run_dir / "calls" / f"{method}-{lang}-{provider}"


def _reusable(inputs: Inputs, method: str, lang: str, contact_id: int, prompt: str, system: str):
    """The record of a previous run for the same input, or None."""
    if inputs.reuse_dir is None:
        return None
    path = calls_folder(inputs.reuse_dir, method, lang, inputs.provider.name) / f"{contact_id}.json"
    if not path.exists():
        return None
    old = json.loads(path.read_text(encoding="utf-8"))
    parsed = old.get("parsed")
    if isinstance(parsed, dict) and "missing_ids" not in parsed and parsed.get("ranking"):
        # a record written before the field existed: the ids the model itself did not list
        listed = (old.get("raw") or {}).get("ranking") if isinstance(old.get("raw"), dict) else None
        if isinstance(listed, list):
            parsed["missing_ids"] = [c for c in parsed["ranking"] if c not in set(map(str, listed))]
    same = (
        old.get("prompt_version") == _prompts.PROMPT_VERSION
        and old.get("model") == inputs.provider.resolved_model
        and old.get("tier") == inputs.provider.resolved_tier
        and old.get("prompt") == prompt
        and old.get("system_prompt") == system
        and old.get("status") in {"ok", "partial"}
    )
    return old if same else None


async def recorded_call(
    inputs: Inputs,
    *,
    method: str,
    lang: str,
    contact_id: int,
    prompt: str,
    system_prompt: str,
    schema: dict[str, Any],
    sem: asyncio.Semaphore,
    interpret: Callable[[Any], tuple[dict[str, Any], str, str]],
    extra: dict[str, Any] | None = None,
) -> CallRecord:
    """One schema-enforced call written to ``calls/<method>-<lang>-<provider>/<contact_id>.json``.

    ``interpret(raw) -> (parsed, status, error)`` turns the provider's object into the
    method's parsed result and judges it (``ok`` / ``partial`` / ``failed``); the call
    is recorded whatever happens. ``extra`` is written into the record as it is
    (a method's own fields, e.g. the candidate ids and ASINs it showed).
    """
    folder = calls_folder(inputs.run_dir, method, lang, inputs.provider.name)
    folder.mkdir(parents=True, exist_ok=True)
    old = _reusable(inputs, method, lang, contact_id, prompt, system_prompt)
    if old is not None:
        old["reused_from"] = inputs.reuse_dir.name if inputs.reuse_dir else None
        write_json(folder / f"{contact_id}.json", old)
        return CallRecord(
            contact_id=contact_id,
            status=old["status"],
            seconds=float(old.get("seconds", 0.0)),
            error=old.get("error", ""),
            ranking=old.get("ranking"),
            missing=int(old.get("missing", 0)),
            reused_from=old["reused_from"],
            parsed=old.get("parsed"),
        )
    raw: Any = None
    parsed: dict[str, Any] | None = None
    status, error = "failed", ""
    async with sem:
        t0 = time.perf_counter()  # inside the semaphore: the call itself, not the wait for a slot
        try:
            if inputs.quota_exhausted:
                raise ProviderQuotaError(
                    inputs.provider.name,
                    "skipped: the provider's quota was exhausted earlier in this run "
                    "(rerun with --reuse <this folder> once it is back).",
                )
            raw = await generate_json(
                prompt,
                schema,
                provider=inputs.provider.name,
                system_prompt=system_prompt,
                model=inputs.provider.model,
                tier=inputs.provider.tier,
                timeout=TIMEOUT_SECONDS,
            )
            parsed, status, error = interpret(raw)
        except ProviderQuotaError as exc:
            # The quota does not come back within a run: stop sending, record the rest as
            # failed rows with this reason; --reuse re-calls exactly those next time.
            inputs.quota_exhausted = True
            error = f"{type(exc).__name__}: {exc}"[:500]
        except ProviderRateLimitError as exc:
            # One rejection is transient (the adapter already retried); several in a row is
            # a usage window (Codex's five hours), which the run cannot wait out either.
            inputs.limit_errors_in_a_row += 1
            if inputs.limit_errors_in_a_row >= LIMIT_ERRORS_TO_STOP:
                inputs.quota_exhausted = True
            error = f"{type(exc).__name__}: {exc}"[:500]
        except Exception as exc:  # noqa: BLE001 - one failed call is a row, not a crash
            error = f"{type(exc).__name__}: {exc}"[:500]
        else:
            inputs.limit_errors_in_a_row = 0
        seconds = round(time.perf_counter() - t0, 2)
    record = CallRecord(
        contact_id=contact_id,
        status=status,
        seconds=seconds,
        error=error,
        ranking=(parsed or {}).get("ranking") if parsed else None,
        missing=int((parsed or {}).get("missing", 0)) if parsed else 0,
        parsed=parsed,
    )
    write_json(
        folder / f"{contact_id}.json",
        {
            **asdict(record),
            "method": method,
            "lang": lang,
            "provider": inputs.provider.name,
            "model": inputs.provider.resolved_model,
            "tier": inputs.provider.resolved_tier,
            "provider_cli_version": inputs.provider_cli_version,
            "prompt_version": _prompts.PROMPT_VERSION,
            "database_sha256": inputs.db_sha256,
            "prompt": prompt,
            "system_prompt": system_prompt,
            "raw": raw,
            **(extra or {}),
        },
    )
    return record


def ranking_interpreter(ids: list[str]) -> Callable[[Any], tuple[dict[str, Any], str, str]]:
    """The ``interpret`` of a ranking method: the strict parser over its candidate ids."""

    def interpret(raw: Any) -> tuple[dict[str, Any], str, str]:
        """Parse `raw` against `ids` and package the result as `(parsed, status, error)`."""
        ranking, status, missing, error = parse_ranking(raw, ids)
        return {"ranking": ranking, "missing": len(missing), "missing_ids": missing}, status, error

    return interpret


# ---------------------------------------------------------------------------
# From rankings to a score matrix
# ---------------------------------------------------------------------------


def subset_arena(arena: Arena, contact_ids: list[int]) -> Arena:
    """The arena restricted to ``contact_ids`` (in contact-id order), same catalogue."""
    wanted = set(contact_ids)
    customers = [c for c in arena.customers if c.contact_id in wanted]
    found = {c.contact_id for c in customers}
    if found != wanted:
        raise LookupError(f"contacts not in the arena: {sorted(wanted - found)}")
    return Arena(
        customers=customers, catalog=arena.catalog, all_asins=arena.all_asins, lang=arena.lang
    )


def scores_from_rankings(
    arena: Arena,
    per_customer: list[tuple[list[str], list[int], list[str] | None]],
) -> np.ndarray:
    """``k − position`` for the candidates a customer's call ordered, ``-inf`` elsewhere.

    ``per_customer`` aligns with ``arena.customers``: ``(ids, item_idx, ranking)`` where
    ``ids[n]`` labels ``item_idx[n]`` and ``ranking`` is the model's order (None for
    a failed call: every candidate stays ``-inf`` and the seeded tie-break of the
    protocol ranks them at random, the same way an arm without an opinion is scored).
    """
    out = np.full((arena.n_customers, arena.n_items), NEG_INF, dtype=np.float32)
    for u, (ids, item_idx, ranking) in enumerate(per_customer):
        if not ranking:
            continue
        by_id = dict(zip(ids, item_idx, strict=True))
        k = len(ids)
        for pos, cid in enumerate(ranking):
            out[u, by_id[cid]] = float(k - pos)
    return out


def als_order(
    inputs: Inputs, customer: Customer, item_idx: list[int]
) -> tuple[list[int], list[float]]:
    """``item_idx`` sorted by the ALS score of ``customer`` (best first) with the scores."""
    row = inputs.als_scores[inputs.row_of(customer.contact_id)]
    order = sorted(item_idx, key=lambda j: -float(row[j]))
    return order, [float(row[j]) for j in order]


def als_top(inputs: Inputs, customer: Customer, k: int) -> tuple[list[int], list[float]]:
    """The ``k`` best catalogue items of ``customer`` by ALS with the history masked, best first."""
    arena = inputs.arenas["en"]
    row = np.array(inputs.als_scores[inputs.row_of(customer.contact_id)], dtype=np.float32)
    hist = [arena.asin_to_idx[a] for a in customer.history_asins if a in arena.asin_to_idx]
    row[hist] = NEG_INF
    top = np.argsort(-row, kind="stable")[:k]
    return [int(j) for j in top], [float(row[j]) for j in top]


# ---------------------------------------------------------------------------
# The ranking loop shared by the methods that order candidates
# ---------------------------------------------------------------------------


async def run_ranking(
    inputs: Inputs,
    *,
    method: str,
    arena: Arena,
    system_prompt: str,
    lists: list[tuple[list[int], list[float] | None]],
    als_order_shown: bool,
    profile_lines: dict[int, list[str]] | None = None,
) -> tuple[list[CallRecord], np.ndarray]:
    """One recorded call per customer of ``arena``, then the score matrix.

    ``lists[u]`` is the candidate list of ``arena.customers[u]`` in the order the prompt
    shows it (catalogue indices) with the ALS scores to print, or None when the method
    shows none. Returns the call records (one per customer, in order) and the matrix.
    """
    lang = arena.lang
    sem = asyncio.Semaphore(inputs.concurrency)
    tasks = []
    labelled: list[tuple[list[str], list[int]]] = []
    for customer, (item_idx, shown_scores) in zip(arena.customers, lists, strict=True):
        ids = candidate_ids(len(item_idx))
        labelled.append((ids, item_idx))
        prompt = _prompts.user_prompt(
            lang,
            contact_id=customer.contact_id,
            history_lines=history_lines(customer, arena),
            candidate_lines=candidate_lines(ids, item_idx, arena, shown_scores),
            als_order=als_order_shown,
            profile_lines=(profile_lines or {}).get(customer.contact_id),
        )
        tasks.append(
            recorded_call(
                inputs,
                method=method,
                lang=lang,
                contact_id=customer.contact_id,
                prompt=prompt,
                system_prompt=system_prompt,
                schema=_prompts.ranking_schema(len(ids)),
                sem=sem,
                interpret=ranking_interpreter(ids),
                extra={
                    "candidates": {
                        cid: arena.all_asins[j] for cid, j in zip(ids, item_idx, strict=True)
                    },
                    "held_out": customer.held_out.asin,
                },
            )
        )
    records = list(await asyncio.gather(*tasks))
    for customer, (ids, item_idx), rec in zip(arena.customers, labelled, records, strict=True):
        hidden = arena.asin_to_idx.get(customer.held_out.asin)
        hidden_cid = next((c for c, j in zip(ids, item_idx, strict=True) if j == hidden), None)
        rec.hidden_dropped = bool(
            rec.status == "partial" and hidden_cid in ((rec.parsed or {}).get("missing_ids") or [])
        )
    per_customer = [
        (ids, item_idx, rec.ranking) for (ids, item_idx), rec in zip(labelled, records, strict=True)
    ]
    return records, scores_from_rankings(arena, per_customer)


__all__ = [
    "CONCURRENCY",
    "SHUFFLE_STREAM",
    "TIMEOUT_SECONDS",
    "CallRecord",
    "Inputs",
    "MethodOutput",
    "als_order",
    "als_top",
    "calls_folder",
    "candidate_ids",
    "candidate_lines",
    "history_lines",
    "parse_ranking",
    "ranking_interpreter",
    "recorded_call",
    "run_ranking",
    "scores_from_rankings",
    "shuffled",
    "subset_arena",
    "title_of",
]
