# Understanding the CLI and Terminal UI

This project has a terminal-based user interface (TUI). It lets a user chat with the
agent, see streamed responses, inspect tool calls, approve risky operations, and manage
sessions without opening a web browser.

The UI is implemented mainly by:

| File | Responsibility |
|---|---|
| [`main.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/main.py>) | Starts the command-line application and coordinates the interactive loop |
| [`ui/tui.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/ui/tui.py>) | Formats terminal output with Rich and asks for tool approval |
| [`agent/events.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/events.py>) | Defines events emitted while the agent runs |

The architecture is:

```text
User starts the CLI
        |
        v
main() loads configuration
        |
        v
CLI creates TUI and Agent
        |
        v
User enters a message or slash command
        |
        v
Agent emits events
        |
        v
CLI translates events into TUI calls
        |
        v
TUI renders panels, colors, code, diffs, and prompts
```

## 1. Starting the CLI

The Click command at the bottom of `main.py` accepts an optional prompt and an optional
working directory:

```python
@click.command()
@click.argument("prompt", required=False)
@click.option("--cwd", "-c", ...)
def main(prompt: str | None, cwd: Path | None):
    ...
```

Typical usage:

```bash
python main.py
```

This starts interactive mode.

```bash
python main.py "Explain this project"
```

This sends one prompt and runs without the interactive command loop.

```bash
python main.py --cwd C:/projects/demo
```

This loads the configuration using `C:/projects/demo` as the working directory.

## 2. Configuration startup

Before the UI starts, `main()` calls:

```python
config = load_config(cwd=cwd)
```

The configuration controls values displayed by the welcome screen and used by the
agent, including:

- Model name
- Temperature
- Working directory
- Approval policy
- Maximum turns
- Hooks
- MCP servers

The configuration is passed into `CLI`, and then into `TUI`:

```python
cli = CLI(config)
```

```python
class CLI:
    def __init__(self, config: Config):
        self.agent: Agent | None = None
        self.config = config
        self.tui = TUI(config, console)
```

The TUI needs the configuration mainly for the working directory, model name used when
truncating output, and display behavior.

## 3. `get_console()` and the Rich console

[`ui/tui.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/ui/tui.py>) creates
one shared Rich `Console`:

```python
_console: Console | None = None


def get_console() -> Console:
    global _console
    if _console is None:
        _console = Console(theme=AGENT_THEME, highlight=False)
    return _console
```

Using one console gives the application a consistent theme and output destination.
`highlight=False` prevents Rich from automatically changing text that looks like a
path or URL.

The same console is used by `main.py`:

```python
console = get_console()
```

## 4. The application theme

`AGENT_THEME` assigns names to colors:

```python
AGENT_THEME = Theme(
    {
        "info": "cyan",
        "warning": "yellow",
        "error": "bright_red bold",
        "success": "green",
        "user": "bright_blue bold",
        "assistant": "bright_white",
        "tool": "bright_magenta bold",
        "tool.read": "cyan",
        "tool.write": "yellow",
        "tool.shell": "magenta",
        "tool.mcp": "bright_cyan",
    }
)
```

These names are used in Rich markup:

```python
console.print("[error]Error: something failed[/error]")
```

The result is an emphasized red error rather than plain text.

Tool kinds receive different border colors. For example:

```text
read tool:  cyan border
write tool: yellow border
shell tool: magenta border
MCP tool:   bright cyan border
```

## 5. The `TUI` class

`TUI` is the presentation layer:

```python
class TUI:
    def __init__(
        self,
        config: Config,
        console: Console | None = None,
    ) -> None:
```

It stores:

```python
self.console
self.config
self.cwd
self._assistant_stream_open
self._tool_args_by_call_id
self._max_block_tokens = 2500
```

### Why `_assistant_stream_open` exists

Assistant responses arrive in pieces. This flag lets the UI print one assistant
section around the entire stream instead of printing a new heading for every token.

### Why `_tool_args_by_call_id` exists

The tool-start event contains arguments, while the completion event contains the result.
The dictionary preserves the arguments so the completion renderer can display details
such as the shell command or fetched URL.

## 6. Interactive mode

`CLI.run_interactive()` first prints a welcome panel:

```python
self.tui.print_welcome(
    "AI Agent",
    lines=[
        f"model: {self.config.model_name}",
        f"cwd: {self.config.cwd}",
        "commands: /help /config /approval /model /exit",
    ],
)
```

Example:

```text
╭─ AI Agent ─────────────────────────────╮
│ model: gpt-4o                          │
│ cwd: C:\projects\demo                  │
│ commands: /help /config /approval ...  │
╰────────────────────────────────────────╯
```

The CLI then creates an `Agent` with the TUI confirmation callback:

```python
async with Agent(
    self.config,
    confirmation_callback=self.tui.handle_confirmation,
) as agent:
```

It repeatedly reads:

```python
user_input = console.input("\n[user]>[/user] ").strip()
```

Input is classified as either:

```text
starts with "/"  -> slash command
anything else    -> message for the agent
```

Blank input is ignored.

## 7. Single-prompt mode versus interactive mode

### Single-prompt mode

When a prompt is supplied on the command line:

```python
if prompt:
    result = asyncio.run(cli.run_single(prompt))
```

`run_single()` creates an agent, processes one message, and exits:

```python
async def run_single(self, message: str) -> str | None:
    async with Agent(self.config) as agent:
        self.agent = agent
        return await self._process_message(message)
```

### Interactive mode

Without a prompt:

```python
asyncio.run(cli.run_interactive())
```

the user can send many messages and use slash commands in the same session.

## 8. Agent events drive the UI

The agent does not directly print every response. It emits `AgentEvent` objects defined
in [`agent/events.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/events.py>).

The event types are:

```python
class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    AGENT_END = "agent_end"
    AGENT_ERROR = "agent_error"
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_COMPLETE = "tool_call_complete"
    TEXT_DELTA = "text_delta"
    TEXT_COMPLETE = "text_complete"
```

`CLI._process_message()` consumes the stream:

```python
async for event in self.agent.run(message):
    ...
```

This separates responsibilities:

```text
Agent      -> decides what happened
AgentEvent -> carries structured data
CLI        -> routes the event
TUI        -> displays it
```

## 9. Streaming assistant responses

When a `TEXT_DELTA` event arrives:

```python
if not assistant_streaming:
    self.tui.begin_assistant()
    assistant_streaming = True

self.tui.stream_assistant_delta(content)
```

`begin_assistant()` prints a Rich rule:

```python
self.console.print()
self.console.print(Rule(Text("Assistant", style="assistant")))
```

Each delta is then printed immediately:

```python
self.console.print(content, end="", markup=False)
```

`markup=False` is important: model-generated text containing brackets should be printed
as text rather than accidentally interpreted as Rich markup.

When `TEXT_COMPLETE` arrives, `end_assistant()` closes the visual section:

```python
if self._assistant_stream_open:
    self.console.print()
self._assistant_stream_open = False
```

Example:

```text
──────────────── Assistant ────────────────
The configuration object is the shared settings
container used by the rest of the application.
```

## 10. Tool-call start display

When a tool starts, the CLI obtains its kind and calls:

```python
self.tui.tool_call_start(
    call_id,
    tool_name,
    tool_kind,
    arguments,
)
```

The TUI stores the arguments and creates a rounded Rich `Panel`.

Example:

```text
╭─ ⏺ read_file  #a1b2c3d4 ───────────── running ─╮
│       path  src/config.py                       │
│     offset  1                                  │
│      limit  80                                 │
╰─────────────────────────────────────────────────╯
```

The call ID is shortened to its first eight characters for readability.

### Relative paths

For `path` and `cwd` arguments, the TUI attempts to display paths relative to the
configured working directory:

```python
display_path_rel_to_cwd(val, self.cwd)
```

This keeps the terminal output compact while the actual tool still receives the
original path.

### Argument ordering

`_ordered_args()` puts common arguments in a predictable order:

```python
"read_file": ["path", "offset", "limit"]
"shell": ["command", "timeout", "cwd"]
"edit": ["path", "replace_all", "old_string", "new_string"]
```

Unknown arguments are displayed afterward.

Large string arguments such as file contents are summarized:

```text
content  <42 lines • 1180 bytes>
```

This prevents a tool panel from printing an entire file before the tool has even
finished.

## 11. Tool-call completion display

When a tool completes, the CLI passes the normalized result to:

```python
self.tui.tool_call_complete(
    call_id,
    name,
    tool_kind,
    success,
    output,
    error,
    metadata,
    diff,
    truncated,
    exit_code,
)
```

The panel title uses:

```text
✓ for success
✗ for failure
```

The subtitle is either:

```text
done
failed
```

## 12. Tool-specific rendering

The TUI uses specialized output for common built-in tools.

### `read_file`

The TUI detects the line-number format returned by the tool:

```text
1|def main():
2|    print("hello")
```

It removes the prefixes and displays the result with:

- Syntax highlighting
- Language detection from the file extension
- Line numbers
- A header such as `src/main.py • lines 1-20 of 80`

Example:

```text
╭─ ✓ read_file ───────────────────────── done ─╮
│ src/main.py • lines 1-12 of 12               │
│  1 def main():                                │
│  2     print("hello")                         │
╰───────────────────────────────────────────────╯
```

### `write_file` and `edit`

When these tools return a diff, the TUI displays:

1. The operation result
2. A syntax-highlighted unified diff

Example:

```diff
- old_value = 1
+ new_value = 2
```

This is especially useful because the user can see exactly what changed.

### `shell`

The UI displays:

- The command with a `$` prefix
- The exit code
- The command output

Example:

```text
$ pytest tests/test_config.py
exit_code=0
================= test session starts =================
...
```

### `list_dir`

Metadata is summarized as:

```text
C:\projects\demo • 12 entries
```

### `grep` and `glob`

The UI displays counts such as:

```text
4 matches • searched 9 files
```

or:

```text
7 matches
```

### `web_search` and `web_fetch`

The UI shows useful metadata before the returned text:

```text
python async context manager • 5 results
```

For a fetched page it may show:

```text
200 • 8420 bytes • https://example.com
```

### `todos` and `memory`

Their output is displayed as text. For memory operations, the UI also summarizes:

```text
read user.language • found
```

### MCP and other tools

Unrecognized tools use a generic renderer. The UI displays an error when the call
fails, otherwise it displays the returned text. MCP tools still receive their
tool-kind color through the `tool.mcp` theme style.

## 13. Output truncation

The TUI limits large output blocks:

```python
self._max_block_tokens = 2500
```

It uses `truncate_text()` before rendering large results. This protects the terminal
from huge outputs while retaining the complete result in the agent's internal flow
where appropriate.

If truncation occurred, the panel includes:

```text
note: tool output was truncated
```

This is a display limit, not the same thing as context compaction. Context management
is handled separately by [`context/manager.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/manager.py>).

