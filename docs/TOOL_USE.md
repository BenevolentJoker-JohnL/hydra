# Programmatic Tool Use in Hydra

Hydra now supports **autonomous tool use** similar to Claude's computer use capabilities, but optimized for local development workflows.

## Overview

When you enable the **Tools** checkbox in the chat interface, Hydra can:
- Read and write files in your project
- Execute Python code to test implementations
- Run shell commands
- Search your codebase
- Analyze code structure

## How It Works

1. **Enable Tools**: Check the "Tools" checkbox in the chat input area
2. **Make a Request**: Ask Hydra to perform a task that requires file/system access
3. **Automatic Execution**: Hydra will:
   - Decide which tools to use
   - Execute them autonomously
   - Stream the results in real-time
   - Continue the task with tool outputs

## Available Tools

### File Operations
- **`read_file`** - Read contents of any file
  ```json
  {
    "tool": "read_file",
    "parameters": {"path": "src/main.py"}
  }
  ```

- **`write_file`** - Write content to a file
  ```json
  {
    "tool": "write_file",
    "parameters": {
      "path": "output.txt",
      "content": "Hello World"
    }
  }
  ```

- **`list_directory`** - List files in a directory
  ```json
  {
    "tool": "list_directory",
    "parameters": {"path": "./src"}
  }
  ```

### Code Execution
- **`execute_python`** - Run Python code and get output
  ```json
  {
    "tool": "execute_python",
    "parameters": {
      "code": "print('Hello from Python')"
    }
  }
  ```

- **`run_command`** - Execute shell commands
  ```json
  {
    "tool": "run_command",
    "parameters": {
      "command": "git status"
    }
  }
  ```

### Code Analysis
- **`analyze_code`** - Analyze Python code for structure
  ```json
  {
    "tool": "analyze_code",
    "parameters": {
      "code": "def hello(): pass"
    }
  }
  ```

- **`search_codebase`** - Search for patterns in code
  ```json
  {
    "tool": "search_codebase",
    "parameters": {
      "pattern": "TODO",
      "path": "./src"
    }
  }
  ```

## Example Workflows

### 1. Automated Testing
**Prompt**: "Write a function to calculate fibonacci numbers and test it"

**With Tools Enabled**, Hydra will:
1. Generate the function code
2. Use `write_file` to save it
3. Use `execute_python` to test it
4. Show results and adjust if needed

### 2. Codebase Analysis
**Prompt**: "Find all TODO comments in the project and list them"

**With Tools Enabled**, Hydra will:
1. Use `search_codebase` to find TODOs
2. Present organized results
3. Optionally create a task list

### 3. File Refactoring
**Prompt**: "Read config.py and split it into separate modules"

**With Tools Enabled**, Hydra will:
1. Use `read_file` to load config.py
2. Analyze the structure
3. Use `write_file` to create new modules
4. Update imports automatically

## UI Indicators

When tools are executing, you'll see:
- 🔧 **Executing N tool(s)...** - Tools are running
- ✅ **Success** - Tool executed successfully
- ❌ **Error** - Tool execution failed
- **Continuing with tool results...** - Using outputs

## Safety Features

- **30-second timeout** on command/code execution
- **Sandbox mode** for code execution (no system modifications)
- **Read-only by default** (write requires explicit tool calls)
- **Logged execution** - All tool use is tracked in terminal

## Combining with Other Features

### Tools + Reasoning
Enable both **Tools** and **🧠 Reasoning** for maximum capability:
- Hydra will think deeply about which tools to use
- Self-critique tool usage
- More sophisticated multi-step workflows

### Tools + Artifacts
- Generated code automatically becomes an artifact
- Tools can update artifacts
- Edit artifacts and re-execute with tools

### Tools + Project Context
- Tools have access to project files
- Can read/write within project boundaries
- Respects `.gitignore` patterns

## Architecture

```
User Request (with Tools enabled)
    ↓
StreamingCodeAssistant._process_stream_with_tools()
    ↓
Enhanced prompt with tool descriptions
    ↓
Model generates response with tool calls
    ↓
ToolCaller.extract_tool_calls() finds tool usage
    ↓
ToolCaller.execute_tool_calls() runs them
    ↓
Results streamed back to UI
    ↓
Model continues with tool outputs
```

## Adding Custom Tools

To add your own tools, edit `core/tools.py`:

```python
# In ToolRegistry._register_default_tools()
self.register(Tool(
    name="my_custom_tool",
    description="What this tool does",
    parameters={
        "param1": {"type": "string", "description": "Param description"}
    },
    function=self._my_custom_tool,
    type=ToolType.FUNCTION
))

async def _my_custom_tool(self, param1: str) -> Dict:
    try:
        # Your implementation
        result = do_something(param1)
        return {"success": True, "result": result}
    except Exception as e:
        return {"success": False, "error": str(e)}
```

## Performance Notes

- Tool execution adds ~1-5s per tool call
- Multiple tools can be called in sequence
- Failed tools fallback gracefully
- Tools work with all reasoning modes

## Future Enhancements

- [ ] Browser automation tools
- [ ] Database query tools
- [ ] API integration tools
- [ ] Docker container management
- [ ] Git operations (commit, push, etc.)
- [ ] Package management (pip, npm)

---

**💡 Tip**: Start with simple tool requests to learn the system, then combine tools for complex workflows!
