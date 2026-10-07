"""Event types and payload factories used to stream agent progress to the user interface."""

from __future__ import annotations
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

from client.response import TokenUsage
from tools.base import ToolResult


class AgentEventType(str, Enum):
    """Names for lifecycle, streaming, and tool execution events."""

    # Agent lifecycle
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"

    # Tool calls
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"

    # Text streaming
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"


@dataclass
class AgentEvent:
    """Carry an event name and its JSON-serializable payload."""

    type: AgentEventType
    data: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def agent_start(cls, message: str) -> AgentEvent:
        """Create the event emitted before processing a user message."""
        return cls(
            type=AgentEventType.AGENT_START,
            data={"message": message},
        )

    @classmethod
    def agent_end(
        cls,
        response: str | None = None,
        usage: TokenUsage | None = None,
    ) -> AgentEvent:
        """Create the event emitted after the agent finishes successfully."""
        return cls(
            type=AgentEventType.AGENT_END,
            data={
                "response": response,
                "usage": usage.__dict__ if usage else None,
            },
        )

    @classmethod
    def agent_error(
        cls,
        error: str,
        details: dict[str, Any] | None = None,
    ) -> AgentEvent:
        """Create an event describing an error encountered during a turn."""
        return cls(
            type=AgentEventType.AGENT_ERROR,
            data={"error": error, "details": details or {}},
        )

    @classmethod
    def text_delta(cls, content: str) -> AgentEvent:
        """Text delta."""
        return cls(
            type=AgentEventType.TEXT_DELTA,
            data={"content": content},
        )

    @classmethod
    def text_complete(cls, content: str) -> AgentEvent:
        """Text complete."""
        return cls(
            type=AgentEventType.TEXT_COMPLETE,
            data={"content": content},
        )

    @classmethod
    def tool_call_start(cls, call_id: str, name: str, arguments: dict[str, Any]):
        """Tool call start."""
        return cls(
            type=AgentEventType.TOOL_CALL_START,
            data={
                "call_id": call_id,
                "name": name,
                "arguments": arguments,
            },
        )

    @classmethod
    def tool_call_complete(
        cls,
        call_id: str,
        name: str,
        result: ToolResult,
    ):
        """Tool call complete."""
        return cls(
            type=AgentEventType.TOOL_CALL_COMPLETE,
            data={
                "call_id": call_id,
                "name": name,
                "success": result.success,
                "output": result.output,
                "error": result.error,
                "metadata": result.metadata,
                "diff": result.diff.to_diff() if result.diff else None,
                "truncated": result.truncated,
                "exit_code": result.exit_code,
            },
        )
