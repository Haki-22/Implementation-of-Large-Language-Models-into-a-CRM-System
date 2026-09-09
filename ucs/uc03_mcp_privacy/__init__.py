"""UC-03: the MCP middleware between the CRM database and a chat.

A language model reaches the CRM only through this server. Under the masking
profiles every personal value it receives is a session token from UC-02's
vocabulary and every token it sends back is resolved by the server; every call
is audited; the tool definitions the model reads are pinned.

Modules
-------
- ``server``        FastMCP stdio entry point: manifest check, audited dispatch.
- ``tools``         The fifteen CRM tools for one security profile (``CrmTools``).
- ``envelope``      The session envelope: tokens, handles, restore, the shared map.
- ``audit_log``     Append-only hash-chained JSONL log of tool calls.
- ``tool_manifest`` Pin of the advertised ``tools/list`` payload, verified at start.
- ``categorizer``   Note categoriser: keyword rules, or a model behind the switch.
- ``chat``          CLI chat: type or dictate, the model drives the tools.
- ``stt``           Speech to text: local Whisper by default, Google as comparison.
- ``review``        Review queue for field changes held under the strict profile.
- ``mcp_client``    Blocking MCP client for scripts and tests.
- ``config``        Settings, all environment-overridable.
- ``demo/``         ``smoke.py`` drives the server through the README's guarantees.
- ``eval/``         Synthetic Czech audio corpus and the speech-to-text runs.
"""
