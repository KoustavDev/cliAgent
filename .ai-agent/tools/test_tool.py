"""Example discovered tool used to verify tool loading and invocation."""

from pydantic import BaseModel, Field
from tools.base import Tool, ToolInvocation, ToolResult, ToolKind


class TestToolParams(BaseModel):
    """Validate the message accepted by :class:`TestTool`."""

    message: str = Field(..., description="The message to echo back")


class TestTool(Tool):
    """Echo a message and identify the source of the discovered tool."""

    name = "test_tool"
    description = (
        "A test tool that echoes back the input message. "
        "This tool is discovered from .unified_agent/tool/test_tool.py"
    )
    kind = ToolKind.READ
    schema = TestToolParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        """Validate invocation parameters and return the echoed result."""

        # Validate the incoming mapping before constructing user-facing output.
        params = TestToolParams(**invocation.params)
        message = params.message

        output = f"Test tool received: {message}\n"
        output += "Tool was discovered from: .ai-agent/tool/test_tool.py"

        return ToolResult.success_result(output)
