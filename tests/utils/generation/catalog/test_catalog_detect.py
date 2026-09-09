"""CLI-installation detection that decides which providers a regeneration keeps live."""

from __future__ import annotations

from utils.generation.catalog.detect import detect_installed_providers, is_cli_installed


def test_only_installed_clis_are_detected(monkeypatch):
    providers = {
        "codex": {"binary": "codex"},
        "claude": {"binary": "claude"},
        "agy": {"binary": "agy"},
    }
    monkeypatch.setattr(
        "utils.generation.catalog.detect.shutil.which",
        lambda b: "/usr/bin/codex" if b == "codex" else None,
    )
    assert detect_installed_providers(providers) == {"codex": True, "claude": False, "agy": False}


def test_binary_falls_back_to_cli_then_name(monkeypatch):
    monkeypatch.setattr(
        "utils.generation.catalog.detect.shutil.which", lambda b: "/x" if b == "foo" else None
    )
    assert detect_installed_providers({"p": {"cli": "foo"}}) == {"p": True}
    assert detect_installed_providers({"foo": {}}) == {"foo": True}


def test_empty_binary_is_not_installed(monkeypatch):
    monkeypatch.setattr("utils.generation.catalog.detect.shutil.which", lambda b: "/anything")
    assert is_cli_installed("") is False
    assert is_cli_installed(None) is False
