"""Build a stratified judge test set for Czech message calibration.

Stratification:
  ~60 VALID   messages (60%)
  ~40 INVALID messages (40%), distributed equally across 4 failure subtypes:
    - invalid_vocative  (~10 messages): greeting line mutated / replaced
    - invalid_tv        (~10 messages): T/V register slip (ty/Vy mixed up)
    - invalid_gender    (~10 messages): gender morphology mismatch
    - invalid_combined  (~10 messages): multiple failures co-present

Additionally ~5 borderline-VALID messages are included for judge calibration
robustness: first-name-only address, foreign-origin name vocative, and title
forms like 'doktor'->'doktore'. These are included within the VALID set but
flagged is_borderline=True.

Domain: a fictional mixed-general Czech e-commerce retailer (B2C + B2B +
events).  Messages are sale invitations, order/delivery follow-ups, loyalty
offers, and similar retail outreach.  No brand name is used; the sign-off is
generic.

Output:
  JSON object keyed by message_id, written next to the use-case snapshot files:
  {
    "holdout-001": {
      message_id: str,
      generated_text: str,
      contact_data: {first_name, last_name, gender, formal, name_vocative},
      subtype: str,           # 'valid' | 'invalid_vocative' | 'invalid_tv' |
                              #   'invalid_gender' | 'invalid_combined'
      is_borderline: bool
      # NO label field -- labels are added later by the maintainer
      # by mutating this dict in place (adding "label": "VALID"|"INVALID")
    },
    ...
  }

Caveats:
  The manual gold set should aim for Gwet's AC1 >= 0.85 if a second annotator
  becomes available.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

from utils.file_safety import require_can_write
from utils.paths import JUDGE_TESTSET_SNAPSHOT

# ---------------------------------------------------------------------------
# Template pools for generating plausible Czech customer messages
# ---------------------------------------------------------------------------

# (vocative, first_name, last_name, gender, formal, body_template)
_VALID_FORMAL_MALE_TEMPLATES = [
    (
        "Vážený pane Nováku",
        "Jan",
        "Novák",
        "m",
        True,
        """Vážený pane Nováku,

dovolujeme si Vás pozvat na podzimní výprodej v našem e-shopu, který odstartuje 15. 9. 2026. Těšíme se na Vaši návštěvu.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážený pane Horáku",
        "Tomáš",
        "Horák",
        "m",
        True,
        """Vážený pane Horáku,

rádi bychom Vás informovali o nové kolekci elektroniky dostupné v našem e-shopu. Naše zákaznická linka Vám ráda poradí s výběrem. Neváhejte nás kontaktovat.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážený pane Procházko",
        "Petr",
        "Procházka",
        "m",
        True,
        """Vážený pane Procházko,

děkujeme za Vaši nedávnou objednávku. V příloze naleznete fakturu a sledovací číslo zásilky. Rádi bychom Vám nabídli doplňkové příslušenství.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážený pane Králu",
        "Martin",
        "Král",
        "m",
        True,
        """Vážený pane Králu,

obracíme se na Vás s nabídkou obnovy věrnostního členství. Jako člen získáte přístup k exkluzivním slevám a přednostní dopravě zdarma.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážený pane Blažku",
        "Ondřej",
        "Blažek",
        "m",
        True,
        """Vážený pane Blažku,

nabízíme Vám možnost přejít z běžného účtu na prémiový věrnostní program se slevou 30 % na první objednávku. Akce platí do 30. 6. 2026.

S pozdravem,
Váš zákaznický tým""",
    ),
]

_VALID_FORMAL_FEMALE_TEMPLATES = [
    (
        "Vážená paní Nováková",
        "Jana",
        "Nováková",
        "f",
        True,
        """Vážená paní Nováková,

