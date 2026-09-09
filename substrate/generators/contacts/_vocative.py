"""Czech vocative greeting builder.

The ``vokativ`` library always returns lowercase results, so its output is
post-processed through ``_uppercase_first_letter`` before being inserted into a
greeting.
"""

from __future__ import annotations

import vokativ


# ---------------------------------------------------------------------------
# Case helper
# ---------------------------------------------------------------------------


def _uppercase_first_letter(text: str) -> str:
    """Return text with only the first character uppercased.

    The vokativ library always returns its result lowercase, so we run its
    output through this before plugging it into a greeting. Unlike str.capitalize()
    this leaves any other characters untouched.

    Args:
        text: String to fix. Empty string is returned unchanged.

    Returns:
        text with text[0] uppercased; characters after index 0 are kept as-is.
    """
    if not text:
        return text
    return text[0].upper() + text[1:]


# ---------------------------------------------------------------------------
# Greeting
# ---------------------------------------------------------------------------


def _build_vocative(first_name: str, last_name: str, gender: str, formal: bool) -> str:
    """Build the full greeting string for a Czech name.

    Formal: "Vážený pane <surname-vocative>" / "Vážená paní <surname-vocative>".
    Informal: "Ahoj <first-name-vocative>". Foreign-origin contacts never come
    here; the factory gives them the neutral "Dobrý den," directly.
    """
    is_woman = gender == "f"

    if formal:
        last_vok = _uppercase_first_letter(
            vokativ.vokativ(last_name, last_name=True, woman=is_woman)
        )
        if is_woman:
            return f"Vážená paní {last_vok}"
        else:
            return f"Vážený pane {last_vok}"
    else:
        first_vok = _uppercase_first_letter(
            vokativ.vokativ(first_name, last_name=False, woman=is_woman)
        )
        return f"Ahoj {first_vok}"
