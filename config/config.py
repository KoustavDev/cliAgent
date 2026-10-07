"""Validated configuration models used by the agent and its integrations."""

from __future__ import annotations
from enum import Enum
import os
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, model_validator
from dotenv import load_dotenv

load_dotenv()



class ModelConfig(BaseModel):
    """Model name and generation limits loaded from environment/configuration."""
    name: str = os.getenv("MODEL_NAME")
    temperature: float = Field(default=1, ge=0.0, le=2.0)
    context_window: int = 256_000


class ShellEnvironmentPolicy(BaseModel):
    """Controls which environment variables are passed to subprocesses."""
    ignore_default_excludes: bool = False
    exclude_patterns: list[str] = Field(
        default_factory=lambda: ["*KEY*", "*TOKEN*", "*SECRET*"]
    )
    set_vars: dict[str, str] = Field(default_factory=dict)


class MCPServerConfig(BaseModel):
    """Connection settings for either a stdio or HTTP/SSE MCP server."""
    enabled: bool = True
    startup_timeout_sec: float = 10

    # stdio transport
    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: Path | None = None

    # http/sse transport
    url: str | None = None

    @model_validator(mode="after")
    def validate_transport(self) -> MCPServerConfig:
        """Ensure exactly one supported transport has been configured."""
        has_command = self.command is not None
        has_url = self.url is not None

        if not has_command and not has_url:
            raise ValueError(
                "MCP Server must have either 'command' (stdio) or 'url' (http/sse)"
            )

        if has_command and has_url:
            raise ValueError(
                "MCP Server cannot have both 'command' (stdio) and 'url' (http/sse)"
            )

        return self


class ApprovalPolicy(str, Enum):
    """Allowed levels of user approval for agent actions."""
    ON_REQUEST = "on-request"
    ON_FAILURE = "on-failure"
    AUTO = "auto"
    AUTO_EDIT = "auto-edut"
    NEVER = "never"
    YOLO = "yolo"


class HookTrigger(str, Enum):
    """Lifecycle events that can invoke a configured hook."""
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"


class HookConfig(BaseModel):
    """Command or script configuration for one lifecycle hook."""
    name: str
    trigger: HookTrigger
    command: str | None = None  # python3 tests.py
    script: str | None = None  # *.sh
    timeout_sec: float = 30
    enabled: bool = True

    @model_validator(mode="after")
    def validate_hook(self) -> HookConfig:
        """Require a runnable command or script for every hook."""
        if not self.command and not self.script:
            raise ValueError("Hook must either have 'command' or 'script'")
        return self


class Config(BaseModel):
    """Complete runtime configuration assembled from defaults and files."""
    model: ModelConfig = Field(default_factory=ModelConfig)
    cwd: Path = Field(default_factory=Path.cwd)
    shell_environment: ShellEnvironmentPolicy = Field(
        default_factory=ShellEnvironmentPolicy
    )
    hooks_enabled: bool = False
    hooks: list[HookConfig] = Field(default_factory=list)
    approval: ApprovalPolicy = ApprovalPolicy.ON_REQUEST
    max_turns: int = Field(default=20, ge=1, le=1000)
    max_prompt_tokens: int = Field(default=50000, ge=1)
    mcp_servers: dict[str, MCPServerConfig] = Field(default_factory=dict)

    allowed_tools: list[str] | None = Field(
        None,
        description="If set, only these tools will be available to the agent",
    )

    developer_instructions: str | None = None
    user_instructions: str | None = None

    debug: bool = False

    @property
    def api_key(self) -> str | None:
        """Return the API key supplied through the process environment."""
        return os.getenv("API_KEY")

    @property
    def base_url(self) -> str | None:
        """Return the optional API endpoint supplied through the environment."""
        return os.getenv("BASE_URL")

    @property
    def model_name(self) -> str:
        """Expose the configured model name as a convenience property."""
        return self.model.name

    @model_name.setter
    def model_name(self, value: str) -> None:
        """Update the configured model name."""
        self.model.name = value

    @property
    def temperature(self) -> float:
        """Expose the configured sampling temperature."""
        return self.model.temperature

    @model_name.setter
    def temperature(self, value: str) -> None:
        """Update the configured sampling temperature."""
        self.model.temperature = value

    def validate(self) -> list[str]:
        """Return actionable validation messages without raising exceptions."""
        errors: list[str] = []

        if not self.api_key:
            errors.append("No API key found. Set API_KEY environment variable")

        if not self.cwd.exists():
            errors.append(f"Working directory does not exist: {self.cwd}")

        return errors

    def to_dict(self) -> dict[str, Any]:
        """Serialize the validated configuration for storage or inspection."""
        return self.model_dump(mode="json")
