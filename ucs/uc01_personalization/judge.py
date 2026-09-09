"""Judging a generated message: the script rule and the model-judge cascade.

Two kinds of judge, in a fixed order. The **script rule** (``validate_rules``) is
free and always first: it checks what the contact row stores — the greeting, the
register, gender agreement at four site classes, no leaked instruction text —
and applies a check only when the row stores the field (``unchecked`` otherwise).
The **model judges** read the whole text and run as a second pass over a finished
run (``judge_run.py``): one call (``judge_with_model``) returns three verdicts with
quoted spans, the span check (``span_status``) labels every span found / missing /
n/a, which makes the verdict FULL / PARTIAL / MALFORMED without touching a
boolean; the cascade (``Cascade``, ``judge_cascade``) is the escalation ladder,
level 1 one judge, level 2 two providers joined, level 3 an arbiter from the
third provider at higher effort; ``decide`` is the routing table with the final
states VALID / PARTIAL (a human verifies) / HUMAN (a human decides). The tables
that explain all of this, with the prompts, schemas and file locations, are in
``README.md`` § "How a message is judged"; the decisions of record are D-UC01-4
(gender rule) and D-UC01-5 (cascade).
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import asdict, dataclass, field
from typing import Any

from ucs.uc01_personalization.data import ContactRecord
from utils.generation import PROVIDERS, generate_json, resolve_model, resolve_tier

# ---------------------------------------------------------------------------
# Rules (phase 0)
# ---------------------------------------------------------------------------

_INSTRUCTION_BLEED = (
    "ignore previous",
    "ignore above",
    "system prompt",
    "developer message",
    "jailbreak",
    "prompt injection",
)
_FORMAL_MARKERS = ("vám", "vás", "vaše", "váš", "vámi", "vašeho", "vašem", "vaši")
_INFORMAL_MARKERS = (
    " ti ",
    " tě ",
    " tebe",
    " tvůj",
    " tvoje",
    " tvého",
    " tebou",
    " tobě",
    " ti,",
    " tě,",
)


# ---------------------------------------------------------------------------
# Gender agreement (phase 0, narrow): the sites where a message agrees with its
# addressee. Each pattern yields (word, gender the word implies); "n" = neutral.
# ---------------------------------------------------------------------------

_AUX = r"(?:jste|jsi|ses|sis)"
_FILLER = (
    r"(?:(?:to|si|se|už|ještě|právě|zatím|nedávno|dnes|teď|také|taky|"
    r"zcela|docela|velmi|opravdu|moc|skutečně|naprosto|vždy|stále)\s+){0,2}"
)
# adverbs that end like a participle and may follow the auxiliary
_NOT_PARTICIPLES = {"zcela", "docela", "dokola", "zdola", "zpola", "zhola", "dál", "půl", "cíl"}
# short predicates after the auxiliary: masculine form, feminine adds -a
_PREDICATES = (
    "spokojen|zařazen|vybrán|zvolen|pozván|nadšen|vítán|přihlášen|oceněn|odměněn|"
    "zaregistrován|registrován|zapsán|rád|sám|jist|připraven|povinen|oprávněn|přesvědčen"
)
_ROLE_M = (
    "zákazník|zákazníka|zákazníkovi|zákazníkem|zákazníku|klient|klienta|klientovi|klientem|"
    "kliente|člen|člena|členovi|členem|člene|uživatel|uživatele|uživateli|uživatelem|"
    "partner|partnera|partnerovi|partnerem|partnere|majitel|majitele|majiteli|majitelem"
)
_ROLE_F = (
    "zákaznice|zákaznici|zákaznicí|klientka|klientku|klientkou|klientce|klientko|členka|"
    "členku|členkou|člence|členko|uživatelka|uživatelku|uživatelkou|uživatelce|uživatelko|"
    "partnerka|partnerku|partnerkou|partnerce|partnerko|majitelka|majitelku|majitelkou|majitelce"
)
_ROLE_FRAME = r"(?:jako|jste|jsi|náš|naše|naší|našeho|našemu|naším|milý|milá|věrný|věrná|vážený|vážená|loajální|stálý|stálá|drahý|drahá)"
_ADJ_M = "milý|věrný|vážený|stálý|drahý|spokojený|nadšený|registrovaný|přihlášený"
_ADJ_F = "milá|věrná|vážená|stálá|drahá|spokojená|nadšená|registrovaná|přihlášená"

_GENDER_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # "jste (byl) odkládal / odkládala / odkládali" — l-participle after the auxiliary
    (re.compile(rf"\b{_AUX}\s+{_FILLER}(?:byl[ai]?\s+)?(\w+?(?:l|la|li|ly))\b", re.I), "lpart"),
    # "byl jste", "vybral jsi" — l-participle before the auxiliary
    (re.compile(rf"\b(\w+?(?:l|la|li|ly))\s+{_AUX}\b", re.I), "lpart"),
    # "jste (byl) spokojen / spokojena" — short predicate after the auxiliary or after byl/byla
    (re.compile(rf"\b(?:{_AUX}|byla?)\s+{_FILLER}((?:{_PREDICATES})a?)\b", re.I), "pred"),
    # "jako náš věrný zákazník", "naší loajální zákaznicí" — the recipient's role noun
    (re.compile(rf"\b{_ROLE_FRAME}\s+(?:\w+\s+){{0,2}}?((?:{_ROLE_M}|{_ROLE_F}))\b", re.I), "role"),
    # "věrný zákazník" / "věrná zákaznice" — the adjective on that noun
    (re.compile(rf"\b((?:{_ADJ_M}|{_ADJ_F}))\s+(?:{_ROLE_M}|{_ROLE_F})\b", re.I), "adj"),
)


def _site_gender(word: str, kind: str) -> str:
    """Gender a matched word implies: "m", "f" or "n" (neutral, e.g. plural)."""
    w = word.lower()
    if kind == "lpart":
        return "f" if w.endswith("la") else "n" if w.endswith(("li", "ly")) else "m"
    if kind == "pred":
        return "f" if w.endswith("a") else "m"
    if kind == "role":
        return "f" if re.fullmatch(_ROLE_F, w) else "m"
    return "f" if re.fullmatch(_ADJ_F, w) else "m"


def gender_sites(message: str) -> list[tuple[str, str]]:
    """Every site where the message agrees with its addressee: (word, implied gender)."""
    text = message.replace("\n", " ")
    out: list[tuple[str, str]] = []
    for pattern, kind in _GENDER_PATTERNS:
        for match in pattern.finditer(text):
            word = match.group(1)
            if kind == "lpart" and word.lower() in _NOT_PARTICIPLES:
                continue
            out.append((word, _site_gender(word, kind)))
    return out


@dataclass(frozen=True)
class RulesVerdict:
    """What the rule validator found for one message.

    ``unchecked`` names the checks that could not apply because the contact
    row lacks the field they compare against ("vocative" without a stored
    greeting, "register" with unknown formality, "gender" with unknown gender);
    such a check counts as passed and the row says so (user 2026-09-04:
    validate only what is stored). ``gender_sites`` is the evidence of the
    gender check: the agreeing words and the gender each implies.
    """

    vocative_ok: bool
    register_ok: bool
    duplicate_greeting: bool
    instruction_bleed: list[str] = field(default_factory=list)
    unchecked: list[str] = field(default_factory=list)
    gender_ok: bool = True
    gender_sites: list[str] = field(default_factory=list)
    # Level 6d only: the two prices, the discount and the disclosure sentence of
    # pricing.offer must appear in the message (whitespace and case ignored).
    pricing_ok: bool = True
    pricing_sites: list[str] = field(default_factory=list)

    @property
    def accepted(self) -> bool:
        """Whether the message passes every check that applies (unchecked checks count as passed)."""
        return (
            self.vocative_ok
            and self.register_ok
            and self.gender_ok
            and self.pricing_ok
            and not self.duplicate_greeting
            and not self.instruction_bleed
        )

    @property
    def failures(self) -> list[str]:
        """The failure codes for every check that did not pass, in a fixed order."""
        out = []
        if not self.vocative_ok:
            out.append("VOCATIVE_MISMATCH")
        if self.duplicate_greeting:
            out.append("DUPLICATE_GREETING")
        if not self.register_ok:
            out.append("REGISTER_MISMATCH")
        if not self.gender_ok:
            out.append("GENDER_MISMATCH")
        if self.instruction_bleed:
            out.append("INSTRUCTION_BLEED")
        if not self.pricing_ok:
            out.append("PRICING_MISMATCH")
        return out

    def to_dict(self) -> dict[str, Any]:
        """The dict stored on a Generation (adds ``accepted`` and ``failures``)."""
        data = asdict(self)
        data["accepted"] = self.accepted
        data["failures"] = self.failures
        return data


def _register_consistent(message: str, formal: bool | None) -> bool:
    """No pronoun of the opposite register. Case-insensitive on both sides since 2026-09-04.

    A short message may contain no register pronoun at all, so only the wrong
    register is a failure; the check never demands a same-register marker.
    """
    body = " " + message.replace("\n", " ").lower() + " "
    if formal:
        return not any(m in body for m in _INFORMAL_MARKERS)
    return not any(re.search(r"\b" + re.escape(m) + r"\b", body) for m in _FORMAL_MARKERS)


def _flat(text: str) -> str:
    """``text`` with all whitespace removed and lowercased, for a whitespace/case-insensitive compare."""
    return re.sub(r"\s+", "", text).lower()


def pricing_check(message: str, pricing: dict[str, Any]) -> tuple[bool, list[str]]:
    """Level 6d: the prices, the discount and the disclosure sentence of the offer are in the message.

    Whitespace and case are ignored on both sides, so ``1 234 Kč``, ``1234 Kč`` and a
    line-wrapped disclosure sentence all count; a price is matched as its digit string.
    """
    from ucs.uc01_personalization.pricing import expected_in_message

    flat = _flat(message or "")
    sites: list[str] = []
    ok = True
    for name, value in expected_in_message(pricing).items():
        found = _flat(value) in flat
        sites.append(f"{name}={'ok' if found else 'missing'}")
        ok = ok and found
    return ok, sites


def validate_rules(
    message: str,
    contact: ContactRecord | dict[str, Any],
    pricing: dict[str, Any] | None = None,
) -> RulesVerdict:
    """Run the rule validator on one message against the contact's stored fields.

    ``pricing`` is the offer of level 6d (``pricing.offer``); when given, the message
    must carry its numbers and the disclosure sentence (``pricing_check``). Other
    levels pass nothing and the check does not apply.
    """
    fields = contact.for_judge() if isinstance(contact, ContactRecord) else contact
    greeting = str(fields.get("name_vocative") or "").strip()
    formal = fields.get("formal")
    text = message or ""
    unchecked: list[str] = []
    if greeting:
        # The briefs open with an emoji and a model may keep it in front of the
        # greeting ("🎁 Ahoj Leono, ..."): the salutation is right, the decoration is
        # the brief's. Leading symbols and whitespace are skipped, letters are not
        # (user 2026-09-07, after a manual check of the smoke on contact 4).
        body = re.sub(r"^[\W_]+", "", text)
        vocative_ok = body.startswith(greeting)
        duplicate = text.count(greeting) > 1
    else:
        vocative_ok, duplicate = True, False
        unchecked.append("vocative")
    if formal is None:
        register_ok = True
        unchecked.append("register")
    else:
        register_ok = _register_consistent(text, bool(formal))
    lowered = text.lower()
    bleed = [p for p in _INSTRUCTION_BLEED if p in lowered]
    if re.search(r"<\/?(system|developer|instruction|prompt)[^>]*>", lowered):
        bleed.append("xml_instruction_tag")
    gender = fields.get("gender")
    sites = gender_sites(text)
    if gender not in ("m", "f"):
        gender_ok = True
        unchecked.append("gender")
    else:
        gender_ok = all(g in ("n", gender) for _, g in sites)
    pricing_ok, pricing_sites = (True, []) if pricing is None else pricing_check(text, pricing)
    return RulesVerdict(
        vocative_ok=vocative_ok,
        register_ok=register_ok,
        duplicate_greeting=duplicate,
        instruction_bleed=bleed,
        unchecked=unchecked,
        gender_ok=gender_ok,
        gender_sites=[f"{w}={g}" for w, g in sites],
        pricing_ok=pricing_ok,
        pricing_sites=pricing_sites,
    )


# ---------------------------------------------------------------------------
# Model judges: one call, three verdicts with quoted spans, then the span check
# ---------------------------------------------------------------------------

CRITERIA: tuple[str, ...] = ("vocative", "register", "gender")
EVIDENCE_NA = "neposuzováno"

JUDGE_PROMPT_VERSION = (
    "1.2.0"  # 1.2.0: spans = verbatim text only, several joined with ";", no commentary
)
ARBITER_PROMPT_VERSION = "1.1.0"

JUDGE_SYSTEM = """Jsi přísný korektor českých CRM zpráv. Dostaneš údaje o příjemci a jednu zprávu. Posuď POUZE tři věci:
1. oslovení: zpráva začíná přesně zadaným oslovením a neopakuje ho; není-li oslovení uloženo, posuď jen, zda zpráva začíná správným českým oslovením (5. pád) uvedeného jména;
2. rejstřík: celá zpráva důsledně vyká, nebo důsledně tyká, podle zadání; není-li formálnost uvedena, posuď jen, že zpráva vykání a tykání nemíchá;
3. rod: všechna slova, která se shodují s příjemcem (přídavná jména, příčestí minulá, „vybrán/vybrána", „byl/byla"), mají tvar zadaného pohlaví; není-li pohlaví uvedeno, vrať true a jako úryvek napiš „neposuzováno".
Ke každému bodu uveď jako úryvek POUZE doslovný text zprávy, o který se opíráš: zkopírovaný beze změny, bez uvozovek, bez vysvětlení a bez komentáře; opíráš-li se o více míst, oddě je středníkem. Neposuzuj styl, délku ani obsah."""

ARBITER_SYSTEM = (
    JUDGE_SYSTEM
    + """
