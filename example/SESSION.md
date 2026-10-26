# Understanding `agent/session.py`

The [`agent/session.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>) file defines the `Session` class.

`Session` represents one active conversation between the user and the AI agent. It owns the runtime services needed during that conversation:

- The LLM client
- The conversation context
- Built-in and custom tools
- MCP servers
- Approval and safety checks
- Hooks
- Context compression
- Loop detection
- Session identity and statistics

In simple terms:

```text
Config
  |
  v
Session
  |
  +-- LLM client
  +-- conversation context
  +-- tool registry
  +-- MCP manager
  +-- approval manager
  +-- hook system
  +-- loop detector
  +-- session statistics
```

## 1. What is a session?

A session is the in-memory state of one agent run.

It remembers:

- Which configuration is being used
- Which messages have been exchanged
- Which tools are available
- Which MCP servers are connected
- How many agent turns have occurred
- How many tokens have been used
- When the session was created and updated
- Which session ID identifies it

The session is different from the `Agent` class:

| Class     | Main responsibility                           |
| --------- | --------------------------------------------- |
| `Agent`   | Runs the agent loop and coordinates responses |
| `Session` | Owns the state and services used by that loop |

The agent calls services through the session, for example:

```python
self.session.client.chat_completion(...)
self.session.tool_registry.invoke(...)
self.session.context_manager.add_user_message(...)
```

## 2. How a session is created

The [`Agent`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/agent.py>) creates a session when it is constructed:

```python
self.session = Session(self.config)
```

The same `Config` object is passed to the session. This allows every session component to use the application settings consistently.

The session is normally created inside:

```python
async with Agent(self.config) as agent:
    ...
```

The agent initializes the session before processing messages and closes external resources when the context exits.

## 3. What happens in `__init__`

The constructor creates the core session services.

### Store configuration

```python
self.config = config
```

The session keeps the shared configuration so its components can use settings such as:

- Working directory
- Model name
- Approval policy
- MCP server definitions
- Allowed tools
- Hook settings

### Create the LLM client

```python
self.client = LLMClient(config=config)
```

The [`LLMClient`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/client/llm_client.py>) sends chat-completion requests to the configured model.

The session does not directly call the provider. It keeps the client available for the agent loop and context compactor.

### Create the tool registry

```python
self.tool_registry = create_default_registry(config)
```

This initially registers:

- Built-in tools
- Built-in subagent tools

Later, MCP tools and project-specific tools are added to the same registry during initialization.

The registry is used to:

- List available tools
- Generate tool schemas for the model
- Validate tool parameters
- Invoke tools

### Reserve the context manager

```python
self.context_manager: ContextManager | None = None
```

The context manager is not created until `initialize()` runs because it needs:

- Discovered tools
- User memory
- Configuration

Before initialization, `context_manager` is therefore `None`.

### Create custom-tool discovery

```python
self.discovery_manager = ToolDiscoveryManager(
    self.config,
    self.tool_registry,
)
```

The discovery manager searches for project-specific tools in:

```text
<cwd>/.cli-agent/tools
```

It also searches the user configuration directory. Discovered tools are registered into `tool_registry`.

### Create the MCP manager

```python
self.mcp_manager = MCPManager(self.config)
```

The MCP manager reads `config.mcp_servers`, starts configured MCP connections, and makes their tools available to the agent.

### Create the chat compactor

```python
self.chat_compactor = ChatCompactor(self.client)
```

The compactor helps manage long conversations. When the context becomes too large, the agent uses it to summarize older conversation content.

### Create the approval manager

```python
self.approval_manager = ApprovalManager(
    self.config.approval,
    self.config.cwd,
)
```

The approval manager applies the configured safety policy before mutating or dangerous tools run.

Depending on the policy, a tool operation may be:

- Allowed automatically
- Allowed only after failure
- Sent to the user for confirmation
- Rejected

### Create loop detection

```python
self.loop_detector = LoopDetector()
```

The loop detector records agent actions and helps identify repeated behavior, such as repeatedly calling the same tool with the same arguments.

### Create the hook system

```python
self.hook_system = HookSystem(config)
```

The hook system runs configured commands or scripts before and after agent/tool events, such as:

- Before an agent run
- After an agent run
- Before a tool call
- After a tool call
- When an error occurs

### Create session metadata

```python
self.session_id = str(uuid.uuid4())
self.created_at = datetime.now()
self.updated_at = datetime.now()
self.turn_count = 0
```

Every new session receives:

- A unique UUID
- A creation timestamp
- An update timestamp
- A zero turn count

## 4. The `initialize()` lifecycle

The asynchronous `initialize()` method completes setup that may involve external resources:

```python
async def initialize(self) -> None:
```

It runs in this order:

```text
1. Start MCP servers
2. Register MCP tools
3. Discover custom tools
4. Load user memory
5. Create the context manager
```

### Step 1: Initialize MCP

```python
await self.mcp_manager.initialize()
```

Configured MCP servers are started or connected here.

### Step 2: Register MCP tools

```python
self.mcp_manager.register_tools(self.tool_registry)
```

Tools provided by connected MCP servers are added to the same registry as built-in tools.

### Step 3: Discover custom tools

```python
self.discovery_manager.discover_all()
```

This discovers Python tools from:

```text
<session cwd>/.cli-agent/tools
<user config directory>/tools
```

This is why a file such as `.cli-agent/tools/test_tool.py` can become available to the agent.

### Step 4: Load user memory

```python
user_memory=self._load_memory()
```

The session loads saved memory from the application data directory.

### Step 5: Create context

```python
self.context_manager = ContextManager(
    config=self.config,
    user_memory=self._load_memory(),
    tools=self.tool_registry.get_tools(),
)
```

The context manager receives the final tool list, including:

- Built-in tools
- Subagent tools
- MCP tools
- Custom discovered tools

This allows the system prompt to describe the tools that are actually available in this session.

## 5. User memory loading

The `_load_memory()` method reads:

```text
<application data directory>/cli-agent/user_memory.json
```

The data directory is obtained through [`get_data_dir()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/loader.py>).

