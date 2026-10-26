# Understanding the Utilities

The [`utils/`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils>) package
contains small, reusable helpers used throughout the agent. These functions keep
common concerns out of tools and higher-level services.

The package currently contains:

| File                                                                                | Purpose                                                                                     |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| [`paths.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py>)   | Resolve paths, create parent directories, detect binary files, and format paths for display |
| [`text.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py>)     | Count tokens and safely shorten large text                                                  |
| [`errors.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/errors.py>) | Define structured application and configuration exceptions                                  |

The utilities do not run the agent or decide which tool to call. They provide common
building blocks:

```text
Built-in tools and UI
        |
        v
Reusable path/text/error helpers
        |
        v
Consistent behavior across the application
```

## 1. Why utilities are useful

Without shared helpers, every tool would need to implement its own version of:

- Relative-path resolution
- Parent-directory creation
- Binary-file detection
- Token counting
- Output truncation
- Structured configuration errors

That would produce duplicated and inconsistent behavior. The utilities centralize these
operations so that `read_file`, `write_file`, `edit`, `grep`, `glob`, the context
manager, and the terminal UI can use the same rules.

# `paths.py`

## 2. `resolve_path()`

[`resolve_path()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py:4>)
turns a user-supplied path into an absolute path.

```python
def resolve_path(base: str | Path, path: str | Path):
    path = Path(path)
    if path.is_absolute():
        return path.resolve()

    return Path(base).resolve() / path
```

It has two behaviors.

### Relative path

```python
resolve_path("C:/projects/demo", "src/main.py")
```

Result:

```text
C:\projects\demo\src\main.py
```

### Absolute path

```python
resolve_path("C:/projects/demo", "D:/shared/data.json")
```

Result:

```text
D:\shared\data.json
```

The base directory is ignored for an absolute path.

## 3. Where `resolve_path()` is used

The built-in tools use it before accessing files:

```python
path = resolve_path(invocation.cwd, params.path)
```

This appears in:

- `read_file`
- `write_file`
- `edit`
- `list_dir`
- `grep`
- `glob`
- The patch helper
- MCP-related path handling

For example, if the agent's working directory is:

```text
C:\projects\demo
```

and a tool receives:

```json
{ "path": "src/config.py" }
```

the tool operates on:

```text
C:\projects\demo\src\config.py
```

## 4. Important path-safety limitation

`resolve_path()` makes a path absolute, but it does not restrict the result to the base
directory.

For example:

```python
resolve_path("C:/projects/demo", "../secrets.txt")
```

produces a path outside the project:

```text
C:\projects\demo\..\secrets.txt
```

Because the relative branch does not call `.resolve()` after joining, the `..` component
may remain visible in the returned `Path`. The helper is therefore a path-normalization
convenience, not a complete sandbox or containment check.

## 5. `display_path_rel_to_cwd()`

[`display_path_rel_to_cwd()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py:12>)
formats a path for compact terminal display:

```python
def display_path_rel_to_cwd(path: str, cwd: Path | None) -> str:
```

If the path is inside `cwd`, it returns a relative path:

```python
display_path_rel_to_cwd(
    "C:/projects/demo/src/main.py",
    Path("C:/projects/demo"),
)
```

Result:

```text
src\main.py
```

If the path is outside the working directory, it returns the original path:

```text
D:\shared\data.json
```

The TUI uses this helper when rendering tool arguments:

```python
for key in ("path", "cwd"):
    display_args[key] = str(display_path_rel_to_cwd(val, self.cwd))
```

This changes only what the user sees. It does not change the path sent to a tool.

## 6. `ensure_parent_directory()`

[`ensure_parent_directory()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py:27>)
creates all missing parent directories:

```python
def ensure_parent_directory(path: str | Path) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    return path
```

Example:

```python
path = ensure_parent_directory(
    "C:/projects/demo/generated/reports/result.txt"
)
path.write_text("Done", encoding="utf-8")
```

