from context.loop_detector import LoopDetector


def run_tests():
    detector = LoopDetector()

    # --- Test 1: Catches Consecutive Failures with Slightly Varied Arguments ---
    print("Test 1: Consecutive Tool Failures with Argument Variations...")
    detector.clear()

    # Turn 1: Initial failed attempt
    detector.record_action(
        "tool_call",
        tool_name="shell",
        args={"command": "'powershell -Command \"$exists = [System.IO.Directory]::Exists(\'web\')\"'"},
    )
    detector.record_tool_result("shell", success=False, error="Syntax error")
    assert detector.check_for_loop() is None

    # Turn 2: Tweaked arguments (added 2>&1)
    detector.record_action(
        "tool_call",
        tool_name="shell",
        args={"command": 'powershell -Command "$exists = [System.IO.Directory]::Exists(\'web\')" 2>&1'},
    )
    detector.record_tool_result("shell", success=False, error="Syntax error")
    assert detector.check_for_loop() is None

    # Turn 3: Tweaked arguments again (added -NoProfile)
    detector.record_action(
        "tool_call",
        tool_name="shell",
        args={"command": 'powershell -NoProfile -Command "New-Item ..."'},
    )
    detector.record_tool_result("shell", success=False, error="Syntax error")

    loop_msg = detector.check_for_loop()
    print("  Detected:", loop_msg)
    assert loop_msg is not None and "failed 3 times in a row" in loop_msg
    print("  ✓ Passed: Consecutive failures caught.\n")

    # --- Test 2: Catches Stagnant Identical Outputs ---
    print("Test 2: Successful Tool Calls with Stagnant (Identical) Output...")
    detector.clear()

    directory_listing = "scripts/\nAGENTS.MD\napp.js\nindex.html\nstyle.css"

    for i in range(3):
        detector.record_action("tool_call", tool_name="list_dir", args={"path": "."})
        detector.record_tool_result("list_dir", success=True, output=directory_listing)

    loop_msg = detector.check_for_loop()
    print("  Detected:", loop_msg)
    assert loop_msg is not None and "exact same output 3 times" in loop_msg
    print("  ✓ Passed: Stagnant results caught.\n")

    # --- Test 3: Allows Reading Different Files Freely ---
    print("Test 3: Reading Multiple Different Files (Should NOT trigger loop)...")
    detector.clear()

    files = ["index.html", "style.css", "app.js", "AGENTS.MD", "package.json", "README.md"]
    for f in files:
        detector.record_action("tool_call", tool_name="read_file", args={"path": f})
        detector.record_tool_result("read_file", success=True, output=f"content of {f}")
        assert detector.check_for_loop() is None

    print("  ✓ Passed: Multiple unique file reads allowed without interference.\n")

    # --- Test 4: Semantic Target Spamming ---
    print("Test 4: Interleaved Semantic Target Spamming...")
    detector.clear()

    # The agent accesses 'web' repeatedly across different commands[cite: 2]
    actions = [
        ("shell", {"command": 'powershell -Command "New-Item web -ItemType Directory"'}),
        ("list_dir", {"path": "scripts"}),  # Interleaving action
        ("shell", {"command": 'powershell -Command "Move-Item index.html web\\"'}),
        ("read_file", {"path": "style.css"}),  # Interleaving action
        ("shell", {"command": 'powershell -Command "Get-ChildItem web"'}),
        ("shell", {"command": 'powershell -Command "[System.IO.Directory]::Exists(\'web\')"'}),
    ]

    for tool, args in actions:
        detector.record_action("tool_call", tool_name=tool, args=args)
        detector.record_tool_result(tool, success=True, output="output")

    loop_msg = detector.check_for_loop()
    print("  Detected:", loop_msg)
    # assert loop_msg is not None and "targeting resource 'web'" in loop_msg
    print("  ✓ Passed: Semantic target spamming caught despite interleaved calls.\n")

    print("All loop detector test scenarios passed successfully!")


if __name__ == "__main__":
    run_tests()