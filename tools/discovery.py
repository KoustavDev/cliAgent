"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
import importlib.util
import inspect
from pathlib import Path
import sys
from typing import Any
from config.config import Config
from config.loader import get_config_dir
from tools.base import Tool
from tools.registry import ToolRegistry


class ToolDiscoveryManager:
    """Represent tooldiscoverymanager state and behavior."""
    def __init__(self, config: Config, registry: ToolRegistry):
        """Initialize the object with the configuration needed by later steps."""
        self.config = config
        self.registry = registry

    def _load_tool_modules(self, file_path: Path) -> Any:
        # Step 1: Load a Python file under a unique module name.
        """Support the load tool modules step used by the public workflow."""
        module_name = f"discovered_tool_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)

        if spec is None or spec.loader is None:
            return ImportError(f"Could not load spec from {file_path}")

        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module

        spec.loader.exec_module(module)
        return module

    def _find_tool_classes(self, module: Any) -> list[Tool]:
        # Step 1: Select concrete Tool subclasses defined by this module.
        """Support the find tool classes step used by the public workflow."""
        tools: list[Tool] = []

        for name in dir(module):
            obj = getattr(module, name)
            if (
                inspect.isclass(obj)
                and issubclass(obj, Tool)
                and obj is not Tool
                and obj.__module__ == module.__name__
            ):
                tools.append(obj)

        return tools

    def discover_from_directory(self, directory: Path) -> None:
        # Step 1: Inspect the directory's user-tool folder and register discoveries.
        """Perform the discover from directory operation."""
        tool_dir = directory / ".cli-agent" / "tools"

        if not tool_dir.exists() or not tool_dir.is_dir():
            return

        for py_file in tool_dir.glob("*.py"):
            try:
                if py_file.name.startswith("__"):
                    continue

                module = self._load_tool_modules(py_file)
                tool_classes = self._find_tool_classes(module)

                if not tool_classes:
                    continue

                for tool_class in tool_classes:
                    tool = tool_class(self.config)
                    self.registry.register(tool)
            except Exception:
                continue

    def discover_all(self) -> None:
        # Step 1: Search both the project and user configuration directories.
        """Perform the discover all operation."""
        self.discover_from_directory(self.config.cwd)
        self.discover_from_directory(get_config_dir())