Dostaneš navíc verdikty dvou předchozích soudců i s jejich úryvky; u každého úryvku je poznámka, zda ve zprávě doslova je. Soudci se neshodli, nebo některý citoval text, který ve zprávě není, nebo neodpověděl. Rozhodni sám podle zprávy, ne podle jejich většiny, cituj jen text, který ve zprávě opravdu je, a v poli "reason" jednou větou řekni proč."""
)

JUDGE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "vocative_ok": {"type": "boolean"},
        "vocative_evidence": {"type": "string"},
        "register_ok": {"type": "boolean"},
        "register_evidence": {"type": "string"},
        "gender_ok": {"type": "boolean"},
        "gender_evidence": {"type": "string"},
    },
    "required": [
        "vocative_ok",
        "vocative_evidence",
        "register_ok",
        "register_evidence",
        "gender_ok",
        "gender_evidence",
    ],
    "additionalProperties": False,
}

ARBITER_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {**JUDGE_SCHEMA["properties"], "reason": {"type": "string"}},
    "required": [*JUDGE_SCHEMA["required"], "reason"],
    "additionalProperties": False,
}

STATUS_FULL, STATUS_PARTIAL, STATUS_MALFORMED = "FULL", "PARTIAL", "MALFORMED"
FINAL_VALID, FINAL_PARTIAL, FINAL_HUMAN = "VALID", "PARTIAL", "HUMAN"


@dataclass(frozen=True)
class JudgeSpec:
    """One judge: which CLI, which model (None = the thesis default), which tier."""

    provider: str
    model: str | None = None
    tier: str | None = "low"

    @classmethod
    def parse(cls, text: str) -> JudgeSpec:
        """``provider``, ``provider:model`` or ``provider:model:tier`` (``-`` = default model)."""
        parts = [p.strip() for p in text.split(":")]
        if not parts[0] or parts[0] not in PROVIDERS:
            raise ValueError(f"unknown judge provider {parts[0]!r}; choose from {PROVIDERS}")
        model = parts[1] if len(parts) > 1 and parts[1] not in ("", "-") else None
        tier = parts[2] if len(parts) > 2 and parts[2] else "low"
        return cls(parts[0], model, tier)

    def resolved(self) -> dict[str, Any]:
        """Provider, the concrete model id and tier this spec runs on (provenance)."""
        return {
            "provider": self.provider,
            "model": resolve_model(self.provider, self.model),
            "tier": resolve_tier(self.provider, self.tier, self.model),
        }

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model or '-'}:{self.tier or '-'}"


_QUOTE_CHARS = "„“”\"'`‚‘’"
_QUOTED = re.compile(r"[„“\"‚‘']([^„“”\"‚‘’']{4,}?)[“”\"‘’']")
_EXPLANATION = re.compile(r"\s+[—–-]{1,2}\s+")  # "quote — explanation" from a talkative judge
_FRAGMENT_SEP = re.compile(r"\s*[;|\n]\s*|\s*,\s+")
_MIN_FRAGMENT = 4


def _normalize(text: str) -> str:
    """Case-folded, whitespace-collapsed, outer quotes, dots and ellipses stripped."""
    t = " ".join(text.replace("\n", " ").replace("...", " ").replace("…", " ").split()).casefold()
    return t.strip(" " + _QUOTE_CHARS + ".,;:").strip()


def evidence_fragments(evidence: str) -> list[str]:
    """The pieces of text a judge actually quoted.

    Judges answer in three shapes: one contiguous span; several spans joined
    with ``;`` (the register shows in many places); or a span followed by an
    explanation after a dash. Quoted pieces win when present; otherwise the text
    before a dash-explanation is split on ``;`` / ``|`` / newlines. Pieces
    shorter than ``_MIN_FRAGMENT`` characters are dropped (a lone "a" proves nothing).
    """
    quoted = [q for q in _QUOTED.findall(evidence) if len(_normalize(q)) >= _MIN_FRAGMENT]
    if quoted:
        return quoted
    head = _EXPLANATION.split(evidence, maxsplit=1)[0]
    pieces = [_normalize(x) for x in _FRAGMENT_SEP.split(head)]
    return [x for x in pieces if len(x) >= _MIN_FRAGMENT] or [_normalize(head)]


def span_status(evidence: str | None, message: str) -> str:
    """``found`` when every piece the judge quoted occurs in the message,
    ``n/a`` for the not-assessed marker, ``missing`` otherwise (including an
    empty span). The label never changes a boolean; it says whether the judge
    quoted text that is really there."""
    if evidence is None:
        return "missing"
    ev = _normalize(evidence)
    if not ev:
        return "missing"
    if ev == _normalize(EVIDENCE_NA) or ev.startswith(_normalize(EVIDENCE_NA)):
        return "n/a"
    haystack = _normalize(message)
    pieces = [_normalize(x) for x in evidence_fragments(evidence)]
    pieces = [x for x in pieces if x]
    if not pieces:
        return "missing"
    return "found" if all(x in haystack for x in pieces) else "missing"


@dataclass
class JudgeVerdict:
    """One judge's answer after the span check.

    ``ok`` is empty when the call or its JSON failed (MALFORMED); otherwise it
    holds the three booleans exactly as returned. ``spans`` labels each quoted
    span; the labels never change a boolean. ``verdict`` is the AND of the
    booleans, or ``None`` when MALFORMED.
    """

    role: str  # judge | arbiter
    provider: str
    model: str | None
    tier: str | None
    ok: dict[str, bool] = field(default_factory=dict)
    evidence: dict[str, str] = field(default_factory=dict)
    spans: dict[str, str] = field(default_factory=dict)
    status: str = STATUS_MALFORMED
    reason: str | None = None
    error: str | None = None
    seconds: float = 0.0

    @property
    def verdict(self) -> str | None:
        """"valid" when every criterion's boolean is true, "invalid" otherwise, ``None`` when MALFORMED."""
        if self.status == STATUS_MALFORMED or not self.ok:
            return None
        return "valid" if all(self.ok.get(c) for c in CRITERIA) else "invalid"

    def to_dict(self) -> dict[str, Any]:
        """The dict stored in verdicts.jsonl (adds the derived ``verdict``)."""
        d = asdict(self)
        d["verdict"] = self.verdict
        return d


