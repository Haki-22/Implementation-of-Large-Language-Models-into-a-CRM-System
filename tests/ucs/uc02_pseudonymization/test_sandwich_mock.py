"""End-to-end UC-02 sandwich tests using mocked NER + mocked LLM.

The full UC-02 pipeline is:

    message → static check (regex+checksum) → NER (gliner) → masked text →
    LLM call (system hint + <id> wrapper) → MID + integrity check →
    depseudonymize → final message

These tests cover every stage WITHOUT loading any HuggingFace model and
WITHOUT making any real LLM call. Detection is forced through deterministic
mocks; the LLM is a fake callable that returns canned strings. The roundtrip
property under test: depseudonymize(LLM(pseudonymize(text))) == text when the
LLM preserves placeholders and echoes the envelope ``<id>...</id>`` wrapper.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator
from typing import Any

import pytest

from ucs.uc02_pseudonymization import (
    DETECTION_CLAUSES,
    ENVELOPE_SYS_HINT,
    MID_PATTERN,
    EnvelopeIntegrityError,
    EnvelopeMapping,
    EnvelopeProviderError,
    MappingRegistry,
    check_envelope_integrity,
    compose_system_prompt,
    compose_user_prompt,
    depseudonymize,
    detect_rule_based,
    pseudonymize,
    with_envelope,
)
from ucs.uc02_pseudonymization.code import ner as ner_module
from utils.generation.errors import (
    ProviderQuotaError,
    ProviderRateLimitError,
)
from utils.czech_identifiers import is_valid_iban_cz, is_valid_rc


# ---------------------------------------------------------------------------
# Test fixtures: fake NER + fake LLM
# ---------------------------------------------------------------------------


def make_fake_ner(spans: list[dict[str, Any]]):
    """Return a fake detect_ner that yields the provided spans verbatim."""

    def fake(text: str, *, backend: str = "gliner", threshold: float = 0.5, **_kw):
        return spans

    return fake


@contextlib.contextmanager
def patched_ner(
    monkeypatch: pytest.MonkeyPatch, spans: list[dict[str, Any]]
) -> AsyncIterator[None]:
    """Patch both ``ner_module.detect_ner`` and the envelope fallback fusion."""
    fake = make_fake_ner(spans)
    monkeypatch.setattr(ner_module, "detect_ner", fake)
    yield


def _parse_envelope_prompt(prompt: str) -> tuple[str, str]:
    """Return ``(masked_text, mapping_id)`` from a prompt built by ``compose_user_prompt``
    or any retry-reminder builder. All of those end with
    ``...\\n\\n{masked_text}\\n\\n<id>{mapping_id}</id>\\n``.

    Retry reminder bodies interpolate ``<id>{mapping_id}</id>`` multiple times
    (in instruction text + at the trailing wrapper), so we take the LAST match —
    the trailing wrapper that always sits at the prompt end after the masked
    body.
    """
    matches = list(MID_PATTERN.finditer(prompt))
    if not matches:
        return prompt, ""
    m = matches[-1]
    mid = m.group(1)
    text_part = prompt[: m.start()].rstrip()
    if "\n\n" in text_part:
        masked = text_part.rsplit("\n\n", 1)[-1]
    else:
        masked = text_part
    return masked, mid


class FakeLlm:
    """Async callable that echoes ``<id>{mid}</id>`` + the masked text by default.

    Knobs:
      response_template: format string with ``{text}`` placeholder; if None,
                         body is the masked input verbatim.
      drops:             placeholders to delete from the body (token loss).
      adds:              extra placeholders to append (hallucination).
      drop_mid:          omit the leading ``<id>...</id>`` line.
      mangle_mid:        emit a fake UUID4 hex instead of the requested one.
    """

    def __init__(
        self,
        response_template: str | None = None,
        drops: set[str] | None = None,
        adds: set[str] | None = None,
        drop_mid: bool = False,
        mangle_mid: bool = False,
    ):
        self.template = response_template
        self.drops = drops or set()
        self.adds = adds or set()
        self.drop_mid = drop_mid
        self.mangle_mid = mangle_mid
        self.calls: list[str] = []

    async def __call__(self, prompt: str) -> str:
        self.calls.append(prompt)
        masked, mid = _parse_envelope_prompt(prompt)
        body = self.template.format(text=masked) if self.template else masked
        for token in self.drops:
            body = body.replace(token, "[REDACTED]")
        for token in self.adds:
            body = body + " " + token
        if self.drop_mid or not mid:
            return body
        if self.mangle_mid:
            mid = "f" * 32  # not a valid registered mapping_id
        return f"<id>{mid}</id>\n{body}"


# ---------------------------------------------------------------------------
# Stage 1: static check (rule_based) only
# ---------------------------------------------------------------------------


def test_static_check_detects_all_format_pii():
    text = (
        "Pište na info@firma.cz nebo volejte +420 605 123 456. "
        "IČO 25001388 a IBAN CZ65 0800 0000 1920 0014 5399. "
        "Adresa: 110 00 Praha. DIČ CZ25001388."
    )
    spans = detect_rule_based(text)
    types = {s["pii_type"] for s in spans}
    assert {"EMAIL", "PHONE", "ICO", "IBAN_CZ", "PSC", "DIC"} <= types, (
        f"missing categories; got {types}"
    )


def test_static_check_rejects_invalid_checksum_ico():
    text = "Pochybné IČO 12345672 v textu."
    spans = detect_rule_based(text)
    assert [s for s in spans if s["pii_type"] == "ICO"] == [], "invalid IČO must not be detected"


def test_static_check_rejects_invalid_checksum_iban():
    text = "Nesmyslný účet CZ00 0000 0000 0000 0000 0000 nikoho."
    spans = detect_rule_based(text)
    assert not [s for s in spans if s["pii_type"] == "IBAN_CZ"], "invalid IBAN must not be detected"


def test_static_check_validates_iban_checksum_helper():
    assert is_valid_iban_cz("CZ65 0800 0000 1920 0014 5399")
    assert not is_valid_iban_cz("CZ00 0000 0000 0000 0000 0000")
    assert not is_valid_iban_cz("CZ65080000001920001453")


def test_static_check_rc_helper_handles_pre1954():
    assert is_valid_rc("490815/123")
    assert not is_valid_rc("491315/123")


# ---------------------------------------------------------------------------
# Stage 2: NER fusion (mocked)
# ---------------------------------------------------------------------------


def test_pseudonymize_uses_mocked_fusion(monkeypatch: pytest.MonkeyPatch):
    text = "Pan Jiří Novák volal z +420 605 123 456."
    person_start = text.index("Jiří Novák")
    person_end = person_start + len("Jiří Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_end,
            "pii_type": "PERSON",
            "surface_form": "Jiří Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    masked, mapping = pseudonymize(text)
    tokens = {m["token"] for m in mapping}
    assert "<PERSON_1>" in tokens
    assert "<PHONE_1>" in tokens
    assert masked == "Pan <PERSON_1> volal z <PHONE_1>."

    restored = depseudonymize(masked, mapping)
    assert restored == text


def test_pseudonymize_assigns_ids_in_reading_order(monkeypatch: pytest.MonkeyPatch):
    text = "Email anna@x.cz patří Anně a petr@y.cz patří Petrovi."
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner([]))
    masked, mapping = pseudonymize(text, use_ner=False)
    ordered = sorted(mapping, key=lambda m: m["span_start"])
    assert ordered[0]["token"] == "<EMAIL_1>"
    assert ordered[0]["surface_form"] == "anna@x.cz"
    assert ordered[1]["token"] == "<EMAIL_2>"
    assert ordered[1]["surface_form"] == "petr@y.cz"


def test_pseudonymize_preexisting_tag_no_collision(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner([]))
    text = "Šablona <EMAIL_1>: kontakt na petr@y.cz."
    masked, mapping = pseudonymize(text, use_ner=False)
    assert mapping[0]["token"] == "<EMAIL_2>"
    assert "<EMAIL_2>" in masked
    assert masked.count("<EMAIL_1>") == 1
    restored = depseudonymize(masked, mapping)
    assert restored == text


# ---------------------------------------------------------------------------
# Stage 3+4: full sandwich (text → mask → mock LLM → unmask)
# ---------------------------------------------------------------------------


def test_sandwich_with_mock_llm_roundtrip(monkeypatch: pytest.MonkeyPatch):
    """Roundtrip property: if the LLM echoes the masked text and the MID, the
    final restored text equals the input byte-for-byte and no PII leaked."""
    text = (
        "Pan Jiří Novák volal z +420 605 123 456 ohledně objednávky. "
        "Pošlete na info@firma.cz. IČO 25001388."
    )
    person_start = text.index("Jiří Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_start + len("Jiří Novák"),
            "pii_type": "PERSON",
            "surface_form": "Jiří Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    fake = FakeLlm()
    final = asyncio.run(with_envelope(text, fake))

    assert final == text, f"roundtrip broken: {final!r} != {text!r}"
    assert "Jiří Novák" not in fake.calls[0]
    assert "+420 605 123 456" not in fake.calls[0]
    assert "info@firma.cz" not in fake.calls[0]
    assert "25001388" not in fake.calls[0]


def test_sandwich_strips_mid_wrapper_from_output(monkeypatch: pytest.MonkeyPatch):
    """The MID wrapper is a protocol artefact — it must NOT leak into the final
    restored text returned to the caller."""
    text = "Volal pan Novák."
    person_start = text.index("Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_start + len("Novák"),
            "pii_type": "PERSON",
            "surface_form": "Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    final = asyncio.run(with_envelope(text, FakeLlm()))
    assert "<id>" not in final
    assert "</id>" not in final


def test_sandwich_retries_when_llm_drops_placeholder(monkeypatch: pytest.MonkeyPatch):
    """If the LLM drops a placeholder on attempt 1, the envelope must retry
    and the final must roundtrip when the LLM recovers on attempt 2."""
    text = "Pan Novák volal z +420 605 123 456."
    person_start = text.index("Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_start + len("Novák"),
            "pii_type": "PERSON",
            "surface_form": "Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    import re as _re

    class FlakyLlm:
        def __init__(self):
            self.n = 0

        async def __call__(self, prompt: str) -> str:
            self.n += 1
            masked, mid = _parse_envelope_prompt(prompt)
            if self.n == 1:
                body = _re.sub(r"<PERSON_\d+>", "[someone]", masked, count=1)
            else:
                body = masked
            return f"<id>{mid}</id>\n{body}"

    flaky = FlakyLlm()
    final = asyncio.run(with_envelope(text, flaky, max_attempts=2))
    assert flaky.n == 2, "must have retried once"
    assert final == text


def test_sandwich_retries_when_llm_invents_placeholder(monkeypatch: pytest.MonkeyPatch):
    """If the LLM invents a phantom <PERSON_99>, the envelope must retry."""
    text = "Volal pan Novák."
    person_start = text.index("Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_start + len("Novák"),
            "pii_type": "PERSON",
            "surface_form": "Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    class HallucinatingLlm:
        def __init__(self):
            self.n = 0

        async def __call__(self, prompt: str) -> str:
            self.n += 1
            masked, mid = _parse_envelope_prompt(prompt)
            if self.n == 1:
                body = masked + " (a kolega <PERSON_99>)"
            else:
                body = masked
            return f"<id>{mid}</id>\n{body}"

    h = HallucinatingLlm()
    final = asyncio.run(with_envelope(text, h, max_attempts=2))
    assert h.n == 2
    assert final == text


def test_sandwich_raises_after_persistent_drops(monkeypatch: pytest.MonkeyPatch):
    """If the LLM keeps dropping the same tag across all attempts, the envelope
    raises EnvelopeIntegrityError — no silent corruption."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    fake_spans = [
        {
            "span_start": person_start,
            "span_end": person_start + len("Novák"),
            "pii_type": "PERSON",
            "surface_form": "Novák",
            "ner_confidence": 0.99,
        }
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    import re as _re

    class PersistentBadLlm:
        async def __call__(self, prompt: str) -> str:
            masked, mid = _parse_envelope_prompt(prompt)
            body = _re.sub(r"<PERSON_\d+>", "[redacted]", masked)
            return f"<id>{mid}</id>\n{body}"

    with pytest.raises(EnvelopeIntegrityError) as exc:
        asyncio.run(with_envelope(text, PersistentBadLlm(), max_attempts=2))
    assert exc.value.last_check is not None
    assert any(t.startswith("<PERSON_") for t in exc.value.last_check.missing_in_response)


