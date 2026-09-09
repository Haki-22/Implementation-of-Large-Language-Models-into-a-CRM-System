"""basic-prompt-how-to.py — a short, source-backed guide to writing LLM prompts (Czech and English).

What this is. A distilled "how to write or refactor a prompt for a language model",
packaged as plain Python data: nine rules, five anti-patterns, four frameworks that say
the same thing in different words, and one worked example of the same task written
badly and well. It is a reading aid, not a library: nothing in the repository imports
it (the hyphens in the file name make that deliberate). Run it directly to print the
summary and the short-versus-long demo:

    python basic-prompt-how-to.py

Where it comes from. This is the reference the project's judges and model calls were
drafted from. The coding assistants that helped write those prompts read this file
first. Every rule cites the book or paper it comes from, and a
rule made it in only when two independent sources agree on it. It is kept at the root
of the repository as a first hint for a reader who has not written prompts before.

Both languages. The rules were written in Czech because the prompts they served are
Czech. Each Czech field has an English twin (``do`` / ``do_en``, ``why`` / ``why_en``,
``symptom`` / ``symptom_en``, ...), the comments are bilingual, and the demo prints both.
The two example prompts stay Czech on purpose: they show what a Czech prompt looks like.

---

Co to je. Zhuštěné "jak psát nebo přepsat prompt pro jazykový model", zabalené jako
obyčejná pythonovská data: devět pravidel, pět anti-patternů, čtyři rámce, které říkají
totéž jinými slovy, a jedna ukázka stejné úlohy napsané špatně a dobře. Je to pomůcka
ke čtení, ne knihovna: nic v repozitáři ji neimportuje. Spuštění napřímo vytiskne
souhrn a demo krátkého versus dlouhého promptu.

Odkud to je. Reference, podle které vznikaly prompty pro soudce a volání modelů
v projektu. Kódovací asistenti, kteří s psaním
promptů pomáhali, četli nejdřív tento soubor. Každé pravidlo cituje knihu nebo článek,
odkud pochází, a do seznamu se dostalo jen tehdy, když se na něm shodly dva nezávislé
zdroje. V kořeni repozitáře zůstává jako první nápověda pro čtenáře, který prompty
ještě nepsal.

Sources / Zdroje (bibkeys are the ones the thesis uses):
  - Phoenix, J. & Taylor, M. Prompt Engineering for Generative AI. O'Reilly 2024.
      Five Principles of Prompting: Give Direction / Specify Format / Provide Examples /
      Evaluate Quality / Divide Labor. bibkey: phoenix2024promptengineering
  - Huyen, C. AI Engineering. O'Reilly 2024, ch. 5 (pp. 211-252).
      Best practices: clear instructions, provide context, break tasks, give time to think,
      iterate, organise + version, defensive prompt engineering. bibkey: huyen2024aiengineering
  - Alammar, J. & Grootendorst, M. Hands-On Large Language Models. O'Reilly 2024, ch. 6 (pp. 167-201).
      Seven prompt components: persona, instruction, context, format, audience, tone, data.
      bibkey: alammar2024handsonllms
  - Wei et al. 2022. Chain-of-Thought Prompting. arXiv 2201.11903 (NeurIPS).
      A reasoning slot before the answer. / Prostor pro úvahu před odpovědí. bibkey: wei2022chainofthought
  - Brown et al. 2020. Language Models are Few-Shot Learners. arXiv 2005.14165.
      In-context few-shot learning. bibkey: brown2020gpt3
  - Sahoo et al. 2024. A Systematic Survey of Prompt Engineering. arXiv 2402.07927.
      Taxonomy of 41 techniques. / Taxonomie 41 technik. bibkey: sahoo2024systematic
  - Zheng et al. 2024. "When 'A Helpful Assistant' Is Not Really Helpful".
      A persona does NOT improve accuracy (negative result). / Persona výkon NEZLEPŠUJE.
      bibkey: zheng2024personas
  - Greshake et al. 2023. Indirect Prompt Injection. arXiv 2302.12173.
      Defence: delimit untrusted input. / Obrana: oddělit nedůvěryhodný vstup. bibkey: greshake2023indirect
  - Lee et al. 2025. CheckEval. EMNLP 2025 Main.
      Checklist decomposition for a judge. / Rozklad na checklist pro soudce. bibkey: lee2025checkeval
  - COSTAR — Teo, S. 2024 (GovTech Singapore competition). Practitioner mnemonic, NOT
      peer-reviewed; a grey-zone (blog-tier) citation, not a primary framework.
      / Praktická mnemotechnika, NENÍ recenzovaná; citace z šedé zóny, ne primární rámec.

The ``METADATA`` block below follows the shape of ``PromptSpec`` in ``utils/promptmodel.py``.
/ Blok ``METADATA`` níže má tvar ``PromptSpec`` z ``utils/promptmodel.py``.
"""

