import json
import ast
import subprocess
import os
import re
import hashlib
from typing import Dict, List, Any, Optional, Callable, Set
from dataclasses import dataclass, field
from enum import Enum
import asyncio
from datetime import datetime, timedelta
from loguru import logger

class ToolType(Enum):
    FUNCTION = "function"
    COMMAND = "command"
    API = "api"
    FILE = "file"

class PermissionLevel(Enum):
    """Permission levels for tool execution"""
    SAFE = "safe"                      # Auto-approved, no permission needed
    REQUIRES_APPROVAL = "approval"      # Needs approval, can be auto-approved with rules
    CRITICAL = "critical"               # ALWAYS needs explicit approval, cannot bypass

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Optional[Callable] = None
    type: ToolType = ToolType.FUNCTION
    permission_level: PermissionLevel = PermissionLevel.SAFE

class ApprovalTracker:
    """
    Tracks approved operations to avoid excessive approval prompts.
    Supports auto-approval rules and pattern matching.
    """
    def __init__(self):
        self.approved_operations: Set[str] = set()  # Hashes of approved operations
        self.auto_approve_patterns: List[Dict] = []  # Auto-approval rules
        self.approval_history: List[Dict] = []       # History of approvals
        self.session_approvals: Dict[str, int] = {}  # Count per tool in session

    def _hash_operation(self, tool_name: str, arguments: Dict) -> str:
        """Create a unique hash for an operation"""
        # Normalize arguments for consistent hashing
        normalized = json.dumps(arguments, sort_keys=True)
        operation_str = f"{tool_name}:{normalized}"
        return hashlib.sha256(operation_str.encode()).hexdigest()[:16]

    def is_approved(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel) -> bool:
        """Check if operation is already approved or matches auto-approval rules"""
        # CRITICAL operations NEVER auto-approve
        if permission_level == PermissionLevel.CRITICAL:
            return False

        # SAFE operations always approved
        if permission_level == PermissionLevel.SAFE:
            return True

        # Check if this exact operation was approved before
        op_hash = self._hash_operation(tool_name, arguments)
        if op_hash in self.approved_operations:
            logger.info(f"✅ Auto-approved: {tool_name} (previously approved)")
            return True

        # Check auto-approval patterns
        for pattern in self.auto_approve_patterns:
            if self._matches_pattern(tool_name, arguments, pattern):
                logger.info(f"✅ Auto-approved: {tool_name} (matches pattern: {pattern.get('name', 'unnamed')})")
                return True

        return False

    def _matches_pattern(self, tool_name: str, arguments: Dict, pattern: Dict) -> bool:
        """Check if operation matches an auto-approval pattern"""
        # Check tool name
        if pattern.get('tool') and pattern['tool'] != tool_name:
            return False

        # Check argument patterns
        if 'argument_patterns' in pattern:
            for key, regex_pattern in pattern['argument_patterns'].items():
                if key in arguments:
                    if not re.match(regex_pattern, str(arguments[key])):
                        return False

        # Check conditions
        if 'conditions' in pattern:
            for condition in pattern['conditions']:
                if not self._check_condition(tool_name, arguments, condition):
                    return False

        return True

    def _check_condition(self, tool_name: str, arguments: Dict, condition: Dict) -> bool:
        """Check a specific condition"""
        cond_type = condition.get('type')

        if cond_type == 'path_prefix':
            path = arguments.get('path', '')
            allowed_prefixes = condition.get('allowed_prefixes', [])
            return any(path.startswith(prefix) for prefix in allowed_prefixes)

        elif cond_type == 'file_extension':
            path = arguments.get('path', '')
            allowed_extensions = condition.get('allowed_extensions', [])
            return any(path.endswith(ext) for ext in allowed_extensions)

        elif cond_type == 'max_file_size':
            # Check if file exists and is under size limit
            path = arguments.get('path', '')
            max_size = condition.get('max_bytes', 1024*1024)  # 1MB default
            if os.path.exists(path):
                return os.path.getsize(path) <= max_size
            return True  # If doesn't exist yet, allow

        elif cond_type == 'session_limit':
            # Check if tool hasn't been used too many times this session
            max_uses = condition.get('max_uses', 10)
            return self.session_approvals.get(tool_name, 0) < max_uses

        return True

    def record_approval(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel,
                       auto_approved: bool = False):
        """Record an approval"""
        op_hash = self._hash_operation(tool_name, arguments)
        self.approved_operations.add(op_hash)

        # Track session usage
        self.session_approvals[tool_name] = self.session_approvals.get(tool_name, 0) + 1

        # Add to history
        self.approval_history.append({
            'tool': tool_name,
            'arguments': arguments,
            'permission_level': permission_level.value,
            'auto_approved': auto_approved,
            'timestamp': datetime.now().isoformat(),
            'hash': op_hash
        })

        logger.debug(f"📝 Recorded approval: {tool_name} (auto: {auto_approved})")

    def add_auto_approval_pattern(self, pattern: Dict):
        """Add an auto-approval pattern"""
        self.auto_approve_patterns.append(pattern)
        logger.info(f"➕ Added auto-approval pattern: {pattern.get('name', 'unnamed')}")

    def get_approval_stats(self) -> Dict:
        """Get statistics about approvals"""
        return {
            'total_approvals': len(self.approval_history),
            'unique_operations': len(self.approved_operations),
            'auto_approval_patterns': len(self.auto_approve_patterns),
            'session_usage': dict(self.session_approvals),
            'recent_approvals': self.approval_history[-10:]  # Last 10
        }