The expected JSON structure is similar to:

```json
{
  "entries": {
    "preferred_language": "Python",
    "editor": "VS Code"
  }
}
```

The method converts the entries into text for the context:

```text
User preferences and notes:
- preferred_language: Python
- editor: VS Code
```

That text can then be included in the model context.

If the memory file:

- Does not exist
- Has no entries
- Cannot be parsed

the method returns `None`.

The method also creates the data directory if it does not exist:

```python
data_dir.mkdir(parents=True, exist_ok=True)
```

## 6. Tracking agent turns

The `increment_turn()` method updates session activity:

```python
def increment_turn(self) -> int:
    self.turn_count += 1
    self.updated_at = datetime.now()
    return self.turn_count
```

The agent calls it once for each iteration of the agentic loop:

```python
self.session.increment_turn()
```

For example:

```text
User message
  -> Turn 1: model responds or calls a tool
  -> Turn 2: model receives the tool result
  -> Turn 3: model produces a final answer
```

The turn count is also used for statistics and session persistence.

## 7. Session statistics

`get_stats()` returns a summary dictionary:

```python
def get_stats(self) -> dict[str, Any]:
```

The result contains:

| Field           | Meaning                                                       |
| --------------- | ------------------------------------------------------------- |
| `session_id`    | Unique identifier for the session                             |
| `created_at`    | Session creation time                                         |
| `turn_count`    | Number of agent-loop turns                                    |
| `message_count` | Number of messages in context                                 |
| `token_usage`   | Accumulated token usage                                       |
| `tools_count`   | Number of available tools                                     |
| `mcp_servers`   | Number of connected MCP tools/servers exposed by the registry |

The CLI displays this information through the `/stats` command.

## 8. How `Agent` uses the session

