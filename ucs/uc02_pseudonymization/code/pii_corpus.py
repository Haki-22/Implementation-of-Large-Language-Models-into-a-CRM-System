"""The planted-PII corpus of UC-02, generated from the CRM rows (D-UC02-1).

The corpus is the exam paper for the detector: Czech CRM texts in which the
generator knows exactly which characters are personal data, because it put them
there. Nothing is trained on it.

Three steps:

1. **Plan.** A seeded planner picks a contact per message from ``substrate.db``
   (``uc_contacts`` joined with ``uc_companies``) and decides which of that
   contact's stored fields are planted: the name (nominative, plus one oblique
   form from :mod:`czech_names`), e-mail, phone, address, birth date, bank
   account, IBAN, the employer's name, IČO and DIČ. A rodné číslo comes from
   the identifier generator because no contact stores one. About 5 % of the
   messages also carry an IČO with a wrong check digit as a negative control.
2. **Render.** The ``model`` renderer asks a model for a natural CRM note or
   e-mail that embeds every supplied string verbatim; the ``mock`` renderer
   builds the text from sentence templates without any model call and is the
   offline backup. Both render the same plan, so the two corpora share the
   planted values.
3. **Verify and locate.** Every planted string is searched verbatim; a message
   that lost one is regenerated (model) or fails (mock). A surname-stem count
   catches name forms the renderer added on its own. The gold record of a span
   carries its type, offsets, form label, ``inflected`` flag and the contact id
   as ``entity_id``.

Outputs: ``snapshots/uc02-pii-corpus.json`` + ``uc02-pii-gold.jsonl`` (the
corpus of record) or the ``-mock`` pair (the backup), plus
``corpus-manifest.json`` describing what was generated from what.

Run from the project root::

    python -m ucs.uc02_pseudonymization.code.pii_corpus --renderer mock --force
    python -m ucs.uc02_pseudonymization.code.pii_corpus --renderer model --provider codex --force --force-llm
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as _dt
import hashlib
import json
import logging
import random
import re
import sqlite3
import unicodedata
from pathlib import Path
from typing import Any

from ucs.uc02_pseudonymization.code.czech_names import person_forms
from ucs.uc02_pseudonymization.code.pseudonymizer import surname_stem
from utils.czech_identifiers.generate import generate_rc
from utils.czech_identifiers.validate import ico_check_digit
from utils.file_safety import require_can_write
from utils.generation import DEFAULT_TIER, generate_text, resolve_model, resolve_tier
from utils.llm_switch import add_force_llm_argument, apply_force_llm
from utils.paths import SUBSTRATE_DB, UC02_DIR, UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Taxonomy and plan constants
# ---------------------------------------------------------------------------

PII_TYPES: tuple[str, ...] = (
    "PERSON",
    "EMAIL",
    "PHONE",
    "ADDRESS",
    "DATE",
    "BBAN",
    "IBAN_CZ",
    "ORG",
    "ICO",
    "DIC",
    "RC",
)

# Draw weights: how often a type is asked for when the contact has it.
_TYPE_WEIGHTS: dict[str, int] = {
    "PERSON": 6,
    "EMAIL": 4,
    "PHONE": 4,
    "ADDRESS": 3,
    "DATE": 2,
    "BBAN": 2,
    "IBAN_CZ": 2,
    "ORG": 3,
    "ICO": 2,
    "DIC": 2,
    "RC": 2,
}

# Items per message by density band, and the band cycle over the corpus
# (about 50 % dense, 30 % moderate, 20 % sparse).
_DENSITY_ITEMS: dict[str, int] = {"dense": 4, "moderate": 2, "sparse": 1}
_DENSITY_CYCLE: tuple[str, ...] = (
    "dense", "moderate", "dense", "sparse", "dense",
    "moderate", "dense", "moderate", "dense", "sparse",
)  # fmt: skip

_NEGATIVE_CONTROL_RATE = 0.05
_CANARY_TYPES = frozenset({"PERSON", "RC"})

SCENARIO_BRIEFS: tuple[dict[str, str], ...] = (
    {"scenario": "Interní poznámka z reklamačního telefonátu — zákazník volá kvůli vadnému zboží a žádá o vyřešení reklamace.", "channel": "note"},
    {"scenario": "E-mail potvrzující vrácení peněz za zrušenou objednávku, včetně čísla účtu pro zaslání částky.", "channel": "email"},
    {"scenario": "Žádost zákazníka o změnu doručovací adresy u rozpracované objednávky.", "channel": "email"},
    {"scenario": "Interní poznámka k B2B poptávce — firemní zákazník se ptá na velkoobchodní ceny a fakturační údaje.", "channel": "note"},
    {"scenario": "E-mail řešící problém s platbou — zákazníkovi se nepodařilo dokončit úhradu objednávky.", "channel": "email"},
    {"scenario": "Interní poznámka o zpoždění dodávky — přepravce nahlásil problém s doručením balíku.", "channel": "note"},
    {"scenario": "E-mail s odpovědí na dotaz zákazníka ke konkrétnímu produktu a jeho dostupnosti.", "channel": "email"},
    {"scenario": "Interní poznámka k záruční reklamaci — zákazník uplatňuje záruku na zakoupený spotřebič.", "channel": "note"},
    {"scenario": "E-mail potvrzující aktualizaci kontaktních údajů na zákaznickém účtu.", "channel": "email"},
    {"scenario": "Interní poznámka z hovoru, kde zákazník žádá o storno objednávky a vystavení dobropisu.", "channel": "note"},
    {"scenario": "E-mail s nabídkou náhradního termínu doručení po neúspěšném prvním pokusu.", "channel": "email"},
    {"scenario": "Interní poznámka k dotazu na stav vyřízení objednávky.", "channel": "note"},
    {"scenario": "E-mail s krátkým potvrzením přijetí objednávky a předpokládaného data doručení.", "channel": "email"},
    {"scenario": "Interní poznámka s krátkým záznamem o zpětném zavolání zákazníkovi.", "channel": "note"},
    {"scenario": "E-mail s poděkováním za nákup a žádostí o vyplnění krátké recenze.", "channel": "email"},
    {"scenario": "Interní poznámka o předání podnětu zákazníka na obchodní oddělení.", "channel": "note"},
    {"scenario": "E-mail s upozorněním, že sledovaný produkt je opět skladem.", "channel": "email"},
    {"scenario": "Interní poznámka k žádosti zákazníka o vystavení duplikátu faktury.", "channel": "note"},
)  # fmt: skip


# ---------------------------------------------------------------------------
# CRM rows
# ---------------------------------------------------------------------------

_ROW_SQL = """
select c.id, c.first_name, c.last_name, c.gender, c.email, c.phone,
       c.full_street, c.city, c.postal_code, c.date_of_birth,
       c.bank_account, c.iban, co.name, co.ico, co.dic