def assessable_criteria(contact: ContactRecord) -> set[str]:
    """The criteria the contact's stored facts let a judge assess.

    A judge may answer "neposuzováno" only where the fact is missing; on an
    assessable criterion that answer is a dodge and its span counts as missing.
    """
    out = {"vocative"}  # a name is always there, a stored greeting or not
    if contact.formal is not None:
        out.add("register")
    if contact.gender in ("m", "f"):
        out.add("gender")
    return out


def evaluate_judge_json(
    data: Any,
    message: str,
    *,
    role: str,
    provider: str,
    model: str | None,
    tier: str | None,
    assessable: set[str] | None = None,
) -> JudgeVerdict:
    """Turn a judge's JSON into a ``JudgeVerdict``: read the booleans, label the spans.

    ``assessable`` (see ``assessable_criteria``) turns an "n/a" on a criterion
    the judge should have assessed into "missing".
    """
    verdict = JudgeVerdict(role=role, provider=provider, model=model, tier=tier)
    if not isinstance(data, dict) or not all(
        isinstance(data.get(f"{c}_ok"), bool) for c in CRITERIA
    ):
        verdict.error = f"judge JSON without the three booleans: {str(data)[:200]}"
        return verdict
    verdict.ok = {c: bool(data[f"{c}_ok"]) for c in CRITERIA}
    verdict.evidence = {c: str(data.get(f"{c}_evidence", "")) for c in CRITERIA}
    verdict.spans = {c: span_status(verdict.evidence[c], message) for c in CRITERIA}
    for c in assessable or ():
        if verdict.spans[c] == "n/a":
            verdict.spans[c] = "missing"
    verdict.status = STATUS_PARTIAL if "missing" in verdict.spans.values() else STATUS_FULL
    if role == "arbiter":
        verdict.reason = str(data.get("reason", "")).strip() or None
    return verdict