from __future__ import annotations

METADATA = {
    "id": "basic-prompt-how-to",
    "version": "2",
    "purpose": "Standalone reference: how to write or refactor LLM prompts (rules + frameworks + demo).",
    "purpose_cs": "Samostatná reference: jak psát/refaktorovat LLM prompty (pravidla + rámce + demo).",
    "date_created": "2026-05-29",
    "date_revised": "2026-09-09",
    "audience": "anyone authoring or refactoring LLM prompts in this project, or reading them",
    "scope": "general-purpose (not specific to this thesis)",
    "provenance": "the reference the project's prompts were drafted from; no module imports it",
}


# ---------------------------------------------------------------------------
# 1) JÁDRO — 9 pravidel (operativní playbook)
#    CORE  — 9 rules (the operational playbook)
# ---------------------------------------------------------------------------
# Každé pravidlo: co dělat + proč + zdroj. Cross-source: pravidlo se počítá
# jen pokud je ve 2+ nezávislých zdrojích.
# Each rule: what to do + why + source. Cross-source rule: a rule counts only
# when two or more independent sources state it.

RULES = [
    {
        "n": 1,
        "name": "Give Direction",
        "do": "Explicitní KDO / CO / PROČ / PUBLIKUM / TÓN.",
        "do_en": "Explicit WHO / WHAT / WHY / AUDIENCE / TONE.",
        "why": "Bez směru model klouže do generického registru.",
        "why_en": "Without direction the model slides into a generic register.",
        "src": ["phoenix2024promptengineering #1", "alammar2024handsonllms (Persona+Instruction)"],
    },
    {
        "n": 2,
        "name": "Provide Context",
        "do": "Dej modelu fakta, která potřebuje; vstupní data oddělená od instrukcí.",
        "do_en": "Give the model the facts it needs; keep input data delimited from instructions.",
        "why": "Bez kontextu sáhne do vlastní paměti místo tvých dat. "
        "Hustota kontextu > hustota instrukcí.",
        "why_en": "Without context it reaches for its own memory instead of your data. "
        "Context density beats instruction density.",
        "src": ["huyen2024aiengineering (Provide Sufficient Context)"],
    },
    {
        "n": 3,
        "name": "Specify Format",
        "do": "Přísné schéma + koncová značka. Pro Claude: XML tagy > Markdown nadpisy. "
        "U JSON řetězců apostrofy '…', ne uvozovky (parser).",
        "do_en": "Strict schema + end marker. For Claude: XML tags beat Markdown headings. "
        "Inside JSON string values use apostrophes '…', not double quotes (the parser).",
        "why": "Bez specifikace formátu = peklo při parsování.",
        "why_en": "No format specification means post-parsing hell.",
        "src": ["phoenix2024promptengineering #2", "huyen2024aiengineering (end markers)"],
    },
    {
        "n": 4,
        "name": "Provide Examples",
        "do": "2-5 few-shot párů pokrývajících OKRAJOVÉ případy, ne happy path. "
        "Ukotvené v reálných selháních.",
        "do_en": "2-5 few-shot pairs covering EDGE cases, not the happy path. "
        "Grounded in real failures.",
        "why": "Few-shot poráží zero-shot; bez příkladů ~10-15 % rozptyl na hraničních případech.",
        "why_en": "Few-shot beats zero-shot; without examples expect ~10-15 % variance on border cases.",
        "src": ["phoenix2024promptengineering #3", "brown2020gpt3", "sahoo2024systematic"],
    },
    {
        "n": 5,
        "name": "Divide Labor",
        "do": "1 úloha na prompt; složitá úloha = řetěz 2-4 promptů, ne mega-prompt.",
        "do_en": "One task per prompt; a complex task is a chain of 2-4 prompts, not a mega-prompt.",
        "why": "Mega-prompt se 3 kroky → rozpad konzistence. Řetězení je empiricky lepší.",
        "why_en": "A three-step mega-prompt collapses consistency. Chaining is empirically better.",
        "src": ["phoenix2024promptengineering #5", "huyen2024aiengineering (Break Complex Tasks)"],
    },
    {
        "n": 6,
        "name": "Give Time to Think",
        "do": "Prostor pro úvahu PŘED odpovědí (CoT / evidence span). Self-consistency: "
        "vzorkuj N, většinové hlasování. U reasoning modelů (o1/o3) vynech — dělají to interně.",
        "do_en": "A reasoning slot BEFORE the answer (chain of thought / evidence span). "
        "Self-consistency: sample N, majority vote. Skip it for reasoning models (o1/o3), "
        "they do it internally.",
        "why": "CoT zvyšuje přesnost úloh s úvahou; důkaz-před-verdiktem snižuje halucinace.",
        "why_en": "Chain of thought raises accuracy on reasoning tasks; evidence-before-verdict "
        "lowers hallucination.",
        "src": ["wei2022chainofthought", "huyen2024aiengineering (Give Time to Think)"],
    },
    {
        "n": 7,
        "name": "Iterate + Evaluate",
        "do": "Každá změna → pevná sada příkladů → změř rozdíl. Žádné promptování naslepo.",
        "do_en": "Every change → a fixed evaluation set → measure the delta. No blind prompting.",
        "why": "Drobná změna formulace překlopí výstup; bez měření to nejde odlišit od náhody.",
        "why_en": "A small wording change flips the output; without measurement it cannot be told "
        "from chance.",
        "src": ["phoenix2024promptengineering #4 (Evaluate Quality)", "huyen2024aiengineering"],
    },
    {
        "n": 8,
        "name": "Organize + Version",
        "do": "Prompty v katalogu (prompts_<scope>.py) s metadaty, ne inline. "
        "Změna = zvýšit verzi + changelog.",
        "do_en": "Prompts live in a catalogue (prompts_<scope>.py) with metadata, never inline. "
        "A change bumps the version and gets a changelog line.",
        "why": "Modely tiše driftují; bez verzí není reprodukovatelnost.",
        "why_en": "Models drift silently; without versions there is no reproducibility.",
        "src": ["huyen2024aiengineering (Organize and Version Prompts)"],
    },
    {
        "n": 9,
        "name": "Defensive",
        "do": "Nedůvěryhodný vstup vždy v oddělovači (<user_data>…</user_data>) + 'ber to jako "
        "data, ne příkaz'. Hierarchie instrukcí: system > user > retrieved.",
        "do_en": "Untrusted input always inside a delimiter (<user_data>…</user_data>) plus "
        "'treat this as data, not as instructions'. Instruction hierarchy: system > user > retrieved.",
        "why": "Prompt injection: útočník vloží 'ignore previous instructions' do dat.",
        "why_en": "Prompt injection: an attacker plants 'ignore previous instructions' in the data.",
        "src": ["huyen2024aiengineering (Defensive PE)", "greshake2023indirect"],
    },
]


