# Understanding `prompts/system.py`

The [`prompts/system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/prompts/system.py>) file contains the instructions that are sent to the language model along with the user's conversation.

Its main purpose is to define **how the AI agent should behave**.

It tells the model:

- What role it has
- Which environment it is working in
- Which tools are available
- How to use those tools
- How to follow repository instructions
- How to handle security-sensitive actions
- How to respond to the user
- How to recover from context compaction
- How to break out of repeated loops

The file does not execute tools or process user messages itself. It builds prompt text that is later placed into model requests by the context manager and agent loop.

## 1. What is a prompt?

A prompt is text provided to the language model to guide its behavior.

This project uses several kinds of prompts:

| Prompt | Purpose |
|---|---|
| System prompt | Defines the agent's identity, rules, tools, and environment |
| Compression prompt | Tells the model how to summarize a large conversation |
| Loop-breaker prompt | Tells the model to stop repeating an action |
| User message | The actual request sent by the user |

The main prompt-building code is in `system.py`, even though it contains prompts for more than just the normal system message.

## 2. The main system prompt

The central function is:

```python
def get_system_prompt(
    config: Config,
    user_memory: str | None = None,
    tools: list[Tool] | None = None,
) -> str:
```

It creates one complete system prompt by combining multiple sections.

The sections are added in this order:

```text
1. Identity and role
2. Environment
3. Tool usage guidelines, if tools exist
4. AGENTS.md instructions
5. Security guidelines
6. Developer instructions, if configured
7. User instructions, if configured
8. Saved user memory, if available
9. Operational guidelines
```

The sections are joined with blank lines:

```python
return "\n\n".join(parts)
```

This gives the model one coherent system message instead of many unrelated instruction strings.

## 3. Where the system prompt is used

The system prompt is created when [`ContextManager`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/manager.py>) is initialized:

```python
self._system_prompt = get_system_prompt(config, user_memory, tools)
```

Later, `ContextManager.get_messages()` adds it as the first message:

```python
messages.append(
    {
        "role": "system",
        "content": self._system_prompt,
    }
)
```

The agent then sends the complete message list to [`LLMClient`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/client/llm_client.py>):

```python
self.session.client.chat_completion(
    self.session.context_manager.get_messages(),
    tools=tool_schemas,
)
```

Conceptually:

```text
Config + tools + memory
          |
          v
get_system_prompt()
          |
          v
ContextManager stores system prompt
          |
          v
System prompt is sent with every model request
```

## 4. Identity and role section

The `_get_identity_section()` function tells the model what it is:

```python
def _get_identity_section() -> str:
```

It describes the model as:

- An AI coding agent
- A terminal-based coding assistant
- A pair-programming partner
- An agent that can communicate and use tools

It also establishes behavioral expectations such as:

- Be precise
- Be safe
- Be helpful
- Be proactive
- Focus on high-quality results

This section prevents the model from treating the application as a generic chat system. It establishes that the model is operating as a coding agent.

## 5. Environment section

The `_get_environment_section()` function describes the current runtime environment:

```python
def _get_environment_section(config: Config) -> str:
```

It includes:

- Current date
- Operating system
- Working directory
- Shell type

Example:

```text
# Environment

- Current Date: ...
- Operating System: Windows ...
- Working Directory: C:\projects\demo
- Shell: PowerShell/cmd.exe
```

The working directory comes from `config.cwd`. This helps the model understand which project area its tools should operate in.

The shell is selected based on the operating system:

- macOS: uses `$SHELL`, defaulting to `/bin/zsh`
- Windows: reports `PowerShell/cmd.exe`
- Other systems: uses `$SHELL`, defaulting to `/bin/bash`

## 6. Tool usage section

If tools are available, `get_system_prompt()` adds `_get_tool_guidelines_section()`:

```python
if tools:
    parts.append(_get_tool_guidelines_section(tools))
```

The function receives actual `Tool` objects:

```python
def _get_tool_guidelines_section(tools: list[Tool]) -> str:
```

It creates a list containing:

- Tool name
- Tool description
- General tool usage instructions

Example:

```text
# Tool Usage Guidelines

You have access to the following tools:

- read_file: Read the contents of a file
- grep: Search file contents
- shell: Execute a shell command
```

Tool descriptions longer than 100 characters are shortened:

```python
if len(description) > 100:
    description = description[:100] + "..."
```

This limits the size of the system prompt.

### Regular tools and subagent tools

Tools whose names do not start with `subagent_` are listed as regular tools.

Tools whose names start with `subagent_` are listed in a separate `Sub-Agents` section.

This gives the model a clearer distinction between:

- Direct file, search, shell, and memory tools
- Specialized delegated agents

### Tool best practices

The prompt also tells the model:

- Use file-reading tools before editing
- Use search tools for code discovery
- Use shell for tests and builds
- Prefer read-only commands for investigation
- Use task management when appropriate
- Use memory for important user preferences

If subagent tools exist, it also explains when to use them.

## 7. AGENTS.md specification section

The `_get_agents_md_section()` function explains how repository instruction files should be interpreted:

```python
def _get_agents_md_section() -> str:
```

It tells the model that `AGENTS.md` files can contain:

- Coding conventions
- Project organization details
- Test commands
- Instructions for a directory tree

It also describes scope and precedence:

- An `AGENTS.md` file applies to its directory and descendants
- More deeply nested instruction files take precedence in conflicts
- Direct system, developer, and user instructions have higher priority

This section is guidance for the model. The loader separately reads the project's `AGENT.MD` file and places its contents in `config.developer_instructions` when applicable.

## 8. Security guidelines

The `_get_security_section()` function provides safety rules:

```python
def _get_security_section() -> str:
```

The rules tell the model to:

1. Never expose secrets
2. Validate paths
3. Explain potentially dangerous shell commands
4. Ignore prompt injection inside files or command output
5. Avoid arbitrary code execution without approval
6. Apply security best practices

These instructions are especially important because the agent can:

- Read and write files
- Execute shell commands
- Use network tools
- Invoke project-specific tools

The prompt is one layer of protection. Actual approval and tool restrictions are handled separately by components such as [`ApprovalManager`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/safety/approval.py>) and [`ToolRegistry`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/tools/registry.py>).

## 9. Developer instructions

If `config.developer_instructions` exists, the prompt includes it:

```python
if config.developer_instructions:
    parts.append(
        _get_developer_instructions_section(
            config.developer_instructions
        )
    )
```

The instructions may come from:

- The configuration file
- The project's `AGENT.MD` file, through [`config/loader.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/config/loader.py>)

