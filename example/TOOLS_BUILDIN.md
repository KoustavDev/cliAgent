# Understanding the Built-in Tools

The built-in tools are the standard capabilities available to the AI agent.

They are defined in the [`tools/builtin/`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin>) package and registered by [`get_all_builtin_tools()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/__init__.py>).

The current built-in tools are:

| Tool name    | Purpose                                        | Kind      |
| ------------ | ---------------------------------------------- | --------- |
| `read_file`  | Read text files                                | `READ`    |
| `write_file` | Create or overwrite files                      | `WRITE`   |
| `edit`       | Make precise text replacements                 | `WRITE`   |
| `shell`      | Run system commands                            | `SHELL`   |
| `list_dir`   | List directory contents                        | `READ`    |
| `grep`       | Search file contents with a regular expression | `READ`    |
| `glob`       | Find files by a glob pattern                   | `READ`    |
| `web_search` | Search the web                                 | `NETWORK` |
| `web_fetch`  | Fetch a URL                                    | `NETWORK` |
| `todos`      | Manage the current session's task list         | `MEMORY`  |
| `memory`     | Store persistent user memory                   | `MEMORY`  |

The basic flow is:

```text
User request
      |
      v
Model chooses a built-in tool
      |
      v
ToolRegistry validates the arguments
      |
      v
Approval and hooks are applied when needed
      |
      v
Tool executes
      |
      v
ToolResult returns to the model
```

Every built-in tool follows the common contract described by [`Tool`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>).

## 1. How built-in tools are registered

The package initializer imports all built-in tool classes:

```python
from tools.builtin.edit_file import EditTool
from tools.builtin.glob import GlobTool
from tools.builtin.grep import GrepTool
...
```

Then `get_all_builtin_tools()` returns their classes:

```python
def get_all_builtin_tools() -> list[type]:
    return [
        ReadFileTool,
        WriteFileTool,
        EditTool,
        ShellTool,
        ListDirTool,
        GrepTool,
        GlobTool,
        WebSearchTool,
        WebFetchTool,
        TodosTool,
        MemoryTool,
    ]
```

[`create_default_registry()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>) creates an instance of each class and registers it:

```python
for tool_class in get_all_builtin_tools():
    registry.register(tool_class(config))
```

This happens when a [`Session`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>) is created.

## 2. Tool categories and approval

The tool kind determines whether a tool is considered mutating:

```text
READ       Usually no confirmation
WRITE      May change files
SHELL      Executes system commands
NETWORK    Accesses external services
MEMORY     Changes stored state
```

`WRITE`, `SHELL`, `NETWORK`, and `MEMORY` tools are treated as mutating by the base tool class and can pass through the approval manager.

The model cannot bypass this process. The call goes through [`ToolRegistry.invoke()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>), which performs validation, hooks, approval, execution, and result handling.

# File and project inspection tools

## 3. `read_file`

Implementation: [`tools/builtin/read_file.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/read_file.py>)

### Purpose

`read_file` reads the contents of a text file and returns the lines with line numbers.

It is useful for:

- Understanding source code
- Reading configuration
- Inspecting documentation
- Reading a specific section of a large file

It does not modify files.

### Parameters

```python
class ReadFileParams(BaseModel):
    path: str
    offset: int = 1
    limit: int | None = None
```

| Parameter | Meaning                                                  |
| --------- | -------------------------------------------------------- |
| `path`    | File path, relative to the working directory or absolute |
| `offset`  | First line to read, starting at 1                        |
| `limit`   | Maximum number of lines to read                          |

### Example request

```json
{
  "path": "config/config.py",
  "offset": 1,
  "limit": 40
}
```

### Example output

```text
     1|from enum import Enum
     2|import os
     3|
     4|class Config(BaseModel):
     5|    ...
```

### Safety and limits

The tool:

- Rejects missing paths
- Rejects directories
- Rejects binary files
- Rejects files larger than 10 MB
- Falls back from UTF-8 to Latin-1 when needed
- Limits output to 25,000 tokens
- Marks output as truncated if necessary

For a large file, use:

```json
{
  "path": "large_file.py",
  "offset": 200,
  "limit": 80
}
```

## 4. `list_dir`

Implementation: [`tools/builtin/list_dir.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/list_dir.py>)

### Purpose

`list_dir` lists the files and subdirectories inside a directory.

Directories are shown with a trailing slash:

```text
config/
agent/
README.md
```

### Parameters

```python
class ListDirParams(BaseModel):
    path: str = "."
    include_hidden: bool = False
```

| Parameter        | Meaning                          |
| ---------------- | -------------------------------- |
| `path`           | Directory to list                |
| `include_hidden` | Include names beginning with `.` |

### Example request

```json
{
  "path": "tools",
  "include_hidden": false
}
```

### Example output

```text
builtin/
base.py
discovery.py
registry.py
subagents.py
```

Directories are sorted before files, and hidden items are excluded unless explicitly requested.

## 5. `glob`

Implementation: [`tools/builtin/glob.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/glob.py>)

