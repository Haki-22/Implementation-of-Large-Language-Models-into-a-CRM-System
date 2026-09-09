"""
Vertex AI Gemini provider — reference only; not used in active code.

This wrapper produced some shipped results before the GCP trial credits
expired (2026-05-29). Active UC-04 arms (b4 / b6 / b12 / b13 / b14) have
since been rewired to ``utils.generation.claude.generate_text``. The wrapper
is kept here so a future user with their own Vertex AI billing could re-enable
Gemini-backed arms without recreating the integration — nothing in the rest
of the project imports from this module today except the historical
``substrate/pipeline/translation_pipeline/`` stages, which already ran and
whose snapshot output is committed.

----------------------------------------------------------------------------

A small async client around Google Cloud's Vertex AI ``generateContent``
endpoint.  Uses a service-account JSON key for authentication so it sits on
its own paid quota bucket, separate from the personal ``gemini`` CLI / AI
Studio free-tier key.

Setup
-----
The wrapper reads three environment variables:

    GOOGLE_APPLICATION_CREDENTIALS    absolute path to a service-account JSON key
    GOOGLE_CLOUD_PROJECT              your GCP project ID
    GOOGLE_CLOUD_LOCATION             default region; optional, defaults to "us-central1"

How you put them into the process is up to you.  The recommended pattern
keeps them in a ``.env`` file at the project root and loads it once at
application start:

    from dotenv import load_dotenv
    load_dotenv()

    import asyncio
    from utils.generation.api.vertex import gemini

    text = asyncio.run(gemini.generate_text("Hello, world."))
    print(text)

The wrapper itself does NOT call ``load_dotenv`` on import — that side
effect belongs in the application's entry point, not in a library module.

Region routing
--------------
Gemini 3.x preview models are only published in the ``global`` region.
Gemini 2.5.x and earlier are published per-region.  When the caller asks
for a Gemini 3.x model the wrapper overrides ``GOOGLE_CLOUD_LOCATION`` to
``"global"`` automatically, so callers do not need to remember which
region each model lives in.

Files as input
--------------
The Vertex API does NOT read files from the local disk.  The ``files=``
parameter reads each path locally and sends one ``Part`` per file as plain
UTF-8 text, with a small header so the model can refer back to the source
filename.  For binary inputs (PDF, audio) extend ``_file_part()`` to emit
``inline_data`` parts with the right ``mime_type``.

Usage and cost reporting
------------------------
Each call returns text only (or a parsed JSON value for ``generate_json``).
The Vertex API returns token counts in its ``usageMetadata`` block but
does NOT return a price; converting tokens into money is left to the
caller, who should consult Google Cloud Billing for authoritative numbers.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2 import service_account

from utils.generation.errors import (
    GenerationError,
    ProviderAuthError,
    ProviderJsonError,
    ProviderOutputError,
    ProviderQuotaError,
    ProviderRateLimitError,
    ProviderTimeoutError,
)

logger = logging.getLogger(__name__)


#############################################################
#
# Constants & model inventory
#
#############################################################

PROVIDER_NAME = "vertex-gemini"
DEFAULT_MODEL = "gemini-3.1-pro-preview"
DEFAULT_TIMEOUT_SECONDS = 300

# OAuth scope required for any Vertex AI inference call.
_TOKEN_REFRESH_SCOPES = ("https://www.googleapis.com/auth/cloud-platform",)

# Models below are only published in the "global" region.  When the caller
# asks for one of these the wrapper overrides GOOGLE_CLOUD_LOCATION → "global".
_GLOBAL_ONLY_MODELS = frozenset(
    {
        "gemini-3.1-pro-preview",
        "gemini-3-pro-preview",
        "gemini-3-flash-preview",
        "gemini-3.1-flash-lite-preview",
        "gemini-3.1-flash-lite",
        "gemini-3.5-flash",
    }
)

# The constants below document what model families are reachable through
# this wrapper.  They are kept as tuples (not enums) so they can be passed
# directly to argparse choices, iterated for documentation, etc.  Re-enumerate
# the live inventory for a given GCP project by querying the publisher list:
#
#   curl -H "Authorization: Bearer $(gcloud auth print-access-token)" \
#     https://us-central1-aiplatform.googleapis.com/v1beta1/publishers/google/models

# Heavy reasoning models — Pro family.
VERTEX_GEMINI_PRO_MODELS: tuple[str, ...] = (
    "gemini-3.1-pro-preview",
    "gemini-3-pro-preview",
    "gemini-2.5-pro",
)

# Cheap text models — Flash family.
VERTEX_GEMINI_FLASH_MODELS: tuple[str, ...] = (
    "gemini-3.5-flash",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.1-flash-lite",
    "gemini-2.5-flash",
    "gemini-2.5-flash-lite",
    "gemini-2.0-flash-001",
)

# Multimodal generation — images, TTS, image-to-image.
VERTEX_GEMINI_MULTIMODAL_MODELS: tuple[str, ...] = (
    "gemini-2.5-flash-image",
    "gemini-3-pro-image-preview",
    "gemini-3.1-flash-image-preview",
    "gemini-3.1-flash-tts-preview",
    "gemini-2.5-flash-tts",
    "gemini-2.5-pro-tts",
)

# Speech-to-text — Chirp family.
VERTEX_STT_MODELS: tuple[str, ...] = (
    "chirp-3",
    "chirp-2",
    "medasr",
)

# Translation — task-specific text models.
VERTEX_TRANSLATION_MODELS: tuple[str, ...] = (
    "translate-llm",
    "text-translation",
    "translategemma",
)

# Embeddings — multilingual and English-only options.
VERTEX_EMBEDDING_MODELS: tuple[str, ...] = (
    "gemini-embedding-2",
    "gemini-embedding-001",
    "text-multilingual-embedding-002",
    "text-embedding-005",
    "embeddinggemma",
)

# Image generation — Imagen 4.
VERTEX_IMAGEN_MODELS: tuple[str, ...] = (
    "imagen-4.0-ultra-generate-001",
    "imagen-4.0-generate-001",
    "imagen-4.0-fast-generate-001",
)

# Video generation — Veo.
VERTEX_VEO_MODELS: tuple[str, ...] = (
    "veo-3.1-generate-001",
    "veo-3.1-fast-generate-001",
    "veo-3.1-lite-generate-001",
    "veo-3.0-generate-001",
)

# Combined text-generation model tuple used by the CLI's --model choices.
VERTEX_GEMINI_MODELS: tuple[str, ...] = (
    *VERTEX_GEMINI_PRO_MODELS,
    *VERTEX_GEMINI_FLASH_MODELS,
)

# Built-in tools the wrapper knows how to enable.  Vertex offers more
# tools (code_execution, retrieval, etc.); extend _build_tools() if you
# need them.
_SUPPORTED_TOOLS = frozenset({"google_search", "url_context"})


#############################################################
#
# Public types
#
#############################################################


@dataclass
class VertexUsage:
    """Token counts reported by Vertex for one ``generateContent`` call.

    The Vertex API returns these numbers in its ``usageMetadata`` block.
    Convert them into money downstream using the current Google Cloud
    Vertex AI price list — the wrapper deliberately does not bake rates in.

    Attributes:
        prompt_tokens: Tokens billed as input (prompt + system + files).
        output_tokens: Tokens in the visible model output.
        thoughts_tokens: Internal reasoning tokens.  Google bills these
            at the output rate even though they are not part of the
            returned text.
        total_tokens: Tokens reported in ``totalTokenCount``.  Usually
            equals ``prompt_tokens + output_tokens + thoughts_tokens``.
        model: The model ID that produced the call.
        region: The Vertex region the call hit (``"global"`` or e.g.
            ``"us-central1"``).
    """

    prompt_tokens: int
    output_tokens: int
    thoughts_tokens: int
    total_tokens: int
    model: str
    region: str


#############################################################
#
# Credentials & endpoint helpers
#
#############################################################


# Cached credentials live at module scope so we do not re-read the JSON
# key file on every call.  Single-process, single-event-loop use is
# assumed; wrap _resolve_credentials() in asyncio.to_thread() and add a
# lock if you call this wrapper from multiple threads at once.
_cached_credentials: service_account.Credentials | None = None


def _resolve_credentials() -> service_account.Credentials:
    """Load and cache the service-account credentials, refreshing on demand.

    The credentials object holds a short-lived OAuth access token that
    the wrapper attaches to every Vertex request.  ``Credentials.refresh``
    is a synchronous HTTP call to ``oauth2.googleapis.com``; in async code
    that runs at high concurrency consider wrapping this call in
    ``asyncio.to_thread`` to avoid blocking the event loop.

    Returns:
        A ready-to-use ``google.oauth2.service_account.Credentials`` with
        a non-expired access token in ``credentials.token``.

    Raises:
        ProviderAuthError: If ``GOOGLE_APPLICATION_CREDENTIALS`` is not
            set, or points to a file that does not exist.
    """
    global _cached_credentials

    key_path = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not key_path:
        raise ProviderAuthError(
            PROVIDER_NAME,
            "GOOGLE_APPLICATION_CREDENTIALS is not set.",
            hint=(
                "Set GOOGLE_APPLICATION_CREDENTIALS to the absolute path of your "
                "service-account JSON key. See https://cloud.google.com/docs/"
                "authentication/application-default-credentials"
            ),
        )

    if not Path(key_path).exists():
        raise ProviderAuthError(
            PROVIDER_NAME,
            f"Service-account key not found at {key_path!r}.",
            hint=(
                "Re-download the JSON key from the GCP Console under "
                "IAM & Admin -> Service Accounts -> Keys."
            ),
        )

    if _cached_credentials is None:
        _cached_credentials = service_account.Credentials.from_service_account_file(
            key_path,
            scopes=list(_TOKEN_REFRESH_SCOPES),
        )

    if not _cached_credentials.valid:
        _cached_credentials.refresh(GoogleAuthRequest())

    return _cached_credentials


def _resolve_region(model: str) -> str:
    """Pick the Vertex region for one model.

    Args:
        model: The Gemini model ID, e.g. ``"gemini-3.1-pro-preview"``.

    Returns:
        ``"global"`` for models that are only published globally,
        otherwise the value of ``GOOGLE_CLOUD_LOCATION`` (defaulting to
        ``"us-central1"``).
    """
    if model in _GLOBAL_ONLY_MODELS:
        return "global"
    return os.environ.get("GOOGLE_CLOUD_LOCATION", "us-central1")


def _endpoint(model: str, region: str, project: str) -> str:
    """Return the full ``generateContent`` URL for one model + region + project.

    Args:
        model: Gemini model ID.
        region: Vertex region (``"global"`` or a regional name like
            ``"us-central1"``).
        project: GCP project ID.

    Returns:
        The absolute HTTPS URL the client should POST to.
    """
    host = (
        "aiplatform.googleapis.com" if region == "global" else f"{region}-aiplatform.googleapis.com"
    )
    return (
        f"https://{host}/v1/projects/{project}/locations/{region}"
        f"/publishers/google/models/{model}:generateContent"
    )


#############################################################
#
# Request building
#
#############################################################


def _file_part(path: str) -> dict[str, Any]:
    """Read one local file and wrap it as a Vertex ``parts`` text entry.

    Each file becomes its own ``Part`` with a small ``=== FILE: ... ===``
    header so the model can refer back to its source filename in the
    response.  Useful when the prompt asks the model to compare or cite
    several documents.

    Args:
        path: Path to a UTF-8 text file readable by the current process.

    Returns:
        A ``parts``-shaped dict ready to be appended to the request body.

    Raises:
        FileNotFoundError: If ``path`` does not point at an existing file.
    """
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Vertex Gemini file attachment not found: {path}")
    body = file_path.read_text(encoding="utf-8", errors="replace")
    header = f"=== FILE: {file_path.name} ({file_path} | {len(body)} chars) ==="
    return {"text": f"{header}\n{body}\n=== END FILE ==="}


def _build_tools(tools: list[str] | None) -> list[dict[str, Any]]:
    """Translate a list of tool names into the Vertex ``tools`` array.

    Two built-in tools are recognised today:

    - ``"google_search"`` — Google Search grounding.  The model emits
      inline citations in its response.
    - ``"url_context"`` — Automatic URL fetching.  Any http(s) URLs that
      appear in the prompt or system instruction are fetched by the model
      (up to 20 per request) and included as context.

    Args:
        tools: A list of tool names, or ``None``.

    Returns:
        The ``tools`` array to insert into the request body, possibly
        empty.

    Raises:
        ValueError: If ``tools`` contains a name the wrapper does not
            know how to translate.
    """
    if not tools:
        return []
    blocks: list[dict[str, Any]] = []
    for name in tools:
        if name not in _SUPPORTED_TOOLS:
            raise ValueError(
                f"Unsupported Vertex tool: {name!r} (supported: {sorted(_SUPPORTED_TOOLS)})"
            )
        if name == "google_search":
            blocks.append({"googleSearch": {}})
        elif name == "url_context":
            blocks.append({"urlContext": {}})
    return blocks


def _build_request(
    prompt: str,
    *,
    system_prompt: str | None,
    files: list[str] | None,
    schema: dict[str, Any] | None,
    tools: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble the JSON body sent to ``generateContent``.

    Args:
        prompt: The user-facing prompt text.
        system_prompt: Optional system instruction; sent via Vertex's
            native ``system_instruction`` field rather than prepended to
            the prompt.
        files: Optional list of local file paths attached as separate
            text parts.
        schema: Optional JSON Schema.  When supplied the response is
            constrained to valid JSON matching the schema; ``tools`` must
            be ``None`` in that case (Vertex disallows both together).
        tools: Optional list of built-in tool names, see ``_build_tools``.

    Returns:
        The assembled request body.

    Raises:
        ValueError: If both ``schema`` and ``tools`` are supplied.
    """
    parts: list[dict[str, Any]] = []
    if files:
        for path in files:
            parts.append(_file_part(path))
    parts.append({"text": prompt})

    body: dict[str, Any] = {"contents": [{"role": "user", "parts": parts}]}

    if system_prompt:
        body["system_instruction"] = {"parts": [{"text": system_prompt}]}

    if schema is not None:
        if tools:
            raise ValueError(
                "Vertex google_search / url_context tools are incompatible with "
                "structured JSON output (response_schema). Use generate_text instead."
            )
        body["generationConfig"] = {
            "response_mime_type": "application/json",
            "response_schema": schema,
        }

    tool_blocks = _build_tools(tools)
    if tool_blocks:
        body["tools"] = tool_blocks

    return body