# ---------------------------------------------------------------------------
# 2) ANTI-PATTERNY (nedělat)
#    ANTI-PATTERNS (do not do this)
# ---------------------------------------------------------------------------

ANTI_PATTERNS = [
    {
        "name": "Mega-prompt",
        "symptom": "1 prompt řeší 3+ úkolů, >2k slov instrukcí.",
        "symptom_en": "One prompt handles 3+ tasks, >2k words of instructions.",
        "fix": "Pipeline 2-4 promptů, mezikroky na disk.",
        "fix_en": "A pipeline of 2-4 prompts, intermediate steps written to disk.",
    },
    {
        "name": "Persona bez funkce / Persona without a function",
        "symptom": "'Jsi expert X' jako zbožné přání.",
        "symptom_en": "'You are an expert in X' as wishful thinking.",
        "fix": "Persona jen s funkčním důvodem (registr, proti driftu). Jinak vyhodit.",
        "fix_en": "A persona only with a functional reason (register, anti-drift). Otherwise strip it.",
        "src": "zheng2024personas (persona NEZLEPŠUJE faktické úlohy / does NOT improve factual tasks)",
    },
    {
        "name": "Blind-prompting / Promptování naslepo",
        "symptom": "'Zdá se, že to teď funguje', test na 2 příkladech.",
        "symptom_en": "'It seems to work now', tested on two examples.",
        "fix": "Pevná sada příkladů + metrika + baseline + A/B.",
        "fix_en": "A fixed evaluation set + a metric + a baseline + A/B.",
    },
    {
        "name": "Rozvláčnost / Verbosity",
        "symptom": "3000slovný prompt s obecnými výzvami.",
        "symptom_en": "A 3000-word prompt full of generic appeals.",
        "fix": "Pro každou větu: 'když ji smažu, ztratí model nějakou schopnost?'. Krátký, "
        "kontextově hustý prompt vyhrává. 'Lost in the middle' (informace uprostřed dlouhého "
        "vstupu se ignoruje).",
        "fix_en": "For every sentence ask: 'if I delete it, does the model lose an ability?'. "
        "Short and context-dense wins. 'Lost in the middle': information in the middle of a "
        "long input gets ignored.",
    },
    {
        "name": "Cargo-cult triky / Cargo-cult tricks",
        "symptom": "'$300 spropitné za odpověď', 'Q: místo Questions:', magické fráze.",
        "symptom_en": "'$300 tip for the answer', 'Q: instead of Questions:', magic phrases.",
        "fix": "Fungují u slabších modelů a zastarávají. Silné modely chtějí čisté instrukce.",
        "fix_en": "They work on weaker models and go stale. Strong models want clean instructions.",
        "src": "huyen2024aiengineering (hacky tricks become outdated)",
    },
]