def test_sandwich_no_pii_pass_through(monkeypatch: pytest.MonkeyPatch):
    """No-PII inputs skip envelope semantics — no MID, no integrity check."""
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner([]))
    text = "Žádné osobní údaje v této větě."
    fake = FakeLlm(response_template="VÝSTUP: {text}")
    final = asyncio.run(with_envelope(text, fake))
    assert final == "VÝSTUP: " + text


def test_sandwich_pass_through_drops_a_stray_id_line(monkeypatch: pytest.MonkeyPatch):
    """With nothing masked no id was sent; a model that copies the example id from the
    rules as its first line must not leak it into the answer (codex, 2026-09-07)."""
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner([]))
    text = "Žádné osobní údaje v této větě."
    fake = FakeLlm(response_template="<id>9f2c1c0c4f7c4a2b8e8e7d6c5b4a3a2a</id>\nVÝSTUP: {text}")
    final = asyncio.run(with_envelope(text, fake))
    assert final == "VÝSTUP: " + text


def test_rules_read_dic_and_iban_in_lower_case():
    """The rule layer is case-insensitive on the country prefix; the surface form is the
    text as typed (casing table 2026-09-07: 12 items lost in lower case before this)."""
    from ucs.uc02_pseudonymization.code.pseudonymizer import detect_rule_based

    text = "dič cz12345678, iban cz65 0800 0000 1920 0014 5399, e-mail a@b.cz"
    spans = {s["pii_type"]: s["surface_form"] for s in detect_rule_based(text)}
    assert spans["DIC"] == "cz12345678"
    assert spans["IBAN_CZ"] == "cz65 0800 0000 1920 0014 5399"
    assert spans["EMAIL"] == "a@b.cz"


