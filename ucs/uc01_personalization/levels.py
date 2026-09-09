"""The personalisation ladder: what each level adds, what it needs, and how its text is produced.

Same person, same brief, one message per level; each level adds one kind of
customer data, so the differences between rows are attributable:

    L0  generic       the brief as written, no model            (zero point)
    L1  merge         greeting + Ty/Vy swap table + gender words, Python only (today's CRM)
    L2  morphology    greeting, gender, Ty/Vy -> the model rewrites for agreement
    L3a linguistic    + frequent words + the customer's own writing sample
    L3b purchases     + the newest purchases with product and category
    L3c reviews       + the newest review headlines
    L3d role          + job title and employer (B2B contacts)
    L3  behaviour     + all of the above
    L4  aspects       L3 + what the customer praises / criticises (from UC-04)
    L5  psychographic L3 + the OCEAN profile
    L6a recommendations  L5 + UC-04's recommended products with a Czech reason
    L6b topics           L5 + UC-04's interest themes
    L6c lifecycle        L5 + the lifecycle stage
    L6d pricing          L6a + the price line: the best recommendation at list price, the
                         lowest-ranked one with the discount, the disclosure sentence (pricing.py)
    L6  hyper            L5 + recommendations, topics and lifecycle (the assignment's tier;
                         the price line stays the single-field arm 6d)

``needs`` is the enrichment a contact must have for the level to run at all;
the runner records a skip with the missing slot instead of calling a model.
``optional`` slots are added when present (a B2B role in L3; aspects in L5 and
L6 once UC-04 produces them). Identity gaps (no stored greeting, unknown gender
or formality) never block a level: the row runs with what it has, the prompt
says what is unknown, and the judge checks only what is stored (user
2026-09-04, second decision of the walkthrough). Decisions of 2026-09-04.
"""

from __future__ import annotations

from dataclasses import dataclass

from ucs.uc01_personalization.data import Brief, ContactRecord, Enrichment
from ucs.uc01_personalization import prompts

# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Level:
    """One rung: its inputs and whether a model is called."""

    id: str
    name: str
    uses_model: bool
    needs: tuple[str, ...] = ()
    optional: tuple[str, ...] = ()

    @property
    def slots(self) -> tuple[str, ...]:
        """All slots this level may use: the required ``needs`` followed by ``optional``."""
        return self.needs + self.optional

    def missing(self, contact: ContactRecord, enrichment: Enrichment) -> list[str]:
        """The enrichment inputs this contact lacks for the level; empty means it can run.

        Identity fields are deliberately not checked here: a defective row (no
        greeting, unknown gender or formality) still runs every level, so the
        reader sees what the system does with a half-known customer.
        """
        del contact  # identity gaps do not block; see the module docstring
        present = enrichment.present()
        return [s for s in self.needs if s not in present]


_L3 = ("frequent_words", "style_excerpt", "purchases", "reviews")

LEVELS: dict[str, Level] = {
    lvl.id: lvl
    for lvl in (
        Level("0", "generic", False),
        Level("1", "merge", False),
        Level("2", "morphology", True),
        Level("3a", "linguistic", True, needs=("frequent_words", "style_excerpt")),
        Level("3b", "purchases", True, needs=("purchases",)),
        Level("3c", "reviews", True, needs=("reviews",)),
        Level("3d", "role", True, needs=("role",)),
        Level("3", "behaviour", True, needs=_L3, optional=("role",)),
        Level("4", "aspects", True, needs=_L3 + ("aspects",), optional=("role",)),
        Level("5", "psychographic", True, needs=_L3 + ("ocean",), optional=("role", "aspects")),
        Level(
            "6a",
            "recommendations",
            True,
            needs=_L3 + ("ocean", "recommendations"),
            optional=("role", "aspects"),
        ),
        Level("6b", "topics", True, needs=_L3 + ("ocean", "topics"), optional=("role", "aspects")),
        Level(
            "6c",
            "lifecycle",
            True,
            needs=_L3 + ("ocean", "lifecycle"),
            optional=("role", "aspects"),
        ),
        Level(
            "6d",
            "pricing",
            True,
            needs=_L3 + ("ocean", "recommendations", "pricing"),
            optional=("role", "aspects"),
        ),
        Level(
            "6",
            "hyper",
            True,
            needs=_L3 + ("ocean", "recommendations", "topics", "lifecycle"),
            optional=("role", "aspects"),
        ),
    )
}

