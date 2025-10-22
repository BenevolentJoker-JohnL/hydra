"""
Unified Code Assistant with Intelligent Task Routing
Handles: Generation, Debugging, Explaining, Troubleshooting, Refactoring
"""

import re
import ast
import asyncio
from typing import Dict, Any, Optional, List, Tuple
from enum import Enum
from dataclasses import dataclass
from loguru import logger
from .json_pipeline import JSONPipeline, CodeResponseSchema, ExplanationResponseSchema, AnalysisResponseSchema
from .memory_manager import get_memory_manager

class CodeTaskType(Enum):
    """Types of code tasks we can handle"""
    GENERATE = "generate"       # Create new code
    DEBUG = "debug"              # Fix broken code
    EXPLAIN = "explain"          # Explain how code works
    TROUBLESHOOT = "troubleshoot"  # Diagnose issues
    REFACTOR = "refactor"        # Improve existing code
    REVIEW = "review"            # Code review
    OPTIMIZE = "optimize"        # Performance optimization
    TEST = "test"                # Generate tests
    DOCUMENT = "document"        # Add documentation

@dataclass
class CodeTask:
    """Represents a code-related task"""
    task_type: CodeTaskType
    prompt: str
    code: Optional[str] = None
    language: str = "python"
    context: Dict[str, Any] = None
    error_message: Optional[str] = None
    performance_metrics: Optional[Dict] = None

class TaskDetector:
    """Intelligently detect task type from prompt and context"""
    
    # Keywords for each task type
    TASK_KEYWORDS = {
        CodeTaskType.GENERATE: [
            'write', 'create', 'implement', 'build', 'make', 'develop',
            'code', 'function', 'class', 'module', 'script', 'program'
        ],
        CodeTaskType.DEBUG: [
            'debug', 'fix', 'error', 'bug', 'broken', 'crash', 'exception',
            'not working', 'doesn\'t work', 'issue', 'problem', 'fault'
        ],
        CodeTaskType.EXPLAIN: [
            'explain', 'describe', 'what', 'how', 'why', 'understand',
            'clarify', 'means', 'does', 'purpose', 'walkthrough'
        ],
        CodeTaskType.TROUBLESHOOT: [
            'troubleshoot', 'diagnose', 'investigate', 'analyze error',
            'root cause', 'why is', 'figure out', 'identify issue'
        ],
        CodeTaskType.REFACTOR: [
            'refactor', 'improve', 'clean', 'reorganize', 'restructure',
            'simplify', 'better', 'cleaner', 'more efficient', 'redesign'
        ],
        CodeTaskType.REVIEW: [
            'review', 'check', 'audit', 'evaluate', 'assess', 'critique',
            'feedback', 'suggestions', 'improvements'
        ],
        CodeTaskType.OPTIMIZE: [
            'optimize', 'performance', 'faster', 'speed up', 'efficient',
            'reduce memory', 'complexity', 'bottleneck', 'slow'
        ],
        CodeTaskType.TEST: [
            'test', 'unit test', 'testing', 'test case', 'coverage',
            'pytest', 'unittest', 'mock', 'assertion'
        ],
        CodeTaskType.DOCUMENT: [
            'document', 'documentation', 'docstring', 'comment', 'annotate',
            'readme', 'api docs', 'usage', 'examples'
        ]
    }
    
    @classmethod
    def detect_task_type(cls, prompt: str, context: Dict = None) -> CodeTaskType:
        """Detect the task type from prompt and context"""
        prompt_lower = prompt.lower()
        context = context or {}
        
        # Check for explicit task type in context
        if 'task_type' in context:
            task_str = context['task_type'].upper()
            if task_str in CodeTaskType.__members__:
                return CodeTaskType[task_str]
        
        # Score each task type based on keyword matches
        scores = {}
        for task_type, keywords in cls.TASK_KEYWORDS.items():
            score = sum(1 for keyword in keywords if keyword in prompt_lower)
            scores[task_type] = score
        
        # Check for specific patterns
        if 'error' in context or 'traceback' in context or 'exception' in prompt_lower:
            scores[CodeTaskType.DEBUG] += 3
            scores[CodeTaskType.TROUBLESHOOT] += 2
        
        if any(pattern in prompt_lower for pattern in ['what is', 'how does', 'explain']):
            scores[CodeTaskType.EXPLAIN] += 3
        
        if 'code' in context and not any(word in prompt_lower for word in ['write', 'create', 'implement']):
            # If code is provided and we're not generating new code
            if 'improve' in prompt_lower or 'better' in prompt_lower:
                scores[CodeTaskType.REFACTOR] += 2
            elif 'performance' in prompt_lower or 'slow' in prompt_lower:
                scores[CodeTaskType.OPTIMIZE] += 2
        
        # Return task with highest score, default to GENERATE
        if max(scores.values()) > 0:
            return max(scores, key=scores.get)
        return CodeTaskType.GENERATE
    
    @classmethod
    def extract_code_from_context(cls, prompt: str, context: Dict) -> Optional[str]:
        """Extract code from prompt or context"""
        # Check context first
        if context:
            if 'code' in context:
                return context['code']
            if 'file_content' in context:
                return context['file_content']
            if 'referenced_files' in context and context['referenced_files']:
                # Return first file's content
                return next(iter(context['referenced_files'].values()))
        
        # Extract from prompt using code block detection
        code_pattern = r'```(?:\w+)?\s*\n(.*?)```'
        matches = re.findall(code_pattern, prompt, re.DOTALL)
        if matches:
            return matches[0].strip()
        
        return None