class ToolRegistry:
    def __init__(self, use_git: bool = True, project_dir: str = "."):
        self.tools = {}
        self.use_git = use_git
        self.git = None

        # Initialize git integration if enabled
        if use_git:
            try:
                from .git_integration import GitIntegration
                self.git = GitIntegration(project_dir)
                if self.git.is_git_repo():
                    logger.info("✅ Git integration enabled for tools")
                else:
                    logger.info("📁 Not a git repo, git integration disabled")
                    self.git = None
            except Exception as e:
                logger.warning(f"⚠️ Git integration unavailable: {e}")
                self.git = None

        self._register_default_tools()
        
    def register(self, tool: Tool):
        self.tools[tool.name] = tool
        
    def get(self, name: str) -> Optional[Tool]:
        return self.tools.get(name)
        
    def list_tools(self) -> List[Dict]:
        return [
            {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters
            }
            for tool in self.tools.values()
        ]
        
    def _register_default_tools(self):
        # File operations - READ ONLY (SAFE)
        self.register(Tool(
            name="read_file",
            description="Read contents of a file",
            parameters={
                "path": {"type": "string", "description": "File path to read"}
            },
            function=self._read_file,
            type=ToolType.FILE,
            permission_level=PermissionLevel.SAFE  # Reading is safe
        ))

        self.register(Tool(
            name="write_file",
            description="Write content to a file (CRITICAL: modifies filesystem)",
            parameters={
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"}
            },
            function=self._write_file,
            type=ToolType.FILE,
            permission_level=PermissionLevel.CRITICAL  # Writing is critical - always needs approval
        ))

        self.register(Tool(
            name="list_directory",
            description="List files in a directory",
            parameters={
                "path": {"type": "string", "description": "Directory path"}
            },
            function=self._list_directory,
            type=ToolType.FILE,
            permission_level=PermissionLevel.SAFE  # Listing is safe
        ))

        # Code execution - REQUIRES APPROVAL
        self.register(Tool(
            name="execute_python",
            description="Execute Python code and return output (can be auto-approved with rules)",
            parameters={
                "code": {"type": "string", "description": "Python code to execute"}
            },
            function=self._execute_python,
            type=ToolType.FUNCTION,
            permission_level=PermissionLevel.REQUIRES_APPROVAL  # Can be auto-approved
        ))

        self.register(Tool(
            name="run_command",
            description="Run a shell command (CRITICAL: can modify system)",
            parameters={
                "command": {"type": "string", "description": "Command to run"}
            },
            function=self._run_command,
            type=ToolType.COMMAND,
            permission_level=PermissionLevel.CRITICAL  # Shell commands are critical
        ))

        # Code analysis - SAFE
        self.register(Tool(
            name="analyze_code",
            description="Analyze Python code for issues",
            parameters={
                "code": {"type": "string", "description": "Code to analyze"}
            },
            function=self._analyze_code,
            type=ToolType.FUNCTION,
            permission_level=PermissionLevel.SAFE  # Analysis is safe
        ))

        # Search - SAFE
        self.register(Tool(
            name="search_codebase",
            description="Search for patterns in codebase",
            parameters={
                "pattern": {"type": "string", "description": "Search pattern"},
                "path": {"type": "string", "description": "Path to search", "default": "."}
            },
            function=self._search_codebase,
            type=ToolType.FUNCTION,
            permission_level=PermissionLevel.SAFE  # Searching is safe
        ))

        # Git operations
        if self.git and self.git.is_git_repo():
            self.register(Tool(
                name="git_commit",
                description="Commit current changes with a message",
                parameters={
                    "message": {"type": "string", "description": "Commit message"}
                },
                function=self._git_commit,
                type=ToolType.COMMAND,
                permission_level=PermissionLevel.REQUIRES_APPROVAL  # Commits need approval but can auto-approve
            ))

            self.register(Tool(
                name="git_status",
                description="Get git repository status",
                parameters={},
                function=self._git_status,
                type=ToolType.FUNCTION,
                permission_level=PermissionLevel.SAFE
            ))
        
    async def _read_file(self, path: str) -> Dict:
        try:
            with open(path, 'r') as f:
                content = f.read()
            return {"success": True, "content": content}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def _write_file(self, path: str, content: str) -> Dict:
        try:
            # Git-aware file writing
            result = {"success": True, "path": path}

            # If git integration is available, generate diff first
            if self.git and self.git.is_git_repo():
                try:
                    # Generate diff before writing
                    file_change = self.git.create_file_change(path, content)
                    result["diff"] = file_change.diff
                    result["change_type"] = file_change.change_type
                    result["git_enabled"] = True

                    # Create Hydra branch if not on one
                    status = self.git.get_status()
                    if not status.current_branch.startswith(self.git.hydra_branch_prefix):
                        success, branch_name = self.git.create_hydra_branch("file-edits")
                        if success:
                            result["branch_created"] = branch_name
                            logger.info(f"📝 Created branch for edits: {branch_name}")
                except Exception as git_error:
                    logger.warning(f"Git operations failed, proceeding without git: {git_error}")
                    result["git_enabled"] = False

            # Write the file
            os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)

            logger.success(f"✅ Wrote file: {path}")
            return result

        except Exception as e:
            logger.error(f"❌ Failed to write {path}: {e}")
            return {"success": False, "error": str(e)}
            
    async def _list_directory(self, path: str) -> Dict:
        try:
            files = os.listdir(path)
            return {"success": True, "files": files}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def _execute_python(self, code: str) -> Dict:
        try:
            result = subprocess.run(
                ["python", "-c", code],
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Execution timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def _run_command(self, command: str) -> Dict:
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30
            )
            return {
                "success": True,
                "stdout": result.stdout,
                "stderr": result.stderr,
                "returncode": result.returncode
            }
        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Command timeout"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    async def _analyze_code(self, code: str) -> Dict:
        try:
            tree = ast.parse(code)
            
            issues = []
            functions = []
            classes = []
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    functions.append(node.name)
                elif isinstance(node, ast.ClassDef):
                    classes.append(node.name)
                    
            return {
                "success": True,
                "functions": functions,
                "classes": classes,
                "issues": issues,
                "valid_syntax": True
            }
        except SyntaxError as e:
            return {
                "success": False,
                "error": str(e),
                "valid_syntax": False
            }
            
    async def _search_codebase(self, pattern: str, path: str = ".") -> Dict:
        try:
            result = subprocess.run(
                ["grep", "-r", "-n", pattern, path],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            matches = []
            for line in result.stdout.split('\n'):
                if line:
                    parts = line.split(':', 2)
                    if len(parts) >= 3:
                        matches.append({
                            "file": parts[0],
                            "line": parts[1],
                            "content": parts[2]
                        })
                        
            return {"success": True, "matches": matches[:20]}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _git_commit(self, message: str) -> Dict:
        """Commit current changes"""
        if not self.git:
            return {"success": False, "error": "Git not available"}

        try:
            success = self.git.commit_changes(message)
            if success:
                status = self.git.get_status()
                return {
                    "success": True,
                    "message": "Changes committed",
                    "branch": status.current_branch,
                    "commit_message": message
                }
            else:
                return {"success": False, "error": "Commit failed"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _git_status(self) -> Dict:
        """Get git repository status"""
        if not self.git:
            return {"success": False, "error": "Git not available"}

        try:
            status = self.git.get_status()
            return {
                "success": True,
                "is_repo": status.is_repo,
                "current_branch": status.current_branch,
                "is_clean": status.is_clean,
                "modified_files": status.modified_files,
                "untracked_files": status.untracked_files,
                "staged_files": status.staged_files
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

class ToolCaller:
    def __init__(self, registry: ToolRegistry, approval_tracker: Optional[ApprovalTracker] = None):
        self.registry = registry
        self.approval_tracker = approval_tracker or ApprovalTracker()
        self.approval_callback = None  # Will be set by UI to handle approval requests
        
    def extract_tool_calls(self, response: str) -> List[Dict]:
        """Extract tool calls from model response"""
        tool_calls = []
        
        # Pattern 1: JSON-like tool calls
        json_pattern = r'```tool\n(.*?)\n```'
        json_matches = re.findall(json_pattern, response, re.DOTALL)
        
        for match in json_matches:
            try:
                tool_call = json.loads(match)
                tool_calls.append(tool_call)
            except:
                pass
                
        # Pattern 2: Function-like calls
        func_pattern = r'(\w+)\((.*?)\)'
        func_matches = re.findall(func_pattern, response)
        
        for name, args in func_matches:
            if name in self.registry.tools:
                try:
                    # Parse arguments
                    args_dict = {}
                    if args:
                        # Simple parsing for key=value pairs
                        for arg in args.split(','):
                            if '=' in arg:
                                key, value = arg.split('=', 1)
                                key = key.strip()
                                value = value.strip().strip('"\'')
                                args_dict[key] = value
                                
                    tool_calls.append({
                        "tool": name,
                        "arguments": args_dict
                    })
                except:
                    pass
                    
        return tool_calls
        
    def set_approval_callback(self, callback):
        """Set callback function for requesting user approval"""
        self.approval_callback = callback

    async def _request_approval(self, tool_name: str, arguments: Dict, permission_level: PermissionLevel) -> bool:
        """Request user approval for tool execution"""
        # If no callback is set, deny critical operations by default
        if not self.approval_callback:
            if permission_level == PermissionLevel.CRITICAL:
                logger.warning(f"⚠️ No approval callback set, denying critical operation: {tool_name}")
                return False
            return True  # Allow non-critical if no callback

        # Request approval through callback
        try:
            approved = await self.approval_callback(tool_name, arguments, permission_level)
            return approved
        except Exception as e:
            logger.error(f"❌ Approval callback failed: {e}")
            return False

    async def execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Execute extracted tool calls with approval checks"""
        results = []

        for call in tool_calls:
            tool_name = call.get("tool") or call.get("name")
            arguments = call.get("arguments", {}) or call.get("parameters", {})

            # Get tool info
            tool = self.registry.get(tool_name)
            if not tool:
                results.append({
                    "tool": tool_name,
                    "error": "Tool not found",
                    "approved": False
                })
                continue

            # Check if operation needs approval
            permission_level = tool.permission_level
            is_auto_approved = self.approval_tracker.is_approved(tool_name, arguments, permission_level)

            if not is_auto_approved:
                # Need to request approval
                logger.info(f"🔐 Requesting approval for {permission_level.value} operation: {tool_name}")

                approved = await self._request_approval(tool_name, arguments, permission_level)

                if not approved:
                    logger.warning(f"⛔ Operation denied by user: {tool_name}")
                    results.append({
                        "tool": tool_name,
                        "error": "Operation denied by user",
                        "approved": False,
                        "permission_level": permission_level.value
                    })
                    continue

                # Record approval
                self.approval_tracker.record_approval(tool_name, arguments, permission_level, auto_approved=False)
            else:
                # Auto-approved, still record it
                self.approval_tracker.record_approval(tool_name, arguments, permission_level, auto_approved=True)

            # Log to console
            logger.info(f"🔨 Tool call: {tool_name} with args: {arguments}")

            # Also log to terminal if available
            try:
                import streamlit as st
                if hasattr(st.session_state, 'terminal'):
                    from ..ui.terminal import GenerationLogger
                    term_logger = GenerationLogger(st.session_state.terminal)
                    term_logger.log_tool_call(tool_name, arguments)
            except:
                pass

            # Execute tool
            if tool.function:
                try:
                    result = await tool.function(**arguments)
                    results.append({
                        "tool": tool_name,
                        "result": result,
                        "approved": True,
                        "permission_level": permission_level.value,
                        "auto_approved": is_auto_approved
                    })
                except Exception as e:
                    results.append({
                        "tool": tool_name,
                        "error": str(e),
                        "approved": True,
                        "execution_failed": True
                    })

                    # Log error to console
                    logger.error(f"❌ Tool {tool_name} failed: {e}")

                    # Also log to terminal if available
                    try:
                        import streamlit as st
                        if hasattr(st.session_state, 'terminal'):
                            term_logger.log_error(f"Tool {tool_name} failed: {e}", "Tools")
                    except:
                        pass
            else:
                results.append({
                    "tool": tool_name,
                    "error": "Tool function not available",
                    "approved": True
                })

        return results
        
    def format_tools_for_prompt(self) -> str:
        """Format available tools for inclusion in prompt"""
        tools_desc = "Available tools:\n\n"
        
        for tool in self.registry.tools.values():
            tools_desc += f"- {tool.name}: {tool.description}\n"
            tools_desc += f"  Parameters: {json.dumps(tool.parameters)}\n\n"
            
        tools_desc += "\nTo use a tool, format your response as:\n"
        tools_desc += "```tool\n{\"tool\": \"tool_name\", \"arguments\": {\"param\": \"value\"}}\n```\n"
        
        return tools_desc

class ToolEnhancedGenerator:
    def __init__(self, load_balancer, tool_registry: ToolRegistry):
        self.lb = load_balancer
        self.registry = tool_registry
        self.caller = ToolCaller(tool_registry)
        
    async def generate_with_tools(self, prompt: str, model: str, **kwargs) -> Dict:
        # Add tool descriptions to prompt
        enhanced_prompt = f"""{prompt}

{self.caller.format_tools_for_prompt()}

When you need to use tools, include tool calls in your response.
"""
        
        # Get initial response
        response = await self.lb.generate(
            model=model,
            prompt=enhanced_prompt,
            **kwargs
        )
        
        # Extract and execute tool calls
        tool_calls = self.caller.extract_tool_calls(response['response'])
        
        if tool_calls:
            tool_results = await self.caller.execute_tool_calls(tool_calls)
            
            # Generate follow-up with tool results
            follow_up_prompt = f"""Previous response: {response['response']}

Tool execution results:
{json.dumps(tool_results, indent=2)}

Please continue with the task using these results."""
            
            final_response = await self.lb.generate(
                model=model,
                prompt=follow_up_prompt,
                **kwargs
            )
            
            return {
                "response": final_response['response'],
                "tool_calls": tool_calls,
                "tool_results": tool_results
            }
            
        return response