"""Load and merge system, project, and workspace instruction configuration."""

from pathlib import Path
from typing import Any

from platformdirs import user_config_dir, user_data_dir
import tomli

from config.config import Config
from utils.errors import ConfigError
import logging

logger = logging.getLogger(__name__)
CONFIG_FILE_NAME = "config.toml"

AGENT_MD_FILE = "AGENTS.MD"


def get_config_dir() -> Path:
    """Return the platform-specific directory for user configuration."""
    return Path(user_config_dir("ai-agent"))


def get_data_dir() -> Path:
    """Return the platform-specific directory for agent data."""
    return Path(user_data_dir("ai-agent"))


def get_system_config_path() -> Path:
    """Build the path to the system-level TOML configuration file."""
    return get_config_dir() / CONFIG_FILE_NAME


def _parse_toml(path: Path):
    """Read one TOML file and convert filesystem errors into ConfigError."""
    try:
        with open(path, "rb") as f:
            return tomli.load(f)
    except tomli.TOMLDecodeError as e:
        raise ConfigError("Invalid TOML in {path}: {e}", config_file=str(path)) from e
    except (OSError, IOError) as e:
        raise ConfigError(
            "Failed to read config file {path}: {e}", config_file=str(path)
        ) from e


def _get_project_config(cwd: Path) -> Path | None:
    """Find a project config in the workspace's .ai-agent directory."""
    current = cwd.resolve()
    agent_dir = current / ".ai-agent"

    if agent_dir.is_dir():
        config_file = agent_dir / CONFIG_FILE_NAME
        if config_file.is_file():
            return config_file

    return None


def _get_agent_md_files(cwd: Path) -> Path | None:
    """Read workspace developer instructions from AGENTS.MD, when present."""
    current = cwd.resolve()

    if current.is_dir():
        agent_md_file = current / AGENT_MD_FILE
        if agent_md_file.is_file():
            content = agent_md_file.read_text(encoding="utf-8")
            return content

    return None


def _merge_dicts(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Recursively overlay project values on top of base configuration."""
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _merge_dicts(result[key], value)
        else:
            result[key] = value

    return result


def load_config(cwd: Path | None) -> Config:
    """Load, merge, and validate configuration for the supplied workspace."""
    cwd = cwd or Path.cwd()

    system_path = get_system_config_path()

    config_dict: dict[str, Any] = {}

    if system_path.is_file():
        try:
            # Start with optional user-wide settings; invalid files are non-fatal.
            config_dict = _parse_toml(system_path)
        except ConfigError:
            logger.warning(f"Skipping invalid system config: {system_path}")

    project_path = _get_project_config(cwd)
    if project_path:
        try:
            # Overlay project settings so they take precedence over system values.
            project_config_dict = _parse_toml(project_path)
            config_dict = _merge_dicts(config_dict, project_config_dict)
        except ConfigError:
            logger.warning(f"Skipping invalid system config: {system_path}")

    if "cwd" not in config_dict:
        # Keep the resolved workspace explicit even when no config file sets it.
        config_dict["cwd"] = cwd

    if "developer_instructions" not in config_dict:
        agent_md_content = _get_agent_md_files(cwd)
        if agent_md_content:
            config_dict["developer_instructions"] = agent_md_content

    try:
        config = Config(**config_dict)
    except Exception as e:
        raise ConfigError(f"Invalid configuration: {e}") from e

    return config