## 14. Approval prompts

Mutating tools can request confirmation through the callback supplied to `Agent`.

The callback is:

```python
confirmation_callback=self.tui.handle_confirmation
```

`handle_confirmation()` builds an approval panel containing:

- Tool name
- Description
- Shell command, when present
- File diff, when present

Example:

```text
╭─ Approval required ─────────────────────────╮
│ edit                                         │
│ Replace the selected text                    │
│                                              │
│ - old_value = 1                              │
│ + new_value = 2                              │
╰──────────────────────────────────────────────╯

Approve? [y/n] (n):
```

The prompt accepts:

```text
y, yes -> approve
n, no  -> reject
```

The default is `n`, so pressing Enter rejects the operation.

The UI only asks the question. The approval policy and tool execution remain part of
the agent/tool system.

## 15. Slash commands

Slash commands are handled by `CLI._handle_command()`.

### `/help`

Displays Markdown help from `TUI.show_help()`:

```text
/help       Show this help
/exit       Exit the agent
/clear      Clear conversation history
/config     Show current configuration
...
```

### `/exit` and `/quit`

Return `False` from `_handle_command()`, causing the interactive loop to stop.

### `/clear`

Clears:

```python
self.agent.session.context_manager.clear()
self.agent.session.loop_detector.clear()
```

Then prints:

```text
Conversation cleared
```

This removes the current conversation context and resets loop-detection history.

### `/config`

Shows the active values:

```text
Current Configuration
  Model: gpt-4o
  Temperature: 1.0
  Approval: on-request
  Working Dir: C:\projects\demo
  Max Turns: 100
  Hooks Enabled: False
```

### `/model`

Without an argument:

```text
/model
```

shows the current model.

With an argument:

```text
/model gpt-4o-mini
```

changes `config.model_name` for the running CLI configuration.

### `/approval`

Without an argument, it displays the current policy:

```text
/approval
```

With an argument:

```text
/approval auto
```

it attempts to set an `ApprovalPolicy` value.

Invalid values produce an error and list the valid enum values.

### `/stats`

Displays session statistics obtained from:

```python
self.agent.session.get_stats()
```

This can include turn count, token usage, tool counts, and session information.

### `/tools`