def _facts(contact: ContactRecord) -> str:
    """The contact's stored greeting, gender and formality as the Czech prompt block a judge reads."""
    greeting = (
        f"Oslovení: {contact.name_vocative}"
        if contact.name_vocative
        else f"Jméno: {contact.first_name} {contact.last_name}\nOslovení: není uloženo"
    )
    gender = {"m": "muž", "f": "žena"}.get(contact.gender or "", "neuvedeno")
    formality = (
        "neuvedeno" if contact.formal is None else ("vykání" if contact.formal else "tykání")
    )
    return f"{greeting}\nPohlaví: {gender}\nFormálnost: {formality}"


def _render_prior(prior: list[JudgeVerdict]) -> str:
    """The prior judges' verdicts as the Czech lines the arbiter prompt shows it, one judge per line."""
    lines = []
    for v in prior:
        if v.status == STATUS_MALFORMED:
            lines.append(f"- {v.provider}: neodpověděl ({v.error or 'bez verdiktu'})")
            continue
        parts = []
        for c in CRITERIA:
            note = {"found": "ve zprávě je", "missing": "VE ZPRÁVĚ NENÍ", "n/a": "neposuzováno"}[
                v.spans[c]
            ]
            parts.append(f"{c}={'ok' if v.ok[c] else 'CHYBA'} („{v.evidence[c]}“ – {note})")
        lines.append(f"- {v.provider}: " + "; ".join(parts))
    return "\n".join(lines)