from uc_contacts c left join uc_companies co on co.id = c.company_id
where c.is_clean = 1
order by c.id
"""


def load_contact_rows(db_path: Path = SUBSTRATE_DB) -> list[dict[str, Any]]:
    """Return the clean contacts with their employer, as plain dicts."""
    keys = (
        "contact_id", "first_name", "last_name", "gender", "email", "phone",
        "full_street", "city", "postal_code", "date_of_birth",
        "bank_account", "iban", "company_name", "ico", "dic",
    )  # fmt: skip
    with sqlite3.connect(db_path) as db:
        return [dict(zip(keys, row)) for row in db.execute(_ROW_SQL)]


def format_postal_code(raw: str) -> str:
    """Return a Czech postal code as ``NNN NN``."""
    digits = "".join(ch for ch in raw if ch.isdigit())
    return f"{digits[:3]} {digits[3:]}" if len(digits) == 5 else raw


def format_date(iso: str) -> str:
    """Return an ISO date as the Czech ``D. M. YYYY``."""
    d = _dt.date.fromisoformat(iso)
    return f"{d.day}. {d.month}. {d.year}"


def available_values(row: dict[str, Any], rng: random.Random) -> dict[str, str]:
    """Return the surface value of every type this contact can plant."""
    values: dict[str, str] = {}
    if row.get("first_name") and row.get("last_name"):
        values["PERSON"] = f"{row['first_name']} {row['last_name']}"
    if row.get("email"):
        values["EMAIL"] = row["email"]
    if row.get("phone"):
        values["PHONE"] = row["phone"]
    if row.get("full_street") and row.get("city") and row.get("postal_code"):
        values["ADDRESS"] = (
            f"{row['full_street']}, {format_postal_code(row['postal_code'])} {row['city']}"
        )
    if row.get("date_of_birth"):
        values["DATE"] = format_date(str(row["date_of_birth"])[:10])
    if row.get("bank_account"):
        values["BBAN"] = row["bank_account"]
    if row.get("iban"):
        values["IBAN_CZ"] = row["iban"]
    if row.get("company_name"):
        values["ORG"] = row["company_name"]
    if row.get("ico"):
        values["ICO"] = row["ico"]
    if row.get("dic"):
        values["DIC"] = row["dic"]
    # No contact stores a rodné číslo (by design); one is generated for the
    # message from the contact's gender and a plausible birth year.
    year = (
        int(str(row["date_of_birth"])[:4]) if row.get("date_of_birth") else rng.randint(1955, 2004)
    )
    values["RC"] = generate_rc(
        year, rng.randint(1, 12), "f" if row.get("gender") == "f" else "m", rng
    )
    return values


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def _invalid_ico(rng: random.Random) -> str:
    """Return an IČO-shaped string whose check digit is wrong (negative control)."""
    seven = str(rng.randint(1, 9)) + "".join(str(rng.randint(0, 9)) for _ in range(6))
    wrong = (ico_check_digit(seven) + rng.randint(1, 9)) % 10
    return seven + str(wrong)


def _canonical(pii_type: str, surface: str) -> str:
    """Return the comparison form of a value (folded e-mail, digits-only numbers)."""
    collapsed = " ".join(surface.split())
    if pii_type == "EMAIL":
        decomposed = unicodedata.normalize("NFKD", collapsed)
        return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    if pii_type in {"PHONE", "IBAN_CZ", "BBAN", "ICO", "DIC", "RC"}:
        return (
            collapsed.replace(" ", "").replace("-", "")
            if pii_type != "BBAN"
            else collapsed.replace(" ", "")
        )
    return collapsed


def plan_corpus(rows: list[dict[str, Any]], n: int, seed: int) -> list[dict[str, Any]]:
    """Return ``n`` message plans: contact, scenario, planted strings with their labels.

    Each plan lists ``items``: ``{pii_type, surface_form, form, inflected}``; a
    PERSON always plants the nominative and, when the name supports it, one
    oblique form chosen at random. Everything is decided here, so the mock and
    the model renderer receive the same strings.
    """
    if n < 0:
        raise ValueError(f"n must be non-negative, got {n}")
    rng = random.Random(seed)
    plans: list[dict[str, Any]] = []
    for i in range(n):
        row = rng.choice(rows)
        density = _DENSITY_CYCLE[i % len(_DENSITY_CYCLE)]
        brief = SCENARIO_BRIEFS[i % len(SCENARIO_BRIEFS)]
        values = available_values(row, rng)
        wanted = _DENSITY_ITEMS[density]
        chosen: list[str] = []
        pool = [t for t in PII_TYPES if t in values]
        while len(chosen) < wanted and len(chosen) < len(pool):
            candidates = [t for t in pool if t not in chosen]
            weights = [_TYPE_WEIGHTS[t] for t in candidates]
            chosen.append(rng.choices(candidates, weights=weights, k=1)[0])
        items: list[dict[str, Any]] = []
        for pii_type in chosen:
            items.append(
                {
                    "pii_type": pii_type,
                    "surface_form": values[pii_type],
                    "form": "nom",
                    "inflected": False,
                }
            )
            if pii_type == "PERSON" and row.get("gender") in ("m", "f"):
                forms = person_forms(row["first_name"], row["last_name"], row["gender"])
                oblique = [label for label in forms if label != "nom"]
                if oblique:
                    label = rng.choice(oblique)
                    items.append(
                        {
                            "pii_type": "PERSON",
                            "surface_form": forms[label],
                            "form": label,
                            "inflected": True,
                        }
                    )
        near_miss = _invalid_ico(rng) if rng.random() < _NEGATIVE_CONTROL_RATE else None
        plans.append(
            {
                "message_id": f"uc02-msg-{i:05d}",
                "contact_id": row["contact_id"],
                "gender": row.get("gender"),
                "scenario": brief["scenario"],
                "channel": brief["channel"],
                "density_band": density,
                "items": items,
                "near_miss_ico": near_miss,
            }
        )
    return plans


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------

_MOCK_SENTENCES: dict[str, tuple[str, ...]] = {
    "PERSON": ("Volal {v}, řešili jsme jeho objednávku.", "Zákazník {v} žádá o vyjádření do konce týdne.", "Případ zakládá {v}."),
    "PERSON_oblique": ("Domluveno s {v}, ozveme se zpět.", "Potvrzení pošleme {v} e-mailem.", "Podle {v} zboží dorazilo poškozené."),
    "EMAIL": ("Odpověď poslat na {v}.", "Kontaktní e-mail je {v}.", "Fakturu zaslat na adresu {v}."),
    "PHONE": ("Zavolat zpět na {v}.", "Telefon pro dopolední hovor: {v}.", "Číslo k zastižení je {v}."),
    "ADDRESS": ("Zásilku doručit na {v}.", "Nová doručovací adresa: {v}.", "Reklamované zboží vyzvedne kurýr na {v}."),
    "DATE": ("Datum narození pro ověření: {v}.", "Ověřeno podle data narození {v}.", "Ve formuláři uvedeno narození {v}."),
    "BBAN": ("Vrácení platby na účet {v}.", "Dobropis proplatit na {v}.", "Číslo účtu pro refundaci: {v}."),
    "IBAN_CZ": ("Platba přišla z účtu {v}.", "Pro zahraniční platbu uveden IBAN {v}.", "Vrátit částku na IBAN {v}."),
    "ORG": ("Faktura vystavena na firmu {v}.", "Objednávka jde přes {v}.", "Firemní zákazník: {v}."),
    "ICO": ("IČO odběratele {v}.", "Fakturační údaje: IČO {v}.", "Podle rejstříku IČO {v}."),
    "DIC": ("DIČ pro fakturaci {v}.", "Plátce DPH, DIČ {v}.", "Na faktuře uvést DIČ {v}."),
    "RC": ("Rodné číslo uvedené ve formuláři je {v}.", "Pro ověření totožnosti zadáno rodné číslo {v}.", "Ve smlouvě figuruje rodné číslo {v}."),
}  # fmt: skip


def render_mock(plan: dict[str, Any], rng: random.Random) -> str:
    """Render a message from sentence templates; every planted string appears verbatim."""
    intro = (
        f"Poznámka: {plan['scenario']}"
        if plan["channel"] == "note"
        else f"Dobrý den, píšeme vám k této věci: {plan['scenario']}"
    )
    sentences = [intro]
    for item in plan["items"]:
        key = (
            "PERSON_oblique"
            if item["pii_type"] == "PERSON" and item["inflected"]
            else item["pii_type"]
        )
        sentence = rng.choice(_MOCK_SENTENCES[key]).format(v=item["surface_form"])
        sentences.append(sentence[:-1] if sentence.endswith("..") else sentence)
    if plan["near_miss_ico"]:
        sentences.append(f"Interní kontrolní označení {plan['near_miss_ico']}.")
    sentences.append(
        "Záznam uložen." if plan["channel"] == "note" else "S pozdravem, zákaznická podpora."
    )
    return " ".join(sentences)


_MODEL_SYSTEM_PROMPT = (
    "Píšeš výhradně česky jako pracovník zákaznické podpory českého e-shopu. "
    "Vracíš pouze samotný text zprávy, bez nadpisů, odrážek a komentářů."
)


def build_model_prompt(plan: dict[str, Any]) -> str:
    """Return the prompt that asks a model for prose around the planted strings."""
    kind = "interní poznámku v CRM" if plan["channel"] == "note" else "e-mail zákazníkovi"
    lines = []
    for item in plan["items"]:
        if item["pii_type"] == "PERSON":
            role = (
                "jméno zákazníka v 1. pádě"
                if not item["inflected"]
                else "totéž jméno ve skloněném tvaru, použij ho v další větě"
            )
        else:
            role = {
                "EMAIL": "e-mail",
                "PHONE": "telefon",
                "ADDRESS": "adresa",
                "DATE": "datum narození",
                "BBAN": "číslo účtu",
                "IBAN_CZ": "IBAN",
                "ORG": "název firmy",
                "ICO": "IČO",
                "DIC": "DIČ",
                "RC": "rodné číslo",
            }[item["pii_type"]]
        lines.append(f'  - {role}: "{item["surface_form"]}"')
    near = (
        f'\nDo textu navíc přirozeně vlož toto interní označení, doslova: "{plan["near_miss_ico"]}".\n'
        if plan["near_miss_ico"]
        else ""
    )
    return (
        f"Napiš realistickou, přirozenou {kind} v češtině (3 až 6 vět).\n\n"
        f"Situace: {plan['scenario']}\n\n"
        "Do textu zapracuj následující údaje. Každý z nich použij PŘESNĚ tak, jak je "
        "uveden, znak po znaku, včetně mezer, diakritiky a interpunkce. Jméno osoby "
        "použij pouze v uvedených tvarech a jen tolikrát, kolik tvarů je uvedeno; "
        "nepřidávej žádný další tvar jména ani jiné jméno:\n"
        + "\n".join(lines)
        + near
        + "\nText napiš jako jeden souvislý celek. Nevypisuj údaje do seznamu, vplet je do vět. "
        "Vrať pouze samotný text zprávy."
    )


async def render_model(
    plan: dict[str, Any], *, provider: str, model: str | None, tier: str | None, timeout: int
) -> str:
    """Ask the model for the message text (one call)."""
    return await generate_text(
        build_model_prompt(plan),
        provider=provider,
        system_prompt=_MODEL_SYSTEM_PROMPT,
        model=model,
        tier=tier,
        timeout=timeout,
    )


# ---------------------------------------------------------------------------
# Verification and gold
# ---------------------------------------------------------------------------


def verify_text(text: str, plan: dict[str, Any]) -> list[str]:
    """Return the problems a rendered text has, empty when it is acceptable.

    Checks: every planted string present verbatim; the surname stem occurs
    exactly as many times as name forms were planted (a form the renderer added
    on its own would be an unlabelled name); no placeholder-shaped token; a
    length between 80 and 1 500 characters.
    """
    issues: list[str] = []
    for item in plan["items"]:
        if item["surface_form"] not in text:
            issues.append(f"missing {item['pii_type']} {item['surface_form']!r}")
    if plan["near_miss_ico"] and plan["near_miss_ico"] not in text:
        issues.append("missing near-miss IČO")
    persons = [item for item in plan["items"] if item["pii_type"] == "PERSON"]
    if persons:
        # Count the surname stem outside the other planted strings (an e-mail
        # local part carries the surname too and is not a name mention).
        scrubbed = text
        for item in plan["items"]:
            if item["pii_type"] != "PERSON":
                scrubbed = scrubbed.replace(item["surface_form"], " " * len(item["surface_form"]))
        words = {item["surface_form"].split()[-1].lower() for item in persons}
        alternatives = {re.escape(w) + r"\b" for w in words} | {
            re.escape(surname_stem(w)) + r"\w*" for w in words
        }
        pattern = r"\b(?:" + "|".join(sorted(alternatives)) + ")"
        occurrences = len(re.findall(pattern, scrubbed, flags=re.IGNORECASE))
        if occurrences != len(persons):
            issues.append(
                f"surname {sorted(words)} occurs {occurrences}x, {len(persons)} forms planted"
            )
    if re.search(r"<[A-Z][A-Z_]*_\d+[a-z]?>", text):
        issues.append("placeholder-shaped token in text")
    if not 80 <= len(text) <= 1500:
        issues.append(f"length {len(text)} outside 80..1500")
    return issues


def locate_gold(text: str, plan: dict[str, Any]) -> list[dict[str, Any]]:
    """Return the gold spans of a rendered text: every verbatim occurrence of every planted string.

    Longer strings are located first and their characters reserved, so a surname
    form inside a full-name form is not marked twice.
    """
    spans: list[dict[str, Any]] = []
    taken: set[int] = set()
    context_tag = "formal" if plan["channel"] == "email" else "informal"
    for item in sorted(plan["items"], key=lambda it: -len(it["surface_form"])):
        surface = item["surface_form"]
        start = text.find(surface)
        while start != -1:
            end = start + len(surface)
            if not (set(range(start, end)) & taken):
                taken.update(range(start, end))
                spans.append(
                    {
                        "span_start": start,
                        "span_end": end,
                        "pii_type": item["pii_type"],
                        "surface_form": surface,
                        "canonical_form": _canonical(item["pii_type"], surface),
                        "form": item["form"],
                        "inflected": item["inflected"],
                        "entity_id": plan["contact_id"]
                        if item["pii_type"]
                        in ("PERSON", "EMAIL", "PHONE", "ADDRESS", "DATE", "BBAN", "IBAN_CZ", "RC")
                        else None,
                        "context_tag": context_tag,
                        "is_canary": item["pii_type"] in _CANARY_TYPES,
                    }
                )
            start = text.find(surface, end)
    spans.sort(key=lambda s: s["span_start"])
    return spans


# ---------------------------------------------------------------------------
# Corpus generation
# ---------------------------------------------------------------------------


async def generate_corpus(
    rows: list[dict[str, Any]],
    *,
    n: int,
    seed: int,
    renderer: str,
    provider: str = "codex",
    model: str | None = None,
    tier: str | None = DEFAULT_TIER,
    timeout: int = 300,
    max_tries: int = 3,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Plan, render, verify and locate ``n`` messages; return ``(corpus, gold)``.

    With ``renderer="model"`` a message whose text fails verification is asked
    for again up to ``max_tries`` times; if it still fails, the mock rendering
    is used for that message and the corpus row says so (``renderer: "mock
    (fallback)"``, ``verification.issues``), so the reviewer sees it.
    """
    if renderer not in ("mock", "model"):
        raise ValueError("renderer must be 'mock' or 'model'")
    plans = plan_corpus(rows, n, seed)
    mock_rng = random.Random(seed + 1)
    corpus: list[dict[str, Any]] = []
    gold: list[dict[str, Any]] = []
    for plan in plans:
        used = renderer
        tries = 0
        issues: list[str] = []
        text = ""
        if renderer == "model":
            for tries in range(1, max_tries + 1):
                try:
                    text = (
                        await render_model(
                            plan, provider=provider, model=model, tier=tier, timeout=timeout
                        )
                    ).strip()
                except Exception as exc:  # noqa: BLE001 — recorded per message, never fatal
                    issues = [f"generation failed: {exc}"]
                    text = ""
                    continue
                issues = verify_text(text, plan)
                if not issues:
                    break
            if issues:
                logger.warning(
                    "%s: model text rejected after %d tries (%s); mock fallback",
                    plan["message_id"],
                    tries,
                    "; ".join(issues),
                )
                used = "mock (fallback)"
                text = render_mock(plan, mock_rng)
        else:
            text = render_mock(plan, mock_rng)
            issues = verify_text(text, plan)
            if issues:
                raise RuntimeError(f"{plan['message_id']}: mock text failed verification: {issues}")
        spans = locate_gold(text, plan)
        near_misses = []
        if plan["near_miss_ico"]:
            at = text.find(plan["near_miss_ico"])
            near_misses.append(
                {
                    "surface_form": plan["near_miss_ico"],
                    "near_miss_type": "ICO_INVALID_CHECKSUM",
                    "span_start": at if at != -1 else None,
                    "span_end": at + len(plan["near_miss_ico"]) if at != -1 else None,
                }
            )
        corpus.append(
            {
                "message_id": plan["message_id"],
                "text": text,
                "contact_id": plan["contact_id"],
                "scenario": plan["scenario"],
                "channel": plan["channel"],
                "density_band": plan["density_band"],
                "renderer": used,
                "tries": tries if renderer == "model" else 0,
                "verification": {"ok": not issues, "issues": issues},
                "planted": [
                    {
                        "pii_type": it["pii_type"],
                        "surface_form": it["surface_form"],
                        "form": it["form"],
                    }
                    for it in plan["items"]
                ],
                "is_negative_control": plan["near_miss_ico"] is not None,
                "planted_pii_count": len(plan["items"]),
                "gold_span_count": len(spans),
                "near_misses": near_misses,
            }
        )
        gold.extend({"message_id": plan["message_id"], **span} for span in spans)
    return corpus, gold


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------