# ---------------------------------------------------------------------------
# 3) FRAMEWORKY (různé mnemotechniky pro stejnou podstatu)
#    FRAMEWORKS (different mnemonics for the same substance)
# ---------------------------------------------------------------------------
# Mapují se navzájem — jiná notace, stejná pravidla. Phoenix má knižní autoritu,
# COSTAR je novější mnemotechnika z praxe (NE recenzovaná).
# They map onto each other: different notation, the same rules. Phoenix carries
# the authority of a book; COSTAR is a newer practitioner mnemonic (NOT peer-reviewed).

FRAMEWORKS = {
    "phoenix_five_principles": {
        "source": "phoenix2024promptengineering (O'Reilly 2024, model-agnostic, since 2022)",
        "tier": "book — primary",
        "items": [
            "Give Direction — describe the style or a reference persona / popiš styl či referenční personu",
            "Specify Format — rules + output structure / pravidla + struktura výstupu",
            "Provide Examples — a diverse set of correctly solved cases / různorodá sada správně vyřešených případů",
            "Evaluate Quality — find the errors, rate, test what drives performance / najdi chyby, hodnoť, testuj, co řídí výkon",
            "Divide Labor — split into chained steps for complex goals / rozděl do zřetězených kroků",
        ],
    },
    "costar": {
        "source": "Teo, S. 2024, GovTech Singapore competition (Medium/blog)",
        "tier": "practitioner mnemonic — grey zone (NOT peer-reviewed)",
        "items": [
            "C — Context",
            "O — Objective",
            "S — Style",
            "T — Tone",
            "A — Audience",
            "R — Response (format)",
        ],
        "note": "Maps onto Phoenix: C/O/A → Give Direction, S/T → style + tone, R → Specify Format. "
        "LACKS Examples, Evaluate and Divide Labor. A good entry checklist for non-technical "
        "requesters, NOT a complete discipline.",
        "note_cs": "Mapuje na Phoenix: C/O/A → Give Direction, S/T → styl + tón, R → Specify Format. "
        "POSTRÁDÁ Examples, Evaluate a Divide Labor. Dobrý vstupní checklist pro netechnické "
        "zadavatele, NE kompletní disciplína.",
    },
    "huyen_best_practices": {
        "source": "huyen2024aiengineering ch. 5 (O'Reilly 2024)",
        "tier": "book — primary",
        "items": [
            "Write Clear and Explicit Instructions",
            "Provide Sufficient Context",
            "Break Complex Tasks into Simpler Subtasks",
            "Give the Model Time to Think",
            "Iterate on Your Prompts",
            "Organize and Version Prompts",
            "Defensive Prompt Engineering (delimiter / instruction hierarchy)",
        ],
    },
    "alammar_components": {
        "source": "alammar2024handsonllms ch. 6 (O'Reilly 2024)",
        "tier": "book — primary",
        "items": ["Persona", "Instruction", "Context", "Format", "Audience", "Tone", "Data"],
        "note": "A prompt is a composition of components; experiment with which combinations help the task.",
        "note_cs": "Prompt = složení komponent; experimentuj, které kombinace úloze pomáhají.",
    },
}