dovolujeme si Vás pozvat na podzimní výprodej v našem e-shopu. Akce startuje 15. 9. 2026. Těšíme se na Vaši návštěvu.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážená paní Horáková",
        "Eva",
        "Horáková",
        "f",
        True,
        """Vážená paní Horáková,

obracíme se na Vás v souvislosti s Vaší nedávnou objednávkou. Rádi bychom Vám nabídli prodlouženou záruku na zakoupené zboží.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážená paní Dvořáková",
        "Lenka",
        "Dvořáková",
        "f",
        True,
        """Vážená paní Dvořáková,

máme pro Vás speciální nabídku přechodu na věrnostní program Plus. Budeme rádi, pokud nás kontaktujete pro více informací.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážená paní Marková",
        "Kateřina",
        "Marková",
        "f",
        True,
        """Vážená paní Marková,

rádi bychom Vás informovali o nové sezónní kolekci. Naše nabídka je sestavena podle nejnovějších trendů. Neváhejte si prohlédnout náš e-shop.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Vážená paní Vlčková",
        "Martina",
        "Vlčková",
        "f",
        True,
        """Vážená paní Vlčková,

děkujeme za Váš zájem o náš věrnostní program. Přikládáme podrobné informace o výhodách členství a možnostech splátkového nákupu.

S pozdravem,
Váš zákaznický tým""",
    ),
]

_VALID_INFORMAL_TEMPLATES = [
    (
        "Ahoj Honzo",
        "Honza",
        "Novotný",
        "m",
        False,
        """Ahoj Honzo,

chceme tě pozvat na náš víkendový výprodej. Bude to skvělá příležitost ulovit oblíbené značky za super ceny. Mrkni na e-shop!

Tvůj zákaznický tým""",
    ),
    (
        "Ahoj Lucie",
        "Lucie",
        "Procházková",
        "f",
        False,
        """Ahoj Lucie,

máme pro tebe zajímavou nabídku. Přechod na věrnostní program Plus je teď dostupný za výhodných podmínek. Ozvi se nám!

Tvůj zákaznický tým""",
    ),
    (
        "Ahoj Radku",
        "Radek",
        "Černý",
        "m",
        False,
        """Ahoj Radku,

děkujeme za tvou nedávnou objednávku. Sledovací číslo zásilky najdeš v příloze. Dej vědět, jestli máš zájem o doplňky k zakoupenému zboží.

Tvůj zákaznický tým""",
    ),
]

_VALID_FOREIGN_TEMPLATES = [
    (
        "Dobrý den,",
        "Martin",
        "Schmidt",
        "m",
        True,
        """Dobrý den,

dovolujeme si Vás informovat o aktuální nabídce slev v našem e-shopu. Rádi Vám poskytneme veškeré informace. Kontaktujte nás na níže uvedeném e-mailu.

S pozdravem,
Váš zákaznický tým""",
    ),
    (
        "Dobrý den,",
        "Fatima",
        "Alves",
        "f",
        True,
        """Dobrý den,

obracíme se na Vás s pozvánkou na náš sezónní výprodej. Akce je otevřena všem registrovaným zákazníkům. Nakupte se slevou do 31. 8. 2026.

