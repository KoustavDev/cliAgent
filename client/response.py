"""Data structures and parsers for streamed and non-streamed API responses."""

from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from typing import Any
import json


@dataclass
class TextDelta:
    """A fragment of assistant text emitted by the language model."""

    content: str

    def __str__(self):
        """Return the fragment's text for display and concatenation."""

        return self.content


class StreamEventType(str, Enum):
    """Kinds of events exposed by the LLM client."""

    TEXT_DELTA = "text_delta"
    MESSAGE_COMPLETE = "message_complete"
    ERROR = "error"

    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_DELTA = "tool_call_delta"
    TOOL_CALL_COMPLETE = "tool_call_complete"


@dataclass
class TokenUsage:
    """Token counters reported by a model response."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    cached_tokens: int = 0

    def __add__(self, other: TokenUsage):
        """Combine usage counters from multiple response fragments."""

        return TokenUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
        )


@dataclass
class ToolCallDelta:
    """Incremental tool-call information from a streamed response."""

    call_id: str
    name: str | None = None
    arguments_delta: str = ""


@dataclass
class ToolCall:
    """A complete tool call ready for dispatch."""

    call_id: str
    name: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass
class StreamEvent:
    """Normalized event emitted while processing an API response."""

    type: StreamEventType
    text_delta: TextDelta | None = None
    error: str | None = None
    finish_reason: str | None = None
    tool_call_delta: ToolCallDelta | None = None
    tool_call: ToolCall | None = None
    usage: TokenUsage | None = None


@dataclass
class ToolResultMessage:
    """Tool output formatted for a follow-up model request."""

    tool_call_id: str
    content: str
    is_error: bool = False

    def to_openai_message(self) -> dict[str, Any]:
        """Convert this result to the provider's tool-message shape."""

        # Keep provider-required metadata separate from the tool's text output.
        return {
            "role": "tool",
            "tool_call_id": self.tool_call_id,
            "content": self.content,
        }


def parse_tool_call_arguments(arguments_str: str) -> dict[str, Any]:
    """Decode tool arguments while preserving malformed raw input."""

    if not arguments_str:
        return {}

    try:
        return json.loads(arguments_str)
    except json.JSONDecodeError:
        # Preserve malformed arguments so callers can report or inspect them.
        return {"raw_arguments": arguments_str}
