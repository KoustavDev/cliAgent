"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
from tools.builtin.edit_file import EditTool
from tools.builtin.glob import GlobTool
from tools.builtin.grep import GrepTool
from tools.builtin.list_dir import ListDirTool
from tools.builtin.memory import MemoryTool
from tools.builtin.read_file import ReadFileTool
from tools.builtin.shell import ShellTool
from tools.builtin.todo import TodosTool
from tools.builtin.web_fetch import WebFetchTool
from tools.builtin.web_search import WebSearchTool
from tools.builtin.write_file import WriteFileTool

__all__ = [
    "ReadFileTool",
    "WriteFileTool",
    "EditTool",
    "ShellTool",
    "ListDirTool",
    "GrepTool",
    "GlobTool",
    "WebSearchTool",
    "WebFetchTool",
    "TodosTool",
    "MemoryTool",
]


def get_all_builtin_tools() -> list[type]:
    # Step 1: Return the standard tool classes used by the default registry.
    """Return the all builtin tools needed by the caller."""
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
