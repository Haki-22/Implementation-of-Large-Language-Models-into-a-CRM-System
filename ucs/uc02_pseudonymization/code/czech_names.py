"""Inflected forms of Czech personal names for the planted-PII corpus.

The corpus plants a person's name in the nominative and once more in an oblique
case, the way a CRM note mentions people ("volal pan Novák", "řekl jsem panu
Novákovi", "s paní Slavíkovou"). The forms come from a small rule table keyed by
the contact's gender and the ending of the word; only the regular, high-frequency
paradigms are covered and a name outside them gets no oblique form rather than a
wrong one. The forms are strings the generator supplies to the renderer, so a
form that is unusual is at worst an unnatural sentence, never a wrong gold label.
"""

from __future__ import annotations

# Cases used by the corpus, with the label written into the gold record.
CASES: tuple[str, ...] = ("gen", "dat", "instr")

_SOFT_CONSONANTS = ("č", "ř", "š", "ž", "c", "j", "ď", "ť", "ň")


# ---------------------------------------------------------------------------
# Surnames
# ---------------------------------------------------------------------------


def decline_surname(surname: str, gender: str, case: str) -> str | None:
    """Return ``surname`` in ``case`` for a person of ``gender`` ('m' / 'f'), or None.

    Feminine: the -ová paradigm only (Slavíková → Slavíkové, Slavíkovou) and the
    adjectival -á (Černá → Černé, Černou). Masculine: hard-consonant nouns
    (Novák → Nováka, Novákovi, Novákem), soft-consonant nouns (Tomeš → Tomeše),
    nouns in -a (Svoboda → Svobody, Svobodovi, Svobodou), adjectives in -ý
    (Černý → Černého, Černému, Černým) and in -í (Krejčí → Krejčího, Krejčímu,
    Krejčím), and the fleeting-e nouns in -ek / -el (Havlíček → Havlíčka).
    """
    if case not in CASES or not surname:
        return None
    s = surname
    if gender == "f":
        if s.endswith("ová"):
            return s[:-1] + {"gen": "é", "dat": "é", "instr": "ou"}[case]
        if s.endswith("á"):
            return s[:-1] + {"gen": "é", "dat": "é", "instr": "ou"}[case]
        return None
    if s.endswith("ý"):
        return s[:-1] + {"gen": "ého", "dat": "ému", "instr": "ým"}[case]
    if s.endswith("í"):
        return s[:-1] + {"gen": "ího", "dat": "ímu", "instr": "ím"}[case]
    if s.endswith("a"):
        return s[:-1] + {"gen": "y", "dat": "ovi", "instr": "ou"}[case]
    if s.endswith(("e", "o", "u", "i", "y", "á", "é", "ů")):
        return None
    stem = s
    if len(s) > 3 and s.endswith(("ek", "el")) and s[-3] not in "aeiouáéíóúůy":
        stem = s[:-2] + s[-1]  # Havlíček -> Havlíčk-, Pavel -> Pavl-
    if s.endswith(_SOFT_CONSONANTS):
        return stem + {"gen": "e", "dat": "ovi", "instr": "em"}[case]
    return stem + {"gen": "a", "dat": "ovi", "instr": "em"}[case]


# ---------------------------------------------------------------------------
# First names
# ---------------------------------------------------------------------------


def decline_first_name(first: str, gender: str, case: str) -> str | None:
    """Return ``first`` in ``case``, or None when the paradigm is not covered.

    Feminine names in -a (Romana → Romany, Romaně, Romanou; Lenka → Lenky, Lence,
    Lenkou) and in -ie (Marie → Marie, Marii, Marií). Masculine names follow the
    surname rules (Jan → Jana, Janovi, Janem; Jiří → Jiřího; Pavel → Pavla).
    """
    if case not in CASES or not first:
        return None
    f = first
    if gender == "f":
        if f.endswith("ie"):
            return f[:-1] + {"gen": "e", "dat": "i", "instr": "í"}[case]
        if f.endswith("a"):
            if case == "gen":
                return f[:-1] + "y"
            if case == "instr":
                return f[:-1] + "ou"
            stem = f[:-1]
            if stem.endswith("k"):
                return stem[:-1] + "ce"
            if stem.endswith("g"):
                return stem[:-1] + "ze"
            if stem.endswith("h"):
                return stem[:-1] + "ze"
            if stem.endswith("r"):
                return stem[:-1] + "ře"
            if stem.endswith(("ch",)):
                return stem[:-2] + "še"
            return stem + "ě" if stem[-1] in "bdmnptvzsl" else stem + "e"
        return None
    return decline_surname(f, "m", case)


# ---------------------------------------------------------------------------
# Forms a corpus message may plant
# ---------------------------------------------------------------------------


def person_forms(first: str, last: str, gender: str) -> dict[str, str]:
    """Return the name forms available for planting, keyed by form label.

    Always ``"nom"`` (the full nominative). Then the oblique surname-only forms
    ``"gen_surname"`` / ``"dat_surname"`` / ``"instr_surname"`` and the full-name
    forms ``"gen_full"`` / ``"dat_full"`` / ``"instr_full"`` for every case both
    words support. A form equal to another form is dropped.
    """
    forms: dict[str, str] = {"nom": f"{first} {last}".strip()}
    for case in CASES:
        surname = decline_surname(last, gender, case)
        if surname:
            forms[f"{case}_surname"] = surname
            given = decline_first_name(first, gender, case)
            if given:
                forms[f"{case}_full"] = f"{given} {surname}"
    seen: set[str] = set()
    out: dict[str, str] = {}
    for label, form in forms.items():
        if form in seen:
            continue
        seen.add(form)
        out[label] = form
    return out


__all__ = ["CASES", "decline_first_name", "decline_surname", "person_forms"]
