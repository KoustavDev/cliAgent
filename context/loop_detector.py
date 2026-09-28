from collections import Counter, deque
import hashlib
from pathlib import Path
import re
from typing import Any


class LoopDetector:
    def __init__(self):
        self.max_exact_repeats = 3
        self.max_cycle_length = 3
        self.max_tool_target_repeats = 4
        self.max_consecutive_tool_failures = 3
        self.max_consecutive_identical_results = 3  # Trips if same output appears 3 times in a row

        self._history: deque[str] = deque(maxlen=20)
        self._target_history: deque[tuple[str, str]] = deque(maxlen=15)

        # Track failure loops: {tool_name: consecutive_failure_count}
        self._consecutive_failures: dict[str, int] = {}
        self._last_failed_tool: str | None = None
        self._last_failure_reason: str | None = None

        # Track stagnant result loops: {tool_name: (last_result_hash, consecutive_count)}
        self._stagnant_results: dict[str, tuple[str, int]] = {}
        self._last_stagnant_tool: str | None = None

    def _extract_target(self, tool_name: str, args: dict[str, Any]) -> str | None:
        """Extract a normalized semantic target from tool arguments."""
        if not isinstance(args, dict):
            return None

        for key in ("path", "cwd", "destination", "source", "url"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                try:
                    name = Path(val).name.strip().lower()
                    if name:
                        return name
                except Exception:
                    pass

        if tool_name == "shell":
            cmd = args.get("command")
            if isinstance(cmd, str):
                matches = re.findall(r"['\"]([^'\"]+)['\"]", cmd)
                if matches:
                    try:
                        name = Path(matches[-1]).name.strip().lower()
                        if name:
                            return name
                    except Exception:
                        pass

                file_verbs = re.findall(
                    r"(?:mkdir|move|copy|rm|del|remove-item|new-item|get-childitem|cat|ls|dir)\s+([^\s;&|]+)",
                    cmd,
                    re.IGNORECASE,
                )
                if file_verbs:
                    try:
                        return Path(file_verbs[-1]).name.strip().lower()
                    except Exception:
                        pass

        for key in ("key", "query", "id"):
            val = args.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip().lower()

        return None

    def record_action(self, action_type: str, **details: Any):
        """Record the model's intent or action."""
        output = [action_type]

        if action_type == "tool_call":
            tool_name = details.get("tool_name", "")
            output.append(tool_name)
            args = details.get("args", {})

            if isinstance(args, dict):
                for k in sorted(args.keys()):
                    output.append(f"{k}={str(args[k])}")

                target = self._extract_target(tool_name, args)
                if tool_name and target:
                    self._target_history.append((tool_name, target))

        elif action_type == "response":
            output.append(details.get("text", ""))

        signature = "|".join(output)
        self._history.append(signature)

    def record_tool_result(
        self,
        tool_name: str,
        success: bool,
        output: str = "",
        error: str | None = None,
    ):
        """Record the execution outcome and output hash to detect stagnation."""
        # 1. Update Failure Tracker
        if not success:
            count = self._consecutive_failures.get(tool_name, 0) + 1
            self._consecutive_failures[tool_name] = count
            self._last_failed_tool = tool_name
            self._last_failure_reason = error or output or "Command failed with non-zero exit code"
            # Reset stagnant result tracker for this tool if it fails
            self._stagnant_results.pop(tool_name, None)
        else:
            self._consecutive_failures[tool_name] = 0

            # 2. Update Stagnant (Identical Result) Tracker
            # Normalize whitespace so harmless spacing changes don't evade the check
            normalized_output = " ".join(output.split())
            if normalized_output:
                res_hash = hashlib.sha256(normalized_output.encode("utf-8")).hexdigest()
                last_hash, count = self._stagnant_results.get(tool_name, ("", 0))

                if res_hash == last_hash:
                    new_count = count + 1
                    self._stagnant_results[tool_name] = (res_hash, new_count)
                    if new_count >= self.max_consecutive_identical_results:
                        self._last_stagnant_tool = tool_name
                else:
                    self._stagnant_results[tool_name] = (res_hash, 1)

    def check_for_loop(self) -> str | None:
        # 1. Repeated identical result stagnation check
        for tool_name, (_, count) in self._stagnant_results.items():
            if count >= self.max_consecutive_identical_results:
                return (
                    f"Tool '{tool_name}' returned the exact same output {count} times in a row. "
                    "The state of the system is not changing. Do not repeat this check."
                )

        # 2. Consecutive failure loop check
        for tool_name, fail_count in self._consecutive_failures.items():
            if fail_count >= self.max_consecutive_tool_failures:
                reason = self._last_failure_reason or "repeated execution errors"
                return (
                    f"Tool '{tool_name}' failed {fail_count} times in a row with errors: "
                    f"'{reason[:120]}'. Stop retrying variations of this command."
                )

        if len(self._history) < 2:
            return None

        # 3. Exact identical action repetition
        if len(self._history) >= self.max_exact_repeats:
            recent = list(self._history)[-self.max_exact_repeats :]
            if len(set(recent)) == 1:
                return f"Same action repeated {self.max_exact_repeats} times"

        # 4. Repeating cycle loops (A -> B -> A -> B)
        if len(self._history) >= self.max_cycle_length * 2:
            history = list(self._history)
            for cycle_len in range(
                2, min(self.max_cycle_length + 1, len(history) // 2 + 1)
            ):
                recent = history[-cycle_len * 2 :]
                if recent[:cycle_len] == recent[cycle_len:]:
                    return f"Detected repeating cycle of length {cycle_len}"

        # 5. Semantic target spamming
        if len(self._target_history) >= self.max_tool_target_repeats:
            counts = Counter(self._target_history)
            for (tool, target), count in counts.items():
                if count >= self.max_tool_target_repeats:
                    return (
                        f"Repeatedly invoking '{tool}' targeting resource "
                        f"'{target}' ({count} times in recent turns)"
                    )

        return None

    def clear(self) -> None:
        self._history.clear()
        self._target_history.clear()
        self._consecutive_failures.clear()
        self._stagnant_results.clear()
        self._last_failed_tool = None
        self._last_failure_reason = None
        self._last_stagnant_tool = None