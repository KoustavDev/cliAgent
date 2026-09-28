#!/usr/bin/env python

import os
import sys
import json
from datetime import datetime


def main():
    trigger = os.environ.get("AI_AGENT_TRIGGER")
    cwd = os.environ.get("AI_AGENT_CWD")
    tool_name = os.environ.get("AI_AGENT_TOOL_NAME")
    tool_params = os.environ.get("AI_AGENT_TOOL_PARAMS")
    tool_result = os.environ.get("AI_AGENT_TOOL_RESULT")
    user_message = os.environ.get("AI_AGENT_USER_MESSAGE")
    agent_response = os.environ.get("AI_AGENT_RESPONSE")
    error = os.environ.get("AI_AGENT_ERROR")

    log_data = {
        "timestamp": datetime.now().isoformat(),
        "trigger": trigger,
        "cwd": cwd,
        "tool_name": tool_name,
        "tool_params": tool_params,
        "tool_result": tool_result,
        "user_message": user_message,
        "agent_response": agent_response,
        "error": error,
    }

    log_path = os.path.expanduser(f"{cwd}/.ai-agent/hook.log")
    os.makedirs(os.path.dirname(log_path), exist_ok=True)
    with open(log_path, "a") as f:
        f.write(f"[HOOK] {json.dumps(log_data)}\n")

    sys.exit(0)


if __name__ == "__main__":
    main()
