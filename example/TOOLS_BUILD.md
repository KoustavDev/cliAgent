# Understanding `tools/base.py` and `tools/registry.py`

The files [`tools/base.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>) and [`tools/registry.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>) form the foundation of the tool system.

They answer two important questions:

```text
base.py
  What does a tool look like?

registry.py
  How are tools found, listed, validated, approved, and executed?
```

The complete tool flow is:

```text
Tool implementation
        |
        v
Tool base contract
        |
        v
ToolRegistry registers it
        |
        v
Model receives its schema
        |
        v
Model requests a tool call
        |
        v
Registry validates and checks approval
        |
        v
Tool executes
        |
        v
ToolResult returns to the model
```

## 1. What is a tool?

A tool is an operation the AI agent can request, such as:

- Reading a file
- Searching a project
- Writing or editing a file
- Running a shell command
- Storing memory
- Managing todos
- Calling an MCP server
- Delegating work to a subagent

Tools are not arbitrary functions. Each tool has:

- A name
- A description
- An input schema
- A category
- An execution method
- A standard result format

The `Tool` base class in `base.py` defines this common contract.

## 2. `ToolKind`

`ToolKind` categorizes tools:

```python
class ToolKind(str, Enum):
    READ = "read"
    WRITE = "write"
    SHELL = "shell"
    NETWORK = "network"
    MEMORY = "memory"
    MCP = "mcp"
```

The category is used mainly for safety decisions.

### Read tools

```python
ToolKind.READ
```

These inspect information without changing external state.

Example:

```python
class ReadFileTool(Tool):
    kind = ToolKind.READ
```

### Mutating or potentially dangerous tools

The base class treats these kinds as mutating:

```python
ToolKind.WRITE
ToolKind.SHELL
ToolKind.NETWORK
ToolKind.MEMORY
```

These may require approval before execution.

`ToolKind.MCP` is a category for Model Context Protocol tools, but it is not included in the base class's default mutating set.

## 3. `FileDiff`

`FileDiff` represents a file change:

```python
@dataclass
class FileDiff:
    path: Path
    old_content: str
    new_content: str
    is_new_file: bool = False
    is_deletion: bool = False
```

It stores:

- The affected path
- The old file contents
- The new file contents
- Whether the file is new
- Whether the file is being deleted

The `to_diff()` method creates a unified diff with Python's `difflib`:

```python
def to_diff(self) -> str:
```

The output can be shown to a user before a file-changing operation is approved.

For a new file, the old side is represented as:

```text
/dev/null
```

For a deletion, the new side is represented as:

```text
/dev/null
```

`FileDiff` is optional because not every tool changes files.

## 4. `ToolResult`

Every tool returns a `ToolResult`:

```python
@dataclass
class ToolResult:
    success: bool
    output: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    truncated: bool = False
    diff: FileDiff | None = None
    exit_code: int | None = None
```

This gives the registry and agent one consistent result format regardless of which tool ran.

### Result fields

| Field       | Meaning                                               |
| ----------- | ----------------------------------------------------- |
| `success`   | Whether the operation completed successfully          |
| `output`    | Human- or model-readable output                       |
| `error`     | Error text, if the operation failed                   |
| `metadata`  | Structured details such as paths or validation errors |
| `truncated` | Whether the output was shortened                      |
| `diff`      | File change information, when applicable              |
| `exit_code` | Process exit code for command-based tools             |

### Successful result

Tools can create a successful result with:

```python
return ToolResult.success_result("Operation completed")
```

This creates a result equivalent to:

```python
ToolResult(
    success=True,
    output="Operation completed",
    error=None,
)
```

### Error result

Tools can create an error result with:

```python
return ToolResult.error_result("File not found")
```

This creates a result with `success=False`.

### Model output

The `to_model_output()` method converts a result into text for the model:

```python
def to_model_output(self) -> str:
```

For a successful result, it returns only the output:

```text
File contents...
```

For a failed result, it returns:

```text
Error: File not found

Output:
...
```

This is how tool results are added to the conversation context.

## 5. `ToolInvocation`

`ToolInvocation` carries the information needed during execution:

```python
@dataclass
class ToolInvocation:
    params: dict[str, Any]
    cwd: Path
```

It contains:

- `params`: Arguments supplied by the model
- `cwd`: The configured working directory

For example:

```python
ToolInvocation(
    params={"path": "config/config.py"},
    cwd=Path("C:/projects/cli-agent"),
)
```