# ---------------------------------------------------------------------------
# 4) DEMO — stejná úloha, krátce vs dlouze (ukázka, že 'krátké vyhrává')
#    DEMO — the same task, short versus long (showing that 'short wins')
# ---------------------------------------------------------------------------
# Úloha: klasifikuj sentiment recenze produktu jako POSITIVE/NEGATIVE/NEUTRAL.
# Task: classify the sentiment of a product review as POSITIVE / NEGATIVE / NEUTRAL.
# Oba prompty jsou záměrně česky: ukazují, jak vypadá český prompt. Anglický
# čtenář najde strukturu v komentářích a v bloku "Proč" pod nimi.
# Both prompts are deliberately Czech: they show what a Czech prompt looks like.
# An English reader can follow the structure from the comments and the "Why" block below.

# --- KRÁTKÝ (kontextově hustý, doporučený) ---------------------------------
# --- SHORT (context-dense, recommended) --------------------------------------
# Structure: <role> one line · <task> what is judged · <rules> two edge rules
# (mixed = NEUTRAL, sarcasm by intent) · <output_format> strict JSON with an
# opening marker · <examples> two edge cases · <review> the delimited input.
SHORT_PROMPT = """\
<role>Klasifikátor sentimentu recenzí elektroniky.</role>

<task>Klasifikuj recenzi jako POSITIVE / NEGATIVE / NEUTRAL. Hodnotíš celkový postoj
zákazníka k produktu, ne jednotlivé dílčí stížnosti.</task>

<rules>
- NEUTRAL = smíšené (klady i zápory vyvážené) nebo čistě faktické bez hodnocení.
- Sarkasmus hodnoť podle skutečného záměru, ne doslovných slov.
</rules>

<output_format>JSON, začni '{'. {"sentiment": "POSITIVE|NEGATIVE|NEUTRAL"}</output_format>

<examples>
"Skvělý výkon, ale baterie slabá." → {"sentiment": "NEUTRAL"}
"No prostě dokonalost, jen co píšu o tom třetí reklamaci." → {"sentiment": "NEGATIVE"}
</examples>

<review>{review_text}</review>
"""

