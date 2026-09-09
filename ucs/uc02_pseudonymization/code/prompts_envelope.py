"""UC-02 envelope sandwich — prompt catalog (Czech bodies).

Every prompt carries structured metadata plus a body string. Body text is
Czech because UC-02 demonstrates anonymisation of Czech CRM messages and
the LLM receives instructions in the target-language context.

Three prompts:
  1. ENVELOPE_SYS_HINT   – system-prompt prefix inserted before the
                            caller's task prompt. Teaches the LLM to
                            preserve <TYPE_N> placeholder tokens verbatim
                            and to echo the <id>...</id> correlation
                            wrapper.
  2. RETRY_REMINDER_TAGS – retry reminder when the LLM dropped or
                            invented <TYPE_N> tokens.
  3. RETRY_REMINDER_MID  – retry reminder when the LLM dropped or
                            changed the <id>...</id> MID.

``envelope.py`` imports these ``PromptSpec`` objects and reads
``.system_instruction`` rather than holding inline string literals.

Changelog:
  1.3.0 — ENVELOPE_SYS_HINT gains a <context> block after the rules: the map
          stays with the operator, every token is restored locally after the
          answer (so the model writes as if it knew the data and never refuses
          for lack of it), and the level of the envelope filled by the caller
          through {detection_clause} (DETECTION_CLAUSES: rules / rules + NER).
          Found on the demo page 2026-09-07: without it a model can answer
          that it does not know who <PERSON_1> is.
  1.2.0 — ENVELOPE_SYS_HINT rule 1 names the suffixed token form
          (<PERSON_1b> = another grammatical form of the same entity as
          <PERSON_1>) introduced by the entity unification mode (D-UC02-4);
          target models come from utils.generation defaults.
  1.1.0 — ENVELOPE_SYS_HINT: added <role> slot (anti-drift), wrapped
          rules in <rules>...</rules>, sharpened Rule 5 (no preamble
          before the wrapper), added explicit case-sensitivity warning
          in Rule 1, unified terminology on "placeholder token" /
          "wrapper <id>...</id>" / "character-by-character".
          RETRY_REMINDER_TAGS + RETRY_REMINDER_MID: rewritten to a
          symmetric (a)/(b) structure that reminds the model of the MID
          wrapper inside the retry prompt as well.
          The defensive <user_input>...</user_input> delimiter is NOT
          applied — deliberate prototype scope (UC-02 demonstrates
          pseudonymisation, not full prompt-injection defence).
          Border-case few-shot examples deferred to 1.2.0 once real
          failures are observed.
  1.0.0 — initial draft (kept inline in envelope.py).
"""

from __future__ import annotations

from utils.generation import DEFAULT_MODELS
from utils.promptmodel import PromptSpec

# Target models for the envelope sandwich: the thesis defaults of the three
# providers in ``utils.generation`` (one source of truth, D-GEN-1).
_TARGET_MODELS = [model for model in DEFAULT_MODELS.values() if model]

_APPLICATION = "ucs.uc02_pseudonymization.code.envelope"
_DATE_CREATED = "2026-05-20"
_LAST_MODIFIED = "2026-09-07"


# ---------------------------------------------------------------------------
# 1. ENVELOPE_SYS_HINT — system-prompt prefix
# ---------------------------------------------------------------------------

