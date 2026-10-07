"""Manual smoke test for shell execution on the host platform."""

import asyncio
from pathlib import Path
from config.config import Config
from tools.base import ToolInvocation
from tools.builtin.shell import ShellTool

async def test():
    """Create, inspect, and remove a path containing spaces."""
    config = Config(cwd=Path.cwd())
    shell = ShellTool(config)

    # 1. Test directory creation with spaces
    test_dir = Path.cwd() / "test web dir"
    res1 = await shell.execute(
        ToolInvocation(
            params={"command": f'mkdir "{test_dir}"'},
            cwd=Path.cwd(),
        )
    )
    print("1. Mkdir Result:")
    print("Success:", res1.success)
    print("Output:", res1.output)
    print("Error:", res1.error)

    # 2. Test listing in PowerShell
    res2 = await shell.execute(
        ToolInvocation(
            params={"command": f'Get-ChildItem -Path "{test_dir}"'},
            cwd=Path.cwd(),
        )
    )
    print("\n2. Get-ChildItem Result:")
    print("Success:", res2.success)
    print("Output:", res2.output)

    # 3. Cleanup
    await shell.execute(
        ToolInvocation(
            params={"command": f'Remove-Item -Recurse -Force "{test_dir}"'},
            cwd=Path.cwd(),
        )
    )
    print("\nCleanup complete.")

if __name__ == "__main__":
    asyncio.run(test())