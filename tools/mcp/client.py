"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
from dataclasses import dataclass, field
from enum import Enum
import os
from pathlib import Path
from typing import Any
from config.config import MCPServerConfig
from fastmcp import Client
from fastmcp.client.transports import SSETransport, StdioTransport
from utils.environment import normalize_process_environment


class MCPServerStatus(str, Enum):
    """Represent mcpserverstatus state and behavior."""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


@dataclass
class MCPToolInfo:

    """Represent mcptoolinfo state and behavior."""
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""


class MCPClient:
    """Represent mcpclient state and behavior."""
    def __init__(
        self,
        name: str,
        config: MCPServerConfig,
        cwd: Path,
    ) -> None:
        """Initialize the object with the configuration needed by later steps."""
        self.name = name
        self.config = config
        self.cwd = cwd
        self.status = MCPServerStatus.DISCONNECTED
        self._client: Client | None = None

        self._tools: dict[str, MCPToolInfo] = dict()

    @property
    def tools(self) -> list[MCPToolInfo]:
        """Perform the tools operation."""
        return list(self._tools.values())

    def _create_transport(self) -> StdioTransport | SSETransport:
        # Step 1: Build the configured stdio or SSE transport.
        """Support the create transport step used by the public workflow."""
        if self.config.command:
            env = normalize_process_environment(os.environ)
            env.update(normalize_process_environment(self.config.env))

            return StdioTransport(
                command=self.config.command,
                args=list(self.config.args),
                env=env,
                cwd=str(self.config.cwd or self.cwd),
                log_file=Path(os.devnull),
            )
        else:
            return SSETransport(url=self.config.url)

    async def connect(self) -> None:
        # Step 1: Open the server connection and cache its advertised tools.
        """Perform the connect operation and return its result."""
        if self.status == MCPServerStatus.CONNECTED:
            return

        self.status = MCPServerStatus.CONNECTING

        try:
            self._client = Client(transport=self._create_transport())

            # The context manager performs the MCP handshake before discovery.
            await self._client.__aenter__()

            tool_result = await self._client.list_tools()
            for tool in tool_result:
                self._tools[tool.name] = MCPToolInfo(
                    name=tool.name,
                    description=tool.description or "",
                    input_schema=(
                        tool.input_schema if hasattr(tool, "input_schema") else {}
                    ),
                    server_name=self.name,
                )

            self.status = MCPServerStatus.CONNECTED
        except Exception:
            self.status = MCPServerStatus.ERROR
            raise

    async def disconnect(self) -> None:
        # Step 1: Close the transport and clear server metadata.
        """Perform the disconnect operation and return its result."""
        if self._client:
            # Closing the context releases stdio children and network sockets.
            await self._client.__aexit__(None, None, None)
            self._client = None

        self._tools.clear()
        self.status = MCPServerStatus.DISCONNECTED

    async def call_tool(self, tool_name: str, arguments: dict[str, Any]):
        # Step 1: Invoke the remote tool, then flatten content into text output.
        """Perform the call tool operation and return its result."""
        if not self._client or self.status != MCPServerStatus.CONNECTED:
            raise RuntimeError(f"Not connected to server {self.name}")

        # Keep remote invocation inside this client's lifecycle boundary.
        result = await self._client.call_tool(tool_name, arguments)

        output = []
        for item in result.content:
            if hasattr(item, "text"):
                output.append(item.text)
            else:
                output.append(str(item))

        return {
            "output": "\n".join(output),
            "is_error": result.is_error,
        }
