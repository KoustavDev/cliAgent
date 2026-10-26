# Understanding `config/loader.py`

The [`config/loader.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/loader.py>) file is responsible for finding, reading, combining, and validating configuration before the rest of the application starts.

It is the boundary between external configuration sources and the typed [`Config`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>) object used by the agent.

## 1. Main responsibility

The loader performs these steps:

```text
Configuration files and environment
              |
              v
        load_config()
              |
              v
       Combined dictionary
              |
              v
          Config(...)
              |
              v
       Validated Config object
```

The rest of the application does not need to know:

- Where configuration files are stored
- Which configuration has higher priority
- How TOML is parsed
- How project configuration overrides system configuration
- How `AGENT.MD` becomes developer instructions

Those concerns are centralized in this file.

## 2. Configuration locations

### System configuration

`get_config_dir()` uses `platformdirs` to find the operating-system-specific user configuration directory:

```python
def get_config_dir() -> Path:
    return Path(user_config_dir("cli-agent"))
```

The system configuration file is:

```text
<user config directory>/cli-agent/config.toml
```

`get_system_config_path()` builds this path:

```python
def get_system_config_path() -> Path:
    return get_config_dir() / CONFIG_FILE_NAME
```

Using `platformdirs` means the code does not hard-code a Windows, macOS, or Linux path.

### Project configuration

For a selected working directory, `_get_project_config()` looks for:

```text
<working directory>/.cli-agent/config.toml
```

This allows each project to have configuration specific to that project.

### Developer instructions

The loader also looks for:

```text
<working directory>/AGENT.MD
```

When found, the file contents are stored in `Config.developer_instructions`. These instructions can later be included in the model's system prompt by [`prompts/system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/prompts/system.py>).

## 3. Important constants

```python
CONFIG_FILE_NAME = "config.toml"
AGENT_MD_FILE = "AGENT.MD"
```

Keeping these names in one place prevents different parts of the application from using inconsistent filenames.

## 4. Reading TOML files

`_parse_toml()` reads a TOML file in binary mode and parses it with `tomli`:

```python
def _parse_toml(path: Path):
    with open(path, "rb") as f:
        return tomli.load(f)
```

The returned value is a dictionary that can be passed to `Config`:

```python
{
    "max_turns": 50,
    "approval": "on-request",
    "model": {
        "name": "gpt-4o",
        "temperature": 0.7,
    },
}
```

### Error conversion

The loader converts file and parsing failures into the project-specific [`ConfigError`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/utils/errors.py>):

- Invalid TOML raises a configuration error
- File access failures raise a configuration error

This gives callers a consistent error type instead of exposing parser-specific or operating-system-specific exceptions.

## 5. Configuration precedence

`load_config()` loads sources in this order:

```text
1. System configuration
2. Project configuration
3. Working-directory fallback
4. AGENT.MD fallback
5. Pydantic Config validation
```

The project configuration has higher priority than the system configuration.

For example, suppose the system file contains:

```toml
max_turns = 100
max_prompt_tokens = 50000

[model]
temperature = 1.0
```

and the project file contains:

```toml
max_turns = 30
max_prompt_tokens = 50000

[model]
name = "gpt-4o"
```

The resulting values are conceptually:

```text
max_turns = 30
max_prompt_tokens = 50000
model.temperature = 1.0
model.name = "gpt-4o"
```

The project file overrides `max_turns` and `max_prompt_tokens`, while the system value for `model.temperature` is preserved. These limits apply independently to each user prompt. When a limit is reached, interactive sessions ask for confirmation before continuing; non-interactive sessions stop.

## 6. Recursive dictionary merging

`_merge_dicts()` combines two dictionaries:

```python
def _merge_dicts(base, override):
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value
    return result
```

Its behavior is:

- New keys from the override are added
- Existing scalar values are replaced
- Nested dictionaries are merged recursively
- Lists are replaced as a whole rather than merged element by element

This is important for nested settings such as `[model]` and `[shell_environment]`.

## 7. The `load_config()` lifecycle

The main function is:

```python
def load_config(cwd: Path | None) -> Config:
```

### Step 1: Select the working directory

```python
cwd = cwd or Path.cwd()
```

If the CLI provides `--cwd`, that path is used. Otherwise, the process's current directory is used.

### Step 2: Load the system configuration

If the system `config.toml` exists, it is parsed.

If it is invalid, the loader logs a warning and continues with an empty configuration dictionary. This makes a broken optional system configuration non-fatal.

### Step 3: Load the project configuration

If `<cwd>/.cli-agent/config.toml` exists, it is parsed and merged over the system configuration.

### Step 4: Set the working directory fallback

If neither configuration file provides `cwd`, the selected working directory is added:

```python
if "cwd" not in config_dict:
    config_dict["cwd"] = cwd
```

This ensures the final `Config` object always represents the directory selected by the CLI.

### Step 5: Set developer instructions

If no `developer_instructions` value was configured, the loader reads `AGENT.MD` from the working directory and uses its contents:

```python
if "developer_instructions" not in config_dict:
    agent_md_content = _get_agent_md_files(cwd)
    if agent_md_content:
        config_dict["developer_instructions"] = agent_md_content
```

An explicitly configured `developer_instructions` value therefore takes priority over `AGENT.MD`.

### Step 6: Build the typed `Config`

Finally, the combined dictionary is passed to the configuration model:

```python
config = Config(**config_dict)
```

Pydantic then validates:

- Field types
- Enum values
- Numeric limits
- Nested models
- MCP transport rules
- Hook requirements

If validation fails, the loader wraps the failure in `ConfigError`.

## 8. Example configuration flow

Assume the CLI is started with:

```text
python main.py --cwd C:/projects/demo
```

The loader checks:

```text
<user config directory>/cli-agent/config.toml
C:/projects/demo/.cli-agent/config.toml
C:/projects/demo/AGENT.MD
```

It then performs:

```text
system config
      +
project overrides
      +
cwd fallback
      +
AGENT.MD fallback
      |
      v
Config(...)
```

The resulting object is passed from [`main.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/main.py>) into `CLI`, then into `Agent`, `Session`, tools, hooks, MCP, and the LLM client.

## 9. Why the loader is useful

Without `loader.py`, every component might independently:

- Read its own TOML file
- Read environment variables
- Decide which configuration wins
- Handle parsing failures
- Locate project instructions

That would create duplicated logic and inconsistent behavior.

The loader provides one reliable entry point:

```python
config = load_config(cwd)
```

After that, components only need the resulting `Config` object.

## 10. Error-handling behavior

There are two different error behaviors:

### Optional configuration files

Invalid system or project TOML is logged as a warning and skipped by `load_config()`.

### Final configuration model

If the combined values cannot create a valid `Config`, `load_config()` raises `ConfigError`.

This distinction allows missing or invalid optional files to be skipped while still rejecting configuration that reaches the model but violates the schema.

## 11. Current implementation notes

The current loader has a few details worth knowing:

1. The warning in the project-configuration exception branch says `"Skipping invalid system config"` even though it is handling the project file. The message should refer to the project configuration.

2. `_get_agent_md_files()` is annotated as returning `Path | None`, but it actually returns the file contents as `str | None`. The annotation should match the actual return value.

3. The loader logs and skips invalid system/project TOML files. This is intentional behavior, but it can hide configuration mistakes unless the log output is visible to the user.

4. Environment variables such as `API_KEY`, `BASE_URL`, and `MODEL_NAME` are handled mainly by [`config/config.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/config.py>), not directly by this loader. The loader's job is primarily file discovery, TOML parsing, merging, and `Config` construction.

## Summary

`config/loader.py` is the configuration assembly layer.

Its responsibilities are:

```text
Locate files
  -> Parse TOML
  -> Merge system and project settings
  -> Apply cwd and AGENT.MD fallbacks
  -> Construct validated Config
  -> Return one shared configuration object
```

The rest of the application can therefore depend on a single, validated `Config` object instead of knowing where settings came from.
