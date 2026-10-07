"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field

from utils.paths import resolve_path


class ListDirParams(BaseModel):
    """Represent listdirparams state and behavior."""
    path: str = Field(
        ".", description="Directory path to list (default: current directory)"
    )
    include_hidden: bool = Field(
        False,
        description="Whether to include hidden files and directories (default: false",
    )


class ListDirTool(Tool):
    """Represent listdirtool state and behavior."""
    name = "list_dir"
    description = "List contents of a directory"
    kind = ToolKind.READ
    schema = ListDirParams

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # Step 1: Resolve the directory and format its immediate entries.
        """Perform the execute operation and return its result."""
        params = ListDirParams(**invocation.params)

        dir_path = resolve_path(invocation.cwd, params.path)

        if not dir_path.exists() or not dir_path.is_dir():
            return ToolResult.error_result(f"Directory does not exist: {dir_path}")

        try:
            items = sorted(
                dir_path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
        except Exception as e:
            return ToolResult.error_result(f"Error listing directory: {e}")

        if not params.include_hidden:
            items = [item for item in items if not item.name.startswith(".")]

        if not items:
            return ToolResult.success_result(
                "Directory is empty", metadata={"path": str(dir_path), "entries": 0}
            )

        lines = []

        for item in items:
            if item.is_dir():
                lines.append(f"{item.name}/")
            else:
                lines.append(item.name)

        return ToolResult.success_result(
            "\n".join(lines),
            metadata={
                "path": str(dir_path),
                "entries": len(items),
            },
        )
