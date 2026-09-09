"""The three Czech prompts behind the outputs for UC-01: recommendation reason, persona, aspects.

EDIT THE CZECH TEXT HERE. Every prompt follows the seven rules of the thesis's
chapter on prompt engineering: an explicit role, reader and goal; the output format
fixed by a JSON schema the provider enforces; one worked example; the chain (classical
recommendation -> model sentence); thinking time through the provider's reasoning tier;
a fixed population and a log of every call; and this file as the versioned catalogue.
The May prompts (``llm_outputs/prompts.py`` v0.3, English skeleton with Czech output)
were rewritten here in Czech, with purchase ids instead of ASINs so that a reason's
evidence can be checked against the history, and with a verbatim-quote rule for the
aspects so that a quote can be checked against the review text.

``PROMPT_VERSION`` is recorded in every run; bump it when any text here changes.
"""

from __future__ import annotations

from typing import Any

# 1.0.0 (2026-09-07): Czech rewrite of the May prompts; evidence by purchase id; quotes verbatim.
# 1.0.1 (2026-09-07): after the four-provider smoke: the reason must not name the purchase ids
# (two providers wrote "(H03, H22)" into the sentence) and must be a sentence, not JSON.
PROMPT_VERSION = "1.0.1"

HISTORY_CAP = 40  # newest purchases shown to the model in the reason prompt
REVIEW_CHARS_CAP = 8_000  # Czech review text shown to the aspects prompt
PERSONA_REVIEWS = 5  # longest reviews shown to the persona prompt
PERSONA_REVIEW_CHARS = 300

# ---------------------------------------------------------------------------
# Recommendation reason: one Czech sentence, grounded in cited purchases
# ---------------------------------------------------------------------------

REASON_SYSTEM = (
    "Jsi copywriter českého e-shopu s elektronikou a příslušenstvím. Dostaneš nákupní "
    "historii jednoho zákazníka (každý řádek má identifikátor H01, H02 …, datum, hodnocení "
    "hvězdičkami a název produktu) a jeden doporučený produkt. Napiš jednu českou větu, proč "
    "právě tento produkt právě tomuto zákazníkovi: opři ji o konkrétní nákupy z historie "
    "(značka, typ produktu, doplněk k něčemu, co už má).\n\n"
    "Pravidla: nejvýš 30 slov; třetí osoba nebo neosobní tvar, bez oslovení (oslovení a vykání "
    "řeší jiná část systému); bez reklamních frází (žádné „skvělý“, „nepřekonatelný“, "
    "„nezmeškejte“); nic si nevymýšlej, uveď jen to, co historie nese; identifikátory H01, H02 … "
    "do věty nepiš, věta jmenuje produkty, identifikátory patří jen do evidence_ids.\n\n"
    'Vrať pouze JSON podle schématu: {"reason": "<věta>", "evidence_ids": ["<H..>", ...]} '
    "s jedním až třemi identifikátory nákupů, o které se věta opírá.\n\n"
    "Příklad. Historie: H01 2013-02-11 ★4 USB zesilovač FiiO E10; H02 2013-01-04 ★5 Sluchátka "
    "Sony MDR-7506. Doporučený produkt: Redukce 3,5 mm na 6,3 mm jack. Odpověď: "
    '{"reason": "Redukce doplní sluchátka Sony MDR-7506 a zesilovač FiiO E10, takže je půjde '
    'zapojit i do zařízení s velkým jackem.", "evidence_ids": ["H02", "H01"]}'
)

REASON_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "reason": {"type": "string", "maxLength": 240},
        "evidence_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 3,
            "items": {"type": "string", "pattern": "^H[0-9]{2,3}$"},
        },
    },
    "required": ["reason", "evidence_ids"],
    "additionalProperties": False,
}