async def judge_with_model(
    message: str,
    contact: ContactRecord,
    spec: JudgeSpec,
    *,
    role: str = "judge",
    prior: list[JudgeVerdict] | None = None,
    timeout: int = 180,
) -> JudgeVerdict:
    """One judge call, behind the switch; never raises, a failure is a MALFORMED verdict."""
    resolved = spec.resolved()
    prompt = (
        f"{_facts(contact)}\n\n<zpráva>\n{message}\n</zpráva>\n\n"
        + (
            f"Předchozí verdikty:\n{_render_prior(prior)}\n\n"
            if role == "arbiter" and prior
            else ""
        )
        + "Vrať JSON podle schématu."
    )
    started = time.monotonic()
    try:
        data = await generate_json(
            prompt,
            ARBITER_SCHEMA if role == "arbiter" else JUDGE_SCHEMA,
            provider=spec.provider,
            system_prompt=ARBITER_SYSTEM if role == "arbiter" else JUDGE_SYSTEM,
            model=spec.model,
            tier=spec.tier,
            timeout=timeout,
            retries=0,
        )
        verdict = evaluate_judge_json(
            data, message, role=role, assessable=assessable_criteria(contact), **resolved
        )
    except Exception as exc:  # noqa: BLE001 - a failed judge is a MALFORMED verdict, never a crash
        verdict = JudgeVerdict(role=role, error=f"{type(exc).__name__}: {exc}", **resolved)
    verdict.seconds = round(time.monotonic() - started, 2)
    return verdict


