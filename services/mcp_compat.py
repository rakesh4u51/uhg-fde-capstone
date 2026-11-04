from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastmcp import Client

try:
    import langchain_mcp  # noqa: F401
except Exception:  # pragma: no cover
    langchain_mcp = None


@dataclass
class CompatibleMCPTool:
    """Compatibility wrapper that preserves the older adapter contract used by this app."""

    name: str
    description: str
    inputSchema: dict[str, Any] = field(default_factory=dict)
    args_schema: dict[str, Any] = field(default_factory=dict)
    client: Any = None

    def __post_init__(self) -> None:
        if not self.args_schema:
            self.args_schema = self.inputSchema

    async def ainvoke(self, arguments: dict[str, Any] | None = None) -> Any:
        if self.client is None:
            raise RuntimeError("MCP client is not initialized.")

        payload = arguments or {}
        result = await self.client.call_tool(self.name, payload)
        if hasattr(result, "data"):
            return result.data
        return result


class MCPAdapter:
    """Bridge the newer FastMCP/AI Studio stack to the legacy adapter contract used by the app."""

    def __init__(self, server: Any):
        self.server = server
        self.client: Client | None = None
        self._tools: list[CompatibleMCPTool] = []

    async def __aenter__(self) -> "MCPAdapter":
        self.client = Client(self.server)
        await self.client.__aenter__()
        raw_tools = await self.client.list_tools()
        self._tools = [
            CompatibleMCPTool(
                name=getattr(tool, "name", ""),
                description=getattr(tool, "description", "") or "",
                inputSchema=getattr(tool, "inputSchema", {}) or {},
                client=self.client,
            )
            for tool in raw_tools
        ]
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        if self.client is not None:
            await self.client.__aexit__(exc_type, exc, tb)
            self.client = None

    async def list_tools(self) -> list[CompatibleMCPTool]:
        if self.client is None:
            raise RuntimeError("MCP adapter has not been opened. Call await adapter.__aenter__() first.")
        return self._tools
