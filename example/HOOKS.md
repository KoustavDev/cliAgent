# Understanding `hooks/hook_system.py`

The [`hooks/hook_system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/hooks/hook_system.py>) file implements the application's hook system.

A hook is a command or script that runs automatically when a specific agent event occurs.

Hooks allow the application to perform extra work around agent activity without changing the main agent loop.

Examples include:

- Logging agent activity
- Auditing tool usage
- Sending notifications
- Running validation
- Collecting metrics
- Recording errors
- Integrating with external scripts

The overall flow is:

```text
Agent or tool event
        |
        v
HookSystem selects matching hooks
        |
        v
HookSystem builds environment variables
        |
        v
Command or script executes
        |
        v
Agent continues
```

## 1. What is `HookSystem`?

The main class is:

```python
class HookSystem:
```

It receives the application's [`Config`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>) object and manages the configured hooks.

The session creates it here:

```python
self.hook_system = HookSystem(config)
```

This happens in [`agent/session.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>).

The hook system does not decide which tools the model can use and does not replace the approval system. Its responsibility is to run external commands at configured lifecycle events.

## 2. Enabling hooks

Hooks are disabled by default in `Config`:

```python
hooks_enabled: bool = False
```

They must be enabled explicitly:

```toml
hooks_enabled = true
```

When `HookSystem` is created, it loads only enabled hooks:

```python
self.hooks: list[HookConfig] = []

if self.config.hooks_enabled:
    self.hooks = [hook for hook in self.config.hooks if hook.enabled]
```

This means a hook must pass two checks:

1. `Config.hooks_enabled` must be `true`
2. The individual hook's `enabled` field must be `true`

If the global setting is false, no hooks are loaded even if individual hooks have `enabled = true`.

## 3. Defining a hook

Hooks are represented by [`HookConfig`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>):

```python
class HookConfig(BaseModel):
    name: str
    trigger: HookTrigger
    command: str | None = None
    script: str | None = None
    timeout_sec: float = 30
    enabled: bool = True
```

Each hook has:

| Field         | Purpose                                  |
| ------------- | ---------------------------------------- |
| `name`        | Human-readable identifier                |
| `trigger`     | Event at which the hook should run       |
| `command`     | Shell command to execute                 |
| `script`      | Inline shell script to execute           |
| `timeout_sec` | Maximum execution time                   |
| `enabled`     | Enables or disables this individual hook |

A hook must define either `command` or `script`:

```python
@model_validator(mode="after")
def validate_hook(self) -> HookConfig:
    if not self.command and not self.script:
        raise ValueError("Hook must either have 'command' or 'script'")
    return self
```

## 4. Hook triggers

The supported trigger values are defined by [`HookTrigger`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>):

```python
class HookTrigger(str, Enum):
    BEFORE_AGENT = "before_agent"
    AFTER_AGENT = "after_agent"
    BEFORE_TOOL = "before_tool"
    AFTER_TOOL = "after_tool"
    ON_ERROR = "on_error"
```

They represent:

| Trigger        | When it runs                                |
| -------------- | ------------------------------------------- |
| `before_agent` | Before processing a user request            |
| `after_agent`  | After the agent produces its final response |
| `before_tool`  | Immediately before a tool executes          |
| `after_tool`   | After a tool completes or is rejected       |
| `on_error`     | When explicitly triggered with an exception |

## 5. Example configuration

The project currently enables hooks in [`.cli-agent/config.toml`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/.cli-agent/config.toml>):

```toml
hooks_enabled = true

[[hooks]]
name = "test_before_tool"
trigger = "before_tool"
command = "python3 ./scripts/test_tool.py"

[[hooks]]
name = "test_before_agent"
trigger = "before_agent"
command = "python3 ./scripts/test_tool.py"
```

This configuration creates two hooks:

1. Run `python3 ./scripts/test_tool.py` before each agent request
2. Run `python3 ./scripts/test_tool.py` before each tool call

The hook command is executed with the configured working directory from `config.cwd`.

## 6. Running a command hook

If a hook has a `command`, `_run_hook()` calls:

```python
await self._run_command(
    hook.command,
    hook.timeout_sec,
    env,
)
```

The command is started by `_run_command()`:

```python
process = await asyncio.create_subprocess_shell(
    command,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
    cwd=self.config.cwd,
    env=env,
    start_new_session=True,
)
```

Important behavior:

- It runs asynchronously
- It uses a shell
- It runs from `config.cwd`
- Standard output and standard error are captured
- The hook receives the constructed environment
- A new process group/session is started

Because the method awaits `process.communicate()`, the agent waits for the hook to finish before continuing.

## 7. Running an inline script hook

If a hook does not have a command, `_run_hook()` treats its `script` field as an inline shell script.