### Purpose

`glob` finds files matching a file pattern.

It supports recursive patterns such as:

```text
**/*.py
```

It is useful when the exact file name or directory is not known.

### Parameters

```python
class GlobParams(BaseModel):
    pattern: str
    path: str = "."
```

| Parameter | Meaning                      |
| --------- | ---------------------------- |
| `pattern` | Glob pattern to match        |
| `path`    | Directory in which to search |

### Example request

```json
{
  "pattern": "**/*Config*.py",
  "path": "."
}
```

### Example output

```text
config/config.py
config/loader.py
```

Only files are returned. Results are limited to the first 1,000 matches in the output.

## 6. `grep`

Implementation: [`tools/builtin/grep.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/grep.py>)

### Purpose

`grep` searches file contents with a regular expression and returns matching lines with file names and line numbers.

It is useful for finding:

- Class definitions
- Function calls
- Configuration fields
- TODO comments
- References to a symbol

### Parameters

```python
class GrepParams(BaseModel):
    pattern: str
    path: str = "."
    case_insensitive: bool = False
```

| Parameter          | Meaning                          |
| ------------------ | -------------------------------- |
| `pattern`          | Regular expression to search for |
| `path`             | File or directory to search      |
| `case_insensitive` | Ignore letter case when matching |

### Example request

```json
{
  "pattern": "class\\s+\\w*Config\\w*",
  "path": ".",
  "case_insensitive": false
}
```

### Example output

```text
=== config/config.py ===
13:class ModelConfig(BaseModel):
90:class Config(BaseModel):
```

The tool skips common large/generated directories:

```text
node_modules
__pycache__
.git
.venv
venv
```

It also skips hidden files during recursive directory search.

If the regular expression is invalid, it returns an error result instead of executing the search.

# File modification tools

## 7. `write_file`

Implementation: [`tools/builtin/write_file.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/write_file.py>)

### Purpose

`write_file` creates a file or completely replaces its contents.

Use it when:

- Creating a new file
- Rewriting a complete file
- Writing generated content

For a small partial change, use `edit` instead.

### Parameters

```python
class WriteFileParams(BaseModel):
    path: str
    content: str
    create_directories: bool = True
```

| Parameter            | Meaning                           |
| -------------------- | --------------------------------- |
| `path`               | File to create or overwrite       |
| `content`            | Complete content to write         |
| `create_directories` | Create missing parent directories |

### Example request

```json
{
  "path": "notes/example.txt",
  "content": "First line\nSecond line\n",
  "create_directories": true
}
```

### Example result

```text
Created C:\project\notes\example.txt 2 lines
```

If the file already exists, it is overwritten:

```text
Updated C:\project\notes\example.txt 2 lines
```

### Confirmation and diff

`write_file` is a `WRITE` tool. Before execution it:

1. Reads the old content, if the file exists
2. Creates a [`FileDiff`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/base.py>)
3. Adds the diff to `ToolConfirmation`
4. Lets the user review the proposed change

Overwriting an existing file is marked as dangerous, while creating a new file is not marked dangerous by this tool.

The execution result also includes a `FileDiff`.

## 8. `edit`

Implementation: [`tools/builtin/edit_file.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/edit_file.py>)

### Purpose

`edit` performs a precise text replacement.

Use it for:

- Changing one function
- Updating a configuration value
- Replacing a known block
- Making a surgical modification

### Parameters

```python
class EditParams(BaseModel):
    path: str
    old_string: str = ""
    new_string: str
    replace_all: bool = False
```

| Parameter     | Meaning                                                 |
| ------------- | ------------------------------------------------------- |
| `path`        | File to edit                                            |
| `old_string`  | Exact text to find                                      |
| `new_string`  | Replacement text; can be empty to delete                |
| `replace_all` | Replace every occurrence instead of requiring one match |

The old text must match exactly, including whitespace and indentation.

### Example request

Suppose `settings.py` contains:

```python
DEBUG = False
```

The tool request is:

```json
{
  "path": "settings.py",
  "old_string": "DEBUG = False",
  "new_string": "DEBUG = True",
  "replace_all": false
}
```

The result is:

```text
Edited C:\project\settings.py: replaced 1 occurrence(s)
```

### Matching behavior

The tool returns an error when:

- The file does not exist and `old_string` is not empty
- `old_string` is empty for an existing file
- The old text is not found
- The old text appears more than once and `replace_all` is false
- The replacement makes no change

For a new file, use an empty `old_string`:

```json
{
  "path": "new_file.py",
  "old_string": "",
  "new_string": "print('hello')\n"
}
```

### Confirmation and diff

Before editing, the tool calculates the expected new content and creates a `FileDiff`. The user can review the exact change before approval.

# System and network tools

## 9. `shell`

Implementation: [`tools/builtin/shell.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/shell.py>)