def test_integrity_check_helper_flags_missing_and_extra():
    m = EnvelopeMapping()
    m.entries["<PERSON_1>"] = "Novák"
    m.entries["<EMAIL_1>"] = "a@b.cz"
    result = check_envelope_integrity("Pan <PERSON_1> a falešný <PERSON_99>", m)
    assert not result.ok
    assert "<EMAIL_1>" in result.missing_in_response
    assert "<PERSON_99>" in result.extra_in_response


def test_envelope_rejects_invalid_max_attempts():
    async def _llm(_: str) -> str:
        return ""

    with pytest.raises(ValueError):
        asyncio.run(with_envelope("x", _llm, max_attempts=0))


def test_envelope_rejects_no_callers():
    with pytest.raises(ValueError):
        asyncio.run(with_envelope("x", llm_calls=[]))


def test_envelope_rejects_both_call_args():
    async def _llm(_: str) -> str:
        return ""

    with pytest.raises(ValueError):
        asyncio.run(with_envelope("x", _llm, llm_calls=[_llm]))


# ---------------------------------------------------------------------------
# Mapping ID + registry + prompt composition (concurrency support)
# ---------------------------------------------------------------------------


def test_envelope_mapping_has_unique_id_per_call():
    m1 = EnvelopeMapping()
    m2 = EnvelopeMapping()
    assert m1.mapping_id != m2.mapping_id
    assert len(m1.mapping_id) == 32
    int(m1.mapping_id, 16)
    int(m2.mapping_id, 16)