The agentic loop depends on the session for almost every operation.

### User messages

```python
self.session.context_manager.add_user_message(message)
```

### Model requests

```python
self.session.client.chat_completion(
    self.session.context_manager.get_messages(),
    tools=tool_schemas,
)
```

### Tool schemas

```python
tool_schemas = self.session.tool_registry.get_schemas()
```

### Tool execution

```python
result = await self.session.tool_registry.invoke(
    tool_call.name,
    tool_call.arguments,
    self.config.cwd,
    self.session.hook_system,
    self.session.approval_manager,
)
```

### Tool results

```python
self.session.context_manager.add_tool_result(
    tool_result.tool_call_id,
    tool_result.content,
)
```

### Context compression

```python
summary, usage = await self.session.chat_compactor.compress(
    self.session.context_manager
)
```

### Loop detection

```python
self.session.loop_detector.record_action(...)
self.session.loop_detector.check_for_loop()
```

The session acts as the central object that connects all these services.

## 9. Session persistence

The session itself is in memory, but its state can be saved by the CLI through [`PersistenceManager`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/persistence.py>).

The CLI creates a `SessionSnapshot` containing values from the session:

```python
SessionSnapshot(
    session_id=self.agent.session.session_id,
    created_at=self.agent.session.created_at,
    updated_at=self.agent.session.updated_at,
    turn_count=self.agent.session.turn_count,
    messages=self.agent.session.context_manager.get_messages(),
    total_usage=self.agent.session.context_manager.total_usage,
)
```

The snapshot can be saved as a session or checkpoint and later used to create a new `Session` with the old conversation restored.

Important distinction:

```text
Session          = live in-memory runtime object
SessionSnapshot  = serializable saved representation
```

When a session is resumed, a new `Session` is created and initialized, then the saved metadata and messages are copied into it.

## 10. Resource cleanup

The session owns resources that must be closed:

- The asynchronous LLM client
- MCP connections

The agent cleans these up when its asynchronous context ends:

```python
await self.session.client.close()
await self.session.mcp_manager.shutdown()
```

This prevents open network connections and background MCP processes from being left behind.

## 11. Why `Session` is useful

Without `Session`, the `Agent` class would need to create and manage every service itself:

- LLM connection
- Context state
- Tools
- MCP
- Hooks
- Approval
- Memory
- Statistics

`Session` keeps those responsibilities together and gives the agent one stable interface:

```python
self.session.client
self.session.context_manager
self.session.tool_registry
self.session.approval_manager
self.session.hook_system
```

This improves organization and makes it possible to:

- Run multiple independent sessions
- Save and restore conversation state
- Test agent behavior with configured services
- Replace individual services without rewriting the agent loop

## 12. Complete lifecycle example

The normal lifecycle looks like this:

```text
CLI loads Config
      |
      v
Agent creates Session
      |
      v
Session.__init__()
      |
      +-- Create LLM client
      +-- Register built-in tools
      +-- Create MCP manager
      +-- Create approval manager
      +-- Create hooks and loop detector
      +-- Assign session ID and timestamps
      |
      v
Session.initialize()
      |
      +-- Connect MCP servers
      +-- Register MCP tools
      +-- Discover .cli-agent/tools
      +-- Load user memory
      +-- Create context manager
      |
      v
Agent processes user messages
      |
      +-- Add messages to context
      +-- Call the model
      +-- Invoke tools
      +-- Track turns and usage
      +-- Compress context when necessary
      |
      v
Save session or close resources
```

## Summary

[`agent/session.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>) defines the runtime container for one cli-agent conversation.

Its main responsibilities are:

```text
Create the agent services
  -> Connect external tools and MCP servers
  -> Discover project tools
  -> Load user memory
  -> Create conversation context
  -> Track turns and statistics
  -> Provide services to Agent
```

The `Session` class does not itself decide what the model should say. Instead, it supplies the state and services that [`Agent`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/agent.py>) needs to run the conversation safely and consistently.
