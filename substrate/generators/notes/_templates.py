"""The Czech text the seeded notes are rendered from.

Read this file to see what the substrate's notes actually say. Everything here
is content, not machinery: the gender-bearing verb table and the two template
pools. Templates use ``str.format`` placeholders, which
:mod:`substrate.generators.notes._render` fills from a contact row.

Two pools, because they have different preconditions:

``_PLAIN_TEMPLATES``
    Carry no personal data. Usable for any contact, except that the ones with a
    gender-bearing verb need a known gender.
``_PII_TEMPLATES``
    Quote one of the contact's own fields. Each carries the fields it needs and
    is eligible only when the contact actually has them, so a note never invents
    an identifier -- every value in a note traces back to the contact row, which
    is what lets UC-02 derive its gold spans from the substrate.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Verb agreement
# ---------------------------------------------------------------------------

# Gender-bearing verb slots: slot name -> (masculine, feminine) past-tense form.
_VERBS: dict[str, tuple[str, str]] = {
    "ptal": ("ptal", "ptala"),
    "projevil": ("projevil", "projevila"),
    "pozadoval": ("požadoval", "požadovala"),
    "reklamoval": ("reklamoval", "reklamovala"),
    "vznesl": ("vznesl", "vznesla"),
    "potvrdil": ("potvrdil", "potvrdila"),
    "informovan": ("informován", "informována"),
}

# ---------------------------------------------------------------------------
# Templates without personal data
# ---------------------------------------------------------------------------

# (category, template). Templates may use {first}, {full} and the verb slots
# above. Templates without a verb slot are the only ones a contact with unknown
# gender can receive.

_PLAIN_TEMPLATES: tuple[tuple[str, str], ...] = (
    ("complaint", "{first} {reklamoval} poškozený obal zásilky, sjednána sleva 10 %."),
    ("complaint", "Stížnost na nefunkční příslušenství, {first} {pozadoval} výměnu kusu."),
    ("complaint", "Reklamace vyřízena vrácením peněz na účet, zákazník informován e-mailem."),
    ("support", "{first} se {ptal} na záruční podmínky, zaslány e-mailem."),
    ("support", "Dotaz na kompatibilitu příslušenství, doporučen produkt z katalogu."),
    ("support", "{first} {vznesl} dotaz na stav reklamace předchozí objednávky."),
    ("sales", "{first} {projevil} zájem o sezónní výprodej elektroniky."),
    ("sales", "Poptávka na velkoobchodní ceník, předáno obchodnímu zástupci."),
    ("sales", "Nabídnut věrnostní program, {first} {potvrdil} zájem o registraci."),
    (
        "follow_up",
        "{first} {pozadoval} krátké shrnutí k předchozí objednávce, zavolat příští týden.",
    ),
    ("follow_up", "Domluvena schůzka k prezentaci novinek, termín upřesní {first}."),
    ("follow_up", "Bez reakce na poslední nabídku, připomenout po konci měsíce."),
    ("delivery", "{first} se {ptal} na možnost osobního odběru v prodejně."),
    ("delivery", "Zásilka zpožděna u dopravce, {first} {informovan} o novém termínu."),
    ("delivery", "Balík nedoručen, zahájena reklamace u přepravce."),
    ("general", "{first} preferuje stručné e-mailové aktualizace, bez telefonátů."),
    ("general", "Poznámka ze schůzky: {first} porovnává varianty, rozhodne do konce měsíce."),
    ("general", "Domluvena fakturace na firmu, doklad vystaven."),
)

# ---------------------------------------------------------------------------
# Templates quoting the contact's own data
# ---------------------------------------------------------------------------

# (category, template, required contact fields). A PII template is eligible
# only when the contact carries every field it references.
_PII_TEMPLATES: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("support", "Telefonní kontakt ověřen pro {full}: {phone}.", ("phone",)),
    ("support", "Záruční podmínky zaslat na {email}.", ("email",)),
    (
        "delivery",
        "Doručovací adresa potvrzena: {street}, {city} {postal}.",
        ("full_street", "city", "postal_code"),
    ),
    (
        "delivery",
        "{first} {potvrdil} doručení na adresu {street}, {city}.",
        ("full_street", "city"),
    ),
    (
        "sales",
        "Cenovou nabídku poslat na {email}, {first} {pozadoval} odpověď do týdne.",
        ("email",),
    ),
    ("general", "{full} žádá vést poznámku pod zákaznickým kódem {reviewer}.", ("reviewer_id",)),
)