# ---------------------------------------------------------------------------
# The cascade: levels 1-3 and the routing table
# ---------------------------------------------------------------------------

JUDGE_ORDER: tuple[str, ...] = ("claude", "agy", "codex")
ARBITER_TIER = "high"


@dataclass(frozen=True)
class Cascade:
    """Level 1 = one judge; 2 = two judges joined; 3 = two judges + an arbiter."""

    level: int
    judges: tuple[JudgeSpec, ...]
    arbiter: JudgeSpec | None = None

    def __post_init__(self) -> None:
        """Validate the cascade's shape: a known level, the right judge count, an arbiter when level 3 needs one.

        Raises:
            ValueError: the level is not 1/2/3, the judge count does not match
                the level, level 3 has no arbiter, or level 2's two judges
                share a provider.
        """
        need = 1 if self.level == 1 else 2
        if self.level not in (1, 2, 3):
            raise ValueError("cascade level must be 1, 2 or 3")
        if len(self.judges) != need:
            raise ValueError(f"level {self.level} takes {need} judge(s), got {len(self.judges)}")
        if self.level == 3 and self.arbiter is None:
            raise ValueError("level 3 needs an arbiter")
        if self.level == 2 and self.judges[0].provider == self.judges[1].provider:
            raise ValueError("level 2 and 3 judges must come from two providers")

    def to_dict(self) -> dict[str, Any]:
        """The cascade as recorded in a judge folder's config.json (resolved models, prompt versions)."""
        return {
            "level": self.level,
            "judges": [j.resolved() for j in self.judges],
            "arbiter": self.arbiter.resolved() if self.arbiter else None,
            "judge_prompt_version": JUDGE_PROMPT_VERSION,
            "arbiter_prompt_version": ARBITER_PROMPT_VERSION if self.arbiter else None,
        }


