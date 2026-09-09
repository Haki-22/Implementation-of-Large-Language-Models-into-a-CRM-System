"""Provider-independent records returned by the CLI MCP host adapters."""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class McpCall:
    """One observed invocation; hosts without a transcript rely on the server audit."""

    tool_name: str
    """Fully qualified name, for example ``mcp__uc03__search_contacts``."""
    input: dict[str, Any] = field(default_factory=dict)
    output: str | None = None