It creates a temporary file:

```python
with tempfile.NamedTemporaryFile(
    mode="w", suffix=".sh", delete=False
) as f:
    f.write("#!/bin/bash\n")
    f.write(hook.script)
    script_path = f.name
```

Then it:

1. Makes the temporary file executable
2. Runs it through `_run_command()`
3. Deletes it in the `finally` block

```python
finally:
    os.unlink(script_path)
```

This means inline scripts are temporary and are not retained after execution.

## 8. Hook timeouts

The command is given a timeout:

```python
await asyncio.wait_for(
    process.communicate(),
    timeout=timeout,
)
```

If the hook runs longer than `timeout_sec`, the process is terminated.

On Unix-like systems:

```python
os.killpg(os.getpgid(process.pid), signal.SIGKILL)
```

On Windows:

```python
process.kill()
```

The process is then awaited:

```python
await process.wait()
```

This prevents a hook from blocking the agent indefinitely.

## 9. Environment variables passed to hooks

The `_build_env()` method starts with a copy of the current process environment:

```python
env = os.environ.copy()
```

It then adds agent-specific variables:

```python
env["AI_AGENT_TRIGGER"] = trigger.value
env["AI_AGENT_CWD"] = str(self.config.cwd)
```

Depending on the event, it may also add:

```text
AI_AGENT_TOOL_NAME
AI_AGENT_USER_MESSAGE
AI_AGENT_ERROR
AI_AGENT_RESPONSE
AI_AGENT_TOOL_PARAMS
AI_AGENT_TOOL_RESULT
```

This lets a hook script understand why it was run and what happened.

## 10. `before_agent`

The method is:

```python
async def trigger_before_agent(self, user_message: str) -> None:
```

It builds an environment containing:

```text
AI_AGENT_TRIGGER=before_agent
AI_AGENT_CWD=<configured working directory>
AI_AGENT_USER_MESSAGE=<user request>
```

Then it runs every hook whose trigger matches:

```python
for hook in self.hooks:
    if hook.trigger == HookTrigger.BEFORE_AGENT:
        await self._run_hook(hook, env)
```

The agent calls it before processing the message:

```python
await self.session.hook_system.trigger_before_agent(message)
```

This is useful for:

- Logging a new request
- Checking project state
- Preparing files
- Starting a monitoring operation
- Rejecting or reporting unsupported situations through an external system

## 11. `after_agent`

The method is:

```python
async def trigger_after_agent(
    self,
    user_message: str,
    agent_response: str,
) -> None:
```

It provides:

```text
AI_AGENT_TRIGGER=after_agent
AI_AGENT_CWD=<configured working directory>
AI_AGENT_USER_MESSAGE=<original request>
AI_AGENT_RESPONSE=<final response>
```

The agent calls it after the agent loop completes:

```python
await self.session.hook_system.trigger_after_agent(
    message,
    final_response,
)
```

This is useful for:

- Saving an audit record
- Sending a completion notification
- Recording the final answer
- Updating an external task tracker

## 12. `before_tool`

The method is:

```python
async def trigger_before_tool(
    self,
    tool_name: str,
    tool_params: dict[str, Any],
) -> None:
```

It passes:

```text
AI_AGENT_TRIGGER=before_tool
AI_AGENT_CWD=<configured working directory>
AI_AGENT_TOOL_NAME=<tool name>
AI_AGENT_TOOL_PARAMS=<JSON encoded arguments>
```

The parameters are encoded with:

```python
env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
```

The registry calls this before executing a valid tool:

```python
await hook_system.trigger_before_tool(name, params)
```

This can be used to:

- Log tool calls
- Check external policy
- Record the requested arguments
- Prepare a test or monitoring record

Important: this hook does not replace the application's approval manager. Approval is handled separately by [`tools/registry.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>).

## 13. `after_tool`

The method is:

```python
async def trigger_after_tool(
    self,
    tool_name: str,
    tool_params: dict[str, Any],
    tool_result: ToolResult,
) -> None:
```

It provides:

```text
AI_AGENT_TRIGGER=after_tool
AI_AGENT_CWD=<configured working directory>
AI_AGENT_TOOL_NAME=<tool name>
AI_AGENT_TOOL_PARAMS=<JSON encoded arguments>
AI_AGENT_TOOL_RESULT=<tool output or error>
```

The result is converted to model output:

```python
env["AI_AGENT_TOOL_RESULT"] = tool_result.to_model_output()
```

The registry calls this after:

- Successful tool execution
- Invalid tool parameters
- Unknown tools
- Rejected operations
- Tool exceptions

This makes `after_tool` useful for consistent audit logging regardless of how the tool ended.

## 14. `on_error`

The method is:

```python
async def trigger_on_error(self, error: Exception) -> None:
```

It provides:

```text
AI_AGENT_TRIGGER=on_error
AI_AGENT_CWD=<configured working directory>
AI_AGENT_ERROR=<exception text>
```

This can be used to notify an external service or write an error audit record.

The method exists, but the current codebase does not appear to call `trigger_on_error()` from the main agent or registry error paths. Therefore, an `on_error` hook will not run automatically unless another caller invokes this method.

## 15. The example hook script

The project includes [`scripts/test_tool.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/scripts/test_tool.py>).

Despite its name, this file is a hook script, not an agent tool.

It reads environment variables:

```python
trigger = os.environ.get("AI_AGENT_TRIGGER")
cwd = os.environ.get("AI_AGENT_CWD")
tool_name = os.environ.get("AI_AGENT_TOOL_NAME")
user_message = os.environ.get("AI_AGENT_USER_MESSAGE")
error = os.environ.get("AI_AGENT_ERROR")
```

It stores them in a dictionary with a timestamp and writes a log line to `hook.log`.

The flow is:

```text
Agent event
    |
    v
HookSystem builds environment
    |
    v
scripts/test_tool.py reads environment
    |
    v
Script writes an audit record
```

The script is configured as a command in [`.cli-agent/config.toml`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/.cli-agent/config.toml>).

This is different from [`.cli-agent/tools/test_tool.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/.cli-agent/tools/test_tool.py>), which is a dynamically discovered cli-agent tool.

## 16. Hooks do not directly modify agent behavior

The hook system runs external commands, but hook output is not returned as a model message.

The subprocess output is captured here:

```python
stdout=asyncio.subprocess.PIPE
stderr=asyncio.subprocess.PIPE
```

However, `_run_command()` does not currently read, log, or return that output after `communicate()`.

Therefore, hooks are mainly useful for side effects such as:

- Writing logs
- Sending notifications
- Updating external systems
- Running checks

They do not currently provide output that the language model can directly inspect.

## 17. Hook failures

`_run_hook()` catches exceptions:

```python
except Exception as e:
    print(e)
```

This means a hook failure normally does not stop the agent. The application prints the exception and continues.

A hook timeout is also handled inside `_run_command()` by terminating the process and waiting for it to exit.

This gives hooks a best-effort behavior: they can perform auxiliary work without making the primary agent request fail.

## 18. Hook execution order

Hooks are stored in the order they appear in configuration:

```python
self.hooks = [hook for hook in self.config.hooks if hook.enabled]
```

For a given trigger, matching hooks execute sequentially:

```python
for hook in self.hooks:
    if hook.trigger == HookTrigger.BEFORE_TOOL:
        await self._run_hook(hook, env)
```

The next hook starts after the previous hook finishes or fails.

## 19. Complete lifecycle example

For a tool call, the flow is:

```text
Model requests a tool
        |
        v
ToolRegistry validates parameters
        |
        v
HookSystem.trigger_before_tool()
        |
        v
before_tool hooks execute
        |
        v
ApprovalManager checks the operation
        |
        v
Tool executes
        |
        v
HookSystem.trigger_after_tool()
        |
        v
after_tool hooks execute
        |
        v
Tool result returns to the agent
```

For an agent request:

```text
User sends a message
        |
        v
trigger_before_agent()
        |
        v
Agent processes the request
        |
        v
trigger_after_agent()
        |
        v
Final response is complete
```

## 20. Current implementation notes

1. The hook system uses `create_subprocess_shell()`. Hook commands should therefore be treated as trusted configuration and should not be built by directly concatenating untrusted user input.

2. Inline `script` hooks are written with a Bash shebang. On Windows, script hooks may require additional handling because Bash may not be available. Command hooks are generally more portable when they explicitly invoke the correct interpreter.

3. The example hook script writes to a hard-coded macOS path:

   ```python
   /Users/rivaanranawat/Desktop/cli-agent/hook.log
   ```

   This path may not exist or be appropriate on another machine.

4. The `after_agent` environment includes `AI_AGENT_RESPONSE`, but `_build_env()` does not define that variable itself; `trigger_after_agent()` adds it directly.

5. The current `on_error` method is available but is not wired into the main error paths.

## Summary

[`hooks/hook_system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/hooks/hook_system.py>) provides lifecycle callbacks for the agent.

Its responsibilities are:

```text
Load enabled hooks
  -> Select hooks by trigger
  -> Build event-specific environment variables
  -> Run commands or temporary scripts
  -> Enforce timeouts
  -> Continue without crashing the main agent when hooks fail
```

The main application uses hooks for side effects around agent and tool activity. They are separate from tools, approvals, MCP servers, and the context manager, but they are coordinated through the session and tool registry.