#############################################################
#
# HTTP transport
#
#############################################################


def _classify_http_error(status: int, text: str) -> GenerationError:
    """Map a non-2xx Vertex response to one of our typed errors.

    Args:
        status: HTTP status code returned by Vertex.
        text: Response body text.  Only the first 1000 characters are
            retained as ``details`` to keep tracebacks readable.

    Returns:
        A ``GenerationError`` (or one of its more specific subclasses)
        that the caller can either re-raise or branch on.
    """
    snippet = text[:1000]
    lowered = text.lower()

    if status in (401, 403):
        return ProviderAuthError(
            PROVIDER_NAME,
            f"HTTP {status}: authentication or authorization failed.",
            hint=(
                "Verify the service account has the 'Vertex AI User' role "
                "and the Vertex AI API is enabled in your GCP project."
            ),
            details=snippet,
        )
    if status == 429:
        return ProviderRateLimitError(
            PROVIDER_NAME,
            f"HTTP {status}: Vertex throttled the request.",
            hint="Lower concurrency or retry after the suggested backoff.",
            details=snippet,
        )
    if status == 400 and "quota" in lowered:
        return ProviderQuotaError(
            PROVIDER_NAME,
            f"HTTP {status}: Vertex quota exhausted.",
            hint="Check the project's Vertex AI quotas in the GCP Console.",
            details=snippet,
        )
    if status == 404:
        return ProviderOutputError(
            PROVIDER_NAME,
            f"HTTP {status}: model not found in this region.",
            hint=(
                "Gemini 3.x preview models are only published in the "
                "'global' region; verify your model ID against "
                "https://cloud.google.com/vertex-ai/generative-ai/docs/learn/models."
            ),
            details=snippet,
        )
    return GenerationError(
        PROVIDER_NAME,
        f"HTTP {status} from Vertex.",
        details=snippet,
    )


