"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
import uuid
from config.config import Config
from tools.base import Tool, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field


class TodosParams(BaseModel):
    """Represent todosparams state and behavior."""
    action: str = Field(..., description="Action: 'add', 'complete', 'list', 'clear'")
    id: str | None = Field(None, description="Todo ID (for complete)")
    content: str | None = Field(None, description="Todo content (for add)")


class TodosTool(Tool):
    """Represent todostool state and behavior."""
    name = "todos"
    description = "Manage a task list for the current session. Use this to track progress on multi-step tasks."
    kind = ToolKind.MEMORY
    schema = TodosParams

    def __init__(self, config: Config) -> None:
        """Initialize the object with the configuration needed by later steps."""
        super().__init__(config)
        self._todos: dict[str, str] = {}

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        # Step 1: Dispatch the requested todo operation against session storage.
        """Perform the execute operation and return its result."""
        params = TodosParams(**invocation.params)

        if params.action.lower() == "add":
            if not params.content:
                return ToolResult.error_result("`content` required for 'add' action")
            todo_id = str(uuid.uuid4())[:8]
            self._todos[todo_id] = params.content
            return ToolResult.success_result(
                f"Added todo [{todo_id}]: {params.content}"
            )
        elif params.action.lower() == "complete":
            if not params.id:
                return ToolResult.error_result("`id` required for 'complete' action")
            if params.id not in self._todos:
                return ToolResult.error_result(f"Todo not found: {params.id}")

            content = self._todos.pop(params.id)
            return ToolResult.success_result(f"Completed todo [{params.id}]: {content}")
        elif params.action == "list":
            if not self._todos:
                return ToolResult.success_result("No todos")
            lines = ["Todos:"]

            for todo_id, content in self._todos.items():
                lines.append(f"  [{todo_id}] {content}")
            return ToolResult.success_result("\n".join(lines))
        elif params.action == "clear":
            count = len(self._todos)
            self._todos.clear()
            return ToolResult.success_result(f"Cleared {count} todos")
        else:
            return ToolResult.error_result(f"Unknown action: {params.action}")
