# Understanding `tools/subagents.py` and `tools/discovery.py`

The files [`tools/subagents.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/subagents.py>) and [`tools/discovery.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/discovery.py>) extend the basic tool system.

They provide two different capabilities:

```text
subagents.py
  Runs a smaller, specialized AI agent for a focused task.

discovery.py
  Finds custom Python tools and loads them dynamically.
```

Together, they make the tool system extensible and capable of delegating specialized work.

## Part 1: `tools/subagents.py`

## 1. What is a subagent?

A subagent is a separate `Agent` instance created to perform a focused task.

Instead of asking the main agent to do every part of a complex task, the main model can call a subagent tool:

```text
Main agent
    |
    v
Calls specialized subagent tool
    |
    v
New Agent with separate configuration and context
    |
    v
Subagent investigates or reviews
    |
    v
Result returns to the main agent
```

The subagent has:

- Its own `Agent` instance
- Its own `Session`
- Its own context manager
- Its own tool registry
- Its own turn limit
- Its own timeout
- Optionally, a restricted tool list

The subagent is not just a helper function. It is a separate agent run inside the main agent's tool execution flow.

## 2. `SubagentParams`

The input schema is:

```python
class SubagentParams(BaseModel):
    goal: str = Field(
        ...,
        description="The specific task or goal for the subagent to accomplish",
    )
```

Every subagent call requires one parameter:

```json
{
  "goal": "Investigate how authentication is implemented"
}
```

The `goal` tells the subagent what to do for this particular invocation.

Pydantic validates this input before execution through the normal tool registry.

## 3. `SubagentDefinition`

`SubagentDefinition` describes a type of subagent:

```python
@dataclass
class SubagentDefinition:
    name: str
    description: str
    goal_prompt: str
    allowed_tools: list[str] | None = None
    max_turns: int = 20
    timeout_seconds: float = 600
```

It contains:

| Field             | Purpose                                   |
| ----------------- | ----------------------------------------- |
| `name`            | Internal name of the specialized subagent |
| `description`     | What the subagent is designed to do       |
| `goal_prompt`     | Its specialist instructions               |
| `allowed_tools`   | Optional list of tools it may use         |
| `max_turns`       | Maximum agent-loop iterations             |
| `timeout_seconds` | Maximum wall-clock execution time         |

The definition is reusable. It describes the subagent type, while `SubagentParams.goal` describes the task for one invocation.

## 4. `SubagentTool`

The main tool wrapper is:

```python
class SubagentTool(Tool):
```

It inherits from the common [`Tool`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>) base class, so the main agent can invoke it like any other tool.

The constructor receives:

```python
def __init__(
    self,
    config: Config,
    definition: SubagentDefinition,
):
```

It stores the definition:

```python
self.definition = definition
```

## 5. Subagent tool name

The tool name is generated dynamically:

```python
@property
def name(self) -> str:
    return f"subagent_{self.definition.name}"
```

For example:

```text
subagent_codebase_investigator
subagent_code_reviewer
```

The `subagent_` prefix allows the prompt builder to recognize these as specialized agents and display them separately from ordinary tools.

## 6. Subagent tool description

The description is also generated:

```python
@property
def description(self) -> str:
    return f"subagent_{self.definition.description}"
```

This description is sent to the model as part of the tool schema and is also included in the system prompt's subagent section.

The current implementation prefixes the description with `subagent_`, so the displayed text may look unusual. The purpose is still to tell the main model what the specialized subagent does.

## 7. Subagents are treated as mutating

`SubagentTool` overrides the base safety classification:

```python
def is_mutating(self, params: dict[str, Any]) -> bool:
    return True
```

This means every subagent call is considered mutating and can go through the approval system.

Even a read-only subagent may be classified this way because it can indirectly use tools, create side effects, or execute operations according to its configuration.

## 8. Executing a subagent

The execution method is:

```python
async def execute(
    self,
    invocation: ToolInvocation,
) -> ToolResult:
```

It performs these steps:

```text
1. Validate the goal
2. Copy the parent configuration
3. Apply the subagent's limits
4. Build a specialist prompt
5. Create a new Agent
6. Stream and monitor subagent events
7. Collect the final response
8. Return a ToolResult to the main agent
```

## 9. Validating the subagent goal

The method parses the invocation:

```python
params = SubagentParams(**invocation.params)
```

Then it checks:

```python
if not params.goal:
    return ToolResult.error_result("No goal specified for sub-agent")
```

The normal registry already performs schema validation, but this explicit check protects the execution method as well.

## 10. Building the subagent configuration

The parent configuration is converted to a dictionary:

```python
config_dict = self.config.to_dict()
```

The subagent then applies its own turn limit:

