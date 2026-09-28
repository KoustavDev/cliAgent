# Understanding the MCP Tools

The [`tools/mcp/`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp>) package connects this AI agent to external **Model Context Protocol (MCP) servers**.

MCP is a protocol that allows an external server to expose tools to an AI application.

Instead of implementing every capability inside this project, the agent can connect to an MCP server that provides tools such as:

- File-system operations
- Database queries
- GitHub operations
- Browser automation
- Cloud services
- Internal company systems

The local application discovers those remote tools, wraps them in the project's common `Tool` interface, and exposes them to the model alongside built-in tools.

The flow is:

```text
MCP configuration
        |
        v
MCPManager creates MCPClient
        |
        v
MCPClient connects to external server
        |
        v
Server lists its tools
        |
        v
MCPManager creates MCPTool wrappers
        |
        v
ToolRegistry registers the wrappers
        |
        v
Model can call MCP tools
```

The package contains three modules:

| File | Responsibility |
|---|---|
| [`client.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/client.py>) | Connects to one MCP server and calls its tools |
| [`mcp_manager.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/mcp_manager.py>) | Manages multiple MCP clients and registers their tools |
| [`mcp_tool.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/mcp_tool.py>) | Adapts a remote MCP tool to the local `Tool` interface |

## 1. What is an MCP server?

An MCP server is an external process or service that implements the Model Context Protocol.

The server owns the actual capability. For example:

```text
Local AI agent
       |
       | MCP protocol
       v
Filesystem MCP server
       |
       v
Reads or writes files
```

The local agent does not need to know the server's internal implementation. It only needs:

- How to connect
- Which tools the server exposes
- The input schema for each tool
- How to send a tool call
- How to read the result

## 2. MCP configuration

MCP server definitions are represented by [`MCPServerConfig`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>):

```python
class MCPServerConfig(BaseModel):
    enabled: bool = True
    startup_timeout_sec: float = 10

    command: str | None = None
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    cwd: Path | None = None

    url: str | None = None
```

Each configured server must use exactly one transport:

```text
stdio: command + args
HTTP/SSE: url
```

The configuration validator rejects:

- A server with neither `command` nor `url`
- A server with both `command` and `url`

## 3. Example stdio configuration

A local MCP server can be configured in `.ai-agent/config.toml`:

```toml
[mcp_servers.filesystem]
enabled = true
startup_timeout_sec = 10
command = "npx"
args = [
  "-y",
  "@modelcontextprotocol/server-filesystem",
  "C:/projects/my-app"
]
```

This means:

```text
Server name: filesystem
Command: npx
Arguments:
  - -y
  - @modelcontextprotocol/server-filesystem
  - C:/projects/my-app
```

The application starts the command and communicates with it through stdio.

## 4. Example HTTP/SSE configuration

An MCP server can also be remote:

```toml
[mcp_servers.remote_tools]
enabled = true
startup_timeout_sec = 15
url = "http://localhost:8000/sse"
```

The agent uses the configured URL with an SSE transport.

Do not configure both:

```toml
command = "..."
url = "..."
```

The configuration model explicitly rejects that combination.

# `client.py`

## 5. `MCPServerStatus`

[`tools/mcp/client.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/client.py>) defines the server status enum:

```python
class MCPServerStatus(str, Enum):
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"
```

The status describes the lifecycle of one MCP connection:

```text
DISCONNECTED
      |
      v
CONNECTING
      |
      +--> CONNECTED
      |
      +--> ERROR
```

The CLI uses this status when displaying:

```text
/mcp
```

## 6. `MCPToolInfo`

The `MCPToolInfo` dataclass stores the description of one remote tool:

```python
@dataclass
class MCPToolInfo:
    name: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    server_name: str = ""
```

It contains:

| Field | Meaning |
|---|---|
| `name` | Tool name as advertised by the MCP server |
| `description` | Tool description from the server |
| `input_schema` | JSON schema for tool arguments |
| `server_name` | Name of the connected MCP server |

The information is obtained from the server during connection.

## 7. `MCPClient`

`MCPClient` manages one configured MCP server:

```python
class MCPClient:
```

It receives:

```python
def __init__(
    self,
    name: str,
    config: MCPServerConfig,
    cwd: Path,
) -> None:
```

It stores:

```python
self.name = name
self.config = config
self.cwd = cwd
self.status = MCPServerStatus.DISCONNECTED
self._client: Client | None = None
self._tools: dict[str, MCPToolInfo] = {}
```

Each client is responsible for:

- Creating the transport
- Connecting to the server
- Listing remote tools
- Calling remote tools
- Disconnecting cleanly