def test_mapping_registry_put_get_pop_roundtrip():
    registry = MappingRegistry()
    m = EnvelopeMapping()
    m.entries["<PERSON_42>"] = "Jiří"
    mid = registry.put(m)
    assert mid == m.mapping_id
    assert mid in registry
    assert len(registry) == 1
    assert registry.pending_count() == 1
    assert registry.active_ids() == [mid]

    retrieved = registry.get(mid)
    assert retrieved is m
    assert retrieved.entries["<PERSON_42>"] == "Jiří"

    popped = registry.pop(mid)
    assert popped is m
    assert mid not in registry
    assert len(registry) == 0
    assert registry.pending_count() == 0
    assert registry.get(mid) is None


def test_concurrent_envelopes_have_distinct_mappings(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner([]))
    text_a = "Volání A: email a@x.cz."
    text_b = "Volání B: email b@y.cz."

    from ucs.uc02_pseudonymization.code.envelope import (
        unmask as env_depseudonymize,
    )
    from ucs.uc02_pseudonymization.code.envelope import (
        mask as env_pseudonymize,
    )

    masked_a, mapping_a = env_pseudonymize(text_a)
    masked_b, mapping_b = env_pseudonymize(text_b)

    assert mapping_a.mapping_id != mapping_b.mapping_id
    assert env_depseudonymize(masked_a, mapping_a) == text_a
    assert env_depseudonymize(masked_b, mapping_b) == text_b
    cross = env_depseudonymize(masked_a, mapping_b)
    assert cross != text_a
    assert "a@x.cz" not in cross