def default_cascade(level: int, generator_provider: str) -> Cascade:
    """Judges = the providers that did not write the message (claude, agy, codex order);
    arbiter = the writer's provider at tier high. ``mock`` judges itself, for plumbing."""
    if generator_provider == "mock":
        if level == 1:
            return Cascade(1, (JudgeSpec("mock", None, None),))
        return _mock_cascade(level)
    others = [p for p in JUDGE_ORDER if p != generator_provider]
    judges = tuple(JudgeSpec(p, None, "low") for p in others[: 1 if level == 1 else 2])
    arbiter = JudgeSpec(generator_provider, None, ARBITER_TIER) if level == 3 else None
    return Cascade(level, judges, arbiter)


def _mock_cascade(level: int) -> Cascade:
    """A ``Cascade`` of ``mock`` judges for plumbing, built without ``Cascade.__post_init__``'s provider check.

    Level 2/3 normally requires two distinct providers; the mock provider
    stands in for both here, so the object is constructed directly instead of
    through the validating constructor.
    """
    # two "providers" are required at level 2/3; the mock stands in for both, so the
    # provider check is bypassed by building the object without validation of names.
    cascade = object.__new__(Cascade)
    object.__setattr__(cascade, "level", level)
    object.__setattr__(
        cascade, "judges", (JudgeSpec("mock", None, None), JudgeSpec("mock", None, None))
    )
    object.__setattr__(cascade, "arbiter", JudgeSpec("mock", None, None) if level == 3 else None)
    return cascade


@dataclass
class CascadeResult:
    """What the cascade decided for one message, with the whole trail."""

    final: str  # VALID | PARTIAL | HUMAN
    reason: str
    rules: dict[str, Any]
    judges: list[JudgeVerdict] = field(default_factory=list)
    arbiter: JudgeVerdict | None = None

    @property
    def calls(self) -> int:
        """How many model calls the cascade made: one per judge, plus one more if an arbiter ran."""
        return len(self.judges) + (1 if self.arbiter else 0)

    def to_dict(self) -> dict[str, Any]:
        """The trail stored per message in verdicts.jsonl."""
        return {
            "final": self.final,
            "reason": self.reason,
            "calls": self.calls,
            "rules": self.rules,
            "judges": [j.to_dict() for j in self.judges],
            "arbiter": self.arbiter.to_dict() if self.arbiter else None,
        }