async def _post(
    body: dict[str, Any],
    *,
    model: str,
    timeout: float,
) -> tuple[dict[str, Any], str]:
    """Send one ``generateContent`` request and return the parsed payload.

    Args:
        body: The fully-assembled request body from ``_build_request``.
        model: Gemini model ID; used to pick the region.
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        A tuple ``(payload, region_used)`` where ``payload`` is the
        decoded JSON body and ``region_used`` is the region the request
        actually hit.

    Raises:
        ProviderAuthError: If ``GOOGLE_CLOUD_PROJECT`` is not set, or
            credential resolution fails.
        ProviderTimeoutError: If the HTTP request times out.
        ProviderJsonError: If Vertex returns a non-JSON response body.
        Other ``GenerationError`` subclasses for non-2xx HTTP status
        codes (see ``_classify_http_error``).
    """
    project = os.environ.get("GOOGLE_CLOUD_PROJECT")
    if not project:
        raise ProviderAuthError(
            PROVIDER_NAME,
            "GOOGLE_CLOUD_PROJECT is not set.",
            hint="Set GOOGLE_CLOUD_PROJECT to your GCP project ID.",
        )

    creds = _resolve_credentials()
    region = _resolve_region(model)
    url = _endpoint(model, region, project)
    headers = {
        "Authorization": f"Bearer {creds.token}",
        "Content-Type": "application/json",
    }

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            resp = await client.post(url, headers=headers, json=body)
        except httpx.TimeoutException as exc:
            raise ProviderTimeoutError(
                PROVIDER_NAME,
                f"Vertex request timed out after {timeout}s.",
                hint="Increase timeout or simplify the prompt.",
            ) from exc

    if resp.status_code >= 400:
        raise _classify_http_error(resp.status_code, resp.text)

    try:
        return resp.json(), region
    except ValueError as exc:
        raise ProviderJsonError(
            PROVIDER_NAME,
            "Vertex returned non-JSON body.",
            details=resp.text[:1000],
        ) from exc


