# Autonomous Agent - Claude Code-Style Execution

## Overview

Hydra now includes an **Autonomous Agent** that provides Claude Code-style iterative task execution. Instead of single-pass code generation, the agent autonomously:

1. **Analyzes** the task and current state
2. **Reasons** about what to do next (using ReasoningEngine)
3. **Executes** tools or generates code
4. **Analyzes** results and checks completion
5. **Loops** until the task is complete or max iterations reached

## Architecture

```
User Request
    ↓
[Autonomous Mode Check]
    ↓
┌──────────────────────────┐
│  AutonomousAgent Loop    │
│  (max 10 iterations)     │
├──────────────────────────┤
│  1. PLANNING Phase       │ ← Uses ReasoningEngine.reason()
│     - Analyze state      │
│     - Decide next action │
│                          │
│  2. EXECUTION Phase      │ ← Uses ToolCaller
│     - Execute tools      │
│     - Generate responses │
│                          │
│  3. ANALYSIS Phase       │ ← Self-evaluate
│     - Check results      │
│     - Verify completion  │
│                          │
│  ↓ Loop if not complete  │
└──────────────────────────┘
    ↓
Stream Results to UI
```

## Components Integrated

### 1. **Reasoning Engine**
- Uses existing `ReasoningEngine` for decision-making
- Supports AUTO, STANDARD, EXTENDED, DEEP thinking modes
- Chain-of-thought, self-critique, iterative refinement

### 2. **Model Orchestrator**
- Leverages `ModelOrchestrator.analyze_task()` for complexity scoring
- Auto-selects light/heavy models based on complexity
- Intelligent routing to appropriate models

### 3. **Tool System**
- Uses existing `ToolCaller` with approval system
- All tools available: read_file, write_file, edit_file, run_command, git operations
- Maintains CRITICAL operation approvals (write_file, run_command)

### 4. **Streaming Architecture**
- Yields progress updates at each iteration
- Real-time status: initializing → planning → executing → analyzing
- Streams thinking process, tool calls, and results

## Usage

### Basic Usage (Python)

```python
code_assistant = StreamingCodeAssistant(sollol, orchestrator)

# Autonomous mode: agent will iteratively solve the task
async for update in code_assistant.process_stream(
    prompt="Create a web server with authentication",
    autonomous=True  # Enable autonomous mode
):
    print(update)
```

### Streamlit UI Integration

The system is already integrated into the Streamlit UI. To enable autonomous mode:

1. **Add UI Toggle** (optional enhancement):
```python
# In app.py, add to sidebar:
autonomous_mode = st.sidebar.checkbox("🤖 Autonomous Mode", value=False, help="Enable Claude Code-style iterative execution")

# Pass to process_stream:
async for chunk_data in code_assistant.process_stream(
    prompt,
    context,
    autonomous=autonomous_mode  # Use the toggle
):
    # ... handle chunks
```

### Modes Comparison

| Mode | Behavior | Use Case |
|------|----------|----------|
| **Normal** (`autonomous=False, use_tools=False`) | Single-pass generation | Simple code generation |
| **Tools** (`use_tools=True`) | Single-pass with tool calls | Code generation with file operations |
| **Autonomous** (`autonomous=True`) | Iterative multi-step execution | Complex tasks requiring planning |

## Example: Autonomous Execution Flow

**Task**: "Fix the authentication bug in user_login.py"

```
Step 1: PLANNING
  🧠 Reasoning: Need to read the file first to understand the issue
  📋 Action: use_tool (read_file)

Step 2: EXECUTING
  🔧 Tool: read_file("user_login.py")
  ✅ Result: [file contents]

Step 3: ANALYZING
  🔍 Analysis: Found the bug - missing password hash check
  ⏳ Task not complete, continuing...

Step 4: PLANNING
  🧠 Reasoning: Need to fix the password validation
  📋 Action: use_tool (edit_file)

Step 5: EXECUTING
  🔧 Tool: edit_file("user_login.py", old_code, new_code)
  ✅ Result: File updated

Step 6: ANALYZING
  🔍 Analysis: Bug fixed, should verify with tests
  ⏳ Task not complete, continuing...

Step 7: PLANNING
  🧠 Reasoning: Run tests to verify fix
  📋 Action: use_tool (run_command)

Step 8: EXECUTING
  🔧 Tool: run_command("pytest tests/test_auth.py")
  ✅ Result: All tests passing

Step 9: ANALYZING
  🔍 Analysis: Fix verified, task complete
  ✅ TASK COMPLETE
```