def test_compose_system_prompt_prepends_envelope_rule():
    task = "Shrň hovor zákazníka do tří vět."
    composed = compose_system_prompt(task)
    assert composed.startswith(ENVELOPE_SYS_HINT.splitlines()[0])
    assert task in composed
    assert composed.index("</context>") < composed.index(task)
    assert "{detection_clause}" not in composed


def test_compose_system_prompt_names_the_envelope_level():
    """The model is told what the detector replaced and that tokens come back locally."""
    task = "Odpověz zákazníkovi."
    both = compose_system_prompt(task, detection="rules+ner")
    rules = compose_system_prompt(task, detection="rules")
    assert DETECTION_CLAUSES["rules+ner"] in both
    assert DETECTION_CLAUSES["rules"] in rules
    assert DETECTION_CLAUSES["rules"] not in both
    assert "lokálně nahradí zpět" in both
    with pytest.raises(ValueError):
        compose_system_prompt(task, detection="magic")


def test_compose_user_prompt_ends_with_mid_wrapper():
    """User prompt MUST end with the MID wrapper on its own line — the LLM
    is told to echo the wrapper from the END of the prompt."""
    masked = "Pan <PERSON_47> volal z <PHONE_823>."
    mid = "a" * 32
    composed = compose_user_prompt(masked, mid)
    assert composed.rstrip().endswith(f"<id>{mid}</id>")
    assert masked in composed