#############################################################
#
# Response parsing
#
#############################################################


def _extract_text(payload: dict[str, Any]) -> str:
    """Pull the model's text response out of a ``generateContent`` body.

    Args:
        payload: The decoded JSON body returned by Vertex.

    Returns:
        The concatenated text from the first candidate, stripped of
        leading and trailing whitespace.

    Raises:
        ProviderOutputError: If the response contains no candidates or
            the first candidate's text is empty.
    """
    candidates = payload.get("candidates") or []
    if not candidates:
        raise ProviderOutputError(
            PROVIDER_NAME,
            "Vertex response had no candidates.",
            details=json.dumps(payload)[:1000],
        )

    parts = candidates[0].get("content", {}).get("parts") or []
    text_chunks = [str(part.get("text", "")) for part in parts if part.get("text")]
    text = "".join(text_chunks).strip()

    if not text:
        finish = candidates[0].get("finishReason")
        raise ProviderOutputError(
            PROVIDER_NAME,
            f"Vertex returned an empty text response (finishReason={finish!r}).",
            details=json.dumps(payload)[:1000],
        )

    return text


def _extract_json(text: str) -> dict[str, Any] | list[Any]:
    """Parse a JSON object or array out of a text response.

    First tries strict ``json.loads``.  If that fails, strips one level
    of Markdown code fence and retries.  As a last-ditch best effort
    falls back to a greedy regex.  This last step is intentionally
    permissive — when ``generate_json`` is called with a real
    ``response_schema`` the model emits clean JSON and the regex never
    fires.

    Args:
        text: The raw model output to parse.

    Returns:
        A ``dict`` or ``list`` decoded from the text.

    Raises:
        ProviderJsonError: If no JSON object or array can be recovered.
    """
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        inner = lines[1:] if len(lines) > 1 else lines
        if inner and inner[-1].strip() == "```":
            inner = inner[:-1]
        cleaned = "\n".join(inner).strip()

    try:
        result = json.loads(cleaned)
        if isinstance(result, (dict, list)):
            return result
    except json.JSONDecodeError:
        pass

    for pattern in (r"\[.*\]", r"\{.*\}"):
        match = re.search(pattern, cleaned, re.DOTALL)
        if match:
            try:
                result = json.loads(match.group(0))
                if isinstance(result, (dict, list)):
                    return result
            except json.JSONDecodeError:
                continue

    raise ProviderJsonError(
        PROVIDER_NAME,
        "generate_json could not extract a JSON object or array from the response.",
        details=f"Response ({len(text)} chars): {text[:1000]!r}",
    )


