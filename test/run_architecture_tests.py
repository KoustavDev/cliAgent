"""End-to-end checks for the agent's major architectural boundaries.

Each test exercises one pipeline concern in isolation, while the module entry
point runs the checks in the same order a developer would troubleshoot them:
loop prevention, context management, safety, persistence, and file editing.
"""

import asyncio
from datetime import datetime
from pathlib import Path

from config.config import ApprovalPolicy, Config
from context.loop_detector import LoopDetector
from context.manager import ContextManager
from agent.persistence import PersistenceManager, SessionSnapshot
from client.response import TokenUsage
from safety.approval import ApprovalContext, ApprovalDecision, ApprovalManager
from tools.base import ToolConfirmation
from tools.builtin.edit_file import EditTool
from tools.base import ToolInvocation


def test_loop_detector():
    """Verify repeated actions are detected and detector state can be reset."""
    print("--- 1. Testing LoopDetector ---")
    detector = LoopDetector()
    
    # Simulate 3 identical actions    
    detector.record_action("tool_call", tool_name="list_dir", args={"path": "./"})
    detector.record_action("tool_call", tool_name="list_dir", args={"path": "./"})
    detector.record_action("tool_call", tool_name="list_dir", args={"path": ".."})

    loop_error = detector.check_for_loop()
    print(f"Repeated action detected: {loop_error}")
    assert loop_error is not None, "LoopDetector failed to catch 3 identical tool calls"
    
    detector.clear()
    assert detector.check_for_loop() is None, "LoopDetector clear() failed"
    print("✓ LoopDetector passed.\n")


def test_tool_pruning():
    """Verify old tool output is replaced once the pruning threshold is met."""
    print("--- 2. Testing ContextManager Tool Output Pruning ---")
    cfg = Config(cwd=Path.cwd())
    ctx = ContextManager(config=cfg, user_memory=None, tools=[])

    # Needs at least 2 user messages to be eligible for pruning
    ctx.add_user_message("First user question")
    # Add a massive tool output (simulating 50k tokens of output)
    huge_tool_output = "data line\n" * 50000
    ctx.add_tool_result("call_1", huge_tool_output)
    
    ctx.add_user_message("Second user question")
    # Add a recent tool result
    ctx.add_tool_result("call_2", "Recent short tool output")

    print(f"Messages before prune: {len(ctx._messages)}")
    pruned_count = ctx.prune_tool_outputs()
    print(f"Pruned message count: {pruned_count}")
    
    first_tool_msg = [m for m in ctx._messages if m.tool_call_id == "call_1"][0]
    print(f"Call 1 content after prune: '{first_tool_msg.content}'")
    assert first_tool_msg.content == "[Old tool result content cleared]", "Tool pruning did not replace older content"
    print("✓ Tool pruning passed.\n")


def test_safety_approval():
    """Verify dangerous shell commands are rejected and safe ones are allowed."""
    print("--- 3. Testing ApprovalManager Blacklist & Safe Patterns ---")
    cwd = Path.cwd()
    approval = ApprovalManager(approval_policy=ApprovalPolicy.ON_REQUEST, cwd=cwd)

    # 1. Dangerous command check
    dangerous_ctx = ApprovalContext(
        tool_name="shell",
        params={"command": "rm -rf /"},
        is_mutating=True,
        affected_paths=[],
        command="rm -rf /",
        is_dangerous=True,
    )
    decision = asyncio.run(approval.check_approval(dangerous_ctx))
    print(f"Decision for 'rm -rf /': {decision}")
    assert decision == ApprovalDecision.REJECTED, "Dangerous command was not rejected"

    # 2. Safe command check
    safe_ctx = ApprovalContext(
        tool_name="shell",
        params={"command": "ls"},
        is_mutating=True,
        affected_paths=[],
        command="ls",
        is_dangerous=False,
    )
    decision = asyncio.run(approval.check_approval(safe_ctx))
    print(f"Decision for 'ls': {decision}")
    assert decision == ApprovalDecision.APPROVED, "Safe command was not auto-approved"
    print("✓ Safety approval passed.\n")


def test_persistence_checkpoints():
    """Verify a saved session checkpoint can be loaded and then cleaned up."""
    print("--- 4. Testing PersistenceManager Checkpoint / Restore ---")
    pm = PersistenceManager()
    
    dummy_snapshot = SessionSnapshot(
        session_id="unit-test-session",
        created_at=datetime.now(),
        updated_at=datetime.now(),
        turn_count=5,
        messages=[{"role": "user", "content": "Hello agent"}],
        total_usage=TokenUsage(prompt_tokens=100, completion_tokens=50, total_tokens=150),
    )
    
    chk_id = pm.save_checkpoint(dummy_snapshot)
    print(f"Saved checkpoint: {chk_id}")
    
    loaded = pm.load_checkpoint(chk_id)
    assert loaded is not None, "Failed to load saved checkpoint"
    assert loaded.session_id == "unit-test-session"
    assert loaded.turn_count == 5
    print(f"Loaded turn count: {loaded.turn_count}")
    
    # Cleanup created test file
    chk_file = pm.checkpoints_dir / f"{chk_id}.json"
    if chk_file.exists():
        chk_file.unlink()
    print("✓ Persistence checkpoint passed.\n")


async def test_file_edit_diff():
    """Verify edit confirmation produces a diff before applying the file edit."""
    print("--- 5. Testing EditTool and Diff Generation ---")
    cfg = Config(cwd=Path.cwd())
    edit_tool = EditTool(cfg)
    test_file = Path.cwd() / "test_sample.txt"
    
    # Create initial file
    test_file.write_text("line one\nline two\nline three\n", encoding="utf-8")
    
    try:
        # Edit one line
        invocation = ToolInvocation(
            params={
                "path": str(test_file),
                "old_string": "line two",
                "new_string": "line TWO (edited)",
            },
            cwd=Path.cwd(),
        )
        
        # Test confirmation diff generation
        confirmation = await edit_tool.get_confirmation(invocation)
        assert confirmation is not None
        diff_str = confirmation.diff.to_diff()
        print("Generated Unified Diff:")
        print(diff_str)
        assert "-line two" in diff_str and "+line TWO (edited)" in diff_str
        
        # Test execution
        result = await edit_tool.execute(invocation)
        assert result.success
        assert "line TWO (edited)" in test_file.read_text(encoding="utf-8")
        print("✓ EditTool execution passed.\n")
    finally:
        if test_file.exists():
            test_file.unlink()


if __name__ == "__main__":
    test_loop_detector()
    test_tool_pruning()
    test_safety_approval()
    test_persistence_checkpoints()
    asyncio.run(test_file_edit_diff())
    print("All architectural unit tests passed successfully!")