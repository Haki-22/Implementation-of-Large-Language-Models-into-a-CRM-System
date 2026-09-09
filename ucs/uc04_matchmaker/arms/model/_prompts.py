"""The prompt catalogue of the model methods: one version, two languages, three system texts, two schemas.

EDIT THE PROMPT TEXT HERE. Every prompt follows the seven rules of the thesis's chapter
on prompt engineering: an explicit role, reader and goal (the reader is the scoring
code, hence JSON only); the output format fixed by a JSON schema the provider
enforces; one short worked example (a longer one would compete with the data); the
chain (a classical model hands over its order, or the model's description hands over
to a dense index); thinking time through the provider's reasoning tier, never a chain
of thought in the answer; a fixed sample, seeded candidate lists and a log of every
call; and this file as the versioned catalogue.

Decision of 2026-09-06 (design §8.1): the Czech branch is Czech throughout, the
instruction as well as the data, so the branch difference measures the Czech tax on
both at once. Each system text therefore exists in English and in Czech under one
``PROMPT_VERSION``; a change of any wording bumps the version, and every run records
the version and the full texts in its ``config.json``.
"""

from __future__ import annotations

from typing import Any

# 1.0.0 (2026-09-07): first version, from the design of 2026-09-06 (spec §5).
# 1.0.1 (2026-09-07): every system text ends with the no-tools sentence. Found on the first agy
#   smoke: given a prompt of this size the agentic CLI reached for a shell command instead of
#   answering, print mode denied it and the turn ended empty (envelope ``denied_actions``:
#   RunCommand, 8 of 8 calls); with the sentence 101 of 101 ids came back. Provider-neutral
#   wording, so every provider sees the same text.
# 1.0.2 (2026-09-07): the Czech no-tools sentence reworded by the author ("odpověz jen JSON
#   objektem"); the 1.0.1 smoke folder was deleted with it, the run of record is 1.0.2.
PROMPT_VERSION = "1.0.2"

# The reader of the answer is the scoring code (rule 1): the model answers in the turn, with
# nothing else. Appended to every system text in both languages.
NO_TOOLS: dict[str, str] = {
    "en": (
        "\n\nAnswer in this turn directly from what you read. Do not run commands, write files "
        "or use any tool; the answer is the JSON object only."
    ),
    "cs": (
        "\n\nOdpověz rovnou v tomto tahu z toho, co jsi přečetl. Nespouštěj příkazy, nezapisuj "
        "soubory a nepoužívej žádné nástroje; odpověz jen JSON objektem."
    ),
}

CANDIDATE_ID_PATTERN = r"^C[0-9]{3}$"
TITLE_CHARS = 120  # a product title is cut here in both the history and the candidate list

# ---------------------------------------------------------------------------
# Ranking methods (1, 3, 4, 5): the shared system text
# ---------------------------------------------------------------------------

RANKING_SYSTEM: dict[str, str] = {
    "en": (
        "You are the recommender of a Czech online shop that sells electronics and accessories. "
        "You will read one customer's complete purchase history (oldest first; each line gives "
        "the date, the star rating the customer gave, and the product title) and a list of "
        "candidate products, each with a short id such as C017.\n\n"
        "Task: order ALL candidates from the most likely next purchase to the least likely, "
        "judged from the history alone. Read the history for the customer's interests, brands, "
        "price level and the direction of the most recent purchases; a candidate that continues "
        "the recent purchases ranks above one that only matches old ones. Never invent an id, "
        "never drop one, never repeat one.\n\n"
        'Answer with JSON only, matching the schema {"ranking": [<every candidate id exactly '
        "once, most likely first>]}.\n\n"
        "Example. History: 2013-01-04 ★5 Sony MDR-7506 headphones; 2013-02-11 ★4 FiiO E10 "
        "USB DAC amplifier. Candidates: C001 Kitchen scale; C002 Headphone stand; C003 3.5 mm to "
        '6.3 mm adapter; C004 Dog leash. Answer: {"ranking": ["C003", "C002", "C001", "C004"]}'
    ),
    "cs": (
        "Jsi doporučovací systém českého e-shopu s elektronikou a příslušenstvím. Dostaneš "
        "celou nákupní historii jednoho zákazníka (od nejstaršího nákupu; každý řádek nese datum, "
        "hodnocení hvězdičkami, které zákazník dal, a název produktu) a seznam kandidátních "
        "produktů, každý s krátkým identifikátorem, například C017.\n\n"
        "Úkol: seřaď VŠECHNY kandidáty od nejpravděpodobnějšího příštího nákupu po nejméně "
        "pravděpodobný, jen podle historie. Z historie vyčti zájmy zákazníka, značky, cenovou "
        "hladinu a směr posledních nákupů; kandidát, který navazuje na poslední nákupy, patří "
        "výš než ten, který odpovídá jen starým. Žádný identifikátor si nevymýšlej, žádný "
        "nevynechej, žádný neopakuj.\n\n"
        'Odpověz pouze JSON podle schématu {"ranking": [<každý identifikátor kandidáta právě '
        "jednou, nejpravděpodobnější první>]}.\n\n"
        "Příklad. Historie: 2013-01-04 ★5 Sluchátka Sony MDR-7506; 2013-02-11 ★4 USB "
        "zesilovač FiiO E10. Kandidáti: C001 Kuchyňská váha; C002 Stojan na sluchátka; C003 "
        'Redukce 3,5 mm na 6,3 mm jack; C004 Vodítko pro psa. Odpověď: {"ranking": ["C003", '
        '"C002", "C001", "C004"]}'
    ),
}