If `generated/reports` does not exist, it is created before the file is written.

The helper returns the original `Path`, so it can be used in a short workflow:

```python
ensure_parent_directory(path).write_text(content, encoding="utf-8")
```

`write_file`, `edit`, and the patch helper use it when creating files or applying
changes.

## 7. `is_binary_file()`

[`is_binary_file()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/paths.py:34>)
checks the first 8192 bytes of a file:

```python
def is_binary_file(path: str | Path) -> bool:
    try:
        with open(path, "rb") as f:
            chunk = f.read(8192)
            return b"\x00" in chunk
    except (OSError, IOError):
        return False
```

If a NUL byte is found, it considers the file binary:

```python
is_binary_file("image.png")
# True, if a NUL byte appears in the first chunk
```

If the file contains ordinary text:

```python
is_binary_file("README.md")
# False
```

The `read_file`, `grep`, and `glob` tools use this helper to avoid treating binary
content as ordinary text.

### Limitation

This is a heuristic, not a full file-format detector. A binary file with no NUL byte in
the first 8192 bytes may be classified as text. Also, an unreadable or missing file
returns `False`, because the helper catches `OSError` and `IOError`.

# `text.py`

## 8. Why token utilities exist

Large text can cause two problems:

1. It can exceed the model's context window.
2. It can make terminal output difficult to read.

[`text.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py>) provides
token-aware helpers used by:

- [`context/manager.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/manager.py>)
  for context accounting
- [`ui/tui.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/ui/tui.py>) for
  display truncation
- The `read_file` tool for large file output

## 9. `get_tokenizer()`

[`get_tokenizer()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py:4>)
selects a tokenizer for a model:

```python
def get_tokenizer(model: str):
    try:
        encoding = tiktoken.encoding_for_model(model)
        return encoding.encode
    except Exception:
        encoding = tiktoken.get_encoding("cl100k_base")
        return encoding.encode
```

For a recognized model, it uses that model's encoding:

```python
tokenizer = get_tokenizer("gpt-4")
tokens = tokenizer("Hello, world!")
```

For an unknown model name, it falls back to `cl100k_base`, which is a general-purpose
encoding supported by `tiktoken`.

The fallback is useful when the configured model is custom or OpenAI-compatible but does
not have a tokenizer registered by name.

## 10. `count_tokens()`

[`count_tokens()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py:13>)
returns the number of tokens in a string:

```python
def count_tokens(text: str, model: str = "gpt-4") -> int:
```

Example:

```python
count_tokens("The agent reads this file.", "gpt-4")
# An integer such as 7
```

The exact count depends on the tokenizer and model.

The context manager uses it when storing messages:

```python
token_count=count_tokens(content, self._model_name)
```

This lets context management compare current usage with the configured context window.

## 11. `estimate_tokens()`