S pozdravem,
Váš zákaznický tým""",
    ),
]


def build_judge_testset(seed: int = 42) -> dict[str, dict[str, Any]]:
    """Build the stratified 100-message judge test set.

    Args:
        seed: Random seed used to shuffle the final entries.

    Returns:
        A dict keyed by message_id.
    """
    rng = random.Random(seed)
    entries: list[dict[str, Any]] = []  # built as list, converted to dict at end
    msg_id = 0

    def _entry(
        subtype: str,
        generated_text: str,
        contact: dict,
        is_borderline: bool = False,
    ) -> dict[str, Any]:
        """Wrap one message as a numbered test-set entry (``holdout-NNN``, no label yet)."""
        nonlocal msg_id
        msg_id += 1
        return {
            "message_id": f"holdout-{msg_id:03d}",
            "generated_text": generated_text,
            "contact_data": contact,
            "subtype": subtype,
            "is_borderline": is_borderline,
            # NO label field -- populated later by the maintainer
        }

    # --- VALID set (60 messages) ---
    # 55 straightforward valid + 5 borderline-valid

    # Formal male (12)
    fm_pool = _VALID_FORMAL_MALE_TEMPLATES * 3  # repeat to reach count
    for i in range(12):
        tmpl = fm_pool[i % len(_VALID_FORMAL_MALE_TEMPLATES)]
        voc, fn, ln, gender, formal, text = tmpl
        entries.append(
            _entry(
                "valid",
                text,
                {
                    "first_name": fn,
                    "last_name": ln,
                    "gender": gender,
                    "formal": formal,
                    "name_vocative": voc,
                },
            )
        )

    # Formal female (12)
    ff_pool = _VALID_FORMAL_FEMALE_TEMPLATES * 3
    for i in range(12):
        tmpl = ff_pool[i % len(_VALID_FORMAL_FEMALE_TEMPLATES)]
        voc, fn, ln, gender, formal, text = tmpl
        entries.append(
            _entry(
                "valid",
                text,
                {
                    "first_name": fn,
                    "last_name": ln,
                    "gender": gender,
                    "formal": formal,
                    "name_vocative": voc,
                },
            )
        )

    # Informal (6)
    inf_pool = _VALID_INFORMAL_TEMPLATES * 3
    for i in range(6):
        tmpl = inf_pool[i % len(_VALID_INFORMAL_TEMPLATES)]
        voc, fn, ln, gender, formal, text = tmpl
        entries.append(
            _entry(
                "valid",
                text,
                {
                    "first_name": fn,
                    "last_name": ln,
                    "gender": gender,
                    "formal": formal,
                    "name_vocative": voc,
                },
            )
        )

    # Foreign-name fallback (2)
    for tmpl in _VALID_FOREIGN_TEMPLATES:
        voc, fn, ln, gender, formal, text = tmpl
        entries.append(
            _entry(
                "valid",
                text,
                {
                    "first_name": fn,
                    "last_name": ln,
                    "gender": gender,
                    "formal": formal,
                    "name_vocative": voc,
                },
            )
        )

    # Borderline-valid: 5 cases
    # (a) first-name-only address (no surname vocative)
    entries.append(
        _entry(
            "valid",
            """Vážený pane Jano,