def _record_usage(model: str, region: str, usage: dict[str, Any]) -> VertexUsage:
    """Log one call's token counts and return them as ``VertexUsage``.

    Args:
        model: Gemini model ID.
        region: Region the call hit.
        usage: The ``usageMetadata`` block from the Vertex response.

    Returns:
        A populated ``VertexUsage`` with prompt, output, and thoughts
        token counts.
    """
    prompt = int(usage.get("promptTokenCount", 0))
    candidates = int(usage.get("candidatesTokenCount", 0))
    thoughts = int(usage.get("thoughtsTokenCount", 0))
    total = int(usage.get("totalTokenCount", prompt + candidates + thoughts))

    logger.info(
        "[vertex] %s @ %s tokens=in:%d/out:%d/think:%d total:%d",
        model,
        region,
        prompt,
        candidates,
        thoughts,
        total,
    )

    return VertexUsage(
        prompt_tokens=prompt,
        output_tokens=candidates,
        thoughts_tokens=thoughts,
        total_tokens=total,
        model=model,
        region=region,
    )


#############################################################
#
# Public API
#
#############################################################


async def generate_text(
    prompt: str,
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    files: list[str] | None = None,
    timeout: int | None = None,
    tools: list[str] | None = None,
) -> str:
    """Generate a text response from a Vertex AI Gemini model.

    This is the simplest entry point for application code.  Prefer it
    over the internal helpers when you want plain text back.

    Args:
        prompt: The user prompt / task instructions.
        system_prompt: Optional system instruction; passed via Vertex's
            native ``system_instruction`` field so it does not consume
            prompt context.
        model: One of ``VERTEX_GEMINI_MODELS``.  Defaults to
            ``DEFAULT_MODEL``.  For Gemini 3.x the region is overridden
            to ``"global"`` automatically.
        files: Optional list of local file paths.  Each file is read as
            UTF-8 and sent as its own ``Part`` with a header so the
            model can refer back to it.
        timeout: Per-request HTTP timeout in seconds.  Defaults to
            ``DEFAULT_TIMEOUT_SECONDS``.
        tools: Optional list of built-in tool names, see ``_build_tools``.
            Currently supports ``"google_search"`` and ``"url_context"``.
            Cannot be combined with ``generate_json``.

    Returns:
        The model's response text, stripped of leading and trailing
        whitespace.

    Raises:
        ProviderAuthError: Missing or invalid credentials / project.
        ProviderTimeoutError: HTTP timeout.
        ProviderRateLimitError: Vertex throttled the request.
        ProviderQuotaError: Project quota exhausted.
        ProviderOutputError: Empty / missing model output, or the model
            ID is not published in the resolved region.
        GenerationError: Any other non-2xx HTTP failure.
    """
    selected_model = model or DEFAULT_MODEL
    body = _build_request(
        prompt,
        system_prompt=system_prompt,
        files=files,
        schema=None,
        tools=tools,
    )
    payload, region = await _post(
        body,
        model=selected_model,
        timeout=float(timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS),
    )
    text = _extract_text(payload)
    _record_usage(selected_model, region, payload.get("usageMetadata", {}))
    return text