def test_envelope_logs_mapping_id_on_retry(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    """The mapping_id must appear in retry warning logs for traceability."""
    import re as _re

    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    class AlwaysBad:
        async def __call__(self, prompt: str) -> str:
            masked, mid = _parse_envelope_prompt(prompt)
            body = _re.sub(r"<PERSON_\d+>", "[gone]", masked)
            return f"<id>{mid}</id>\n{body}"

    caplog.set_level("WARNING")
    with pytest.raises(EnvelopeIntegrityError):
        asyncio.run(with_envelope(text, AlwaysBad(), max_attempts=2))
    retry_warnings = [r for r in caplog.records if "integrity failed" in r.message]
    assert retry_warnings, "expected at least one retry-failure warning"
    assert any(_re.search(r"envelope\[[0-9a-f]{32}\]", r.message) for r in retry_warnings)


# ---------------------------------------------------------------------------
# MID echo: strict pairing, retry on mismatch, orphan rule
# ---------------------------------------------------------------------------


def test_sandwich_retries_when_mid_is_dropped(monkeypatch: pytest.MonkeyPatch):
    """If the LLM omits the <id>...</id> wrapper, the envelope retries with the
    MID reminder. When the LLM recovers, the final restores correctly."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    class DropsMidOnce:
        def __init__(self):
            self.n = 0

        async def __call__(self, prompt: str) -> str:
            self.n += 1
            masked, mid = _parse_envelope_prompt(prompt)
            if self.n == 1:
                return masked  # no MID line
            return f"<id>{mid}</id>\n{masked}"

    llm = DropsMidOnce()
    final = asyncio.run(with_envelope(text, llm, max_attempts=2))
    assert llm.n == 2
    assert final == text


def test_sandwich_rejects_persistent_mid_mismatch(monkeypatch: pytest.MonkeyPatch):
    """LLM echoes a wrong MID across all attempts → EnvelopeIntegrityError."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    fake = FakeLlm(mangle_mid=True)
    with pytest.raises(EnvelopeIntegrityError):
        asyncio.run(with_envelope(text, fake, max_attempts=2))


def test_orphan_rule_accepts_when_only_one_active(monkeypatch: pytest.MonkeyPatch):
    """Registry has exactly one active mapping, LLM dropped MID → accept the
    orphan response (it can only belong to us)."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    registry = MappingRegistry()
    fake = FakeLlm(drop_mid=True)  # no MID echo at all
    final = asyncio.run(with_envelope(text, fake, registry=registry, max_attempts=1))
    assert final == text
    # Registry must be cleaned after the call completes.
    assert registry.pending_count() == 0


def test_orphan_rule_does_not_apply_when_registry_unused(
    monkeypatch: pytest.MonkeyPatch,
):
    """Without a registry, MID-loss must NOT be accepted — strict pairing only."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    fake = FakeLlm(drop_mid=True)
    with pytest.raises(EnvelopeIntegrityError):
        asyncio.run(with_envelope(text, fake, max_attempts=1))


# ---------------------------------------------------------------------------
# Provider chain: rate-limit / quota / timeout triggers fallback
# ---------------------------------------------------------------------------


def test_provider_chain_switches_on_rate_limit(monkeypatch: pytest.MonkeyPatch):
    """Provider 1 raises ProviderRateLimitError → provider 2 succeeds → final OK."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    rate_limited_calls: list[str] = []

    async def rate_limited(prompt: str) -> str:
        rate_limited_calls.append(prompt)
        raise ProviderRateLimitError("provider-A", "429 over capacity")

    healthy = FakeLlm()
    final = asyncio.run(with_envelope(text, llm_calls=[rate_limited, healthy], max_attempts=2))
    assert final == text
    assert len(rate_limited_calls) == 1, "rate-limited provider must NOT be retried"
    assert len(healthy.calls) == 1


def test_provider_chain_raises_provider_error_when_all_exhausted(
    monkeypatch: pytest.MonkeyPatch,
):
    """All providers fail with rate-limit → EnvelopeProviderError."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    async def rl(prompt: str) -> str:
        raise ProviderRateLimitError("A", "429")

    async def quota(prompt: str) -> str:
        raise ProviderQuotaError("B", "quota exhausted")

    with pytest.raises(EnvelopeProviderError) as exc:
        asyncio.run(with_envelope(text, llm_calls=[rl, quota], max_attempts=2))
    assert isinstance(exc.value.last_provider_error, ProviderQuotaError)


def test_provider_chain_switches_on_timeout(monkeypatch: pytest.MonkeyPatch):
    """Provider 1 times out → provider 2 succeeds."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    async def slow(prompt: str) -> str:
        await asyncio.sleep(1.0)
        return prompt  # never reaches here under timeout

    healthy = FakeLlm()
    final = asyncio.run(
        with_envelope(
            text,
            llm_calls=[slow, healthy],
            max_attempts=2,
            timeout_per_attempt=0.05,
        )
    )
    assert final == text
    assert len(healthy.calls) == 1


def test_provider_chain_switches_on_integrity_failure(
    monkeypatch: pytest.MonkeyPatch,
):
    """Provider 1 exhausts max_attempts on integrity failures → provider 2."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    import re as _re

    class AlwaysDrops:
        def __init__(self):
            self.n = 0

        async def __call__(self, prompt: str) -> str:
            self.n += 1
            masked, mid = _parse_envelope_prompt(prompt)
            body = _re.sub(r"<PERSON_\d+>", "[gone]", masked)
            return f"<id>{mid}</id>\n{body}"

    bad = AlwaysDrops()
    healthy = FakeLlm()
    final = asyncio.run(with_envelope(text, llm_calls=[bad, healthy], max_attempts=2))
    assert final == text
    assert bad.n == 2, "bad provider must have used both attempts before switch"
    assert len(healthy.calls) == 1


def test_registry_cleaned_after_failure(monkeypatch: pytest.MonkeyPatch):
    """After EnvelopeIntegrityError or EnvelopeProviderError, the mapping_id
    must NOT linger in the registry."""
    text = "Pan Novák volal."
    person_start = text.index("Novák")
    monkeypatch.setattr(
        ner_module,
        "detect_ner",
        make_fake_ner(
            [
                {
                    "span_start": person_start,
                    "span_end": person_start + len("Novák"),
                    "pii_type": "PERSON",
                    "surface_form": "Novák",
                    "ner_confidence": 0.99,
                }
            ]
        ),
    )

    registry = MappingRegistry()

    async def rl(_: str) -> str:
        raise ProviderRateLimitError("A", "429")

    with pytest.raises(EnvelopeProviderError):
        asyncio.run(with_envelope(text, llm_calls=[rl], registry=registry, max_attempts=1))
    assert registry.pending_count() == 0


# ---------------------------------------------------------------------------
# Integration: the demo case (mocked, no real LLM)
# ---------------------------------------------------------------------------


def test_uc02_demo_text_mocked_end_to_end(monkeypatch: pytest.MonkeyPatch):
    """Same text as the 2026-05-30 19:30 Sonnet demo, but with mocked NER + LLM."""
    text = (
        "Volal pan Jiří Novák z čísla +420 605 123 456 ohledně objednávky "
        "z e-shopu Alza.cz. Požaduje doručení na Václavské náměstí 1, "
        "110 00 Praha. IČO 25001388. Email: jiri.novak@example.cz."
    )
    person_s = text.index("Jiří Novák")
    org_s = text.index("Alza.cz")
    addr_s = text.index("Václavské náměstí 1")
    fake_spans = [
        {
            "span_start": person_s,
            "span_end": person_s + len("Jiří Novák"),
            "pii_type": "PERSON",
            "surface_form": "Jiří Novák",
            "ner_confidence": 0.97,
        },
        {
            "span_start": org_s,
            "span_end": org_s + len("Alza.cz"),
            "pii_type": "ORG",
            "surface_form": "Alza.cz",
            "ner_confidence": 0.95,
        },
        {
            "span_start": addr_s,
            "span_end": addr_s + len("Václavské náměstí 1"),
            "pii_type": "ADDRESS",
            "surface_form": "Václavské náměstí 1",
            "ner_confidence": 0.92,
        },
    ]
    monkeypatch.setattr(ner_module, "detect_ner", make_fake_ner(fake_spans))

    fake = FakeLlm()
    final = asyncio.run(with_envelope(text, fake))
    assert final == text
    for needle in (
        "Jiří Novák",
        "Alza.cz",
        "+420 605 123 456",
        "Václavské náměstí 1",
        "25001388",
        "jiri.novak@example.cz",
    ):
        assert needle not in fake.calls[0], f"{needle} leaked to LLM"
