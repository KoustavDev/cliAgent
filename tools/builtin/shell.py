import asyncio
import os
from pathlib import Path
import signal
import sys
from tools.base import Tool, ToolConfirmation, ToolInvocation, ToolKind, ToolResult
from pydantic import BaseModel, Field
import fnmatch
from utils.environment import normalize_process_environment

BLOCKED_COMMANDS = {
    "rm -rf /",
    "rm -rf ~",
    "rm -rf /*",
    "dd if=/dev/zero",
    "dd if=/dev/random",
    "mkfs",
    "fdisk",
    "parted",
    ":(){ :|:& };:",  # Fork bomb
    "chmod 777 /",
    "chmod -R 777",
    "shutdown",
    "reboot",
    "halt",
    "poweroff",
    "init 0",
    "init 6",
}


class ShellParams(BaseModel):
    command: str = Field(..., description="The shell command to execute")
    timeout: int = Field(
        120, ge=1, le=600, description="Timeout in seconds (default: 120)"
    )
    cwd: str | None = Field(None, description="Working directory for the command")


class ShellTool(Tool):
    name = "shell"
    kind = ToolKind.SHELL
    description = "Execute a shell command. Use this for running system commands, scripts and CLI tools."

    schema = ShellParams

    async def get_confirmation(
        self, invocation: ToolInvocation
    ) -> ToolConfirmation | None:
        params = ShellParams(**invocation.params)

        for blocked in BLOCKED_COMMANDS:
            if blocked in params.command:
                return ToolConfirmation(
                    tool_name=self.name,
                    params=invocation.params,
                    description=f"Execute (BLOCKED): {params.command}",
                    command=params.command,
                    is_dangerous=True,
                )

        return ToolConfirmation(
            tool_name=self.name,
            params=invocation.params,
            description=f"Execute: {params.command}",
            command=params.command,
            is_dangerous=False,
        )

    async def execute(self, invocation: ToolInvocation) -> ToolResult:
        params = ShellParams(**invocation.params)

        command = params.command.lower().strip()
        for blocked in BLOCKED_COMMANDS:
            if blocked in command:
                return ToolResult.error_result(
                    f"Command blocked for safety: {params.command}",
                    metadata={"blocked": True},
                )

        if params.cwd:
            cwd = Path(params.cwd)
            if not cwd.is_absolute():
                cwd = invocation.cwd / cwd
        else:
            cwd = invocation.cwd

        cwd = cwd.resolve()
        if not cwd.is_dir():
            return ToolResult.error_result(
                f"Working directory doesn't exist or is not a directory: {cwd}"
            )

        env = self._build_environment()
        if sys.platform == "win32":
            shell_cmd = self._build_windows_command(params.command)
        else:
            shell_cmd = ["/bin/bash", "-c", params.command]

        process = await asyncio.create_subprocess_exec(
            *shell_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=cwd,
            env=env,
            start_new_session=True,
        )

        try:
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(),
                timeout=params.timeout,
            )
        except asyncio.TimeoutError:
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()
            return ToolResult.error_result(f"Command timed out after {params.timeout}s")

        stdout = stdout_data.decode("utf-8", errors="replace")
        stderr = stderr_data.decode("utf-8", errors="replace")
        exit_code = process.returncode

        output = ""
        if stdout.strip():
            output += stdout.rstrip()

        if stderr.strip():
            output += "\n--- stderr ---\n"
            output += stderr.rstrip()

        if (
            sys.platform == "win32"
            and exit_code == 0
            and output.strip() == params.command.strip()
        ):
            return ToolResult.error_result(
                "Shell command was echoed instead of executed. "
                "The command interpreter may be misconfigured.",
                output=output,
                metadata={"command_echoed": True},
                exit_code=exit_code,
            )

        if exit_code != 0:
            output += f"\nExit code: {exit_code}"

        if len(output) > 100 * 1024:
            output = output[: 100 * 1024] + "\n... [output truncated]"

        return ToolResult(
            success=exit_code == 0,
            output=output,
            error=stderr if exit_code != 0 else None,
            exit_code=exit_code,
        )

    def _build_windows_command(self, command: str) -> list[str]:
        """Run PowerShell cmdlets in PowerShell and other commands in cmd.exe."""
        powershell_commands = (
            "mkdir",
            "md",
            "move",
            "copy",
            "del",
            "erase",
            "ren",
            "rename",
            "get-",
            "new-",
            "remove-",
            "move-",
            "copy-",
            "test-",
            "write-output",
            "write-host",
        )
        first_command = command.lstrip().lower()
        if first_command.startswith(powershell_commands):
            powershell = os.environ.get(
                "WINDIR",
                r"C:\Windows",
            )
            powershell_path = os.path.join(
                powershell,
                "System32",
                "WindowsPowerShell",
                "v1.0",
                "powershell.exe",
            )
            return [
                powershell_path,
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                command,
            ]

        return [
            os.environ.get("COMSPEC", "cmd.exe"),
            "/d",
            "/c",
            command,
        ]

    def _build_environment(self) -> dict[str, str]:
        env = normalize_process_environment(os.environ)

        shell_environment = self.config.shell_environment

        if not shell_environment.ignore_default_excludes:
            for pattern in shell_environment.exclude_patterns:
                keys_to_remove = [
                    k for k in env.keys() if fnmatch.fnmatch(k.upper(), pattern.upper())
                ]

                for k in keys_to_remove:
                    del env[k]

        if shell_environment.set_vars:
            env.update(
                normalize_process_environment(shell_environment.set_vars)
            )

        return env