[`estimate_tokens()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py:22>)
provides a rough fallback estimate:

```python
def estimate_tokens(text: str) -> int:
    return max(1, len(text) // 4)
```

Example:

```python
estimate_tokens("a" * 100)
# 25
```

It approximates one token for every four characters and never returns less than `1`.

The current `count_tokens()` implementation normally returns the result of a
`tiktoken` tokenizer. The estimate helper remains available as a simple approximation,
but is not normally reached because `get_tokenizer()` falls back to `cl100k_base` rather
than returning `None`.

## 12. `truncate_text()`

[`truncate_text()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/text.py:26>)
shortens text to a token budget:

```python
def truncate_text(
    text: str,
    model: str,
    max_tokens: int,
    suffix: str = "\n... [truncated]",
    preserve_lines: bool = True,
):
```

Example:

```python
short_text = truncate_text(
    text=large_output,
    model="gpt-4",
    max_tokens=100,
)
```

If the text already fits, it returns the original text unchanged.

If it does not fit, it appends:

```text
... [truncated]
```

The suffix can be customized:

```python
truncate_text(
    large_output,
    "gpt-4",
    100,
    suffix="\n... [more output omitted]",
)
```

## 13. Line-preserving truncation

By default:

```python
preserve_lines=True
```

the helper keeps complete lines:

```text
line 1
line 2
line 3
... [truncated]
```

The algorithm:

1. Counts the tokens in the original text.
2. Counts the tokens in the suffix.
3. Reserves room for the suffix.
4. Adds complete lines until the target budget is reached.
5. Appends the suffix.

This is useful for logs, source code, and command output because it avoids cutting a
line in the middle.

## 14. Character-based truncation

If no complete line fits inside the target budget, or if:

```python
preserve_lines=False
```

the helper uses `_truncate_by_chars()`.

```python
truncate_text(
    text=large_text,
    model="gpt-4",
    max_tokens=100,
    preserve_lines=False,
)
```

The character-based helper uses binary search to find the longest prefix whose token
count fits:

```text
possible prefix lengths
          |
          v
binary search
          |
          v
longest fitting prefix + suffix
```

This is more precise than simply taking `max_tokens * 4` characters.

## 15. Truncation in the terminal UI

The TUI limits displayed output:

```python
self._max_block_tokens = 2500
```

For example, shell output is passed through:

```python
output_display = truncate_text(
    output,
    self.config.model_name,
    self._max_block_tokens,
)
```

The panel then adds:

```text
note: tool output was truncated
```

This protects the terminal display. It is different from context compaction, which
replaces old conversation history in the context manager.

## 16. Text utility flow example

Suppose a shell tool returns 20,000 lines:

```text
1. shell tool produces output
2. TUI calls count_tokens indirectly through truncate_text()
3. TUI keeps complete lines up to 2500 tokens
4. TUI appends "... [truncated]"
5. User sees a readable panel instead of the entire output
```

The original tool result and the displayed result are separate concepts.

# `errors.py`

## 17. `AgentError`

[`AgentError`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/errors.py:4>)
is the base structured exception for agent-related failures:

```python
class AgentError(Exception):
```

It accepts:

```python
AgentError(
    message,
    details=None,
    cause=None,
)
```

Example:

```python
raise AgentError(
    "Tool execution failed",
    details={"tool": "shell", "exit_code": 1},
)
```

Its string form includes details:

```text
Tool execution failed (tool=shell, exit_code=1)
```

If it wraps another exception:

```python
try:
    parse_data()
except ValueError as exc:
    raise AgentError(
        "Could not parse response",
        cause=exc,
    ) from exc
```

the string includes:

```text
Could not parse response [caused by: ...]
```

## 18. `AgentError.to_dict()`

The exception can be converted into structured data:

```python
error = AgentError(
    "Request failed",
    details={"status_code": 500},
)

error.to_dict()
```

Result:

```python
{
    "type": "AgentError",
    "message": "Request failed",
    "details": {"status_code": 500},
    "cause": None,
}
```

This is useful for logging, APIs, or event payloads where a string is not enough.

## 19. `ConfigError`

[`ConfigError`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/errors.py:34>)
specializes `AgentError` for configuration failures:

```python
class ConfigError(AgentError):
```

It adds two optional fields:

```python
config_key: str | None
config_file: str | None
```

Example:

```python
raise ConfigError(
    "Invalid model configuration",
    config_key="model.temperature",
    config_file="C:/projects/demo/.cli-agent/config.toml",
)
```

Its string representation includes the location:

```text
Invalid model configuration (
    config_key=model.temperature,
    config_file=C:/projects/demo/.cli-agent/config.toml
)
```

The actual formatting is a single line; the multiline form above is only for
readability.

## 20. Configuration loader integration

[`config/loader.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/loader.py>)
uses `ConfigError` when it cannot parse or read configuration:

```python
except tomli.TOMLDecodeError as e:
    raise ConfigError(
        "Invalid TOML in {path}: {e}",
        config_file=str(path),
    ) from e
```

The loader can therefore report not just that configuration failed, but which file was
involved.

The same error type is also used when final Pydantic configuration validation fails:

```python
raise ConfigError(f"Invalid configuration: {e}") from e
```

## 21. Why structured errors are better

Compare plain exceptions:

```python
raise Exception("Bad config")
```

with `ConfigError`:

```python
raise ConfigError(
    "Invalid TOML",
    config_key="mcp_servers.filesystem",
    config_file="C:/projects/demo/.cli-agent/config.toml",
)
```

The second form preserves machine-readable context:

```python
{
    "type": "ConfigError",
    "message": "Invalid TOML",
    "details": {
        "config_key": "mcp_servers.filesystem",
        "config_file": "C:/projects/demo/.cli-agent/config.toml",
    },
    "cause": None,
}
```

# 22. How the utilities work together

Consider the `read_file` workflow:

```text
User supplies "src/main.py"
        |
        v
resolve_path(cwd, "src/main.py")
        |
        v
is_binary_file(path)
        |
        v
read text content
        |
        v
count_tokens(output)
        |
        v
truncate_text(...) if output is too large
        |
        v
TUI renders the result
```

Consider the configuration workflow:

```text
Loader reads config.toml
        |
        v
TOML parsing fails
        |
        v
ConfigError(message, config_file=...)
        |
        v
CLI displays configuration error
```

Consider the file-writing workflow:

```text
User supplies "generated/report.txt"
        |
        v
resolve_path(cwd, path)
        |
        v
ensure_parent_directory(path)
        |
        v
write file
```

## 23. Utility boundaries

These helpers intentionally have narrow responsibilities:

| Utility                   | Does                                  | Does not                            |
| ------------------------- | ------------------------------------- | ----------------------------------- |
| `resolve_path`            | Builds an absolute path               | Enforce project containment         |
| `display_path_rel_to_cwd` | Shortens paths for display            | Change the actual path              |
| `ensure_parent_directory` | Creates parent folders                | Write file contents                 |
| `is_binary_file`          | Performs a NUL-byte heuristic         | Identify every binary format        |
| `count_tokens`            | Counts tokens using `tiktoken`        | Manage the context window           |
| `truncate_text`           | Shortens text to a token budget       | Persist the complete output         |
| `AgentError`              | Stores structured failure information | Automatically log or display errors |
| `ConfigError`             | Adds configuration location details   | Validate configuration itself       |

## 24. Current implementation notes

1. The relative branch of `resolve_path()` does not call `.resolve()` after joining the
   base and relative path, so `..` components are not fully normalized by this helper.

2. `is_binary_file()` only checks the first 8192 bytes and returns `False` when the file
   cannot be opened.

3. `get_tokenizer()` catches every exception while selecting a model tokenizer and
   falls back to `cl100k_base`.

4. `estimate_tokens()` exists as an approximate counter, but the current
   `count_tokens()` path normally receives a tokenizer from `tiktoken`, including the
   fallback tokenizer.

5. The `read_file` tool's large-output branch currently calls `truncate_text()` with an
   argument order that does not match its signature:

   ```python
   truncate_text(output, self.MAX_OUTPUT_TOKENS, suffix=...)
   ```

   The signature expects `(text, model, max_tokens, ...)`. If this branch is reached,
   it can raise a `TypeError` instead of truncating successfully. This is a caller bug
   in `read_file.py`, not a defect in the utility's intended algorithm.

6. `ConfigError` preserves the original exception through `cause`, but the loader's
   messages for invalid TOML currently use `{path}` and `{e}` literally instead of
   interpolating the values.

## Summary

The utilities package provides shared foundations:

```text
paths.py
  Makes file operations consistent

text.py
  Makes token accounting and output limits consistent

errors.py
  Makes failures structured and informative
```

In short:

> The utility modules are the small support layer that keeps path handling, text
> sizing, terminal output, and configuration errors consistent across the agent.