## 8. Listing tools on a client

The `tools` property returns the tools discovered from the server:

```python
@property
def tools(self) -> list[MCPToolInfo]:
    return list(self._tools.values())
```

The internal dictionary prevents duplicate tool names from the same server and gives quick lookup by name.

## 9. Creating a transport

The `_create_transport()` method selects the transport based on configuration:

```python
def _create_transport(self) -> StdioTransport | SSETransport:
```

### Stdio transport

If `config.command` exists:

```python
env = os.environ.copy()
env.update(self.config.env)

return StdioTransport(
    command=self.config.command,
    args=list(self.config.args),
    env=env,
    cwd=str(self.config.cwd or self.cwd),
    log_file=Path(os.devnull),
)
```

The MCP server runs as a local subprocess.

The environment starts as a copy of the current environment and then applies server-specific overrides from `config.env`.

The working directory is:

1. `MCPServerConfig.cwd`, if configured
2. Otherwise, the agent's configured `cwd`

### SSE transport

If no command is configured, the client creates:

```python
SSETransport(url=self.config.url)
```

This connects to the remote HTTP/SSE endpoint.

## 10. Connecting to an MCP server

The `connect()` method is:

```python
async def connect(self) -> None:
```

If already connected, it returns immediately:

```python
if self.status == MCPServerStatus.CONNECTED:
    return
```

Otherwise it changes status:

```python
self.status = MCPServerStatus.CONNECTING
```

Then it:

1. Creates the transport
2. Creates a FastMCP `Client`
3. Enters the client's async context
4. Requests the server's tools
5. Converts tool descriptions into `MCPToolInfo`
6. Marks the client as connected

```python
self._client = Client(transport=self._create_transport())
await self._client.__aenter__()
tool_result = await self._client.list_tools()
```

For each remote tool:

```python
self._tools[tool.name] = MCPToolInfo(
    name=tool.name,
    description=tool.description or "",
    input_schema=tool.inputSchema if hasattr(tool, "inputSchema") else {},
    server_name=self.name,
)
```

If any step fails:

```python
self.status = MCPServerStatus.ERROR
raise
```

The manager can then report the server as failed while allowing other servers to continue.

## 11. Connecting with a timeout

`MCPManager.initialize()` wraps each connection:

```python
asyncio.wait_for(
    client.connect(),
    timeout=client.config.startup_timeout_sec,
)
```

For example:

```toml
startup_timeout_sec = 10
```

means the application will wait up to 10 seconds for that server to connect.

## 12. Disconnecting from a server

The `disconnect()` method:

```python
async def disconnect(self) -> None:
```

It:

1. Leaves the FastMCP client context
2. Clears the client reference
3. Clears discovered tools
4. Sets status to `DISCONNECTED`

```python
if self._client:
    await self._client.__aexit__(None, None, None)
    self._client = None

self._tools.clear()
self.status = MCPServerStatus.DISCONNECTED
```

This is used when the agent shuts down or replaces a session.

## 13. Calling a remote MCP tool

The `call_tool()` method is:

```python
async def call_tool(
    self,
    tool_name: str,
    arguments: dict[str, Any],
):
```

It first checks the connection:

```python
if not self._client or self.status != MCPServerStatus.CONNECTED:
    raise RuntimeError(f"Not connected to server {self.name}")
```

Then it forwards the call:

```python
result = await self._client.call_tool(tool_name, arguments)
```

MCP results may contain several content items. The client collects text:

```python
output = []
for item in result.content:
    if hasattr(item, "text"):
        output.append(item.text)
    else:
        output.append(str(item))
```

It returns a normalized dictionary:

```python
{
    "output": "\n".join(output),
    "is_error": result.is_error,
}
```

This keeps the rest of the local tool system independent from the exact FastMCP result object.

# `mcp_manager.py`

## 14. `MCPManager`

