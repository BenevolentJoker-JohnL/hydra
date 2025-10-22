import json
import ast
import subprocess
import os
import re
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from enum import Enum
import asyncio
from loguru import logger

class ToolType(Enum):
    FUNCTION = "function"
    COMMAND = "command"
    API = "api"
    FILE = "file"

@dataclass
class Tool:
    name: str
    description: str
    parameters: Dict[str, Any]
    function: Optional[Callable] = None
    type: ToolType = ToolType.FUNCTION
    
class ToolRegistry:
    def __init__(self):
        self.tools = {}
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
        # File operations
        self.register(Tool(
            name="read_file",
            description="Read contents of a file",
            parameters={
                "path": {"type": "string", "description": "File path to read"}
            },
            function=self._read_file,
            type=ToolType.FILE
        ))
        
        self.register(Tool(
            name="write_file",
            description="Write content to a file",
            parameters={
                "path": {"type": "string", "description": "File path to write"},
                "content": {"type": "string", "description": "Content to write"}
            },
            function=self._write_file,
            type=ToolType.FILE
        ))
        
        self.register(Tool(
            name="list_directory",
            description="List files in a directory",
            parameters={
                "path": {"type": "string", "description": "Directory path"}
            },
            function=self._list_directory,
            type=ToolType.FILE
        ))
        
        # Code execution
        self.register(Tool(
            name="execute_python",
            description="Execute Python code and return output",
            parameters={
                "code": {"type": "string", "description": "Python code to execute"}
            },
            function=self._execute_python,
            type=ToolType.FUNCTION
        ))
        
        self.register(Tool(
            name="run_command",
            description="Run a shell command",
            parameters={
                "command": {"type": "string", "description": "Command to run"}
            },
            function=self._run_command,
            type=ToolType.COMMAND
        ))
        
        # Code analysis
        self.register(Tool(
            name="analyze_code",
            description="Analyze Python code for issues",
            parameters={
                "code": {"type": "string", "description": "Code to analyze"}
            },
            function=self._analyze_code,
            type=ToolType.FUNCTION
        ))
        
        # Search
        self.register(Tool(
            name="search_codebase",
            description="Search for patterns in codebase",
            parameters={
                "pattern": {"type": "string", "description": "Search pattern"},
                "path": {"type": "string", "description": "Path to search", "default": "."}
            },
            function=self._search_codebase,
            type=ToolType.FUNCTION
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
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'w') as f:
                f.write(content)
            return {"success": True, "path": path}
        except Exception as e:
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

class ToolCaller:
    def __init__(self, registry: ToolRegistry):
        self.registry = registry
        
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
        
    async def execute_tool_calls(self, tool_calls: List[Dict]) -> List[Dict]:
        """Execute extracted tool calls"""
        results = []
        
        for call in tool_calls:
            tool_name = call.get("tool") or call.get("name")
            arguments = call.get("arguments", {})
            
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
            
            tool = self.registry.get(tool_name)
            if tool and tool.function:
                try:
                    result = await tool.function(**arguments)
                    results.append({
                        "tool": tool_name,
                        "result": result
                    })
                except Exception as e:
                    results.append({
                        "tool": tool_name,
                        "error": str(e)
                    })
                    
                    # Log error to console
                    logger.error(f"❌ Tool {tool_name} failed: {e}")
                    
                    # Also log to terminal if available
                    try:
                        if hasattr(st.session_state, 'terminal'):
                            term_logger.log_error(f"Tool {tool_name} failed: {e}", "Tools")
                    except:
                        pass
            else:
                results.append({
                    "tool": tool_name,
                    "error": "Tool not found"
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