class CodeAssistant:
    """Unified code assistant with intelligent routing"""
    
    def __init__(self, load_balancer=None):
        self.lb = load_balancer
        self.detector = TaskDetector()
        self.json_pipeline = JSONPipeline(load_balancer)
        
        # Task-specific model preferences
        self.task_models = {
            CodeTaskType.GENERATE: ['qwen2.5-coder:14b', 'deepseek-coder:latest', 'codestral:latest'],
            CodeTaskType.DEBUG: ['qwen2.5-coder:14b', 'deepseek-coder:latest', 'llama3.2:latest'],
            CodeTaskType.EXPLAIN: ['llama3.2:latest', 'mistral:latest', 'qwen2.5:14b'],
            CodeTaskType.TROUBLESHOOT: ['qwen2.5-coder:14b', 'llama3.2:latest'],
            CodeTaskType.REFACTOR: ['qwen2.5-coder:14b', 'codestral:latest'],
            CodeTaskType.REVIEW: ['qwen2.5-coder:14b', 'llama3.2:latest'],
            CodeTaskType.OPTIMIZE: ['qwen2.5-coder:14b', 'deepseek-coder:latest'],
            CodeTaskType.TEST: ['qwen2.5-coder:14b', 'codestral:latest'],
            CodeTaskType.DOCUMENT: ['llama3.2:latest', 'mistral:latest']
        }
    
    async def process(self, prompt: str, context: Dict = None) -> Dict[str, Any]:
        """Process a code-related request with intelligent routing"""
        context = context or {}
        
        # Detect task type
        task_type = self.detector.detect_task_type(prompt, context)
        logger.info(f"🎯 Detected task type: {task_type.value}")
        
        # Extract code if present
        existing_code = self.detector.extract_code_from_context(prompt, context)
        
        # Create task object
        task = CodeTask(
            task_type=task_type,
            prompt=prompt,
            code=existing_code,
            context=context
        )
        
        # Route to appropriate handler
        handler_map = {
            CodeTaskType.GENERATE: self._handle_generate,
            CodeTaskType.DEBUG: self._handle_debug,
            CodeTaskType.EXPLAIN: self._handle_explain,
            CodeTaskType.TROUBLESHOOT: self._handle_troubleshoot,
            CodeTaskType.REFACTOR: self._handle_refactor,
            CodeTaskType.REVIEW: self._handle_review,
            CodeTaskType.OPTIMIZE: self._handle_optimize,
            CodeTaskType.TEST: self._handle_test,
            CodeTaskType.DOCUMENT: self._handle_document
        }
        
        handler = handler_map.get(task_type, self._handle_generate)
        
        try:
            result = await handler(task)
            
            # Ensure JSON output through pipeline
            json_result = await self.json_pipeline.process(
                response=result.get('response', ''),
                prompt=prompt,
                context={'task_type': task_type.value},
                schema=self._get_schema_for_task(task_type)
            )
            
            # Add task metadata
            json_result['task_info'] = {
                'task_type': task_type.value,
                'had_existing_code': existing_code is not None,
                'language': task.language
            }
            
            return json_result
            
        except Exception as e:
            logger.error(f"Task processing failed: {e}")
            return {
                'error': str(e),
                'task_type': task_type.value,
                'response_type': 'error'
            }
    
    def _get_schema_for_task(self, task_type: CodeTaskType):
        """Get appropriate Pydantic schema for task type"""
        if task_type in [CodeTaskType.GENERATE, CodeTaskType.REFACTOR, CodeTaskType.OPTIMIZE]:
            return CodeResponseSchema
        elif task_type in [CodeTaskType.EXPLAIN, CodeTaskType.DOCUMENT]:
            return ExplanationResponseSchema
        elif task_type in [CodeTaskType.DEBUG, CodeTaskType.TROUBLESHOOT, CodeTaskType.REVIEW]:
            return AnalysisResponseSchema
        else:
            return CodeResponseSchema
    
    async def _handle_generate(self, task: CodeTask) -> Dict:
        """Handle code generation"""
        enhanced_prompt = f"""Generate {task.language} code for the following request:

{task.prompt}

Requirements:
- Write clean, efficient, and well-structured code
- Include necessary imports
- Follow best practices for {task.language}
- Add brief inline comments for complex logic
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.GENERATE]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': '# Code generation requires model connection'}
        
        return response
    
    async def _handle_debug(self, task: CodeTask) -> Dict:
        """Handle debugging"""
        enhanced_prompt = f"""Debug the following {task.language} code:

```{task.language}
{task.code}
```

Problem: {task.prompt}
{f"Error message: {task.context.get('error')}" if task.context and 'error' in task.context else ""}

Provide:
1. The issue identification
2. Root cause analysis
3. Fixed code
4. Explanation of the fix
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.DEBUG]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Debugging requires model connection'}
        
        return response
    
    async def _handle_explain(self, task: CodeTask) -> Dict:
        """Handle code explanation"""
        enhanced_prompt = f"""Explain the following {task.language} code:

```{task.language}
{task.code}
```

Provide:
1. Overall purpose
2. Step-by-step walkthrough
3. Key concepts used
4. Example usage if applicable
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.EXPLAIN]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Explanation requires model connection'}
        
        return response
    
    async def _handle_troubleshoot(self, task: CodeTask) -> Dict:
        """Handle troubleshooting"""
        enhanced_prompt = f"""Troubleshoot the following issue:

Code:
```{task.language}
{task.code}
```

Issue: {task.prompt}
{f"Error details: {task.context.get('error')}" if task.context and 'error' in task.context else ""}

Provide:
1. Possible causes
2. Diagnostic steps
3. Recommended solutions
4. Prevention strategies
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.TROUBLESHOOT]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Troubleshooting requires model connection'}
        
        return response
    
    async def _handle_refactor(self, task: CodeTask) -> Dict:
        """Handle code refactoring"""
        enhanced_prompt = f"""Refactor the following {task.language} code:

```{task.language}
{task.code}
```

Requirements: {task.prompt}

Focus on:
1. Code clarity and readability
2. Reduced complexity
3. Better organization
4. Performance improvements
5. Following {task.language} best practices
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.REFACTOR]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Refactoring requires model connection'}
        
        return response
    
    async def _handle_review(self, task: CodeTask) -> Dict:
        """Handle code review"""
        enhanced_prompt = f"""Review the following {task.language} code:

```{task.language}
{task.code}
```