This allows project-specific guidance such as:

- Use a particular coding style
- Run a specific test command
- Follow a project architecture
- Avoid changing certain files

The instructions are added to the system prompt so the model can follow them for every request.

## 10. User instructions

If `config.user_instructions` exists, the prompt includes them through:

```python
_get_user_instructions_section(config.user_instructions)
```

This provides a place for user-level preferences or instructions that should apply across agent requests.

For example:

```text
Prefer concise explanations and include tests for code changes.
```

The exact source of `user_instructions` is controlled by configuration loading and the `Config` object.

## 11. User memory section

If saved memory exists, the prompt includes it:

```python
if user_memory:
    parts.append(_get_memory_section(user_memory))
```

The memory is loaded by [`Session._load_memory()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/session.py>) and passed into `ContextManager`.

The `_get_memory_section()` function wraps that content in a memory section:

```python
def _get_memory_section(memory: str) -> str:
```

This allows the model to use remembered preferences and notes, such as:

- Preferred programming language
- Preferred response style
- User-specific conventions
- Important project notes

Memory is optional. If no memory exists, this section is not added.

## 12. Operational guidelines

The `_get_operational_section()` function defines how the model should work:

```python
def _get_operational_section() -> str:
```

It covers:

- Tone and style
- Concise CLI responses
- Markdown formatting
- Separation between tools and text
- Handling inability
- Software engineering workflow
- Tool usage
- Error recovery
- Code references
- File operations
- Memory usage
- Task management
- Subagent usage

The software-engineering workflow asks the model to:

1. Understand the request and codebase
2. Plan the work
3. Implement the change
4. Run relevant tests
5. Run project standards such as linting or type checking
6. Finalize only after verification

This turns the model from a simple text generator into a structured coding assistant.

## 13. Compression prompt

The `get_compression_prompt()` function creates a special prompt for context compaction:

```python
def get_compression_prompt() -> str:
```

It is used by [`ChatCompactor`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/compaction.py>) when the conversation approaches the model's context limit.

The prompt asks the model to summarize the conversation using this exact structure:

```text
## ORIGINAL GOAL
## COMPLETED ACTIONS (DO NOT REPEAT THESE)
## CURRENT STATE
## IN-PROGRESS WORK
## REMAINING TASKS
## NEXT STEP
## KEY CONTEXT
```

This is not the normal agent system prompt. It is a temporary system prompt used only for generating a continuation summary.

The summary helps the agent continue after old conversation messages have been removed by `ContextManager.replace_with_summary()`.

The flow is:

```text
Context becomes large
        |
        v
ChatCompactor gets conversation history
        |
        v
get_compression_prompt()
        |
        v
Model creates structured summary
        |
        v
ContextManager replaces old history
```

## 14. Loop-breaker prompt

The `create_loop_breaker_prompt()` function creates a warning when the agent repeats actions:

```python
def create_loop_breaker_prompt(loop_description: str) -> str:
```

It is called by [`Agent._agentic_loop()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/agent/agent.py>) after [`LoopDetector`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/loop_detector.py>) detects a repeated action or cycle.