def decide_single(v: JudgeVerdict) -> tuple[str, str]:
    """The last judge in line (level 1, or the arbiter): FULL composes, PARTIAL and MALFORMED go to the human."""
    if v.status == STATUS_MALFORMED:
        return FINAL_HUMAN, f"{v.role}_malformed"
    if v.status == STATUS_PARTIAL:
        return FINAL_PARTIAL, f"{v.role}_partial_evidence"
    return (
        (FINAL_VALID, f"{v.role}_valid")
        if v.verdict == "valid"
        else (FINAL_HUMAN, f"{v.role}_invalid")
    )


def decide_pair(a: JudgeVerdict, b: JudgeVerdict) -> tuple[str, str] | None:
    """Two joined judges: a decision when both are FULL and agree, else ``None`` = one step onward."""
    if a.status == STATUS_FULL and b.status == STATUS_FULL and a.ok == b.ok:
        return (
            (FINAL_VALID, "judges_agree_valid")
            if a.verdict == "valid"
            else (FINAL_HUMAN, "judges_agree_invalid")
        )
    return None


def onward_reason(a: JudgeVerdict, b: JudgeVerdict) -> str:
    """Why a pair did not compose: the strongest reason first."""
    if STATUS_MALFORMED in (a.status, b.status):
        return "judge_malformed"
    if a.status == STATUS_FULL and b.status == STATUS_FULL:
        return "judges_disagree"
    return "judge_partial_evidence"


def decide(
    level: int, rules: RulesVerdict, judges: list[JudgeVerdict], arbiter: JudgeVerdict | None
) -> tuple[str, str]:
    """The routing table, pure: rules first, then the level's judges, then the arbiter if any."""
    if not rules.accepted:
        return FINAL_HUMAN, "rules:" + ",".join(rules.failures)
    if level == 1:
        return decide_single(judges[0])
    composed = decide_pair(judges[0], judges[1])
    if composed is not None:
        return composed
    if level == 2 or arbiter is None:
        reason = onward_reason(judges[0], judges[1])
        return (FINAL_PARTIAL if reason == "judge_partial_evidence" else FINAL_HUMAN), reason
    return decide_single(arbiter)


async def judge_cascade(
    message: str, contact: ContactRecord, cascade: Cascade, *, timeout: int = 180
) -> CascadeResult:
    """Run the cascade for one message: rules (free), the level's judges, the arbiter if needed."""
    rules = validate_rules(message, contact)
    result = CascadeResult(final=FINAL_HUMAN, reason="", rules=rules.to_dict())
    if not rules.accepted:
        result.final, result.reason = decide(cascade.level, rules, [], None)
        return result
    result.judges = list(
        await asyncio.gather(
            *(judge_with_model(message, contact, spec, timeout=timeout) for spec in cascade.judges)
        )
    )
    if cascade.level == 3 and decide_pair(result.judges[0], result.judges[1]) is None:
        assert cascade.arbiter is not None
        result.arbiter = await judge_with_model(
            message, contact, cascade.arbiter, role="arbiter", prior=result.judges, timeout=timeout
        )
    result.final, result.reason = decide(cascade.level, rules, result.judges, result.arbiter)
    return result


JUDGE_CHOICES = ("rules", "none")


def parse_judges(spec: str) -> tuple[str, ...]:
    """``"rules"`` | ``"none"`` — the judges applied inline during generation.

    The model judges are a second pass over a finished run (``judge <run-id>``);
    ``"llm"`` is therefore no longer a generation-time choice.
    """
    parts = tuple(p.strip().lower() for p in spec.split(",") if p.strip())
    if parts == ("none",):
        return ()
    unknown = set(parts) - {"rules"}
    if unknown or not parts:
        hint = " (model judges run afterwards: `judge <run-id>`)" if "llm" in unknown else ""
        raise ValueError(f"unknown judge(s) {sorted(unknown)}; choose from {JUDGE_CHOICES}{hint}")
    return parts