Lists the tools currently visible to the session, including built-in, custom, subagent,
and connected MCP tools:

```text
Available tools (14)
  • read_file
  • write_file
  • shell
  • filesystem__read_file
```

### `/mcp`

Displays MCP server state:

```text
MCP Servers (1)
  • filesystem: connected (5 tools)
```

Disconnected or failed servers are shown in red.

### `/save`

Creates a `SessionSnapshot` and persists it with `PersistenceManager`.

Example:

```text
Session saved: 7a0e...
```

### `/sessions`

Lists saved sessions and their turn counts:

```text
Saved Sessions
  • 7a0e... (turns: 4, updated: 2026-09-25T12:20:00)
```

### `/resume <session_id>`

Loads a saved session, initializes a replacement `Session`, restores its messages, and
swaps it into the current agent.

Example:

```text
/resume 7a0e...
```

### `/checkpoint`

Creates a checkpoint of the current session:

```text
/checkpoint before-refactor
```

The current implementation creates the checkpoint through
`PersistenceManager.save_checkpoint()`. The optional name is parsed by the command
handler but is not passed into that method.

### `/checkpoints`

The help text advertises this command, but the current `_handle_command()` implementation
does not contain a dedicated `/checkpoints` branch. It therefore falls through to the
unknown-command message.

### `/restore <checkpoint_id>`

Loads a checkpoint, creates a new session, restores its messages, and replaces the
current session.

Example:

```text
/restore checkpoint-123
```

## 16. Error handling in the interactive loop

The loop handles:

```python
except KeyboardInterrupt:
    console.print("\n[dim]Use /exit to quit[/dim]")
except EOFError:
    break
```

Therefore:

- `Ctrl+C` does not immediately terminate the process; it tells the user to use
  `/exit`.
- End-of-file, such as `Ctrl+D` on many terminals, exits the loop.

Agent errors are rendered as:

```python
console.print(f"\n[error]Error: {error}[/error]")
```

After the loop exits, the CLI prints:

```text
Goodbye!
```

## 17. Complete example session

An abbreviated interaction might look like:

```text
╭─ AI Agent ─────────────────────────────╮
│ model: gpt-4o                          │
│ cwd: C:\projects\demo                  │
│ commands: /help /config /approval ...  │
╰────────────────────────────────────────╯

[user]> Read the main configuration file

╭─ ⏺ read_file #a1b2c3d4 ───────── running ─╮
│ path  config/config.py                     │
╰────────────────────────────────────────────╯

╭─ ✓ read_file #a1b2c3d4 ─────────── done ──╮
│ config/config.py • lines 1-80 of 110       │
│  1 from pydantic import BaseModel         │
│  2 ...                                     │
╰────────────────────────────────────────────╯

──────────────── Assistant ─────────────────
The configuration uses Pydantic models to validate
settings before the session starts.

[user]> /stats

Session Statistics
   turns: 1
   ...

[user]> /exit

Goodbye!
```

## 18. Design summary

The UI has three useful layers:

```text
main.py
  Handles process startup, input, slash commands, and event routing

ui/tui.py
  Handles formatting, Rich panels, syntax highlighting, and confirmation prompts

agent/events.py
  Defines the structured events passed between the agent and the CLI
```

The important idea is that the UI does not decide what the agent should do. It only:

1. Accepts user input
2. Sends normal text to the agent
3. Handles local commands
4. Receives structured agent events
5. Presents those events clearly
6. Asks the user before approved operations

In short:

> `main.py` controls the CLI flow, `TUI` controls terminal presentation, and
> `AgentEvent` objects connect agent execution to the user-visible output.

## 19. Current implementation notes

1. `TUI` uses Rich panels, rules, tables, Markdown, syntax highlighting, and prompts
   rather than manually writing ANSI escape sequences.

2. Assistant text is streamed with `markup=False`, preventing model output from being
   interpreted as Rich formatting.

3. Tool output is specialized by tool name. A renamed or custom tool uses the generic
   output path unless its name matches one of the built-in cases.

4. `/help` advertises `/checkpoints`, but the current command dispatcher does not
   implement that command.

5. The checkpoint usage error currently says `/restire` instead of `/restore`.

6. `CLI._get_tool_kind()` assumes the requested tool exists before reading
   `tool.kind`; an unknown tool event could therefore cause an attribute error.

7. The CLI displays output truncation separately from context compaction. A shortened
   terminal panel does not necessarily mean the conversation history was shortened.
