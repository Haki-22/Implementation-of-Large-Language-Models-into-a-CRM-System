"""Detector configurations shared by the table and the false-alarm check.

A configuration name is ``gold`` (the answer key as detector), ``rules``,
``rules+<backend>`` or ``<backend>`` for a backend in ``ner.NER_BACKENDS`` or
``nametag3`` (predictions read from a file). One function turns a name into
spans so the two evaluations cannot drift apart.
"""

from __future__ import annotations

from typing import Any

from ucs.uc02_pseudonymization.code.ner import NER_BACKENDS, detect_ner
from ucs.uc02_pseudonymization.code.pseudonymizer import detect_rule_based, merge_spans


def default_configs(with_nametag3: bool) -> list[str]:
    """Return the full configuration list in table order."""
    configs = ["rules"]
    configs += [f"rules+{b}" for b in NER_BACKENDS]
    if with_nametag3:
        configs.append("rules+nametag3")
    configs += list(NER_BACKENDS)
    if with_nametag3:
        configs.append("nametag3")
    return configs


def detect_with_config(
    config: str,
    text: str,
    *,
    gold_spans: list[dict[str, Any]] | None = None,
    nametag3_spans: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Return the spans one configuration detects in ``text``.

    ``gold_spans`` serves the ``gold`` configuration; ``nametag3_spans`` the two
    NameTag 3 configurations (their predictions come from a file). A standalone
    NER configuration goes through the same join and de-overlap as the hybrid,
    with no rule spans.
    """
    if config == "gold":
        return [dict(s, source="gold") for s in gold_spans or []]
    if config == "rules":
        return detect_rule_based(text)
    backend = config[len("rules+") :] if config.startswith("rules+") else config
    if backend == "nametag3":
        if nametag3_spans is None:
            raise ValueError("nametag3 configurations need predictions from nametag3_adapter")
        ner = nametag3_spans
    else:
        ner = detect_ner(text, backend=backend)
    rules = detect_rule_based(text) if config.startswith("rules+") else []
    return merge_spans(rules, ner, text)


__all__ = ["default_configs", "detect_with_config"]