async def generate_json(
    prompt: str,
    schema: dict[str, Any],
    *,
    system_prompt: str | None = None,
    model: str | None = None,
    files: list[str] | None = None,
    timeout: int | None = None,
) -> dict[str, Any] | list[Any]:
    """Generate a structured JSON response from a Vertex AI Gemini model.

    Uses Vertex's native ``response_mime_type: application/json`` plus
    ``response_schema`` so the model is constrained to emit valid JSON
    matching ``schema``, rather than emitting free-form text that happens
    to contain a JSON object.

    Args:
        prompt: The user prompt / task instructions.
        schema: JSON Schema describing the expected response shape.
        system_prompt: Optional system instruction.
        model: One of ``VERTEX_GEMINI_MODELS``.  Defaults to
            ``DEFAULT_MODEL``.
        files: Optional list of local file paths.
        timeout: Per-request HTTP timeout in seconds.

    Returns:
        A ``dict`` or ``list`` decoded from the model's response.

    Raises:
        ProviderJsonError: If the model output cannot be parsed as JSON.
        Same auth / transport errors as ``generate_text``.
    """
    selected_model = model or DEFAULT_MODEL
    body = _build_request(prompt, system_prompt=system_prompt, files=files, schema=schema)
    payload, region = await _post(
        body,
        model=selected_model,
        timeout=float(timeout if timeout is not None else DEFAULT_TIMEOUT_SECONDS),
    )
    text = _extract_text(payload)
    _record_usage(selected_model, region, payload.get("usageMetadata", {}))
    return _extract_json(text)