ENVELOPE_SYS_HINT = PromptSpec(
    prompt_id="envelope_sys_hint",
    version="1.3.0",
    purpose=(
        "System-prompt prefix placed before the caller's task prompt in the UC-02 sandwich. "
        "Teaches the model (a) to keep every <TYPE_N> placeholder character for character "
        "as an opaque identifier standing for removed personal data, (b) to echo the "
        "<id>...</id> wrapper at the start of its answer as the correlation token of this "
        "one request, (c) that the map stays with the operator and every token is restored "
        "locally after the answer, and which level of the envelope masked the text "
        "({detection_clause}, filled by compose_system_prompt). Body in Czech: the model "
        "works on Czech CRM text."
    ),
    application=_APPLICATION,
    date_created=_DATE_CREATED,
    last_modified=_LAST_MODIFIED,
    target_models=_TARGET_MODELS,
    system_instruction=(
        "<role>\n"
        "Jsi jazykový model zpracovávající uživatelský prompt, ve kterém byly osobní "
        "údaje předem nahrazeny zástupnými tokeny ve tvaru <TYPE_N>. NENÍ tvůj úkol "
        "uhádnout, kdo nebo co se za tokeny skrývá, ani je nahradit reálnými údaji. "
        "Tvůj úkol je odpovědět na původní záměr uživatele a zachovat zástupné tokeny "
        "znak po znaku beze změny.\n"
        "</role>\n"
        "\n"
        "KRITICKÉ PRAVIDLO ZACHOVÁNÍ — přečti dřív, než cokoli dalšího uděláš:\n"
        "\n"
        "V uživatelském promptu jsou zástupné tokeny ve tvaru <TYPE_N> (např. "
        "<PERSON_47>, <PHONE_823>, <EMAIL_12>). Jsou to neprůhledné identifikátory za "
        "reálná osobní data, která byla z důvodu ochrany soukromí odstraněna.\n"
        "\n"
        "V uživatelském promptu je také wrapper <id>...</id>, například "
        "<id>9f2c1c0c4f7c4a2b8e8e7d6c5b4a3a2a</id>. Slouží jako jednorázový korelační "
        "token pouze pro tento jeden požadavek.\n"
        "\n"
        "<rules>\n"
        "1. Zachovej každý zástupný token <TYPE_N> PŘESNĚ tak, jak je zadán, znak po "
        "znaku. Nepřejmenuj ho, nepřečísluj ho, nepřekládej ho ani ho neparafrázuj. "
        "Velká písmena v názvu typu (PERSON, EMAIL, PHONE, ADDRESS, ICO, RC, IBAN, DIC) "
        "jsou součástí identifikátoru — nepřevádej je na malá ani je nemodifikuj. "
        "Token s písmenem za číslem (např. <PERSON_1b>) je jiný gramatický tvar téže "
        "entity jako <PERSON_1>; zachovej ho přesně tak, jak je, včetně písmena.\n"
        "2. Nevytvářej žádné nové tokeny ve tvaru <TYPE_N>.\n"
        "3. Nevymýšlej reálné osobní údaje (jména, telefonní čísla, e-maily, adresy, "
        "identifikátory) jako náhradu za zástupné tokeny.\n"
        "4. Zacházej se zástupnými tokeny jako s neprůhlednými identifikátory. "
        "V odpovědi se na ně odkazuj stejným tokenem, jaký dostal v promptu.\n"
        "5. PRVNÍ ŘÁDEK odpovědi MUSÍ být přesně ten wrapper <id>...</id>, který je "
        "v uživatelském promptu, okopírovaný znak po znaku. Před ním nesmí být žádný "
        "úvodní text, žádné uvozovky, žádné markdown formátování, žádný popis. Druhý "
        "řádek a dál je vlastní odpověď.\n"
        "6. Neměň, neparafrázuj ani negeneruj žádný jiný wrapper <id>...</id>. "
        "V odpovědi smí být přesně jeden wrapper <id>...</id>, a to ten, který přišel "
        "v promptu.\n"
        "</rules>\n"
        "\n"
        "<context>\n"
        "Text prošel pseudonymizační obálkou provozovatele CRM. {detection_clause}\n"
        "Mapa token → údaj zůstává u provozovatele a nikdy ti není poslána. Po tvé odpovědi "
        "provozovatel každý token lokálně nahradí zpět původním údajem, takže čtenář tvé "
        "odpovědi uvidí skutečná jména, čísla a adresy. Piš proto tak, jako bys údaje znal: "
        "oslovuj a odkazuj přes token (např. „Dobrý den, <PERSON_1>,“), nevysvětluj, že tokeny "
        "nevidíš, neptej se, kdo se za nimi skrývá, a neodmítej úkol kvůli chybějícím údajům.\n"
        "</context>\n"
    ),
)

# The level of the envelope, filled into {detection_clause} of ENVELOPE_SYS_HINT by
# ``envelope.compose_system_prompt(task, detection=...)``: the model is told what the
# caller's detector replaced, so it knows what may still be readable in the text.
DETECTION_CLAUSES: dict[str, str] = {
    "rules+ner": (
        "Úroveň obálky: pravidla + český NER. Nahrazeny jsou formátové identifikátory "
        "(e-mail, telefon, IČO, DIČ, rodné číslo, IBAN) i jména osob, firmy, adresy a data."
    ),
    "rules": (
        "Úroveň obálky: jen pravidla. Nahrazeny jsou formátové identifikátory (e-mail, "
        "telefon, IČO, DIČ, rodné číslo, IBAN); jména a adresy mohly v textu zůstat čitelné."
    ),
}


# ---------------------------------------------------------------------------
# 2. RETRY_REMINDER_TAGS — retry reminder for missing / invented <TYPE_N>
# ---------------------------------------------------------------------------