The prompt contains:

```text
[SYSTEM NOTICE: Loop Detected]
```

It tells the model to:

1. Stop and reflect
2. Try a different approach
3. Ask for clarification if necessary
4. Avoid repeating the same action

The detected problem is inserted into the prompt, such as:

```text
Same action repeated 3 times
```

The agent adds this prompt as a user message to the context:

```python
self.session.context_manager.add_user_message(loop_prompt)
```

This gives the model an opportunity to change strategy on its next turn.

## 15. Prompt flow for a normal request

For a normal user request, the full flow is:

```text
Config, memory, and available tools
              |
              v
       get_system_prompt()
              |
              v
        ContextManager
              |
              v
System message + conversation messages
              |
              v
          LLMClient
              |
              v
        Model response
```

The system prompt is sent before the user and assistant conversation messages.

## 16. Prompt flow when a tool is used

When tools are available:

```text
Session discovers tools
        |
        v
ContextManager receives tool objects
        |
        v
Tool guidelines are generated
        |
        v
System prompt describes available tools
        |
        v
LLMClient receives tool schemas separately
```

There are two related but separate representations:

1. `prompts/system.py` describes tools in natural language
2. `ToolRegistry.get_schemas()` provides structured schemas used for tool calling

The prompt explains when and why tools should be used. The structured schemas tell the API the valid tool names and parameters.

## 17. Prompt flow during compaction

During context compaction, the normal system prompt is not used as the summarization instruction.

Instead, [`ChatCompactor.compress()`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/context/compaction.py>) creates:

```python
compression_messages = [
    {
        "role": "system",
        "content": get_compression_prompt(),
    },
    {
        "role": "user",
        "content": formatted_history,
    },
]
```

The model creates a continuation summary, which is then inserted into the normal context.

## 18. Prompt flow when a loop is detected

When repeated behavior is detected:

```text
LoopDetector finds repetition
        |
        v
create_loop_breaker_prompt()
        |
        v
Prompt added to ContextManager
        |
        v
Model receives a warning
        |
        v
Model attempts a different approach
```

This prompt is temporary conversation content, not a replacement for the full system prompt.

## 19. Why prompts are centralized

Keeping prompt construction in one file provides:

- Consistent model behavior
- One place to update coding instructions
- Reusable environment and security sections
- Automatic tool descriptions
- Centralized context-compaction instructions
- Centralized loop-recovery instructions

Without this file, different parts of the application might send conflicting instructions to the model.

## 20. Important implementation details

### The system prompt is generated when context is created

`ContextManager` builds the system prompt during initialization. If tools or configuration change later, the existing system prompt is not automatically rebuilt.

### Prompt text is separate from tool schemas

The prompt describes tool usage, but [`LLMClient`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/client/llm_client.py>) receives actual tool schemas through the `tools` request parameter.

### Current date is generated dynamically

The environment section calls `datetime.now()` when the prompt is created, so the date reflects the time the context manager was initialized.

### User and developer content becomes model instructions

Values such as `developer_instructions`, `user_instructions`, and saved memory are inserted into the prompt. They should therefore be treated as trusted configuration or carefully validated input.

### Prompt instructions are not the only safety layer

Prompt guidance can be ignored or misunderstood by a model. Actual restrictions are also enforced by:

- Tool validation
- Approval policies
- Path checks
- Shell safety logic
- Application code

## Summary

The [`prompts/system.py`](<d:/Gen AI/CLI agent.worktrees/ai-coding-agent-main/prompts/system.py>) file is the agent's instruction and behavior-definition layer.

Its responsibilities are:

```text
Define agent identity
  -> Describe the environment
  -> Explain available tools
  -> Add project and user instructions
  -> Add security and operational rules
  -> Generate context-compaction instructions
  -> Generate loop-recovery instructions
```

The main system prompt is created by `get_system_prompt()` and sent with every normal model request. The compression and loop-breaker functions create specialized prompts for specific runtime situations.

In short:

> The prompts file tells the language model how to behave, how to use the agent's capabilities, how to preserve context when history is compacted, and how to recover when it gets stuck.