def reason_prompt(
    contact_id: int,
    lifecycle_label: str | None,
    history_lines: list[str],
    total_purchases: int,
    product_title: str,
    category: str | None,
    description: str | None,
) -> str:
    """The user turn: the customer, the capped history with ids, the recommended product."""
    shown = len(history_lines)
    lines = [
        f"Zákazník Z-{contact_id} (anonymizován). Fáze v e-shopu: {lifecycle_label or 'neznámá'}.",
        f"Nákupní historie ({total_purchases} nákupů, nejnovější první; zobrazeno {shown}):",
        *history_lines,
        "",
        f"Doporučený produkt: {product_title}",
        f"Kategorie: {category or 'neuvedena'}",
        f"Popis (zkrácený): {(description or '').strip()[:200] or 'bez popisu'}",
        "Vrať JSON.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Persona: two Czech sentences about the buying behaviour
# ---------------------------------------------------------------------------

PERSONA_SYSTEM = (
    "Jsi analytik zákazníků českého e-shopu s elektronikou. Dostaneš souhrn chování jednoho "
    "zákazníka: nejčastější kategorie nákupů, počet nákupů a průměrné hodnocení, fázi "
    "v e-shopu, témata zájmu a ukázky jeho recenzí. Popiš zákazníka dvěma českými větami "
    "(30 až 50 slov) tak, aby marketing věděl, co kupuje, jak často se vrací, na jakou cenovou "
    "hladinu míří a čím se odlišuje.\n\n"
    "Pravidla: jen to, co data nesou, žádné stereotypy (bez audio produktů nepiš „audiofil“); "
    "třetí osoba nebo neosobní tvar, bez oslovení; bez reklamních frází; žádné jméno ani osobní "
    "údaj, persona je typ zákazníka. Dobře: „Zákazník opakovaně dokupuje příslušenství k audio "
    "sestavě a vrací se v krátkých cyklech.“ Špatně: „Náročný zákazník, který miluje prémiový "
    "zvuk.“\n\n"
    'Vrať pouze JSON podle schématu: {"label": "<slug_malymi_pismeny_s_podtrzitky>", '
    '"narrative_cs": "<dvě věty>", "tags": ["<3 až 5 štítků>"], '
    '"price_segment": "budget" | "mid" | "premium" | "mixed"}.'
)

PERSONA_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "label": {"type": "string", "maxLength": 60},
        "narrative_cs": {"type": "string", "maxLength": 400},
        "tags": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {"type": "string", "maxLength": 30},
        },
        "price_segment": {"type": "string", "enum": ["budget", "mid", "premium", "mixed"]},
    },
    "required": ["label", "narrative_cs", "tags", "price_segment"],
    "additionalProperties": False,
}


def persona_prompt(
    contact_id: int,
    n_purchases: int,
    mean_rating: float,
    lifecycle_label: str | None,
    top_categories: list[tuple[str, int]],
    topic_labels: list[str],
    review_samples: list[tuple[str, str]],
) -> str:
    """The user turn: counts, categories, topics and a few review samples."""
    lines = [
        f"Zákazník Z-{contact_id} (anonymizován).",
        f"Nákupů: {n_purchases}, průměrné hodnocení {mean_rating:.1f} z 5, fáze v e-shopu: {lifecycle_label or 'neznámá'}.",
        "Nejčastější kategorie: "
        + (", ".join(f"{c} ({n})" for c, n in top_categories) or "neznámé"),
        "Témata zájmu (klasické shlukování): " + ("; ".join(topic_labels) or "žádná"),
        "Ukázky recenzí (nejdelší, zkrácené):",
        *(f"- {title}: {text}" for title, text in review_samples),
        "Vrať JSON.",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Aspects: what the customer praises or criticises, with a verbatim quote
# ---------------------------------------------------------------------------

ASPECTS_SYSTEM = (
    "Jsi analytik sentimentu produktových recenzí. Dostaneš české recenze jednoho zákazníka. "
    "Vyber 3 až 5 vlastností produktů, které zákazník opakovaně hodnotí (například zvuk, "
    "kvalita zpracování, cena, kompatibilita, výdrž baterie, snadnost použití), a ke každé "
    "urči sentiment: positive, negative, neutral, nebo mixed. Ke každé vlastnosti připoj "
    "doklad: doslovný úryvek z recenzí, nejvýš jedna věta, zkopírovaný beze změny (nic "
    "neparafrázuj, doklad se strojově ověřuje proti textu recenzí). Vlastnost pojmenuj česky "
    "jedním až třemi slovy.\n\n"
    'Vrať pouze JSON podle schématu: {"aspects": [{"aspect": "...", "sentiment": "...", '
    '"evidence": "..."}]}.'
)

ASPECTS_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "aspects": {
            "type": "array",
            "minItems": 3,
            "maxItems": 5,
            "items": {
                "type": "object",
                "properties": {
                    "aspect": {"type": "string", "maxLength": 40},
                    "sentiment": {
                        "type": "string",
                        "enum": ["positive", "negative", "neutral", "mixed"],
                    },
                    "evidence": {"type": "string", "maxLength": 300},
                },
                "required": ["aspect", "sentiment", "evidence"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["aspects"],
    "additionalProperties": False,
}


def aspects_prompt(contact_id: int, n_reviews: int, review_block: str, shown_chars: int) -> str:
    """The user turn: the customer's Czech reviews, newest first, inside a marked block."""
    return "\n".join(
        [
            f"Zákazník Z-{contact_id} (anonymizován).",
            f"Recenze ({n_reviews}, nejnovější první, zkráceno na {shown_chars} znaků):",
            "<recenze>",
            review_block,
            "</recenze>",
            "Vrať JSON.",
        ]
    )


__all__ = [
    "ASPECTS_SCHEMA",
    "ASPECTS_SYSTEM",
    "HISTORY_CAP",
    "PERSONA_REVIEWS",
    "PERSONA_REVIEW_CHARS",
    "PERSONA_SCHEMA",
    "PERSONA_SYSTEM",
    "PROMPT_VERSION",
    "REASON_SCHEMA",
    "REASON_SYSTEM",
    "REVIEW_CHARS_CAP",
    "aspects_prompt",
    "persona_prompt",
    "reason_prompt",
]