RETRY_REMINDER_TAGS = PromptSpec(
    prompt_id="retry_reminder_tags",
    version="1.1.0",
    purpose=(
        "Reminder placed before the user prompt on the next attempt when the integrity "
        "check found missing or invented <TYPE_N> placeholders in the previous answer. "
        "Filled at run time with the missing / extra token lists, the masked text and the "
        "<id>...</id> wrapper."
    ),
    application=_APPLICATION,
    date_created=_DATE_CREATED,
    last_modified=_LAST_MODIFIED,
    target_models=_TARGET_MODELS,
    system_instruction=(
        "PŘIPOMENUTÍ: předchozí odpověď nezachovala všechny zástupné tokeny správně.\n"
        "{missing_clause}"
        "{extra_clause}"
        "\n"
        "Vygeneruj odpověď znovu. Dvě věci musí být splněny současně:\n"
        "(a) PRVNÍ ŘÁDEK odpovědi je wrapper <id>{mapping_id}</id> okopírovaný znak po "
        "znaku z konce tohoto promptu. Žádný úvodní text, žádné uvozovky, žádný "
        "markdown.\n"
        "(b) KAŽDÝ zástupný token <TYPE_N> z původního vstupu zůstane v odpovědi "
        "doslova zachován — nepřejmenovaný, nepřečíslovaný, nevynechaný, nedoplněný "
        "o nové.\n"
        "\n"
        "{masked_text}\n"
        "\n"
        "<id>{mapping_id}</id>\n"
    ),
)

# Clause templates for RETRY_REMINDER_TAGS, filled from the integrity result.
RETRY_REMINDER_TAGS_MISSING_CLAUSE = (
    "- Tyto zástupné tokeny z původního vstupu v odpovědi chyběly: {missing_list}. "
    "Doplň je zpět přesně tak, jak byly v promptu.\n"
)
RETRY_REMINDER_TAGS_EXTRA_CLAUSE = (
    "- Tyto tokeny jsi v odpovědi vymyslel, ale v původním vstupu nebyly: {extra_list}. "
    "Odstraň je.\n"
)


# ---------------------------------------------------------------------------
# 3. RETRY_REMINDER_MID — retry reminder for a missing / changed <id>...</id>
# ---------------------------------------------------------------------------

RETRY_REMINDER_MID = PromptSpec(
    prompt_id="retry_reminder_mid",
    version="1.1.0",
    purpose=(
        "Reminder placed before the user prompt on the next attempt when the answer did not "
        "start with the expected <id>...</id> wrapper or the wrapper did not match the active "
        "mapping_id. Filled at run time with the mapping_id and the masked text."
    ),
    application=_APPLICATION,
    date_created=_DATE_CREATED,
    last_modified=_LAST_MODIFIED,
    target_models=_TARGET_MODELS,
    system_instruction=(
        "PŘIPOMENUTÍ: předchozí odpověď NEZAČÍNALA požadovaným wrapperem "
        "<id>{mapping_id}</id> (buď chyběl, byl zkrácen, nebo měl jiný obsah).\n"
        "\n"
        "Vygeneruj odpověď znovu. Dvě věci musí být splněny současně:\n"
        "(a) PRVNÍ ŘÁDEK odpovědi je přesně wrapper <id>{mapping_id}</id> okopírovaný "
        "znak po znaku. Žádný úvodní text, žádné uvozovky, žádný markdown.\n"
        "(b) Všechny zástupné tokeny <TYPE_N> z původního vstupu zůstanou v odpovědi "
        "doslova zachovány.\n"
        "\n"
        "{masked_text}\n"
        "\n"
        "<id>{mapping_id}</id>\n"
    ),
)


# ---------------------------------------------------------------------------
# User-prompt template (declarative; envelope.py does the composition)
# ---------------------------------------------------------------------------

USER_PROMPT_TEMPLATE = PromptSpec(
    prompt_id="user_prompt_template",
    version="1.1.0",
    purpose=(
        "Shape of the user prompt sent to the model in the UC-02 sandwich: the masked text, "
        "a blank line, the <id>...</id> wrapper at the end. The id sits in the user prompt "
        "(not the system prompt) because the system prompt is per session while the "
        "envelope id is per request."
    ),
    application=_APPLICATION,
    date_created=_DATE_CREATED,
    last_modified=_LAST_MODIFIED,
    target_models=_TARGET_MODELS,
    system_instruction=("{masked_text}\n\n<id>{mapping_id}</id>\n"),
)


__all__ = [
    "PromptSpec",
    "ENVELOPE_SYS_HINT",
    "DETECTION_CLAUSES",
    "RETRY_REMINDER_TAGS",
    "RETRY_REMINDER_TAGS_MISSING_CLAUSE",
    "RETRY_REMINDER_TAGS_EXTRA_CLAUSE",
    "RETRY_REMINDER_MID",
    "USER_PROMPT_TEMPLATE",
]
