"""Canonical prompt-spec model for the project.

Every prompt catalog in the repository should use ``PromptSpec`` for
versioned prompt artefacts with reproducibility metadata.

The class captures:

- stable prompt identity and versioning
- provenance / consumer metadata
- prompt content and optional model hints
- required inputs and structured-output schema

Newly written prompt catalogs should import ``PromptSpec`` from here rather
than defining a local variant.
"""

from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class PromptSpec(BaseModel):
    """Versioned thesis prompt artefact with full reproducibility metadata.

    Designed for catalog modules ``prompts_<scope>.py``; one constant per
    prompt. ``prompt_id + version`` should be persisted alongside the
    provider / model identifier in any result snapshot so the output
    self-describes and can be replayed.
    """

    # ----- Identity (load-bearing for snapshots + reproducibility) ---------

    prompt_id: str = Field(
        ...,
        description=(
            "Stable identifier, dot-separated scope.role. "
            "Examples: 'translation_judge', 'uc01.per_contact.generation', "
            "'synth.contact_enrichment_with_lsm'. Used as the join key in "
            "result snapshots."
        ),
    )
    version: str = Field(
        ...,
        description=(
            "Semantic version string, bumped on every behaviour-changing "
            "edit. Plain integers ('1', '2') are acceptable for trial-phase "
            "prompts; SemVer ('1.2.0') preferred once a prompt is shipped."
        ),
    )

    # ----- Provenance ------------------------------------------------------

    purpose: str = Field(
        ...,
        description=(
            "One-line description of what the prompt does and where it is "
            "consumed. The catalog reader should be able to skim this field "
            "and know the prompt's role without reading the template body."
        ),
    )
    application: str = Field(
        ...,
        description=(
            "Fully-qualified module/component path that consumes this prompt. "
            "A catalog that knows its consumers can notify them on version "
            "bumps."
        ),
    )
    creator: str = Field(
        default="project author",
        description=(
            "Who authored the prompt. Defaults to 'project author'; override "
            "when a particular collaborator or upstream pattern is the "
            "originator."
        ),
    )
    date_created: str = Field(
        ...,
        description="ISO date YYYY-MM-DD when the prompt first entered the catalog.",
    )
    last_modified: str = Field(
        ...,
        description="ISO date YYYY-MM-DD of the most recent edit; mirrors version bumps.",
    )
    change_log: list[str] = Field(
        default_factory=list,
        description=(
            "Short bullet history of behaviour-changing edits. One bullet per "
            "version bump, format 'vN: <one-line summary>'. Optional but "
            "strongly recommended once a prompt has more than one version."
        ),
    )
    source_note: Optional[str] = Field(
        default=None,
        description=(
            "Provenance / inspiration for the prompt design — paper, book "
            "section, earlier prompt id, or pattern reference."
        ),
    )

    # ----- Content (the prompt itself) -------------------------------------

    system_instruction: str = Field(
        ...,
        description=(
            "The actual prompt text. Czech for thesis-Czech-output prompts, "
            "English for code/agent prompts. Use plain string; substitute "
            "input slots at call-time with the field names listed in "
            "`required_inputs`."
        ),
    )

    # ----- Provider + sampling hints (optional during trial) ---------------

    target_models: Optional[list[str]] = Field(
        default=None,
        description=(
            "Concrete provider+model identifiers this prompt is pinned to. "
            "None while the prompt is still being tuned; MUST be set before "
            "a reproducible run. Use the same model names the generation "
            "wrappers accept "
            "(e.g. 'gemini-2.5-pro', 'claude-sonnet-4-6', 'gpt-5.5')."
        ),
    )
    temperature: Optional[float] = Field(
        default=None,
        description=(
            "Ideal sampling temperature when invoking this prompt. None means "
            "'use the wrapper default'. Per Huyen Ch 5 'ideal sampling "
            "parameters' suggestion."
        ),
    )
    top_p: Optional[float] = Field(
        default=None,
        description="Ideal top-p sampling parameter. None means wrapper default.",
    )

    # ----- I/O contract ----------------------------------------------------

    required_inputs: tuple[str, ...] = Field(
        default=(),
        description=(
            "Named slots the caller must substitute before invoking the "
            "prompt (e.g. ('gender', 'formality', 'title') for the contact "
            "enricher). Empty tuple if the prompt has no slots."
        ),
    )
    output_format: str = Field(
        default="text",
        description=(
            "'text' for free-form responses, 'json' when the model must emit "
            "JSON matching `json_schema`. Drives which wrapper entry point "
            "(generate_text vs generate_json) the caller picks."
        ),
    )
    json_schema: Optional[dict] = Field(
        default=None,
        description=(
            "JSON-Schema (lowercase 'object'/'array' types) describing the "
            "expected output when `output_format == 'json'`. Wrapper-specific "
            "dialect translation (e.g. Vertex uppercase 'OBJECT') happens at "
            "call site, not in the catalog."
        ),
    )

    # ----- Helpers ---------------------------------------------------------

    def to_dict(self) -> dict:
        """JSON-serialisable representation for logging / report rows."""
        return self.model_dump()

    def header_for_snapshot(self) -> str:
        """One-line label suitable for CSV / JSONL report headers.

        Example: 'translation_judge v1 (gemini-2.5-pro)'.
        """
        models = ",".join(self.target_models) if self.target_models else "unassigned"
        return f"{self.prompt_id} v{self.version} ({models})"