def snapshot_paths(as_backup: bool) -> tuple[Path, Path]:
    """Return the corpus and gold paths: the record pair, or the ``-mock`` backup pair."""
    if not as_backup:
        return UC02_PII_CORPUS_SNAPSHOT, UC02_PII_GOLD_SNAPSHOT
    return (
        UC02_PII_CORPUS_SNAPSHOT.with_name("uc02-pii-corpus-mock.json"),
        UC02_PII_GOLD_SNAPSHOT.with_name("uc02-pii-gold-mock.jsonl"),
    )


def write_snapshots(
    corpus: list[dict[str, Any]],
    gold: list[dict[str, Any]],
    corpus_path: Path,
    gold_path: Path,
    *,
    manifest: dict[str, Any] | None = None,
    overwrite: bool = False,
) -> None:
    """Write the corpus JSON, the gold JSONL and, when given, the manifest next to them."""
    corpus_file = require_can_write(
        corpus_path, overwrite=overwrite, artifact="PII corpus snapshot"
    )
    gold_file = require_can_write(gold_path, overwrite=overwrite, artifact="PII gold snapshot")
    corpus_file.write_text(
        json.dumps(corpus, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    with gold_file.open("w", encoding="utf-8") as handle:
        for record in gold:
            handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    if manifest is not None:
        manifest = {
            **manifest,
            "corpus_file": corpus_file.name,
            "gold_file": gold_file.name,
            "corpus_sha256": hashlib.sha256(corpus_file.read_bytes()).hexdigest(),
            "gold_sha256": hashlib.sha256(gold_file.read_bytes()).hexdigest(),
        }
        manifest_path = corpus_file.with_name(
            "corpus-manifest.json"
            if corpus_file == UC02_PII_CORPUS_SNAPSHOT
            else "corpus-manifest-mock.json"
        )
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    print(f"Wrote {len(corpus)} messages to {corpus_file}")
    print(f"Wrote {len(gold)} gold spans to {gold_file}")


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser."""
    parser = argparse.ArgumentParser(
        description="Generate the UC-02 planted-PII corpus from the CRM rows."
    )
    add_force_llm_argument(parser)
    parser.add_argument("--n", type=int, default=100)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--renderer", choices=("mock", "model"), default="mock")
    parser.add_argument("--provider", default="codex")
    parser.add_argument("--model", default=None)
    parser.add_argument("--tier", default=DEFAULT_TIER)
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--db", type=Path, default=SUBSTRATE_DB)
    parser.add_argument("--corpus-out", type=Path, default=None, help="Override the corpus path.")
    parser.add_argument("--gold-out", type=Path, default=None, help="Override the gold path.")
    parser.add_argument(
        "--as-backup",
        action="store_true",
        help="Write the -mock backup pair instead of the corpus of record.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite existing snapshots.")
    return parser


def main(argv: list[str] | None = None) -> None:
    """CLI entry point: plan, render, verify, write."""
    args = build_parser().parse_args(argv)
    apply_force_llm(args)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    rows = load_contact_rows(args.db)
    corpus, gold = asyncio.run(
        generate_corpus(
            rows,
            n=args.n,
            seed=args.seed,
            renderer=args.renderer,
            provider=args.provider,
            model=args.model,
            tier=args.tier,
            timeout=args.timeout,
        )
    )
    default_corpus, default_gold = snapshot_paths(args.as_backup)
    flagged = [
        m["message_id"]
        for m in corpus
        if not m["verification"]["ok"] or m["renderer"] != args.renderer
    ]
    manifest = {
        "corpus_id": f"uc02-corpus-v2-{args.renderer}" + ("-backup" if args.as_backup else ""),
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "n": args.n,
        "seed": args.seed,
        "renderer": args.renderer,
        "provider": args.provider if args.renderer == "model" else None,
        "model": resolve_model(args.provider, args.model) if args.renderer == "model" else None,
        "tier": resolve_tier(args.provider, args.tier, args.model)
        if args.renderer == "model"
        else None,
        "contacts_available": len(rows),
        "db": str(args.db.relative_to(UC02_DIR.parent.parent))
        if args.db.is_relative_to(UC02_DIR.parent.parent)
        else str(args.db),
        "types": list(PII_TYPES),
        "gold_spans": len(gold),
        "flagged_messages": flagged,
    }
    write_snapshots(
        corpus,
        gold,
        args.corpus_out or default_corpus,
        args.gold_out or default_gold,
        manifest=manifest,
        overwrite=args.force,
    )
    if flagged:
        print(f"{len(flagged)} message(s) need a look: {', '.join(flagged)}")


if __name__ == "__main__":
    main()