```python
config_dict["max_turns"] = self.definition.max_turns
```

If the definition restricts tools, that restriction is applied:

```python
if self.definition.allowed_tools:
    config_dict["allowed_tools"] = self.definition.allowed_tools
```

Finally, a new configuration object is created:

```python
subagent_config = Config(**config_dict)
```

This gives the subagent a configuration derived from the parent, while allowing the definition to make it more focused and constrained.

## 11. Building the specialist prompt

The subagent receives a prompt containing:

```text
You are a specialized sub-agent with a specific task to complete.

[specialist goal prompt]

YOUR TASK:
[invocation goal]

IMPORTANT:
- Focus only on completing the specified task
- Do not engage in unrelated actions
- Once complete, provide a final response
- Be concise and direct
```

There are two instruction layers:

### `goal_prompt`

Defines the subagent's role.

For example:

```text
You are a codebase investigation specialist.
Use read_file, grep, glob, and list_dir.
Do NOT modify files.
```

### `params.goal`

Defines the current task:

```text
Investigate how authentication is implemented.
```

This allows one subagent definition to handle many different goals.

## 12. Running the nested agent

The subagent is run inside an asynchronous agent context:

```python
async with Agent(subagent_config) as agent:
```

This creates and initializes a completely separate agent session.

That session discovers its own:

- Built-in tools
- Allowed custom tools
- MCP tools
- Context
- Hooks

The subagent starts by running:

```python
async for event in agent.run(prompt):
```

## 13. Subagent timeout

The definition specifies a wall-clock timeout:

```python
deadline = (
    asyncio.get_event_loop().time()
    + self.definition.timeout_seconds
)
```

During event processing, the current time is checked:

```python
if asyncio.get_event_loop().time() > deadline:
    terminate_response = "timeout"
    final_response = "Sub-agent timed out"
    break
```

This prevents the nested agent from running forever.

The timeout is checked while events are being received. It is separate from the subagent's `max_turns` limit.

## 14. Collecting subagent events

The wrapper records tool names:

```python
if event.type == AgentEventType.TOOL_CALL_START:
    tool_calls.append(event.data.get("name"))
```

It records text responses:

```python
elif event.type == AgentEventType.TEXT_COMPLETE:
    final_response = event.data.get("content")
```

It also handles the end event:

```python
elif event.type == AgentEventType.AGENT_END:
    if final_response is None:
        final_response = event.data.get("response")
```

If the nested agent reports an error:

```python
elif event.type == AgentEventType.AGENT_ERROR:
    terminate_response = "error"
    error = event.data.get("error", "Unknown")
    final_response = f"Sub-agent error: {error}"
    break
```

The main agent does not receive every nested event directly. The wrapper summarizes the subagent run into one tool result.

## 15. Subagent result

After the nested agent finishes, the wrapper builds:

```text
Sub-agent '<name>' completed.
Termination: <goal, timeout, or error>
Tools called: <tool names>

Result:
<final response>
```

If an error occurred, it returns:

```python
ToolResult.error_result(result)
```

Otherwise, it returns:

```python
ToolResult.success_result(result)
```

The main agent receives this output as the result of the subagent tool call and can use it in its own reasoning.

## 16. Built-in subagent definitions

The file defines two default subagents.

### Codebase investigator

```python
CODEBASE_INVESTIGATOR = SubagentDefinition(...)
```

Its tool name is:

```text
subagent_codebase_investigator
```

Its purpose is to investigate code structure, patterns, and implementations.

It is allowed to use:

```text
read_file
grep
glob
list_dir
```

It has the default:

```text
max_turns = 20
timeout_seconds = 600
```

It is explicitly instructed not to modify files.

### Code reviewer

```python
CODE_REVIEWER = SubagentDefinition(...)
```

Its tool name is:

```text
subagent_code_reviewer
```

Its purpose is to review changes and identify:

- Bugs
- Code smells
- Security issues
- Improvement opportunities

It is allowed to use:

```text
read_file
grep
list_dir
```

It has tighter limits:

```text
max_turns = 10
timeout_seconds = 300
```

It is also instructed not to modify files.

## 17. Returning default definitions

The factory function is:

```python
def get_default_subagent_definitions() -> list[SubagentDefinition]:
```

It returns:

```python
[
    CODEBASE_INVESTIGATOR,
    CODE_REVIEWER,
]
```

