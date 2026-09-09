"""Typed errors raised by the thesis CLI-based LLM providers."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# The error classes
# ---------------------------------------------------------------------------


class GenerationError(RuntimeError):
    """Base class for all provider failures surfaced by ``utils.generation``."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        hint: str | None = None,
        details: str | None = None,
    ) -> None:
        """Store the failing provider's name plus a message and optional hint/details."""
        self.provider = provider
        self.message = message
        self.hint = hint
        self.details = details
        super().__init__(str(self))

    def __str__(self) -> str:
        """Render as ``"provider: message [Hint: ...] [Details: ...]"``."""
        parts = [f"{self.provider}: {self.message}"]
        if self.hint:
            parts.append(f"Hint: {self.hint}")
        if self.details:
            parts.append(f"Details: {self.details}")
        return " ".join(parts)


class ProviderCliNotFoundError(GenerationError):
    """The provider CLI executable is not installed or not on PATH."""


class ProviderAuthError(GenerationError):
    """The provider CLI is installed but not authenticated or not authorized."""


class ProviderRateLimitError(GenerationError):
    """The provider rejected the request because of rate limiting or overload."""


class ProviderQuotaError(GenerationError):
    """The provider rejected the request because quota, credits, or billing ran out."""


class ProviderTimeoutError(GenerationError):
    """The provider CLI did not finish before the configured timeout."""


class ProviderCliError(GenerationError):
    """The provider CLI exited unsuccessfully for an unclassified reason."""


class ProviderOutputError(GenerationError):
    """The provider CLI succeeded but returned empty or malformed output."""


class ProviderJsonError(ProviderOutputError):
    """The provider output could not be parsed as the expected JSON object."""


class LLMCallsDisabledError(GenerationError):
    """The global switch (``THESIS_LLM_CALLS``, see ``utils.llm_switch``) is off; nothing was called."""


# ---------------------------------------------------------------------------
# What the CLIs print when they fail (conservative text matching)
# ---------------------------------------------------------------------------

_AUTH_PATTERNS = (
    "not authenticated",
    "unauthenticated",
    "unauthorized",
    "unauthorised",
    "authentication",
    "login",
    "log in",
    "sign in",
    "oauth",
    "api key",
    "invalid token",
    "token expired",
    "401",
)

_QUOTA_PATTERNS = (
    "quota",
    "insufficient_quota",
    "billing",
    "credits",
    "spending limit",
    "usage limit",
    "out of quota",
    "resource_exhausted",
    # agy 1.1.27: when the CLI stops answering (observed 2026-09-07 with the account
    # dashboard at ~90 % of the five-hour window, and found afterwards to be a signed-out
    # session), every call fails with "Eligibility check failed: failed to get profile
    # picture … no route to host"; not a network fault of this machine (the same host
    # answered before and after). Treated as quota: not retried, and a run stops sending.
    "eligibility check failed",
)

_RATE_LIMIT_PATTERNS = (
    "rate limit",
    "ratelimit",
    "too many requests",
    "429",
    "overloaded",
    "temporarily unavailable",
)

# The account cannot use the requested model id (2026-09-07: `gpt-5.5` answered
# `404 The model does not exist or you do not have access to it` on the Codex
# account while its siblings worked). Checked before the rate-limit patterns: the
# CLI's reconnect chatter around the 404 used to make it look like an overload.
_MODEL_PATTERNS = (
    "does not exist or you do not have access",
    "model not found",
    "unknown model",
    "unsupported model",
)

_AUTH_HINTS = {
    "codex": "Run `codex` interactively and complete ChatGPT sign-in.",
    "claude": "Run `claude auth` or `claude` interactively and complete sign-in.",
    "agy": "Run `agy` interactively and complete Google sign-in.",
}


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------


def cli_missing(provider: str, binary: str) -> ProviderCliNotFoundError:
    """Return a provider-specific CLI-not-found error."""
    return ProviderCliNotFoundError(
        provider,
        f"CLI executable `{binary}` was not found on PATH.",
        hint=f"Install the {provider} CLI and ensure `{binary}` is visible in this shell.",
    )


def classify_cli_failure(
    provider: str,
    text: str,
    *,
    exit_code: int | None = None,
) -> GenerationError:
    """
    Classify provider stderr/stdout text into a typed generation error.

    The CLIs do not share a stable error schema, so this intentionally uses
    conservative text matching.  Unknown failures still keep the original text
    in ``details`` so a new machine can be diagnosed from the terminal output.
    """
    detail = text.strip()
    lowered = detail.lower()
    prefix = f"CLI exited with code {exit_code}." if exit_code is not None else "CLI failed."

    if any(pattern in lowered for pattern in _QUOTA_PATTERNS):
        return ProviderQuotaError(
            provider,
            f"{prefix} Provider quota, credits, billing, or usage limit blocked the request.",
            hint="Check the provider account/subscription limits. No fallback was attempted.",
            details=detail[:1000],
        )

    if any(pattern in lowered for pattern in _AUTH_PATTERNS):
        return ProviderAuthError(
            provider,
            f"{prefix} Authentication or authorization failed.",
            hint=_AUTH_HINTS.get(provider, "Open the provider CLI interactively and sign in."),
            details=detail[:1000],
        )

    if any(pattern in lowered for pattern in _MODEL_PATTERNS):
        return ProviderCliError(
            provider,
            f"{prefix} The requested model is not available on this account.",
            hint=(
                "Pick a model from the generated menu (`python -m utils.generation.catalog "
                "update` refreshes it) or check the account's plan. No fallback was attempted."
            ),
            details=detail[:1000],
        )

    if any(pattern in lowered for pattern in _RATE_LIMIT_PATTERNS):
        return ProviderRateLimitError(
            provider,
            f"{prefix} Provider rate limit or temporary overload blocked the request.",
            hint="Wait and retry later, or lower concurrency/effort. No fallback was attempted.",
            details=detail[:1000],
        )

    return ProviderCliError(provider, prefix, details=detail[:1000])