máme pro Vás nabídku slev v našem e-shopu. Kontaktujte nás pro více informací.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Malý",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Jano",
            },
            is_borderline=True,
        )
    )
    # (b) foreign-origin name -- vocative attempts Czech suffix
    entries.append(
        _entry(
            "valid",
            """Vážený pane Petrově,

dovolujeme si Vás pozvat na náš sezónní výprodej. Těšíme se na Vaši návštěvu.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Ivan",
                "last_name": "Petrov",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Petrově",
            },
            is_borderline=True,
        )
    )
    # (c) title form: "pane doktore" instead of surname
    entries.append(
        _entry(
            "valid",
            """Vážený pane doktore,

rádi bychom Vám nabídli prémiový věrnostní program. Neváhejte nás kontaktovat.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jakub",
                "last_name": "Kopecký",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane doktore",
            },
            is_borderline=True,
        )
    )
    # (d) informal with slightly non-standard vocative
    entries.append(
        _entry(
            "valid",
            """Ahoj Martine,

chceme ti dát vědět o novém výprodeji. Bylo by super, kdyby ses k nám zase podíval!

Tvůj zákaznický tým""",
            {
                "first_name": "Martin",
                "last_name": "Kovář",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Martine",
            },
            is_borderline=True,
        )
    )
    # (e) paní without surname (honorific only)
    entries.append(
        _entry(
            "valid",
            """Vážená paní inženýrko,

dovolujeme si Vás informovat o nabídce našeho e-shopu. Rádi Vám poskytneme veškeré podrobnosti.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Petra",
                "last_name": "Benešová",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní inženýrko",
            },
            is_borderline=True,
        )
    )

    # Additional valid messages to reach 60
    # (We have: 12+12+6+2+5 = 37; need 23 more from alternating templates)
    extra_valid_pool = (
        _VALID_FORMAL_MALE_TEMPLATES + _VALID_FORMAL_FEMALE_TEMPLATES + _VALID_INFORMAL_TEMPLATES
    )
    extra_idx = 0
    while len([e for e in entries if e["subtype"] == "valid"]) < 60:
        tmpl = extra_valid_pool[extra_idx % len(extra_valid_pool)]
        voc, fn, ln, gender, formal, text = tmpl
        entries.append(
            _entry(
                "valid",
                text,
                {
                    "first_name": fn,
                    "last_name": ln,
                    "gender": gender,
                    "formal": formal,
                    "name_vocative": voc,
                },
            )
        )
        extra_idx += 1

    # --- INVALID set (40 messages, 10 per subtype) ---

    # invalid_vocative (10): greeting line mutated / replaced / missing
    _INVALID_VOCATIVE_CASES = [
        (
            """Dobrý den pane Nováku,

dovolujeme si Vás pozvat na náš sezónní výprodej. Těšíme se na Vaši návštěvu.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Nováku",
            },
        ),
        (
            """Dobrý den,

dovolujeme si Vás pozvat na náš výprodej. Nakupte prosím se slevou do 31. 8.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Eva",
                "last_name": "Horáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Horáková",
            },
        ),
        (
            """Ahoj Honzo,

máme pro tebe novinky. Mrkni na náš e-shop!

Tvůj zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novotný",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Jene",
            },
        ),
        (
            """Milý Tomáši,

rádi bychom Vás informovali o nové kolekci elektroniky. Neváhejte nás kontaktovat.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Tomáš",
                "last_name": "Horák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Horáku",
            },
        ),
        (
            """Vážená paní Malá,

nabízíme Vám přechod na věrnostní program Plus. Kontaktujte nás pro více informací.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Lucie",
                "last_name": "Malá",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Malou",
            },
        ),
        (
            """Dobrý den pane Blažku,

Máme pro Vás nabídku slev.

Váš zákaznický tým""",
            {
                "first_name": "Ondřej",
                "last_name": "Blažek",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Blažku",
            },
        ),
        (
            """Vážená kolegyně Dvořáková,

rádi bychom Vás pozvali na náš výprodej. Nakupte prosím se slevou.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Lenka",
                "last_name": "Dvořáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Dvořáková",
            },
        ),
        (
            """Ahoj Petro,

máme pro tebe skvělou nabídku. Ozvi se nám!

Tvůj zákaznický tým""",
            {
                "first_name": "Petr",
                "last_name": "Procházka",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Petře",
            },
        ),
        (
            """Milý kliente,

dovolujeme si Vás pozvat na náš sezónní výprodej. Těšíme se na Vaši návštěvu.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Kateřina",
                "last_name": "Marková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Marková",
            },
        ),
        (
            """Zdravím Vás,

rádi bychom Vás informovali o nových produktech. Kontaktujte nás.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Martina",
                "last_name": "Vlčková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Vlčková",
            },
        ),
    ]
    for text, contact in _INVALID_VOCATIVE_CASES:
        entries.append(_entry("invalid_vocative", text, contact))

    # invalid_tv (10): T/V register slip
    _INVALID_TV_CASES = [
        (
            """Vážený pane Nováku,

dovolujeme si tě pozvat na náš sezónní výprodej. Přijď, bude to skvělé!

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Nováku",
            },
        ),
        (
            """Vážená paní Horáková,

obracíme se na tebe s nabídkou věrnostního programu. Přihlaš se do 30. 6. 2026.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Eva",
                "last_name": "Horáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Horáková",
            },
        ),
        (
            """Ahoj Lucie,

rádi bychom Vám nabídli slevu na další nákup. Neváhejte se přihlásit.

Tvůj zákaznický tým""",
            {
                "first_name": "Lucie",
                "last_name": "Procházková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Lucie",
            },
        ),
        (
            """Vážený pane Horáku,

posílám ti informace o naší nové kolekci. Ozvi se mi, pokud máš zájem.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Tomáš",
                "last_name": "Horák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Horáku",
            },
        ),
        (
            """Ahoj Radku,

obracíme se na Vás s nabídkou slev. Neváhejte nás kontaktovat.

Tvůj zákaznický tým""",
            {
                "first_name": "Radek",
                "last_name": "Černý",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Radku",
            },
        ),
        (
            """Vážená paní Dvořáková,

chceme tě informovat o nových produktech. Přihlaš se k odběru novinek.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Lenka",
                "last_name": "Dvořáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Dvořáková",
            },
        ),
        (
            """Vážený pane Blažku,

máme pro tebe speciální slevu na další objednávku. Kdy by ti vyhovoval termín doručení?

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Ondřej",
                "last_name": "Blažek",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Blažku",
            },
        ),
        (
            """Ahoj Jano,

rádi bychom Vás pozvali na náš sezónní výprodej. Věříme, že Vás nabídka zaujme.

Tvůj zákaznický tým""",
            {
                "first_name": "Jana",
                "last_name": "Nováková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Jano",
            },
        ),
        (
            """Vážená paní Marková,

gratulujeme ti k dosažení zlatého věrnostního statusu! Máš nyní nárok na dopravu zdarma.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Kateřina",
                "last_name": "Marková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Marková",
            },
        ),
        (
            """Ahoj Ondřeji,

dovolujeme si Vás informovat o nadcházejícím výprodeji. Vaše návštěva e-shopu by nás velmi potěšila.

Tvůj zákaznický tým""",
            {
                "first_name": "Ondřej",
                "last_name": "Kratochvíl",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Ondřeji",
            },
        ),
    ]
    for text, contact in _INVALID_TV_CASES:
        entries.append(_entry("invalid_tv", text, contact))

    # invalid_gender (10): gender morphology mismatch (wrong verb/adj agreement)
    _INVALID_GENDER_CASES = [
        (
            """Vážená paní Horáková,

věříme, že jste byl spokojen s naší poslední objednávkou. Prohlédněte si naši novou kolekci.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Eva",
                "last_name": "Horáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Horáková",
            },
        ),
        (
            """Vážený pane Nováku,

doufáme, že jste byla spokojena s naší nabídkou. Kontaktujte nás pro více informací.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Nováku",
            },
        ),
        (
            """Ahoj Lucie,

jsem rád, že ses rozhodl využít naši slevu. Těším se na tvůj další nákup!

Tvůj zákaznický tým""",
            {
                "first_name": "Lucie",
                "last_name": "Procházková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Lucie",
            },
        ),
        (
            """Vážená paní Dvořáková,

jako náš věrný zákazník máte nárok na exkluzivní slevu. Neváhejte nás kontaktovat.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Lenka",
                "last_name": "Dvořáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Dvořáková",
            },
        ),
        (
            """Vážený pane Horáku,

jako naše věrná zákaznice máte nárok na slevu. Prohlédněte si naši novou kolekci.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Tomáš",
                "last_name": "Horák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Horáku",
            },
        ),
        (
            """Ahoj Radku,

jsem ráda, že ses ozval. Pošleme ti podrobnosti o naší nabídce.

Tvůj zákaznický tým""",
            {
                "first_name": "Radek",
                "last_name": "Černý",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Radku",
            },
        ),
        (
            """Vážená paní Marková,

byl jste zařazen do našeho věrnostního programu. Těšíme se na Vaše další nákupy.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Kateřina",
                "last_name": "Marková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Marková",
            },
        ),
        (
            """Vážený pane Blažku,

jste naší loajální zákaznicí a rádi bychom Vám nabídli slevu. Neváhejte nás kontaktovat.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Ondřej",
                "last_name": "Blažek",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Blažku",
            },
        ),
        (
            """Ahoj Jano,

gratulujeme -- byl jsi zařazen do věrnostního programu! Těšíme se na tebe.

Tvůj zákaznický tým""",
            {
                "first_name": "Jana",
                "last_name": "Nováková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Jano",
            },
        ),
        (
            """Vážená paní Vlčková,

jako náš věrný zákazník máte přístup k exkluzivním slevám. Využijte všechny výhody členství.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Martina",
                "last_name": "Vlčková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Vlčková",
            },
        ),
    ]
    for text, contact in _INVALID_GENDER_CASES:
        entries.append(_entry("invalid_gender", text, contact))

    # invalid_combined (10): multiple failures co-present
    _INVALID_COMBINED_CASES = [
        (
            """Dobrý den,

dovolujeme si tě pozvat na náš sezónní výprodej. Přijď, bude to skvělé! Byl jsi naším nejvěrnějším zákazníkem.

Tvůj zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Nováku",
            },
        ),
        (
            """Milá Evo,

obracíme se na tebe s nabídkou. Jako náš věrný zákazník máš nárok na slevu.

Tvůj zákaznický tým""",
            {
                "first_name": "Eva",
                "last_name": "Horáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Horáková",
            },
        ),
        (
            """Vážená paní Nováku,

byl jste zařazen do našeho věrnostního programu. Přijď a přiveď přátele.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Jan",
                "last_name": "Novák",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Nováku",
            },
        ),
        (
            """Ahoj Lenka,

rádi bychom Vás pozvali na náš výprodej. Jako náš věrný zákazník víte, že se vyplatí nakoupit včas.

Tvůj zákaznický tým""",
            {
                "first_name": "Lenka",
                "last_name": "Dvořáková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Lenko",
            },
        ),
        (
            """Zdravím,

gratulujeme ti k dosažení zlatého věrnostního statusu! Byl jste naším nejvěrnějším zákazníkem.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Kateřina",
                "last_name": "Marková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Marková",
            },
        ),
        (
            """Vážený pane Horáková,

dovolujeme si tě informovat o nových produktech. Přihlaš se k odběru novinek.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Eva",
                "last_name": "Horáková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Horáková",
            },
        ),
        (
            """Ahoj Ondřeji,

jako naše věrná zákaznice máte nárok na slevu. Neváhejte nás kontaktovat.

Tvůj zákaznický tým""",
            {
                "first_name": "Ondřej",
                "last_name": "Blažek",
                "gender": "m",
                "formal": False,
                "name_vocative": "Ahoj Ondřeji",
            },
        ),
        (
            """Milý pane Nováková,

chceme tě informovat o zajímavé nabídce. Byl si naší nejvěrnější zákaznicí v uplynulém roce.

Tvůj zákaznický tým""",
            {
                "first_name": "Jana",
                "last_name": "Nováková",
                "gender": "f",
                "formal": False,
                "name_vocative": "Ahoj Jano",
            },
        ),
        (
            """Vážený pane Vlčková,

posílám ti informace o naší nové kolekci. Ozvi se mi, pokud máš zájem.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Martina",
                "last_name": "Vlčková",
                "gender": "f",
                "formal": True,
                "name_vocative": "Vážená paní Vlčková",
            },
        ),
        (
            """Dobrý den Radku,

jako naše věrná zákaznice jste ideální adresátkou této nabídky. Neváhejte si prohlédnout náš e-shop.

S pozdravem,
Váš zákaznický tým""",
            {
                "first_name": "Radek",
                "last_name": "Černý",
                "gender": "m",
                "formal": True,
                "name_vocative": "Vážený pane Černý",
            },
        ),
    ]
    for text, contact in _INVALID_COMBINED_CASES:
        entries.append(_entry("invalid_combined", text, contact))

    # Shuffle to avoid ordering bias in labelling
    rng.shuffle(entries)

    # Convert to dict keyed by message_id.
    return {e["message_id"]: e for e in entries}


def generate_judge_testset(
    output_path: str | Path = JUDGE_TESTSET_SNAPSHOT,
    seed: int = 42,
    *,
    overwrite: bool = False,
) -> None:
    """Generate the judge test set and write it to JSON.

    Args:
        output_path: Target JSON file path.
        seed: Random seed used to shuffle the final entries.
        overwrite: Allow replacing an existing file when set to `True`.
    """
    testset: dict[str, dict] = build_judge_testset(seed=seed)
    entries = list(testset.values())

    output_file = require_can_write(
        output_path,
        overwrite=overwrite,
        artifact="judge test-set snapshot",
    )
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(testset, f, ensure_ascii=False, indent=2)

    n_valid = sum(1 for e in entries if e["subtype"] == "valid")
    n_borderline = sum(1 for e in entries if e["is_borderline"])
    n_inv_voc = sum(1 for e in entries if e["subtype"] == "invalid_vocative")
    n_inv_tv = sum(1 for e in entries if e["subtype"] == "invalid_tv")
    n_inv_gen = sum(1 for e in entries if e["subtype"] == "invalid_gender")
    n_inv_comb = sum(1 for e in entries if e["subtype"] == "invalid_combined")
    n_invalid = n_inv_voc + n_inv_tv + n_inv_gen + n_inv_comb

    print(f"Judge test-set written to: {output_file}")
    print(f"  Total:              {len(entries)}")
    print(f"  VALID:              {n_valid} ({n_valid / len(entries):.0%})")
    print(f"    of which borderline: {n_borderline}")
    print(f"  INVALID:            {n_invalid} ({n_invalid / len(entries):.0%})")
    print(f"    invalid_vocative: {n_inv_voc}")
    print(f"    invalid_tv:       {n_inv_tv}")
    print(f"    invalid_gender:   {n_inv_gen}")
    print(f"    invalid_combined: {n_inv_comb}")


# ---------------------------------------------------------------------------
# Calibration of the rule validator on this set
# ---------------------------------------------------------------------------


def calibrate(testset_path: str | Path = JUDGE_TESTSET_SNAPSHOT) -> dict[str, dict[str, int]]:
    """Run the rule validator over the set: per subtype, how many it rejects (its recall).

    The set's ``subtype`` is the ground truth (``valid`` should be accepted, every
    ``invalid_*`` rejected). Measured 2026-09-05 with the narrow gender rule
    (D-UC01-4): valid 60/60 accepted, invalid_vocative 10/10 rejected, invalid_tv
    10/10, invalid_combined 10/10, invalid_gender 9/10 — the miss is a sender-side
    form ("jsem ráda" written to a man), which a recipient-agreement rule does not
    read. Before the gender rule (2026-09-04): combined 9/10, gender 0/10.
    """
    from ucs.uc01_personalization.judge import validate_rules

    entries = json.loads(Path(testset_path).read_text(encoding="utf-8"))
    table: dict[str, dict[str, int]] = {}
    for entry in entries.values():
        verdict = validate_rules(entry["generated_text"], entry["contact_data"])
        row = table.setdefault(entry["subtype"], {"n": 0, "accepted": 0, "rejected": 0})
        row["n"] += 1
        row["accepted" if verdict.accepted else "rejected"] += 1
        for failure in verdict.failures:
            row[failure] = row.get(failure, 0) + 1
    return table


def main(argv: list[str] | None = None) -> int:
    """Generate the judge test set, or calibrate the rule validator on it."""
    parser = argparse.ArgumentParser(
        description="Generate the stratified judge test set, or calibrate the rules on it."
    )
    parser.add_argument("--out", default=str(JUDGE_TESTSET_SNAPSHOT), help="Output JSON path.")
    parser.add_argument("--seed", type=int, default=42, help="Random seed.")
    parser.add_argument(
        "--force", action="store_true", help="Overwrite the output JSON file if it already exists."
    )
    parser.add_argument(
        "--calibrate",
        action="store_true",
        help="Do not generate; run the rule validator over the set and print per-subtype recall.",
    )
    args = parser.parse_args(argv)
    if args.calibrate:
        table = calibrate(args.out)
        print(f"{'subtype':<18} {'n':>3} {'accepted':>9} {'rejected':>9}  failures")
        for subtype, row in table.items():
            extra = {k: v for k, v in row.items() if k not in ("n", "accepted", "rejected")}
            print(f"{subtype:<18} {row['n']:>3} {row['accepted']:>9} {row['rejected']:>9}  {extra}")
        return 0
    generate_judge_testset(output_path=args.out, seed=args.seed, overwrite=args.force)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