[`tools/mcp/mcp_manager.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/mcp_manager.py>) manages all configured MCP servers:

```python
class MCPManager:
```

It stores:

```python
self._clients: dict[str, MCPClient] = {}
self._initialized = False
```

The dictionary key is the configured server name:

```toml
[mcp_servers.filesystem]
```

Here, the server name is `filesystem`.

## 15. Initializing all MCP servers

The `initialize()` method is:

```python
async def initialize(self) -> None:
```

It avoids repeating initialization:

```python
if self._initialized:
    return
```

It reads:

```python
mcp_configs = self.config.mcp_servers
```

If no servers are configured, it returns without creating clients.

## 16. Creating clients for enabled servers

For each configured server:

```python
for name, server_config in mcp_configs.items():
    if not server_config.enabled:
        continue

    self._clients[name] = MCPClient(
        name=name,
        config=server_config,
        cwd=self.config.cwd,
    )
```

Disabled servers are skipped.

For example:

```toml
[mcp_servers.database]
enabled = false
command = "..."
```

will not create or start a client.

## 17. Connecting in parallel

The manager builds one connection task per client:

```python
connection_tasks = [
    asyncio.wait_for(
        client.connect(),
        timeout=client.config.startup_timeout_sec,
    )
    for name, client in self._clients.items()
]
```

Then it runs them concurrently:

```python
await asyncio.gather(*connection_tasks, return_exceptions=True)
```

This means one slow or failed server does not necessarily block all other configured servers.

The manager marks initialization complete:

```python
self._initialized = True
```

## 18. Registering MCP tools

After clients connect, the session calls:

```python
self.mcp_manager.register_tools(self.tool_registry)
```

The manager's `register_tools()` method:

```python
def register_tools(self, registry: ToolRegistry) -> int:
```

It:

1. Iterates through all MCP clients
2. Skips clients that are not connected
3. Iterates through each client's discovered tools
4. Creates an `MCPTool` wrapper
5. Registers it in the registry
6. Returns the number of registered tools

The wrapper name is:

```python
name=f"{client.name}__{tool_info.name}"
```

For example:

```text
Server: filesystem
Remote tool: read_file
Local wrapper name: filesystem__read_file
```

The prefix prevents collisions when two MCP servers expose tools with the same remote name.

## 19. Shutting down MCP servers

The `shutdown()` method:

```python
async def shutdown(self) -> None:
```

It disconnects every client concurrently:

```python
disconnection_tasks = [
    client.disconnect()
    for client in self._clients.values()
]

await asyncio.gather(
    *disconnection_tasks,
    return_exceptions=True,
)
```

Then it clears the client registry and resets initialization:

```python
self._clients.clear()
self._initialized = False
```

This is part of agent cleanup.

## 20. Server status reporting

The `get_all_servers()` method returns a UI-friendly summary:

```python
def get_all_servers(self) -> list[dict[str, Any]]:
```

Example output:

```python
[
    {
        "name": "filesystem",
        "status": "connected",
        "tools": 5,
    }
]
```

The CLI displays this with:

```text
/mcp
```

Example:

```text
MCP Servers (1)
  • filesystem: connected (5 tools)
```

# `mcp_tool.py`

## 21. `MCPTool`

[`tools/mcp/mcp_tool.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/mcp/mcp_tool.py>) adapts one remote MCP tool to the local [`Tool`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>) interface.

This adapter is important because the rest of the application already knows how to work with `Tool` objects.

Instead of adding special MCP logic to:

- The agent loop
- The tool registry
- The approval system
- The hooks
- The context manager

the project wraps each remote tool as a normal local tool.

The adapter stores:

```python
self._tool_info = tool_info
self._client = client
self.name = name
self.description = self._tool_info.description
```

## 22. MCP tool schema

The `schema` property converts the remote input schema:

```python
@property
def schema(self) -> dict[str, Any]:
```

It returns:

```python
{
    "type": "object",
    "properties": input_schema.get("properties", {}),
    "required": input_schema.get("required", []),
}
```

This allows the local registry to call `to_openai_schema()` and expose the remote tool's parameters to the language model.

For example, an MCP server may advertise:

```json
{
  "properties": {
    "path": {"type": "string"}
  },
  "required": ["path"]
}
```

The local model sees the same parameter requirements through the wrapper.

## 23. MCP tool category and approval

`MCPTool` is classified as:

```python
kind = ToolKind.MCP
```

It also overrides:

```python
def is_mutating(self, params) -> bool:
    return True
```

Therefore every MCP call is treated as mutating and can require approval.

This is conservative because the local agent cannot reliably infer whether an arbitrary remote tool:

- Changes files
- Sends network requests
- Modifies a database
- Deletes data
- Performs a read-only operation

The remote server owns the tool implementation, so the local wrapper defaults to requiring safety review.

## 24. Executing an MCP tool

The adapter's `execute()` method is:

```python
async def execute(
    self,
    invocation: ToolInvocation,
) -> ToolResult:
```

It forwards the original remote tool name and arguments:

```python
result = await self._client.call_tool(
    self._tool_info.name,
    invocation.params,
)
```

If the remote result reports an error:

```python
if is_error:
    return ToolResult.error_result(output)
```

Otherwise:

```python
return ToolResult.success_result(output)
```

Unexpected failures are converted into:

```python
ToolResult.error_result(f"MCP tool failed: {e}")
```

The main agent therefore receives the same `ToolResult` shape for built-in and MCP tools.

# Complete MCP lifecycle

## 25. Startup lifecycle

The full startup path is:

```text
Application loads Config
        |
        v
Session creates MCPManager
        |
        v
Session.initialize()
        |
        v
MCPManager.initialize()
        |
        v
Create enabled MCPClient objects
        |
        v
Connect clients concurrently
        |
        v
Each client calls list_tools()
        |
        v
MCPToolInfo objects are created
        |
        v
MCPManager.register_tools()
        |
        v
MCPTool wrappers enter ToolRegistry
        |
        v
ContextManager builds a prompt with the final tool list
```

## 26. Tool-call lifecycle

Suppose the model chooses:

```text
filesystem__read_file
```

The call proceeds as:

```text
Model requests filesystem__read_file
        |
        v
ToolRegistry finds MCPTool wrapper
        |
        v
Parameters are validated against remote schema
        |
        v
before_tool hooks run
        |
        v
Approval manager checks the MCP operation
        |
        v
MCPTool.execute()
        |
        v
MCPClient.call_tool("read_file", arguments)
        |
        v
FastMCP sends request to external server
        |
        v
Remote result is normalized
        |
        v
ToolResult returns to the agent
        |
        v
after_tool hooks run
```

## 27. Example end-to-end configuration

Configuration:

```toml
[mcp_servers.filesystem]
enabled = true
startup_timeout_sec = 10
command = "npx"
args = [
  "-y",
  "@modelcontextprotocol/server-filesystem",
  "C:/projects/demo"
]
```

Suppose the server advertises:

```text
read_file
write_file
list_directory
```

The local manager creates wrappers:

```text
filesystem__read_file
filesystem__write_file
filesystem__list_directory
```

The model may request:

```json
{
  "name": "filesystem__read_file",
  "arguments": {
    "path": "README.md"
  }
}
```

The local wrapper removes the server prefix when forwarding:

```python
client.call_tool(
    "read_file",
    {"path": "README.md"},
)
```

The external server returns content, and the wrapper returns it as a local `ToolResult`.

## 28. MCP tools versus built-in tools

| Built-in tool | MCP tool |
|---|---|
| Implemented in this repository | Implemented by an external server |
| Direct Python execution | Protocol request to a remote/local server |
| Schema defined locally | Schema discovered from the server |
| Registered by default registry | Registered after MCP connection |
| Usually has a known safety behavior | Conservatively treated as mutating |
| Fails inside local implementation | Can fail due to connection or remote server |

The adapter hides most of this difference from the rest of the application.

## 29. Error and failure behavior

MCP failures can happen during:

- Transport creation
- Server startup
- Connection setup
- Tool discovery
- Remote tool execution
- Shutdown

During initialization:

```python
await asyncio.gather(*connection_tasks, return_exceptions=True)
```

means individual connection failures are collected rather than immediately aborting all server initialization.

A failed server remains in an error state and its tools are not registered because `register_tools()` only accepts connected clients.

During execution, `MCPTool.execute()` converts failures into a `ToolResult` error.

## 30. Current implementation notes

1. The `tools/mcp` directory contains three Python modules and no `__init__.py` file in the current workspace. Python namespace-package behavior allows the imports to work.

2. The current `.ai-agent/config.toml` contains two filesystem servers. The second uses a package name ending in `222222222222`, which is likely invalid and may remain disconnected.

3. `MCPClient._create_transport()` assumes that a configuration without `command` has a valid `url`. `MCPServerConfig` validation is intended to guarantee this.

4. `MCPManager.initialize()` sets `_initialized = True` even when one or more connection tasks fail. A later initialize call will not retry failed servers unless the manager is shut down first.

5. MCP tools are always marked mutating in `MCPTool.is_mutating()`, even if the remote operation is read-only. This is a conservative safety choice.

6. Tool names are prefixed with the server name when registered locally, which prevents common-name collisions between servers.

7. The MCP client normalizes only textual result content. Non-text content is converted with `str(item)`.

## Summary

The MCP package extends the agent with tools supplied by external servers:

```text
MCPServerConfig
  -> MCPClient connects to one server
  -> MCPClient discovers remote tools
  -> MCPManager manages all clients
  -> MCPTool wraps each remote tool
  -> ToolRegistry exposes them to the model
```

In short:

> `client.py` handles one MCP connection, `mcp_manager.py` coordinates all configured servers, and `mcp_tool.py` makes each remote capability look like a normal local tool.