The tool uses this object instead of reading global state.

## 6. `ToolConfirmation`

`ToolConfirmation` describes an operation that may need user approval:

```python
@dataclass
class ToolConfirmation:
    tool_name: str
    params: dict[str, Any]
    description: str
    diff: FileDiff | None = None
    affected_paths: list[Path] = field(default_factory=list)
    command: str | None = None
    is_dangerous: bool = False
```

It can describe:

- Which tool will run
- Which arguments it received
- What the tool intends to do
- Which files may be affected
- Which shell command will run
- Whether the operation is dangerous

The approval system uses this information to decide whether execution should proceed and to show a confirmation request to the user.

## 7. The `Tool` abstract base class

The main abstraction is:

```python
class Tool(abc.ABC):
```

A custom or built-in tool normally defines:

```python
class MyTool(Tool):
    name = "my_tool"
    description = "Does something useful"
    kind = ToolKind.READ
    schema = MyToolParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        ...
```

The base class provides common behavior so every tool does not need to reimplement validation, safety classification, or schema generation.

## 8. Tool metadata

Every tool has class-level metadata:

```python
name: str = "base_tool"
description: str = "Base tool"
kind: ToolKind = ToolKind.READ
```

Concrete tools override these values.

For example, [`ReadFileTool`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/read_file.py>) defines:

```python
name = "read_file"
description = "Read the contents of a text file..."
kind = ToolKind.READ
```

The name is used by:

- The language model when requesting a tool
- The registry dictionary key
- Loop detection
- Tool-related hooks
- CLI tool listings

The description is shown to the model and users.

## 9. Passing configuration to tools

The base constructor receives `Config`:

```python
def __init__(self, config: Config) -> None:
    self.config = config
```

This allows tools to use shared settings such as:

- Working directory
- Shell environment policy
- Allowed tools
- Model settings
- User instructions

For example, `ShellTool` uses `self.config.shell_environment` to exclude secret-looking environment variables before launching a command.

## 10. Tool schemas

Every tool must provide a schema:

```python
@property
def schema(self) -> dict[str, Any] | type["BaseModel"]:
```

In practice, tools usually define a Pydantic model as a class attribute:

```python
class ReadFileParams(BaseModel):
    path: str
    offset: int = 1
    limit: int | None = None


class ReadFileTool(Tool):
    schema = ReadFileParams
```

The schema tells the model:

- Which parameters are accepted
- Which parameters are required
- What type each parameter has
- What each parameter means

## 11. Parameter validation

The base class validates parameters using the schema:

```python
def validate_params(self, params: dict[str, Any]) -> list[str]:
```

If the schema is a Pydantic model, it attempts:

```python
schema(**params)
```

For invalid input, it converts Pydantic validation errors into readable messages:

```text
Parameter 'path': Field required
Parameter 'offset': Input should be greater than or equal to 1
```

The registry checks these errors before execution.

This prevents tool implementations from receiving obviously invalid parameters.

## 12. Mutating-tool detection

The base class decides whether a tool is mutating:

```python
def is_mutating(self, params: dict[str, Any]) -> bool:
```

It returns `True` for:

```python
ToolKind.WRITE
ToolKind.SHELL
ToolKind.NETWORK
ToolKind.MEMORY
```

It returns `False` for read tools by default.

The `params` argument is available so a specialized tool can override the method and make a more detailed decision based on its specific arguments.

## 13. Creating confirmation data

The default `get_confirmation()` method is:

```python
async def get_confirmation(
    self,
    invocation: ToolInvocation,
) -> ToolConfirmation | None:
```

For read-only tools, it returns:

```python
None
```

For mutating tools, it creates a basic confirmation:

```python
ToolConfirmation(
    tool_name=self.name,
    params=invocation.params,
    description=f"Execute {self.name}",
)
```

Tools can override this method when they need richer information.

For example, `ShellTool` includes the actual command and marks blocked commands as dangerous.

## 14. Executing a tool

The base class requires every concrete tool to implement:

```python
@abc.abstractmethod
async def execute(
    self,
    invocation: ToolInvocation,
) -> ToolResult:
```

The base class does not know how to read files or run commands. Each concrete tool implements its own behavior.

The contract is:

```text
Input:  ToolInvocation
Output: ToolResult
```

An implementation should return a `ToolResult` rather than returning arbitrary strings or raising ordinary user-facing errors.

## 15. Generating the OpenAI tool schema