# --- DLOUHÝ (rozvláčný, anti-pattern — ukázka, co NEDĚLAT) -----------------
# --- LONG (verbose, the anti-pattern — what NOT to do) ------------------------
# Structure: a flattering persona · appeals to do a great job · the task restated
# three times in prose · a vague wish for "some structured format, ideally JSON"
# · the review pasted with no delimiter.
LONG_PROMPT = """\
Ahoj! Jsi velmi zkušený a chytrý expert na analýzu sentimentu s mnohaletou praxí
v oboru e-commerce a maloobchodu s elektronikou. Je velmi důležité, abys odvedl
opravdu skvělou a precizní práci, protože na tom hodně záleží. Pamatuj, že kvalita
tvé analýzy je naprosto klíčová a měl bys vždy postupovat velmi pečlivě a svědomitě.

Tvým úkolem bude přečíst si recenzi, kterou ti za chvíli poskytnu, a poté se zamyslet
nad tím, jaký je celkový sentiment této recenze. Sentiment může být buď pozitivní,
nebo negativní, nebo také neutrální, podle toho, jak se zákazník vyjadřuje a co cítí.
Je také důležité si uvědomit, že někdy lidé píšou recenze sarkasticky, takže bys měl
brát v úvahu i možnost sarkasmu a snažit se pochopit, co tím autor doopravdy myslel.

Také pamatuj, že někdy mohou být recenze smíšené, což znamená, že obsahují jak
pozitivní, tak negativní aspekty, a v takovém případě bys měl zvážit, zda převažuje
to pozitivní nebo negativní, a pokud je to vyrovnané, tak je to neutrální. Faktické
recenze bez emocí jsou také neutrální. Dej si prosím opravdu záležet.

Až budeš mít hotovo, dej mi prosím vědět, jaký je sentiment. Bylo by skvělé, kdybys
to vrátil v nějakém strukturovaném formátu, ideálně jako JSON, ať se to dobře zpracovává.

Tady je ta recenze: {review_text}
"""

# Proč KRÁTKÝ vyhrává nad DLOUHÝM:
#   - "velmi důležité / dej si záležet / skvělou práci" = výplň s nulovou entropií,
#     výkon nezvyšuje (anti-patterny rozvláčnost a cargo-cult).
#   - DLOUHÝ nemá koncovou značku ani přísné JSON schéma → model přidá prózu (pravidlo 3).
#   - DLOUHÝ nemá příklady → kolísá na hraničních případech, jako je sarkasmus (pravidlo 4).
#   - KRÁTKÝ má oddělovač <review> kolem nedůvěryhodného vstupu (pravidlo 9, Defensive).
#   - KRÁTKÝ má ~120 slov proti ~280 slovům DLOUHÉHO, a je PŘESNĚJŠÍ.
# Why SHORT beats LONG:
#   - "very important / do your best / great job" is zero-entropy filler; it does not
#     raise performance (the verbosity and cargo-cult anti-patterns).
#   - LONG has no end marker and no strict JSON schema → the model adds prose (rule 3).
#   - LONG has no examples → it wobbles on border cases such as sarcasm (rule 4).
#   - SHORT wraps the untrusted input in a <review> delimiter (rule 9, Defensive).
#   - SHORT is ~120 words against LONG's ~280, and it is MORE ACCURATE.


def _demo() -> None:
    """Print the rules, anti-patterns, frameworks and the short-versus-long word counts, in both languages."""
    print(f"# {METADATA['id']} v{METADATA['version']}\n")
    print(f"## {len(RULES)} pravidel / rules")
    for r in RULES:
        print(f"  {r['n']}. {r['name']}")
        print(f"       CS: {r['do']}")
        print(f"       EN: {r['do_en']}")
    print(f"\n## {len(ANTI_PATTERNS)} anti-patternů / anti-patterns")
    for a in ANTI_PATTERNS:
        print(f"  - {a['name']}")
        print(f"       CS: {a['symptom']}")
        print(f"       EN: {a['symptom_en']}")
    print(f"\n## Rámce / Frameworks ({len(FRAMEWORKS)})")
    for key, fw in FRAMEWORKS.items():
        print(
            f"  - {key} [{fw['tier']}]: {' / '.join(i.split(' — ')[0].split(' ')[0] for i in fw['items'])}"
        )
    print("\n## Demo: SHORT vs LONG (stejná úloha / the same task)")
    print(
        f"  SHORT = {len(SHORT_PROMPT.split())} slov / words: strict schema + examples + delimiter"
    )
    print(
        f"  LONG  = {len(LONG_PROMPT.split())} slov / words: filler, no schema, no examples → "
        "worse and longer / horší a delší"
    )


if __name__ == "__main__":
    _demo()