## Configuration

The autonomous agent can be configured via `AgentConfig`:

```python
from core.autonomous_agent import AgentConfig

config = AgentConfig(
    max_iterations=10,  # Safety limit
    require_completion_confirmation=True,
    stream_thinking=True,  # Show reasoning process
    enable_self_correction=True,  # Retry on errors
    complexity_threshold_for_deep_thinking=7.0
)

agent = AutonomousAgent(
    reasoning_engine=orchestrator.reasoning_engine,
    orchestrator=orchestrator,
    tool_caller=tool_caller,
    config=config
)
```

## Agent States

The agent progresses through these states:

- **INITIALIZING**: Setting up, analyzing task complexity
- **PLANNING**: Reasoning about next action
- **EXECUTING**: Running tools or generating code
- **ANALYZING**: Evaluating results, checking completion
- **COMPLETED**: Task successfully finished
- **FAILED**: Max iterations reached without completion

## Limitations & Future Enhancements

### Current Limitations
1. Max 10 iterations (safety limit)
2. Simple completion detection (can be enhanced)
3. Basic error recovery (retries once)
4. No multi-agent coordination

### Planned Enhancements
1. **AskUserQuestion integration** - Clarify ambiguities mid-execution
2. **TodoWrite integration** - Track subtasks explicitly
3. **Enhanced completion detection** - Use reasoning to verify task completion
4. **Code execution validation** - Run and verify generated code
5. **Multi-agent orchestration** - Parallel task decomposition

## Integration with Existing Features

✅ **Approval System**: Fully integrated, CRITICAL operations still require approval
✅ **SOLLOL Routing**: Autonomous agent uses existing distributed routing
✅ **Memory Management**: Proactive model unloading still works
✅ **Reasoning Engine**: Leverages all reasoning modes (AUTO, EXTENDED, DEEP)
✅ **Git Integration**: All git tools available for autonomous commits/PRs
✅ **Streaming**: Real-time progress updates to UI

## Performance Considerations

- **Iteration cost**: Each iteration = 1 reasoning call + N tool calls
- **Total time**: Depends on task complexity (2-10 iterations typical)
- **Model selection**: Uses orchestrator's complexity-based selection
- **Distributed**: SOLLOL routing distributes load across nodes

## Comparison to Claude Code

| Feature | Claude Code | Hydra Autonomous Agent |
|---------|-------------|------------------------|
| Iterative execution | ✅ | ✅ |
| Tool use | ✅ | ✅ |
| Reasoning | ✅ (native) | ✅ (via ReasoningEngine) |
| Task decomposition | ✅ | ✅ (basic) |
| Progress tracking | ✅ | ✅ (streaming) |
| Self-correction | ✅ | ✅ (enabled by default) |
| Distributed execution | ❌ | ✅ (via SOLLOL) |
| Local models | ❌ | ✅ |

## Example Use Cases

1. **Complex refactoring**: Multi-file changes with verification
2. **Bug fixing**: Read → Analyze → Fix → Test → Verify
3. **Feature implementation**: Plan → Code → Test → Document
4. **Code review**: Read → Analyze → Suggest → Apply fixes
5. **Project setup**: Create structure → Install deps → Configure → Test

## Getting Started

The autonomous agent is **already integrated** and ready to use! No additional setup required.

To test it:

```python
# Via Streamlit UI - just enable autonomous mode
# Or programmatically:
async for update in code_assistant.process_stream(
    "Implement user authentication with JWT tokens",
    autonomous=True
):
    if update.get('state') == 'completed':
        print("Task completed!")
    else:
        print(f"Step {update.get('step')}: {update.get('message')}")
```

---

**Status**: ✅ Implemented and Integrated
**Version**: 1.0
**Date**: 2025-10-26