The `to_openai_schema()` method converts a tool into the structured schema used by the LLM API:

```python
def to_openai_schema(self) -> dict[str, Any]:
```

For a Pydantic schema, it calls:

```python
json_schema = model_json_schema(schema, mode="serialization")
```

Then it creates:

```python
{
    "name": self.name,
    "description": self.description,
    "parameters": {
        "type": "object",
        "properties": ...,
        "required": ...,
    },
}
```

For `ReadFileTool`, the model receives a schema conceptually like:

```json
{
  "name": "read_file",
  "description": "Read the contents of a text file...",
  "parameters": {
    "type": "object",
    "properties": {
      "path": { "type": "string" },
      "offset": { "type": "integer" },
      "limit": { "type": ["integer", "null"] }
    },
    "required": ["path"]
  }
}
```

The LLM uses this schema to produce valid tool calls.

The method also supports a raw dictionary schema. If the schema is neither a Pydantic model nor a dictionary, it raises `ValueError`.

## 16. What is the `ToolRegistry`?

`ToolRegistry` is the central catalog and execution gateway for tools:

```python
class ToolRegistry:
```

It stores:

```python
self._tools: dict[str, Tool] = {}
self._mcp_tools: dict[str, Tool] = {}
```

There are two groups:

### Regular tools

Stored in `_tools`.

These include:

- Built-in tools
- Custom tools discovered from `.cli-agent/tools`
- Subagent tools

### MCP tools

Stored in `_mcp_tools`.

These are provided by connected Model Context Protocol servers.

Keeping MCP tools separate allows the registry to report connected MCP tools while exposing both groups together when the model needs its available tools.

## 17. Registering regular tools

The `register()` method adds a tool:

```python
def register(self, tool: Tool) -> None:
```

It uses the tool name as the dictionary key:

```python
self._tools[tool.name] = tool
```

If a tool with the same name already exists, it logs:

```text
Overwriting existing tool: <name>
```

This means names must be unique. Registering a duplicate replaces the earlier tool.

## 18. Registering MCP tools

MCP tools use:

```python
def register_mcp_tool(self, tool: Tool) -> None:
```

They are stored in `_mcp_tools`:

```python
self._mcp_tools[tool.name] = tool
```

MCP tools become available alongside normal tools through `get_tools()` and `get()`.

## 19. Unregistering tools

The `unregister()` method removes a regular tool:

```python
def unregister(self, name: str) -> bool:
```

It returns:

- `True` if a regular tool was found and removed
- `False` if the name was not present in `_tools`

This method does not remove MCP tools because MCP tools are managed by the MCP manager.

## 20. Looking up a tool

The `get()` method searches both groups:

```python
def get(self, name: str) -> Tool | None:
```

It checks regular tools first and MCP tools second:

```python
if name in self._tools:
    return self._tools[name]
elif name in self._mcp_tools:
    return self._mcp_tools[name]
```

If no matching tool exists, it returns `None`.

The invocation path uses this lookup to resolve the model's requested tool name.

## 21. Getting available tools

The `get_tools()` method combines both groups:

```python
def get_tools(self) -> list[Tool]:
```

It returns:

```text
regular tools + MCP tools
```

### Allowed-tool filtering

If `config.allowed_tools` is set, only named tools are returned:

```python
if self.config.allowed_tools:
    allowed_set = set(self.config.allowed_tools)
    tools = [t for t in tools if t.name in allowed_set]
```

For example:

```toml
allowed_tools = ["read_file", "grep"]
```

means the model sees only those tools through `get_tools()`.

This filtering affects:

- Tool listings
- Tool schemas sent to the model
- The set of tools presented by the normal registry

The registry still stores other tools internally, but they are not returned as available through `get_tools()`.

## 22. Getting schemas for the model

The `get_schemas()` method converts available tools into API schemas:

```python
def get_schemas(self) -> list[dict[str, Any]]:
    return [tool.to_openai_schema() for tool in self.get_tools()]
```

The agent uses it here:

```python
tool_schemas = self.session.tool_registry.get_schemas()
```

The LLM client sends these schemas to the model:

```python
kwargs["tools"] = self._build_tools(tools)
kwargs["tool_choice"] = "auto"
```

This is how the model learns which tools it can request and which arguments they accept.

## 23. The `invoke()` gateway

The most important registry method is:

```python
async def invoke(
    self,
    name: str,
    params: dict[str, Any],
    cwd: Path,
    hook_system: HookSystem,
    approval_manager: ApprovalManager | None = None,
) -> ToolResult:
```

Every model-requested tool call should pass through this method.

It centralizes:

- Tool lookup
- Parameter validation
- Hooks
- Approval
- Invocation construction
- Exception handling
- Result reporting

## 24. Invocation step 1: lookup

The registry first resolves the name:

```python
tool = self.get(name)
```

If the tool does not exist, it returns a standard error:

```python
ToolResult.error_result(
    f"Unknown tool: {name}",
    metadata={"tool_name": name},
)
```

It also triggers `after_tool`, allowing the failure to be logged consistently.

## 25. Invocation step 2: parameter validation

The registry validates parameters before running the tool:

```python
validation_errors = tool.validate_params(params)
```

If validation fails, it returns:

```python
ToolResult.error_result(
    f"Invalid parameters: {'; '.join(validation_errors)}",
    metadata={
        "tool_name": name,
        "validation_errors": validation_errors,
    },
)
```

The tool is not executed when its arguments are invalid.

The `after_tool` hook still runs so the failed call can be audited.

## 26. Invocation step 3: before-tool hook

After validation, the registry calls:

```python
await hook_system.trigger_before_tool(name, params)
```

This gives configured hooks an opportunity to log or observe the upcoming tool call.

The hook does not itself replace parameter validation or approval.

## 27. Invocation step 4: build the invocation

The registry creates:

```python
invocation = ToolInvocation(
    params=params,
    cwd=cwd,
)
```

The tool receives this object when execution begins.

## 28. Invocation step 5: approval

If an approval manager was supplied, the registry asks the tool whether confirmation is needed:

```python
confirmation = await tool.get_confirmation(invocation)
```

For read-only tools, this normally returns `None`.

For mutating tools, it returns a `ToolConfirmation`.

The registry converts that into an `ApprovalContext`:

```python
context = ApprovalContext(
    tool_name=name,
    params=params,
    is_mutating=tool.is_mutating(params),
    affected_paths=confirmation.affected_paths,
    command=confirmation.command,
    is_dangerous=confirmation.is_dangerous,
)
```

The approval manager then returns a decision.

### Rejected by policy

If the decision is:

```python
ApprovalDecision.REJECTED
```

the tool does not execute. The registry returns:

```text
Operation rejected by safety policy
```

### Confirmation required

If the decision is:

```python
ApprovalDecision.NEEDS_CONFIRMATION
```

the registry asks the configured confirmation callback:

```python
approved = approval_manager.request_confirmation(confirmation)
```

If the user rejects it, execution stops and the registry returns:

```text
User rejected the operation
```

### Approved

If the policy allows the operation or the user approves it, execution continues.

## 29. Invocation step 6: execute the tool

The registry calls:

```python
result = await tool.execute(invocation)
```

The result must be a `ToolResult`.

If the tool raises an unexpected exception, the registry logs it and converts it into an error result:

```python
result = ToolResult.error_result(
    f"Internal error: {str(e)}",
    metadata={
        "tool_name",
        name,
    },
)
```

This prevents one tool exception from crashing the entire agent loop.

## 30. Invocation step 7: after-tool hook

After execution, rejection, validation failure, or an unknown tool, the registry calls:

```python
await hook_system.trigger_after_tool(name, params, result)
```

This gives hooks access to the final result for auditing and logging.

Finally, the registry returns the `ToolResult` to the agent.

## 31. Complete invocation flow

The complete path is:

```text
Model requests tool name and parameters
                |
                v
ToolRegistry.get(name)
                |
       Tool exists?
        /        \
      No          Yes
      |            |
 Return error   Validate parameters
                     |
             Valid parameters?
                /        \
              No          Yes
              |            |
       Return error    before_tool hook
                              |
                              v
                      Create ToolInvocation
                              |
                              v
                        Approval check
                              |
                  Approved or allowed?
                       /          \
                     No            Yes
                     |              |
               Return error     execute()
                                      |
                                      v
                              after_tool hook
                                      |
                                      v
                                ToolResult
```

## 32. Creating the default registry

The factory function is:

```python
def create_default_registry(config: Config) -> ToolRegistry:
```

It:

1. Creates a `ToolRegistry`
2. Loads all built-in tool classes
3. Instantiates each class with `config`
4. Registers each instance
5. Loads default subagent definitions
6. Registers each subagent tool

