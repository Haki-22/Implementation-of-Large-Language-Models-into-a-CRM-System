"""
API-based (non-CLI) generation providers.

CLI providers (`utils.generation.codex`, `.claude`, `.gemini`) use the local
OAuth-authenticated CLI binaries.  API providers in this subpackage call cloud
endpoints directly with service-account or API-key credentials.  Use these
when the CLI providers are quota-blocked or when you need provider features
(file attachments, structured-output mime types, region routing) the CLIs do
not expose.

    from utils.generation.api.vertex import gemini as vertex_gemini

    text = await vertex_gemini.generate_text(
        "Summarise this draft in 200 words.",
        system_prompt="You are an academic editor.",
        model="gemini-3.1-pro-preview",
        files=["draft.md"],
    )
"""
