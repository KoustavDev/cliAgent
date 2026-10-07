"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
from typing import Any
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from tools.mcp.client import MCPClient, MCPToolInfo
from utils.paths import resolve_path


class MCPTool(Tool):

    """Represent mcptool state and behavior."""
    def __init__(
        self,
        config: Config,
        client: MCPClient,
        tool_info: MCPToolInfo,
        name: str,
    ) -> None:
        """Initialize the object with the configuration needed by later steps."""
        super().__init__(config)
        self._tool_info = tool_info
        self._client = client
        self.name = name
        self.description = self._tool_info.description

    @property
    def schema(self) -> dict[str, Any]:
        """Perform the schema operation."""
        input_schema = self._tool_info.input_schema or {}
        return {
            "type": "object",
            "properties": input_schema.get("properties", {}),
            "required": input_schema.get("required", []),
        }

    def is_mutating(self, params) -> bool:
        """Determine whether the requested value mutating."""
        return True

    kind = ToolKind.MCP

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # Step 1: Forward invocation parameters and translate remote failures.
        """Perform the execute operation and return its result."""
        try:
            result = await self._client.call_tool(
                self._tool_info.name,
                invocation.params,
            )
            output = result.get("output", "")
            is_error = result.get("is_error", False)

            if is_error:
                return ToolResult.error_result(output)

            return ToolResult.success_result(output)
        except Exception as e:
            return ToolResult.error_result(f"MCP tool failed: {e}")