```python
registry = ToolRegistry(config)

for tool_class in get_all_builtin_tools():
    registry.register(tool_class(config))

for subagent_def in get_default_subagent_definitions():
    registry.register(SubagentTool(config, subagent_def))
```

This factory is called by [`Session`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>):

```python
self.tool_registry = create_default_registry(config)
```

MCP and project-specific tools are registered later during session initialization.

## 33. Built-in, custom, and MCP tools

The registry brings several tool sources together:

```text
Built-in tools
      |
Custom .cli-agent/tools tools
      |
MCP tools
      |
Subagent tools
      |
      v
One ToolRegistry
```

The discovery manager adds custom project tools after the registry is created. The MCP manager adds MCP tools after connecting to configured servers.

Regardless of source, every tool should satisfy the `Tool` contract and return `ToolResult`.

## 34. Tool registry and the model

The model sees tools through two mechanisms:

### Natural-language guidance

[`prompts/system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/prompts/system.py>) describes tools and general usage practices in the system prompt.

### Structured schemas

`ToolRegistry.get_schemas()` creates structured tool definitions from `Tool.to_openai_schema()`.

The model uses those definitions to request calls such as:

```json
{
  "name": "read_file",
  "arguments": {
    "path": "config/config.py"
  }
}
```

The registry then resolves and invokes `read_file`.

## 35. Why `base.py` and `registry.py` are separate

Separating the abstraction from the registry keeps responsibilities clear.

### `base.py`

Defines:

- What a tool is
- What a tool receives
- What a tool returns
- How parameters are validated
- How safety classification works
- How schemas are generated

### `registry.py`

Defines:

- Where tools are stored
- How tools are registered
- How available tools are filtered
- How schemas are collected
- How calls are routed
- How hooks and approval are coordinated

This allows individual tools to focus on their actual operation instead of duplicating system-level logic.

## 36. Example: custom read-only tool

A minimal custom tool can look like:

```python
from pydantic import BaseModel, Field

from tools.base import Tool, ToolInvocation, ToolKind, ToolResult


class EchoParams(BaseModel):
    message: str = Field(..., description="Message to echo")


class EchoTool(Tool):
    name = "echo"
    description = "Return the supplied message."
    kind = ToolKind.READ
    schema = EchoParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = EchoParams(**invocation.params)
        return ToolResult.success_result(params.message)
```

The discovery system can instantiate and register this class. After registration:

```text
1. The model receives the `echo` schema
2. The model requests `echo`
3. Registry validates `message`
4. No approval is needed because it is read-only
5. `execute()` runs
6. A `ToolResult` returns to the model
```

## 37. Example: mutating tool

A file-writing tool might define:

```python
kind = ToolKind.WRITE
```

The default base behavior considers it mutating and creates a `ToolConfirmation`.

The tool can override `get_confirmation()` to provide:

- A file diff
- A list of affected paths
- A detailed description

The registry then sends that information through the approval manager before executing it.

## 38. Current implementation notes

1. `connected_mcp_servers` is annotated as returning `list[Tool]`, but it currently returns `self._mcp_tools.values()`, which is a dictionary-values view rather than a list.

2. `unregister()` removes only regular tools. MCP tools remain managed by the MCP manager.

3. `allowed_tools` filters tools returned by `get_tools()`, but the registry still stores non-allowed tools internally.

4. The registry checks tool names through `get()`, while `allowed_tools` primarily controls which tools are exposed through `get_tools()` and `get_schemas()`.

5. The exception metadata in the unexpected-error branch appears to use a set literal:

   ```python
   metadata={
       "tool_name",
       name,
   }
   ```

   This does not create the same dictionary shape used elsewhere. The intended form is likely:

   ```python
   metadata={"tool_name": name}
   ```

6. The `Tool` base class defaults to `ToolKind.READ`. Concrete tools should explicitly set their kind so safety behavior is not accidentally misclassified.

## Summary

[`tools/base.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>) defines the common tool contract:

```text
Tool metadata
  -> Parameter schema
  -> Validation
  -> Safety classification
  -> Execution
  -> Standard result
```

[`tools/registry.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>) manages the tool lifecycle:

```text
Register tools
  -> Filter available tools
  -> Generate model schemas
  -> Find requested tools
  -> Validate arguments
  -> Run hooks
  -> Check approval
  -> Execute tools
  -> Return ToolResult
```

Together, these files turn many different operations into one consistent interface that the agent and language model can safely use.