### Purpose

`shell` executes a system command.

It is useful for:

- Running tests
- Checking Git status
- Building the project
- Installing dependencies
- Running scripts
- Inspecting system output

### Parameters

```python
class ShellParams(BaseModel):
    command: str
    timeout: int = 120
    cwd: str | None = None
```

| Parameter | Meaning                            |
| --------- | ---------------------------------- |
| `command` | Command to execute                 |
| `timeout` | Maximum execution time in seconds  |
| `cwd`     | Optional command working directory |

### Example request

```json
{
  "command": "python -m pytest tests",
  "timeout": 120,
  "cwd": "."
}
```

### Example result

```text
5 passed in 1.23s
```

### Safety behavior

`ShellTool` is a `SHELL` tool and always creates a confirmation object.

It checks a list of blocked command patterns, including:

```text
rm -rf /
rm -rf ~
mkfs
fdisk
shutdown
reboot
chmod 777 /
fork bomb syntax
```

Blocked commands return an error:

```text
Command blocked for safety: ...
```

The command is executed through:

- `cmd.exe /c` on Windows
- `/bin/bash -c` on other platforms

Output combines stdout and stderr. Non-zero exit codes are included in the result, and output larger than 100 KB is truncated.

The environment is filtered using `config.shell_environment`, so variables matching patterns such as `*KEY*`, `*TOKEN*`, and `*SECRET*` are excluded by default.

## 10. `web_search`

Implementation: [`tools/builtin/web_search.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/web_search.py>)

### Purpose

`web_search` searches the web and returns titles, URLs, and snippets.

It is useful when the agent needs:

- Current documentation
- External references
- Public information
- Search results before fetching a page

### Parameters

```python
class WebSearchParams(BaseModel):
    query: str
    max_results: int = 10
```

`max_results` must be between 1 and 20.

### Example request

```json
{
  "query": "Pydantic BaseModel validation",
  "max_results": 5
}
```

### Example output

```text
Search results for: Pydantic BaseModel validation
1. Title: Models | Pydantic
   URL: https://docs.pydantic.dev/...
   Snippet: ...
```

The implementation uses `duckduckgo_search` with safe search disabled and a one-year time limit.

This is a `NETWORK` tool, so it can require approval according to the active approval policy.

## 11. `web_fetch`

Implementation: [`tools/builtin/web_fetch.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/web_fetch.py>)

### Purpose

`web_fetch` downloads the text body of a URL.

It is useful after `web_search` finds a relevant page, or when the user gives a direct URL.

### Parameters

```python
class WebFetchParams(BaseModel):
    url: str
    timeout: int = 30
```

| Parameter | Meaning                               |
| --------- | ------------------------------------- |
| `url`     | Must use `http://` or `https://`      |
| `timeout` | Request timeout from 5 to 120 seconds |

### Example request

```json
{
  "url": "https://docs.python.org/3/library/pathlib.html",
  "timeout": 30
}
```

### Example result

```text
<!doctype html>
<html>
...
```

The tool:

- Rejects non-HTTP URLs
- Follows redirects
- Raises errors for unsuccessful HTTP status codes
- Limits response text to 100 KB
- Returns status code and content length in metadata

Because it accesses the network, it is classified as `NETWORK`.

# State and planning tools

## 12. `todos`

Implementation: [`tools/builtin/todo.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/todo.py>)

### Purpose

`todos` manages a task list for the current session.

It helps the agent track multi-step work:

```text
1. Inspect configuration
2. Implement the change
3. Run tests
```

The list is stored in memory on the `TodosTool` instance. It is not persisted to `user_memory.json` or session snapshots by this tool.

### Parameters

```python
class TodosParams(BaseModel):
    action: str
    id: str | None = None
    content: str | None = None
```

Supported actions:

```text
add
complete
list
clear
```

### Add example

```json
{
  "action": "add",
  "content": "Run the test suite"
}
```

Example result:

```text
Added todo [a1b2c3d4]: Run the test suite
```

The generated ID is needed to complete the task.

### List example

```json
{
  "action": "list"
}
```

Output:

```text
Todos:
  [a1b2c3d4] Run the test suite
```

### Complete example

```json
{
  "action": "complete",
  "id": "a1b2c3d4"
}
```

Output:

```text
Completed todo [a1b2c3d4]: Run the test suite
```

### Clear example

```json
{
  "action": "clear"
}
```

Output:

```text
Cleared 2 todos
```

## 13. `memory`

Implementation: [`tools/builtin/memory.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/builtin/memory.py>)