Provide:
1. Overall assessment
2. Potential issues or bugs
3. Code quality analysis
4. Security considerations
5. Performance observations
6. Specific recommendations
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.REVIEW]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Code review requires model connection'}
        
        return response
    
    async def _handle_optimize(self, task: CodeTask) -> Dict:
        """Handle performance optimization"""
        enhanced_prompt = f"""Optimize the following {task.language} code for performance:

```{task.language}
{task.code}
```

Focus: {task.prompt}

Provide:
1. Performance bottleneck analysis
2. Optimized version of the code
3. Complexity analysis (before/after)
4. Expected performance improvements
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.OPTIMIZE]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Optimization requires model connection'}
        
        return response
    
    async def _handle_test(self, task: CodeTask) -> Dict:
        """Handle test generation"""
        enhanced_prompt = f"""Generate comprehensive tests for the following {task.language} code:

```{task.language}
{task.code}
```

Requirements:
1. Unit tests for all functions/methods
2. Edge cases and error conditions
3. Use appropriate testing framework
4. Include test documentation
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.TEST]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Test generation requires model connection'}
        
        return response
    
    async def _handle_document(self, task: CodeTask) -> Dict:
        """Handle documentation generation"""
        enhanced_prompt = f"""Generate documentation for the following {task.language} code:

```{task.language}
{task.code}
```

Include:
1. Module/class overview
2. Function/method documentation
3. Parameter descriptions
4. Return value descriptions
5. Usage examples
6. Any important notes or warnings
"""
        
        if self.lb:
            models = self.task_models[CodeTaskType.DOCUMENT]
            response = await self._call_best_model(models, enhanced_prompt)
        else:
            response = {'response': 'Documentation generation requires model connection'}
        
        return response
    
    async def _call_best_model(self, models: List[str], prompt: str) -> Dict:
        """Try to call models in preference order"""
        for model in models:
            try:
                logger.debug(f"Trying model: {model}")
                response = await self.lb.generate(
                    model=model,
                    prompt=prompt,
                    temperature=0.7
                )
                return response
            except Exception as e:
                logger.warning(f"Model {model} failed: {e}")
                continue
        
        # All models failed
        return {'response': 'All models unavailable', 'error': True}

class StreamingCodeAssistant(CodeAssistant):
    """Code assistant with streaming support"""
    
    async def process_stream(self, prompt: str, context: Dict = None):
        """Process with streaming output"""
        context = context or {}
        
        # Detect task type
        task_type = self.detector.detect_task_type(prompt, context)
        logger.info(f"🎯 Streaming task: {task_type.value}")
        
        # Get appropriate model
        models = self.task_models[task_type]
        
        successful_stream = False
        for i, model in enumerate(models):
            try:
                logger.info(f"Attempting stream with {model} ({i+1}/{len(models)})")
                
                async for chunk in self.lb.generate_stream(
                    model=model,
                    prompt=prompt
                    # NO TIMEOUT - resource constrained systems need time
                ):
                    if 'response' in chunk:
                        yield {
                            'task_type': task_type.value,
                            'chunk': chunk['response'],
                            'model': model,
                            'done': chunk.get('done', False)
                        }
                successful_stream = True
                break
            except Exception as e:
                error_msg = str(e)
                logger.warning(f"Stream with {model} failed: {error_msg}")
                
                # Check if it's an OOM error
                memory_mgr = get_memory_manager()
                if memory_mgr.detect_oom_error(error_msg):
                    logger.error(f"OOM detected with {model}, getting smaller fallbacks")
                    memory_mgr.mark_model_unloaded(model)
                    
                    # Get memory-appropriate fallback models
                    fallback_models = memory_mgr.get_fallback_chain(model, task_type.value)
                    logger.info(f"Fallback models: {fallback_models}")
                    
                    # Replace remaining models with smaller ones
                    remaining = models[i+1:] if i < len(models) - 1 else []
                    models = models[:i+1] + fallback_models[:3]  # Add up to 3 fallbacks
                
                if i == len(models) - 1:  # Last model
                    logger.error(f"All models failed for task {task_type.value}")
                    # Return error message
                    yield {
                        'task_type': task_type.value,
                        'chunk': f"\n\n⚠️ All models failed. Last error: {error_msg}\n",
                        'model': 'error',
                        'done': True,
                        'error': True
                    }
                else:
                    logger.info(f"Trying next model...")
                    continue