# Tool Approval System

Hydra includes a comprehensive **approval system** to control tool execution with **mandatory approvals** for critical operations, **auto-approval** for safe operations, and **intelligent approval tracking** to minimize interruptions.

## Overview

When tools are enabled in the chat interface, Hydra can autonomously use 7 different tools to read files, execute code, search the codebase, and more. The approval system ensures:

- **Safety First**: Critical operations (write_file, run_command) ALWAYS require explicit approval
- **Smart Auto-Approval**: Safe operations and previously approved operations don't interrupt workflow
- **Approval Memory**: Same operations aren't asked twice
- **Pattern Matching**: Custom rules for auto-approving trusted operations
- **Session Limits**: Prevents excessive auto-approvals

## Permission Levels

### 🟢 SAFE (Auto-Approved)

These tools are read-only and always auto-approved:

- **`read_file`** - Read file contents
- **`list_directory`** - List files in a directory
- **`analyze_code`** - Analyze Python code structure
- **`search_codebase`** - Search for patterns in code

**No approval needed** - these tools cannot modify your system.

### 🟡 REQUIRES_APPROVAL (Can Be Auto-Approved)

These tools require approval but can be auto-approved with rules:

- **`execute_python`** - Execute Python code

**Approval needed on first use**, but can be auto-approved based on:
- Session limits (e.g., max 10 executions)
- Pattern matching (e.g., only simple print statements)
- Previously approved same operations

### 🔴 CRITICAL (ALWAYS Requires Approval)

These tools can modify your system and **ALWAYS** require explicit approval:

- **`write_file`** - Write content to files (creates directories automatically)
- **`run_command`** - Execute shell commands

**CANNOT BE BYPASSED** - every use requires manual approval.

## How It Works

### 1. First-Time Execution

When Hydra wants to use a tool requiring approval:

```
🔐 Pending Approval Request

⚠️ Approve write_file? (Permission: critical)

Tool: write_file
Permission Level: critical
Arguments:
{
  "path": "./output/result.txt",
  "content": "Hello World"
}

⚠️ CRITICAL OPERATION - This action can modify your system. Review carefully!

[✅ Approve]  [❌ Deny]  [🔄 Approve Similar]
```

### 2. Approval Options

**✅ Approve**: Approve this one operation