def generate_text_sync(prompt: str, **kwargs: Any) -> str:
    """Blocking convenience wrapper around :func:`generate_text`.

    Useful in scripts, notebooks, or other non-async contexts.  Do not
    call this from inside a running event loop; use ``generate_text``
    directly there instead.
    """
    return asyncio.run(generate_text(prompt, **kwargs))


def generate_json_sync(
    prompt: str,
    schema: dict[str, Any],
    **kwargs: Any,
) -> dict[str, Any] | list[Any]:
    """Blocking convenience wrapper around :func:`generate_json`."""
    return asyncio.run(generate_json(prompt, schema, **kwargs))


__all__ = [
    "DEFAULT_MODEL",
    "DEFAULT_TIMEOUT_SECONDS",
    "PROVIDER_NAME",
    "VERTEX_GEMINI_FLASH_MODELS",
    "VERTEX_GEMINI_MODELS",
    "VERTEX_GEMINI_MULTIMODAL_MODELS",
    "VERTEX_GEMINI_PRO_MODELS",
    "VERTEX_EMBEDDING_MODELS",
    "VERTEX_IMAGEN_MODELS",
    "VERTEX_STT_MODELS",
    "VERTEX_TRANSLATION_MODELS",
    "VERTEX_VEO_MODELS",
    "VertexUsage",
    "generate_json",
    "generate_json_sync",
    "generate_text",
    "generate_text_sync",
]


#############################################################
#
# CLI entry point
#
#############################################################
#
# Run with ``python -m utils.generation.api.vertex.gemini``.  All paths
# are absolute or relative to the current working directory.  Prints a
# token-usage summary to stdout after writing the model's response to
# the file given by ``--output``.  Exit code 0 on success, non-zero with
# a traceback on any error.
#
# Example:
#
#   python -m utils.generation.api.vertex.gemini \
#       --model gemini-3.1-pro-preview \
#       --system-prompt-file sys.txt \
#       --prompt-file prompt.txt \
#       --files draft.md,context.md \
#       --output answer.txt


def _main() -> int:
    """CLI entry point: send one prompt to a Vertex Gemini model and write its response to a file."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Invoke a Vertex AI Gemini model from the command line.",
    )
    parser.add_argument(
        "--model",
        default=DEFAULT_MODEL,
        choices=list(VERTEX_GEMINI_MODELS),
    )
    parser.add_argument(
        "--prompt-file",
        required=True,
        help="UTF-8 text file containing the user prompt.",
    )
    parser.add_argument(
        "--system-prompt-file",
        help="UTF-8 text file containing the system instruction (optional).",
    )
    parser.add_argument(
        "--files",
        default="",
        help=(
            "Comma-separated list of files to attach as separate text Parts "
            "(e.g. 'draft.md,context.md')."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Path to write the model's text response.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Per-request HTTP timeout in seconds (default {DEFAULT_TIMEOUT_SECONDS}).",
    )
    parser.add_argument(
        "--google-search",
        action="store_true",
        help="Enable Google Search grounding (the model emits inline citations).",
    )
    parser.add_argument(
        "--url-context",
        action="store_true",
        help="Enable URL-context auto-fetching (up to 20 URLs per request).",
    )
    args = parser.parse_args()

    prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    system_prompt = (
        Path(args.system_prompt_file).read_text(encoding="utf-8")
        if args.system_prompt_file
        else None
    )
    files = [f.strip() for f in args.files.split(",") if f.strip()] or None
    tools = [
        name
        for name, on in (
            ("google_search", args.google_search),
            ("url_context", args.url_context),
        )
        if on
    ] or None

    text = generate_text_sync(
        prompt,
        system_prompt=system_prompt,
        model=args.model,
        files=files,
        timeout=args.timeout,
        tools=tools,
    )
    Path(args.output).write_text(text, encoding="utf-8")
    print(
        f"[vertex-cli] {args.model}: wrote {len(text)} chars to {args.output}",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