### Purpose

`memory` stores user preferences and notes in a persistent JSON file.

Unlike `todos`, memory survives the current session and can be loaded in later sessions by [`Session._load_memory()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>).

The file is:

```text
<application data directory>/cli-agent/user_memory.json
```

### Parameters

```python
class MemoryParams(BaseModel):
    action: str
    key: str | None = None
    value: str | None = None
```

Supported actions:

```text
set
get
delete
list
clear
```

### Set example

```json
{
  "action": "set",
  "key": "preferred_language",
  "value": "Python"
}
```

Output:

```text
Set memory: preferred_language
```

The JSON file becomes:

```json
{
  "entries": {
    "preferred_language": "Python"
  }
}
```

### Get example

```json
{
  "action": "get",
  "key": "preferred_language"
}
```

Output:

```text
Memory found: preferred_language: Python
```

### List example

```json
{
  "action": "list"
}
```

Output:

```text
Stored memories:
  preferred_language: Python
```

### Delete example

```json
{
  "action": "delete",
  "key": "preferred_language"
}
```

### Clear example

```json
{
  "action": "clear"
}
```

This removes all stored entries.

`memory` is a `MEMORY` tool, so changes may require approval.

# 14. Typical investigation workflow

The built-in inspection tools work well together:

```text
User asks: "Where is Config used?"
        |
        v
list_dir(".")
        |
        v
glob("**/*.py")
        |
        v
grep("Config", ".")
        |
        v
read_file("config/config.py")
```

The model can use:

- `list_dir` to understand the structure
- `glob` to find candidate files
- `grep` to locate references
- `read_file` to inspect the implementation

# 15. Typical editing workflow

For a small change:

```text
read_file("settings.py")
        |
        v
edit(
    path="settings.py",
    old_string="DEBUG = False",
    new_string="DEBUG = True"
)
        |
        v
User reviews FileDiff
        |
        v
Change is approved and applied
```

For a complete new file:

```text
write_file(
    path="new_module.py",
    content="..."
)
```

For verification:

```text
shell(command="python -m pytest")
```

# 16. Typical web research workflow

```text
web_search("Python pathlib documentation")
        |
        v
Select a relevant URL
        |
        v
web_fetch("https://docs.python.org/...")
        |
        v
Use the page content in the response
```

Both operations are network operations and should be used carefully.

# 17. Built-in tool lifecycle

Every call follows the shared registry path:

```text
Model creates tool call
        |
        v
ToolRegistry finds the tool
        |
        v
Pydantic validates parameters
        |
        v
before_tool hooks run
        |
        v
Approval manager checks mutating/network operations
        |
        v
Tool.execute() runs
        |
        v
Exceptions become ToolResult errors
        |
        v
after_tool hooks run
        |
        v
Result is added to conversation context
```

Read-only inspection tools normally proceed without confirmation. File, shell, network, todo, and memory operations can be subject to the configured approval policy.

# 18. Tool allowlisting

The configuration can restrict which built-in tools are exposed:

```toml
allowed_tools = ["read_file", "grep", "list_dir"]
```

Then `ToolRegistry.get_tools()` returns only those named tools, and the model receives only their schemas.

For example, with the configuration above:

```text
Available:
  read_file
  grep
  list_dir

Not exposed:
  write_file
  edit
  shell
  web_search
  web_fetch
```

# 19. Current implementation notes

1. `TodosTool` stores todos only in the current tool instance, so they are lost when the session or registry is recreated.

2. `MemoryTool` persists data in `user_memory.json`, which is later included in a new session's system prompt.

3. `WebSearchParams.max_results` is validated, but the current `WebSearchTool.execute()` implementation does not pass that value into the DuckDuckGo search call or explicitly slice the returned results. The requested limit may therefore not be enforced.

4. `GlobTool` contains a private `_find_files()` helper, but `execute()` uses `Path.glob()` directly, so that helper is currently unused.

5. File paths are resolved through `resolve_path()` and command execution uses the configured working directory. The exact path-safety behavior is implemented in [`utils/paths.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py>).

6. Network tools return large text bodies, but `web_fetch` limits the response to 100 KB and `read_file` limits output to 25,000 tokens to reduce context pressure.

## Summary

The built-in tools provide the agent's standard capabilities:

```text
Inspect files and directories
  -> Search source code
  -> Create and edit files
  -> Run commands
  -> Search and fetch web content
  -> Track current tasks
  -> Remember user preferences
```

Each tool defines a Pydantic parameter schema and an asynchronous `execute()` method. The common registry applies validation, hooks, approval, and error handling so the model can use all built-in tools through one consistent and controlled interface.