**❌ Deny**: Reject the operation (tool won't execute)

**🔄 Approve Similar**: Approve this AND similar operations (creates auto-approval rule)
- **Not available for CRITICAL operations** - they always require explicit approval
- Available for REQUIRES_APPROVAL operations

### 3. Auto-Approval

After approval, Hydra remembers:

- **Exact same operation**: Same tool + same arguments = auto-approved
- **Pattern matches**: Operations matching auto-approval rules
- **Session limits**: Won't auto-approve beyond configured limits

## Auto-Approval Rules

Default rules configured in `ui/approval_handler.py`:

```python
# Read project files
{
    'name': 'Read project files',
    'tool': 'read_file',
    'conditions': [
        {
            'type': 'path_prefix',
            'allowed_prefixes': ['./', '/home/joker/hydra']
        }
    ]
}

# Execute Python with session limit
{
    'name': 'Execute safe Python',
    'tool': 'execute_python',
    'conditions': [
        {
            'type': 'session_limit',
            'max_uses': 10  # Max 10 per session
        }
    ]
}
```

### Condition Types

**`path_prefix`**: Auto-approve if path starts with allowed prefix
```python
{
    'type': 'path_prefix',
    'allowed_prefixes': ['./src/', './tests/']
}
```

**`file_extension`**: Auto-approve for specific file types
```python
{
    'type': 'file_extension',
    'allowed_extensions': ['.py', '.txt', '.md']
}
```

**`max_file_size`**: Auto-approve if file under size limit
```python
{
    'type': 'max_file_size',
    'max_bytes': 1024 * 1024  # 1MB
}
```

**`session_limit`**: Auto-approve up to N uses per session
```python
{
    'type': 'session_limit',
    'max_uses': 10
}
```

## UI Features

### Approval Dialogs

Appear at the top of the chat when approval is needed:

- **Expandable details**: See exact tool parameters
- **Color-coded warnings**: Yellow for approval, Red for critical
- **Three-button choice**: Approve / Deny / Approve Similar
- **Real-time**: Hydra waits for your decision

### Settings Panel

Navigate to **⚙️ Settings → 🔐 Tool Approvals** to:

- View approval statistics
- See permission levels for all tools
- Reset all approvals
- Add custom rules (coming soon)

### Approval Statistics

```
📊 Approval Statistics
  Total Approvals: 15
  Unique Operations: 8
  Auto-Approval Rules: 5

Session Usage:
  - execute_python: 5 uses
  - write_file: 2 uses

Recent Approvals:
  - read_file (auto)
  - execute_python (auto)
  - write_file
  - run_command
```

## Security Guarantees

### 🔒 CRITICAL Operations CANNOT Be Bypassed

```python
# This will ALWAYS trigger approval dialog
approval_tracker.is_approved('write_file', args, PermissionLevel.CRITICAL)
# Returns: False (even if approved before)
```

Critical operations are checked in `core/tools.py:53-57`:

```python
def is_approved(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel) -> bool:
    # CRITICAL operations NEVER auto-approve
    if permission_level == PermissionLevel.CRITICAL:
        return False  # ← CANNOT BYPASS
```

### 🔐 Approval Callback Required

If no approval callback is set, critical operations are denied:

```python
async def _request_approval(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel) -> bool:
    if not self.approval_callback:
        if permission_level == PermissionLevel.CRITICAL:
            logger.warning(f"⚠️ No approval callback set, denying critical operation: {tool_name}")
            return False  # ← Fail-safe denial
    # ...
```

### 🛡️ Defense in Depth

1. **Permission Level Enforcement**: Each tool has a fixed permission level
2. **Mandatory Approval Check**: ToolCaller checks before execution
3. **No Bypass for Critical**: Hardcoded check prevents auto-approval
4. **Approval Tracking**: All approvals logged with timestamps
5. **Session Limits**: Prevents runaway auto-approvals

## Example Workflows

### Workflow 1: Safe File Exploration

```
User: "Read the README.md file"
Hydra: Uses read_file tool
Status: ✅ Auto-approved (SAFE permission level)
Action: File contents displayed immediately
```

### Workflow 2: Python Execution (First Time)

```
User: "Test the fibonacci function"
Hydra: Wants to use execute_python
Status: 🟡 Approval required

[Approval Dialog Appears]
User: Clicks "🔄 Approve Similar"

Hydra: Executes code
Status: ✅ Approved + auto-approval rule created
Future: Next 10 Python executions auto-approved
```

### Workflow 3: File Writing (CRITICAL)

```
User: "Save the results to output.txt"
Hydra: Wants to use write_file
Status: 🔴 CRITICAL approval required

[Approval Dialog Appears]
⚠️ CRITICAL OPERATION - This action can modify your system.

User: Reviews path and content
User: Clicks "✅ Approve"

Hydra: Creates file
Status: ✅ Approved (but NOT auto-approved for future)

Next time: Approval required again (CRITICAL can't auto-approve)
```

### Workflow 4: Repeated Operations

```
User: "Search for 'TODO' comments"
Hydra: Uses search_codebase
Status: ✅ Auto-approved (SAFE)

User: "Search for 'FIXME' comments"
Hydra: Uses search_codebase again
Status: ✅ Auto-approved (still SAFE)

No interruptions, smooth workflow.
```

## Implementation Details

### Architecture

```
User Request (Tools enabled)
    ↓
ToolCaller.execute_tool_calls()
    ↓
For each tool:
    ├─ Check permission level
    ├─ ApprovalTracker.is_approved()?
    │    ├─ SAFE → Auto-approve
    │    ├─ CRITICAL → Deny (must request)
    │    └─ REQUIRES_APPROVAL → Check patterns/history
    ├─ If not approved: _request_approval()
    │    ├─ Create approval request
    │    ├─ Show UI dialog
    │    └─ Wait for user decision
    ├─ If approved: Execute tool
    └─ Record approval in tracker
```

### Key Files

**`core/tools.py`**:
- `PermissionLevel` enum (lines 20-24)
- `ApprovalTracker` class (lines 35-161)
- `ToolCaller.execute_tool_calls()` with approval checks (lines 452-545)

**`ui/approval_handler.py`**:
- `ApprovalHandler` class for Streamlit UI
- `render_approval_stats()` for statistics display
- `setup_auto_approval_rules()` for default rules

**`app.py`**:
- Approval handler initialization (lines 302-311)
- Pending approvals rendering (line 318)
- Settings panel integration (lines 1130-1203)

### Approval Tracking

Operations are hashed for comparison:

```python
def _hash_operation(self, tool_name: str, arguments: Dict) -> str:
    normalized = json.dumps(arguments, sort_keys=True)
    operation_str = f"{tool_name}:{normalized}"
    return hashlib.sha256(operation_str.encode()).hexdigest()[:16]
```

Same tool + same arguments = same hash = auto-approved.

## Testing

Run comprehensive approval system tests:

```bash
python test_approval_system.py
```

Tests verify:
- ✅ Permission levels enforced
- ✅ CRITICAL operations NEVER auto-approve
- ✅ SAFE operations always auto-approve
- ✅ Auto-approval patterns work
- ✅ Session limits prevent excessive approvals
- ✅ Previously approved operations remembered

## Adding Custom Rules

Edit `ui/approval_handler.py` in `setup_auto_approval_rules()`:

```python
def setup_auto_approval_rules(approval_tracker):
    # Your custom rule
    approval_tracker.add_auto_approval_pattern({
        'name': 'My custom rule',
        'tool': 'execute_python',
        'argument_patterns': {
            'code': r'print\(.*\)'  # Only auto-approve print statements
        },
        'conditions': [
            {
                'type': 'session_limit',
                'max_uses': 20
            }
        ]
    })
```

## Best Practices

### For Users

1. **Review CRITICAL approvals carefully** - They can modify your system
2. **Use "Approve Similar" for trusted operations** - Reduces interruptions
3. **Check approval statistics** - See what's being auto-approved
4. **Reset approvals if concerned** - Settings → Tool Approvals → Reset

### For Developers

1. **Mark destructive tools as CRITICAL** - Always require approval
2. **Use SAFE for read-only** - Don't interrupt workflow
3. **Add sensible auto-approval rules** - Balance security and UX
4. **Test approval flows** - Verify critical operations can't bypass

## Troubleshooting

### Tools Not Working

**Problem**: Tools execute but nothing happens

**Solution**: Check approval handler is initialized:
```python
if 'approval_handler' in st.session_state:
    print("Approval handler active")
```

### Too Many Approvals

**Problem**: Getting approval prompts for same operation repeatedly

**Solution**: Click "🔄 Approve Similar" instead of "✅ Approve"

### Can't Approve Critical Operations Automatically

**Problem**: Want to auto-approve write_file

**Solution**: **This is by design** - Critical operations ALWAYS require approval for security. Use REQUIRES_APPROVAL level for less dangerous operations.

## Future Enhancements

- [ ] Custom approval rule UI in settings
- [ ] Approval history export
- [ ] Per-project approval rules
- [ ] Time-based auto-approval (e.g., approve for 1 hour)
- [ ] Approval notifications/logging
- [ ] Approval delegation (team settings)

---

**🔒 Remember**: The approval system is designed to keep you safe while minimizing interruptions. CRITICAL operations ALWAYS require your explicit approval - this cannot be bypassed.