The registry uses this function in [`create_default_registry()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>):

```python
for subagent_def in get_default_subagent_definitions():
    registry.register(SubagentTool(config, subagent_def))
```

Therefore, subagent tools are available when the session's default registry is created.

## 18. How subagents appear to the main model

The main model sees subagents as ordinary tool definitions, for example:

```text
subagent_codebase_investigator
subagent_code_reviewer
```

The prompt builder recognizes the `subagent_` prefix and places them in a separate section:

```text
## Sub-Agents
```

The model can then choose to delegate a focused task:

```json
{
  "name": "subagent_codebase_investigator",
  "arguments": {
    "goal": "Find where configuration is loaded and explain its precedence."
  }
}
```

## 19. Subagent lifecycle

The complete lifecycle is:

```text
Main model requests subagent tool
          |
          v
ToolRegistry validates goal
          |
          v
Approval manager checks subagent operation
          |
          v
SubagentTool creates derived Config
          |
          v
SubagentTool creates nested Agent
          |
          v
Nested Agent creates Session
          |
          v
Subagent performs its focused work
          |
          v
Subagent result is collected
          |
          v
ToolResult returns to main agent
```

## Part 2: `tools/discovery.py`

## 20. What is tool discovery?

Tool discovery allows the application to find Python files containing custom tool classes without hard-coding every tool import.

Instead of changing the main registry for each project-specific tool, a project can place a file in:

```text
<working directory>/.cli-agent/tools/
```

The discovery manager finds the file, imports it, identifies `Tool` subclasses, creates instances, and registers them.

The flow is:

```text
.cli-agent/tools/*.py
          |
          v
Load Python module dynamically
          |
          v
Find classes inheriting from Tool
          |
          v
Instantiate classes with Config
          |
          v
Register in ToolRegistry
```

## 21. `ToolDiscoveryManager`

The main class is:

```python
class ToolDiscoveryManager:
```

It receives:

```python
def __init__(
    self,
    config: Config,
    registry: ToolRegistry,
):
```

It stores:

```python
self.config = config
self.registry = registry
```

The discovery manager needs both:

- `Config` to construct tool instances
- `ToolRegistry` to register discovered tools

## 22. Where discovery runs

The session creates the manager:

```python
self.discovery_manager = ToolDiscoveryManager(
    self.config,
    self.tool_registry,
)
```

Then `Session.initialize()` calls:

```python
self.discovery_manager.discover_all()
```

This occurs after MCP initialization and before the context manager is created.

That order ensures the final tool list can be passed into the system prompt.

## 23. Discovery locations

`discover_all()` searches two locations:

```python
def discover_all(self) -> None:
    self.discover_from_directory(self.config.cwd)
    self.discover_from_directory(get_config_dir())
```

The first location is project-specific:

```text
<config.cwd>/.cli-agent/tools/
```

The second location is the user-level configuration directory:

```text
<user config directory>/cli-agent/tools/
```

This supports both:

- Tools shared by one project
- Tools shared across projects for the current user

## 24. Searching a directory

The method:

```python
def discover_from_directory(self, directory: Path) -> None:
```

builds:

```python
tool_dir = directory / ".cli-agent" / "tools"
```

If the directory does not exist or is not a directory, discovery stops quietly:

```python
if not tool_dir.exists() or not tool_dir.is_dir():
    return
```

It then scans:

```python
for py_file in tool_dir.glob("*.py"):
```

Only Python files directly in the tools directory are considered. The current implementation does not recursively search subdirectories.

## 25. Ignoring special Python files

Files whose names start with `__` are skipped:

```python
if py_file.name.startswith("__"):
    continue
```

This prevents files such as:

```text
__init__.py
```

from being treated as custom tool modules.

## 26. Dynamic module loading

The `_load_tool_modules()` method imports a file by path:

```python
def _load_tool_modules(self, file_path: Path) -> Any:
```

It creates a generated module name:

```python
module_name = f"discovered_tool_{file_path.stem}"
```

For example:

```text
test_tool.py
```

becomes a module named:

```text
discovered_tool_test_tool
```

It then creates an import specification:

```python
spec = importlib.util.spec_from_file_location(
    module_name,
    file_path,
)
```

If the specification or loader cannot be created, it returns an `ImportError` object.

Otherwise it:

1. Creates a module object
2. Stores it in `sys.modules`
3. Executes the file
4. Returns the loaded module

```python
module = importlib.util.module_from_spec(spec)
sys.modules[module_name] = module
spec.loader.exec_module(module)
return module
```

This lets the application load custom tools without a normal package import.

## 27. Finding tool classes

The `_find_tool_classes()` method searches a loaded module:

```python
def _find_tool_classes(self, module: Any) -> list[Tool]:
```

It examines every module attribute:

```python
for name in dir(module):
    obj = getattr(module, name)
```

It accepts a class only if:

```python
inspect.isclass(obj)
and issubclass(obj, Tool)
and obj is not Tool
and obj.__module__ == module.__name__
```

These checks mean:

1. The object must be a class
2. It must inherit from `Tool`
3. It cannot be the base `Tool` class itself
4. It must be defined in the discovered module

The `__module__` check prevents imported tool classes from being accidentally registered again.

## 28. Instantiating and registering custom tools

After classes are found:

```python
for tool_class in tool_classes:
    tool = tool_class(self.config)
    self.registry.register(tool)
```

Every discovered class must therefore support the base constructor:

```python
def __init__(self, config: Config):
```

If a custom tool uses the inherited constructor, it automatically receives `config`.

The registry then makes the tool available to:

- The system prompt
- The model's structured tool schemas
- The `/tools` CLI command
- The agent invocation path

## 29. Example discovered tool

A file such as:

```text
project/.cli-agent/tools/test_tool.py
```

may contain:

```python
from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class TestToolParams(BaseModel):
    message: str = Field(..., description="The message to echo back")


class TestTool(Tool):
    name = "test_tool"
    description = "Echo a message."
    kind = ToolKind.READ
    schema = TestToolParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = TestToolParams(**invocation.params)
        return ToolResult.success_result(params.message)
```

When discovery runs:

```text
1. `test_tool.py` is imported
2. `TestTool` is identified as a Tool subclass
3. `TestTool(self.config)` is created
4. It is registered under `test_tool`
5. The model can request it
```

## 30. Discovery error behavior

Each Python file is handled inside:

```python
try:
    ...
except Exception:
    continue
```

If a module:

- Has a syntax error
- Has a missing import
- Defines an invalid tool
- Fails during class construction
- Raises during registration

the file is skipped and discovery continues with the next file.

This prevents one broken optional custom tool from stopping application startup.

However, the current implementation does not log the exception, so diagnosing a skipped tool may be difficult.

## 31. Discovery and tool-name conflicts

Discovered tools are registered using the normal registry:

```python
self.registry.register(tool)
```

If a discovered tool has the same name as an existing regular tool, the registry logs a warning and overwrites the previous entry.

Therefore, custom tools should use unique names to avoid replacing:

- Built-in tools
- Subagent tools
- Other project tools

MCP tools are stored separately, but duplicate lookup names can still make behavior confusing.

## 32. Discovery security considerations

Dynamic discovery executes Python files found in the configured tool directories:

```python
spec.loader.exec_module(module)
```

Importing a Python module executes its top-level code.

Therefore, only trusted files should be placed in:

```text
.cli-agent/tools/
```

A custom tool can access the same environment and application capabilities as other Python code. Discovery is an extensibility feature, not a sandbox.

## 33. Discovery versus subagents

These features solve different problems:

| Feature   | Purpose                                     |
| --------- | ------------------------------------------- |
| Subagents | Delegate a focused task to another AI agent |
| Discovery | Load custom Python tool implementations     |

They can work together. A discovered tool could perform a project-specific operation, and a subagent could be configured with access to selected tools.

## 34. Complete startup flow

The relevant session startup sequence is:

```text
Session.__init__()
      |
      v
Create default registry
      |
      +-- Register built-in tools
      +-- Register default subagent tools
      |
      v
Session.initialize()
      |
      +-- Start MCP servers
      +-- Register MCP tools
      +-- Discover project tools
      +-- Discover user-level tools
      +-- Create ContextManager
      |
      v
System prompt and schemas include final tool list
```

## 35. Complete subagent call flow

```text
Main model chooses subagent tool
        |
        v
ToolRegistry validates `goal`
        |
        v
Approval checks the subagent call
        |
        v
SubagentTool builds derived Config
        |
        v
Nested Agent runs with focused prompt
        |
        v
Nested tools are called
        |
        v
Nested response is collected
        |
        v
Main tool call receives ToolResult
```

## 36. Why these files are useful

Without `subagents.py`, the main agent would have to perform all specialized work itself.

Without `discovery.py`, every custom project tool would need to be manually imported and added to the registry.

Together they provide:

- Delegated specialist reasoning
- Project-specific extensibility
- User-level reusable tools
- Controlled subagent limits
- Dynamic tool registration
- A single registry interface for the main agent

## Summary

[`tools/subagents.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/subagents.py>) creates specialized nested agents:

```text
Define specialist
  -> Restrict tools and turns
  -> Run a nested Agent
  -> Collect its response
  -> Return it as a ToolResult
```

[`tools/discovery.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/discovery.py>) loads custom tool classes dynamically:

```text
Search .cli-agent/tools
  -> Import Python modules
  -> Find Tool subclasses
  -> Instantiate them with Config
  -> Register them in ToolRegistry
```

In short:

> `subagents.py` adds specialized AI workers, while `discovery.py` adds custom executable tools. Both integrate with the common `Tool` and `ToolRegistry` architecture.