# Methods 3 and 5: the candidates arrive in the order a collaborative-filtering model gave them.
ALS_ORDER_ADDENDUM: dict[str, str] = {
    "en": (
        "\n\nThe candidates are listed in the order a collaborative-filtering model (ALS, trained "
        "on what other customers of the shop bought) ranked them, most likely first, each with its "
        "score. Keep that order wherever the history gives you no reason to change it; move a "
        "candidate only when the history supports the move."
    ),
    "cs": (
        "\n\nKandidáti jsou uvedeni v pořadí, v jakém je seřadil model kolaborativního filtrování "
        "(ALS, naučený z toho, co kupovali ostatní zákazníci obchodu), nejpravděpodobnější první, "
        "každý se svým skóre. Toto pořadí zachovej všude, kde ti historie nedává důvod ho měnit; "
        "kandidáta přesuň jen tehdy, když to historie podporuje."
    ),
}

# Method 4: the same, plus the customer profile as a tie-breaker.
PROFILE_ADDENDUM: dict[str, str] = {
    "en": (
        "\n\nYou also receive the customer's profile: a Big Five personality estimate (five scores "
        "1-5), the customer's stage in the shop's lifecycle, interest topics, and, when present, "
        "a short persona description and the product aspects the customer praises or criticises. "
        "Use the profile only to break ties between candidates the history does not separate; "
        "the history comes first."
    ),
    "cs": (
        "\n\nDostaneš také profil zákazníka: odhad osobnosti Big Five (pět skóre 1–5), fázi "
        "životního cyklu zákazníka v obchodě, témata zájmu a, pokud jsou k dispozici, krátký popis "
        "persony a vlastnosti produktů, které zákazník chválí nebo kritizuje. Profil použij jen "
        "k rozhodnutí mezi kandidáty, které historie nerozliší; historie má přednost."
    ),
}

# ---------------------------------------------------------------------------
# Method 2: the model describes the next purchase, the catalogue index finds it
# ---------------------------------------------------------------------------

DESCRIBE_SYSTEM: dict[str, str] = {
    "en": (
        "You are the recommender of a Czech online shop that sells electronics and accessories. "
        "From one customer's complete purchase history (oldest first: date, star rating, product "
        "title), describe the customer's most likely next purchase as a product listing line: the "
        "product type, the brand if the history suggests one, and the attribute that matters "
        "(size, capacity, compatibility, model family). Give three such lines, most likely first, "
        "written in the language of the titles you read. Do not name a product the customer "
        'already bought. Answer with JSON only: {"next_purchases": ["<line 1>", "<line 2>", '
        '"<line 3>"]}.\n\n'
        "Example. History: 2013-01-04 ★5 Sony MDR-7506 headphones; 2013-02-11 ★4 FiiO E10 "
        'USB DAC amplifier. Answer: {"next_purchases": ["3.5 mm to 6.3 mm headphone jack adapter", '
        '"Headphone stand for over-ear headphones", "Replacement ear pads for Sony MDR-7506"]}'
    ),
    "cs": (
        "Jsi doporučovací systém českého e-shopu s elektronikou a příslušenstvím. Z celé nákupní "
        "historie jednoho zákazníka (od nejstaršího nákupu: datum, hodnocení hvězdičkami, název "
        "produktu) popiš nejpravděpodobnější příští nákup zákazníka jako řádek z nabídky obchodu: "
        "typ produktu, značku, pokud ji historie naznačuje, a vlastnost, na které záleží "
        "(velikost, kapacita, kompatibilita, modelová řada). Napiš tři takové řádky, "
        "nejpravděpodobnější první, v jazyce názvů, které čteš. Nejmenuj produkt, který zákazník "
        'už koupil. Odpověz pouze JSON: {"next_purchases": ["<řádek 1>", "<řádek 2>", '
        '"<řádek 3>"]}.\n\n'
        "Příklad. Historie: 2013-01-04 ★5 Sluchátka Sony MDR-7506; 2013-02-11 ★4 USB "
        'zesilovač FiiO E10. Odpověď: {"next_purchases": ["Redukce 3,5 mm na 6,3 mm jack pro '
        'sluchátka", "Stojan na sluchátka přes uši", "Náhradní náušníky pro Sony MDR-7506"]}'
    ),
}

