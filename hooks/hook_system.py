"""Tools, safety checks, or lifecycle hooks provided by this module.

The public objects below validate inputs, perform their operation, and return
structured results without changing the surrounding application workflow.
"""
import asyncio
import json
import os
import signal
import sys
import tempfile
from typing import Any
from config.config import Config, HookConfig, HookTrigger
from tools.base import ToolResult
from utils.environment import normalize_process_environment


class HookSystem:
    """Represent hooksystem state and behavior."""
    def __init__(self, config: Config):
        """Initialize the object with the configuration needed by later steps."""
        self.config = config
        # Filter once at startup so disabled hooks never enter the event loops.
        self.hooks: list[HookConfig] = []
        if self.config.hooks_enabled:
            self.hooks = [hook for hook in self.config.hooks if hook.enabled]

    async def _run_hook(self, hook: HookConfig, env: dict[str, str]) -> None:
        """Support the run hook step used by the public workflow."""
        try:
            if hook.command:
                # Commands run directly; script hooks get a short-lived executable file.
                await self._run_command(hook.command, hook.timeout_sec, env)
            else:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".sh", delete=False
                ) as f:
                    f.write("#!/bin/bash\n")
                    f.write(hook.script)
                    script_path = f.name
                try:
                    os.chmod(script_path, 0o755)
                    await self._run_command(script_path, hook.timeout_sec, env)
                finally:
                    os.unlink(script_path)
        except Exception as e:
            print(f"Hook '{hook.name}' failed: {e}")

    async def _run_command(
        self,
        command: str,
        timeout: float,
        env: dict[str, str],
    ) -> None:
        """Support the run command step used by the public workflow."""
        # Use a subprocess so hooks cannot block the agent's event loop.
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.config.cwd,
            env=normalize_process_environment(env),
            start_new_session=True,
        )

        try:
            await asyncio.wait_for(process.communicate(), timeout=timeout)
        except asyncio.TimeoutError:
            # A timed-out hook is forcibly stopped, then reaped before returning.
            if sys.platform != "win32":
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            else:
                process.kill()
            await process.wait()

    def _build_env(
        self,
        trigger: HookTrigger,
        tool_name: str | None = None,
        user_message: str | None = None,
        error: Exception | None = None,
    ) -> dict[str, str]:
        """Support the build env step used by the public workflow."""
        env = os.environ.copy()
        env["AI_AGENT_TRIGGER"] = trigger.value
        env["AI_AGENT_CWD"] = str(self.config.cwd)

        if tool_name:
            env["AI_AGENT_TOOL_NAME"] = tool_name

        if user_message:
            env["AI_AGENT_USER_MESSAGE"] = user_message

        if error:
            env["AI_AGENT_ERROR"] = str(error)

        return env

    async def trigger_before_agent(self, user_message: str) -> None:
        """Run hooks for the before agent lifecycle event."""
        # Build event metadata once and pass the same snapshot to matching hooks.
        env = self._build_env(
            HookTrigger.BEFORE_AGENT,
            user_message=user_message,
        )

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_AGENT:
                await self._run_hook(hook, env)

    async def trigger_after_agent(
        self,
        user_message: str,
        agent_response: str | None,
    ) -> None:
        """Run hooks for the after agent lifecycle event."""
        env = self._build_env(
            HookTrigger.AFTER_AGENT,
            user_message=user_message,
        )
        if agent_response is not None:
            env["AI_AGENT_RESPONSE"] = agent_response

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_AGENT:
                await self._run_hook(hook, env)

    async def trigger_before_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
    ) -> None:
        """Run hooks for the before tool lifecycle event."""
        env = self._build_env(HookTrigger.BEFORE_TOOL, tool_name=tool_name)
        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.BEFORE_TOOL:
                await self._run_hook(hook, env)

    async def trigger_after_tool(
        self,
        tool_name: str,
        tool_params: dict[str, Any],
        tool_result: ToolResult,
    ) -> None:
        """Run hooks for the after tool lifecycle event."""
        env = self._build_env(HookTrigger.AFTER_TOOL, tool_name=tool_name)
        env["AI_AGENT_TOOL_PARAMS"] = json.dumps(tool_params)
        env["AI_AGENT_TOOL_RESULT"] = tool_result.to_model_output()

        for hook in self.hooks:
            if hook.trigger == HookTrigger.AFTER_TOOL:
                await self._run_hook(hook, env)

    async def trigger_on_error(self, error: Exception) -> None:
        """Run hooks for the on error lifecycle event."""
        env = self._build_env(HookTrigger.ON_ERROR, error=error)

        for hook in self.hooks:
            if hook.trigger == HookTrigger.ON_ERROR:
                await self._run_hook(hook, env)