LADDER: tuple[str, ...] = tuple(LEVELS)


def parse_levels(spec: str) -> list[Level]:
    """``"0,1,2,3a"`` -> the levels, in ladder order; ``"all"`` is every rung."""
    if spec.strip().lower() == "all":
        return list(LEVELS.values())
    wanted = {part.strip().lower().lstrip("l") for part in spec.split(",") if part.strip()}
    unknown = wanted - set(LEVELS)
    if unknown:
        raise ValueError(f"unknown level(s) {sorted(unknown)}; choose from {list(LEVELS)}")
    return [LEVELS[k] for k in LADDER if k in wanted]


# ---------------------------------------------------------------------------
# The no-model rungs
# ---------------------------------------------------------------------------

_TY_VY_SWAPS: tuple[tuple[str, str], ...] = (
    ("pro Vás", "pro tebe"),
    ("pro vás", "pro tebe"),
    ("k Vašemu", "k tvému"),
    ("k vašemu", "k tvému"),
    ("Vašemu", "tvému"),
    ("vašemu", "tvému"),
    ("Vaše", "tvoje"),
    ("vaše", "tvoje"),
    ("Váš", "tvůj"),
    ("váš", "tvůj"),
    ("Vám", "ti"),
    ("vám", "ti"),
    ("Vás", "tě"),
    ("vás", "tě"),
    ("vy jste", "ty jsi"),
    ("Vy jste", "Ty jsi"),
    ("jste", "jsi"),
    ("máte", "máš"),
    ("čekáte", "čekáš"),
    ("přihlaste se", "přihlas se"),
    ("Přihlaste se", "Přihlas se"),
    ("potvrďte", "potvrď"),
    ("Potvrďte", "Potvrď"),
    ("mrkněte", "mrkni"),
    ("Mrkněte", "Mrkni"),
)

_GENDER_WORDS: tuple[tuple[str, str, str], ...] = (
    # plural-neutral form, feminine, masculine
    ("pozváni", "pozvána", "pozván"),
    ("vybráni", "vybrána", "vybrán"),
    ("zákazníci", "zákaznice", "zákazník"),
    ("účastníky", "účastnice", "účastníka"),
)

_GENERIC_GREETINGS = ("Vážený zákazníku,", "Vážená zákaznice,", "Vážení zákazníci,", "Dobrý den,")
_LEADING_EMOJI = "🔥✨🏆📅🛒🎁⚡💡🚀🎉 "


def generic(brief: Brief) -> str:
    """L0: the brief exactly as the operator wrote it."""
    return brief.default_template


def merge(brief: Brief, contact: ContactRecord) -> str:
    """L1: what a mail merge does — insert the stored greeting, swap the register table, four gender words.

    This is the state today's mail-merge CRM reaches: deterministic
    substitution that cannot know which other words in a free text need agreement
    ("co jste odkládali" stays plural for a woman). L2 exists because of that.

    A half-known contact gets what a mail merge would give: unknown formality
    keeps the template's vykání, unknown gender keeps the plural-neutral words,
    a missing greeting becomes "Dobrý den" (or "Ahoj <first name>" for tykání).
    """
    body = brief.default_template.strip().lstrip(_LEADING_EMOJI).strip()
    for greeting in _GENERIC_GREETINGS:
        if body.startswith(greeting):
            body = body[len(greeting) :].strip()
    body = body[:1].lower() + body[1:] if body else body
    if contact.formal is False:
        for before, after in _TY_VY_SWAPS:
            body = body.replace(before, after)
    if contact.gender in ("m", "f"):
        female = contact.gender == "f"
        for neutral, fem, masc in _GENDER_WORDS:
            body = body.replace(neutral, fem if female else masc)
    greeting = (
        contact.name_vocative
        or (f"Ahoj {contact.first_name}" if contact.formal is False else "Dobrý den")
    ).rstrip(" ,")
    return f"{greeting}, {body}"


# ---------------------------------------------------------------------------
# The model rungs
# ---------------------------------------------------------------------------


def build_prompt(
    level: Level, contact: ContactRecord, brief: Brief, enrichment: Enrichment
) -> tuple[str, str]:
    """(system, user) prompt for a model level, carrying exactly the level's slots."""
    if not level.uses_model:
        raise ValueError(f"level {level.id} does not call a model")
    return prompts.build(contact, brief, enrichment, level.slots)