DESCRIBE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "next_purchases": {
            "type": "array",
            "minItems": 3,
            "maxItems": 3,
            "items": {"type": "string", "maxLength": 200},
        }
    },
    "required": ["next_purchases"],
    "additionalProperties": False,
}


def ranking_schema(n_candidates: int) -> dict[str, Any]:
    """The schema of a ranking answer: candidate ids, at most one per candidate.

    ``minItems`` is 1, not ``n_candidates``: a model that stops early yields a
    *partial* call (the parser appends what is missing and the card counts it),
    whereas a schema that forced the full length would push the model into
    repeating ids, which the parser must reject as a failed call.
    """
    return {
        "type": "object",
        "properties": {
            "ranking": {
                "type": "array",
                "minItems": 1,
                "maxItems": n_candidates,
                "items": {"type": "string", "pattern": CANDIDATE_ID_PATTERN},
            }
        },
        "required": ["ranking"],
        "additionalProperties": False,
    }


# ---------------------------------------------------------------------------
# The user part: one template, the fixed words per language
# ---------------------------------------------------------------------------

_WORDS: dict[str, dict[str, str]] = {
    "en": {
        "customer": "Customer C-{id} (anonymised). Product titles in English.",
        "history": "Purchase history ({n} purchases, oldest first):",
        "candidates": "Candidates ({k}; {order}):",
        "shuffled": "in random order",
        "als_order": "in ALS order with score",
        "profile": "Profile:",
        "big_five": "Big Five (1-5)",
        "lifecycle": "lifecycle",
        "topics": "interest topics",
        "persona": "persona",
        "aspects": "aspects praised / criticised",
        "return": "Return the JSON.",
    },
    "cs": {
        "customer": "Zákazník Z-{id} (anonymizováno). Názvy produktů česky.",
        "history": "Nákupní historie ({n} nákupů, od nejstaršího):",
        "candidates": "Kandidáti ({k}; {order}):",
        "shuffled": "v náhodném pořadí",
        "als_order": "v pořadí modelu ALS se skóre",
        "profile": "Profil:",
        "big_five": "Big Five (1–5)",
        "lifecycle": "fáze životního cyklu",
        "topics": "témata zájmu",
        "persona": "persona",
        "aspects": "chválené / kritizované vlastnosti",
        "return": "Vrať JSON.",
    },
}


def system_text(kind: str, lang: str, *, als_order: bool = False, profile: bool = False) -> str:
    """The complete system text of a method: base text, the addenda it uses, the no-tools sentence last.

    ``kind`` is ``"ranking"`` (methods 1, 3, 4, 5) or ``"describe"`` (method 2);
    ``als_order`` adds the ALS-order addendum (3, 4, 5), ``profile`` the profile addendum (4).
    """
    if kind == "ranking":
        text = RANKING_SYSTEM[lang]
        if als_order:
            text += ALS_ORDER_ADDENDUM[lang]
        if profile:
            text += PROFILE_ADDENDUM[lang]
    elif kind == "describe":
        if als_order or profile:
            raise ValueError("the describe text takes no addendum")
        text = DESCRIBE_SYSTEM[lang]
    else:
        raise ValueError(f"unknown system text kind {kind!r}")
    return text + NO_TOOLS[lang]


def words(lang: str) -> dict[str, str]:
    """The fixed words of the user template for a branch."""
    if lang not in _WORDS:
        raise ValueError(f"no prompt words for lang {lang!r}; known: {sorted(_WORDS)}")
    return _WORDS[lang]


def user_prompt(
    lang: str,
    *,
    contact_id: int,
    history_lines: list[str],
    candidate_lines: list[str] | None,
    als_order: bool = False,
    profile_lines: list[str] | None = None,
) -> str:
    """The user part: customer line, history, candidates (when the method has them), profile (method 4)."""
    w = words(lang)
    out = [w["customer"].format(id=contact_id), w["history"].format(n=len(history_lines))]
    out += history_lines
    if candidate_lines is not None:
        order = w["als_order"] if als_order else w["shuffled"]
        out.append(w["candidates"].format(k=len(candidate_lines), order=order))
        out += candidate_lines
    if profile_lines:
        out.append(w["profile"])
        out += profile_lines
    out.append(w["return"])
    return "\n".join(out)


__all__ = [
    "ALS_ORDER_ADDENDUM",
    "CANDIDATE_ID_PATTERN",
    "DESCRIBE_SCHEMA",
    "DESCRIBE_SYSTEM",
    "NO_TOOLS",
    "PROFILE_ADDENDUM",
    "PROMPT_VERSION",
    "RANKING_SYSTEM",
    "TITLE_CHARS",
    "ranking_schema",
    "system_text",
    "user_prompt",
    "words",
]
