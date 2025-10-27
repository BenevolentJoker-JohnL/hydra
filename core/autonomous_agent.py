"""
Autonomous Agent - Claude Code-style iterative task execution

Provides autonomous multi-step problem solving by orchestrating:
- ReasoningEngine for decision-making
- ToolCaller for action execution
- ModelOrchestrator for complexity analysis
- Iterative loop until task completion
"""

import asyncio
import json
from typing import Dict, List, Any, Optional, AsyncGenerator
from dataclasses import dataclass, field
from enum import Enum
from loguru import logger

from .reasoning_engine import ReasoningEngine, ReasoningMode
from .tools import ToolCaller
from .orchestrator import ModelOrchestrator, TaskComplexity


class AgentState(Enum):
    """Agent execution states"""
    INITIALIZING = "initializing"
    PLANNING = "planning"
    EXECUTING = "executing"
    ANALYZING = "analyzing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class AgentStep:
    """Represents a single step in agent execution"""
    step_number: int
    state: AgentState
    action: str  # What the agent is doing
    reasoning: Optional[str] = None  # Why it's doing it
    tool_calls: List[Dict] = field(default_factory=list)
    tool_results: List[Dict] = field(default_factory=list)
    response: Optional[str] = None
    error: Optional[str] = None
    complete: bool = False


@dataclass
class AgentConfig:
    """Configuration for autonomous agent behavior"""
    max_iterations: int = 10  # Safety limit
    require_completion_confirmation: bool = True
    stream_thinking: bool = True
    enable_self_correction: bool = True
    complexity_threshold_for_deep_thinking: float = 7.0


class AutonomousAgent:
    """
    Autonomous agent that iteratively solves tasks using reasoning and tools.

    Similar to Claude Code, this agent:
    1. Analyzes the task and current state
    2. Reasons about what to do next
    3. Executes tools or generates responses
    4. Analyzes results and checks completion
    5. Loops until task is done or max iterations reached
    """

    def __init__(
        self,
        reasoning_engine: ReasoningEngine,
        orchestrator: ModelOrchestrator,
        tool_caller: ToolCaller,
        config: Optional[AgentConfig] = None
    ):
        self.reasoning_engine = reasoning_engine
        self.orchestrator = orchestrator
        self.tool_caller = tool_caller
        self.config = config or AgentConfig()

        # Track execution state
        self.steps: List[AgentStep] = []
        self.context_memory: List[Dict] = []

        logger.info("🤖 AutonomousAgent initialized")

    async def execute_autonomous(
        self,
        task: str,
        context: Optional[Dict] = None,
        model: Optional[str] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Autonomously execute a task with iterative planning and execution.

        Yields progress updates at each step for streaming to UI.

        Args:
            task: The task to accomplish
            context: Additional context (files, error messages, etc.)
            model: Optional model to use (otherwise auto-selected)

        Yields:
            Dict containing step updates, thinking, tool execution, responses
        """
        logger.info(f"🚀 Starting autonomous execution: {task[:100]}...")

        # Initialize
        yield {
            'state': AgentState.INITIALIZING.value,
            'message': '🤖 Initializing autonomous agent...',
            'step': 0
        }

        # Analyze task complexity
        complexity = await self.orchestrator.analyze_task(task, context)
        logger.info(f"📊 Task complexity: {complexity.value}")

        yield {
            'state': AgentState.INITIALIZING.value,
            'message': f'📊 Task complexity assessed: {complexity.value}',
            'complexity': complexity.value,
            'step': 0
        }

        # Build initial context
        task_context = self._build_context(task, context)
        iteration = 0
        task_complete = False

        # Main autonomous loop
        while not task_complete and iteration < self.config.max_iterations:
            iteration += 1
            logger.info(f"🔄 Iteration {iteration}/{self.config.max_iterations}")

            # Create step
            step = AgentStep(
                step_number=iteration,
                state=AgentState.PLANNING,
                action="planning_next_action"
            )
            self.steps.append(step)

            yield {
                'state': AgentState.PLANNING.value,
                'message': f'🧠 Step {iteration}: Planning next action...',
                'step': iteration
            }

            # PHASE 1: REASON about what to do next
            step.state = AgentState.PLANNING
            planning_decision = await self._reason_about_next_action(
                task, task_context, iteration
            )

            step.reasoning = planning_decision.get('reasoning')
            step.action = planning_decision.get('action')

            if self.config.stream_thinking and step.reasoning:
                yield {
                    'state': AgentState.PLANNING.value,
                    'message': '💭 Thinking...',
                    'thinking': step.reasoning,
                    'step': iteration
                }

            yield {
                'state': AgentState.PLANNING.value,
                'message': f'📋 Action: {step.action}',
                'action': step.action,
                'step': iteration
            }

            # PHASE 2: EXECUTE the planned action
            step.state = AgentState.EXECUTING
            yield {
                'state': AgentState.EXECUTING.value,
                'message': f'⚙️ Executing: {step.action}',
                'step': iteration
            }

            execution_result = await self._execute_action(
                planning_decision, task, task_context, model
            )

            step.tool_calls = execution_result.get('tool_calls', [])
            step.tool_results = execution_result.get('tool_results', [])
            step.response = execution_result.get('response')
            step.error = execution_result.get('error')

            # Stream tool execution
            if step.tool_calls:
                for i, tool_call in enumerate(step.tool_calls):
                    yield {
                        'state': AgentState.EXECUTING.value,
                        'message': f'🔧 Tool {i+1}/{len(step.tool_calls)}: {tool_call.get("tool")}',
                        'tool_call': tool_call,
                        'step': iteration
                    }

                    if i < len(step.tool_results):
                        yield {
                            'state': AgentState.EXECUTING.value,
                            'message': '✅ Tool executed',
                            'tool_result': step.tool_results[i],
                            'step': iteration
                        }

            # Stream response chunks if present
            if step.response:
                yield {
                    'state': AgentState.EXECUTING.value,
                    'chunk': step.response,
                    'step': iteration
                }

            # PHASE 3: ANALYZE results and check completion
            step.state = AgentState.ANALYZING
            yield {
                'state': AgentState.ANALYZING.value,
                'message': '🔍 Analyzing results...',
                'step': iteration
            }

            analysis = await self._analyze_step_results(
                task, step, task_context
            )

            step.complete = analysis.get('task_complete', False)
            task_complete = step.complete

            # Update context with what we learned
            self.context_memory.append({
                'step': iteration,
                'action': step.action,
                'tool_results': step.tool_results,
                'response': step.response,
                'complete': step.complete
            })

            yield {
                'state': AgentState.ANALYZING.value,
                'message': analysis.get('message', 'Step analyzed'),
                'complete': task_complete,
                'step': iteration
            }

            # Handle errors with self-correction
            if step.error and self.config.enable_self_correction:
                logger.warning(f"⚠️ Error in step {iteration}: {step.error}")
                yield {
                    'state': AgentState.ANALYZING.value,
                    'message': f'⚠️ Error detected, will attempt correction: {step.error}',
                    'error': step.error,
                    'step': iteration
                }
                # Add error to context for next iteration
                task_context['last_error'] = step.error

        # Final state
        if task_complete:
            logger.success(f"✅ Task completed in {iteration} steps")
            yield {
                'state': AgentState.COMPLETED.value,
                'message': f'✅ Task completed successfully in {iteration} steps!',
                'step': iteration,
                'done': True
            }
        else:
            logger.warning(f"⚠️ Max iterations ({self.config.max_iterations}) reached")
            yield {
                'state': AgentState.FAILED.value,
                'message': f'⚠️ Reached maximum iterations ({self.config.max_iterations})',
                'step': iteration,
                'done': True
            }

    def _build_context(self, task: str, context: Optional[Dict]) -> Dict:
        """Build comprehensive context for agent reasoning"""
        ctx = {
            'task': task,
            'available_tools': self.tool_caller.list_tools(),
            'previous_steps': [],
            'context_memory': []
        }

        if context:
            ctx.update(context)

        return ctx

    async def _reason_about_next_action(
        self,
        task: str,
        context: Dict,
        iteration: int
    ) -> Dict[str, Any]:
        """
        Use reasoning engine to decide what to do next.

        Returns dict with:
        - reasoning: The thought process
        - action: What to do (use_tool, generate_code, ask_clarification, complete)
        - details: Specific parameters for the action
        """
        # Build reasoning prompt
        reasoning_prompt = self._build_reasoning_prompt(task, context, iteration)

        # Use reasoning engine
        try:
            result = await self.reasoning_engine.reason(
                task=reasoning_prompt,
                mode=ReasoningMode.AUTO  # Let it decide complexity
            )

            # Parse the reasoning output
            decision = self._parse_reasoning_output(result.get('response', ''))
            return decision

        except Exception as e:
            logger.error(f"Reasoning failed: {e}")
            # Fallback to basic action
            return {
                'reasoning': f"Error in reasoning: {e}",
                'action': 'generate_response',
                'details': {}
            }

    def _build_reasoning_prompt(self, task: str, context: Dict, iteration: int) -> str:
        """Build prompt for reasoning about next action"""
        previous_steps = "\n".join([
            f"Step {mem['step']}: {mem['action']} → {'✅' if mem.get('complete') else '⏳'}"
            for mem in self.context_memory[-3:]  # Last 3 steps
        ])

        tools_list = "\n".join([
            f"- {tool['name']}: {tool.get('description', '')}"
            for tool in context.get('available_tools', [])
        ])

        prompt = f"""You are an autonomous coding agent working on a task. Analyze the current state and decide the next action.

TASK: {task}

ITERATION: {iteration}

PREVIOUS STEPS:
{previous_steps if previous_steps else "None - this is the first step"}

AVAILABLE TOOLS:
{tools_list}

CURRENT CONTEXT:
{json.dumps(context.get('context_memory', []), indent=2) if context.get('context_memory') else 'No additional context'}

Analyze the situation and decide:
1. What is the current state?
2. What needs to be done next?
3. Which action should be taken? Options:
   - use_tool: Execute a specific tool
   - generate_code: Write code to solve the problem
   - analyze_results: Examine previous results
   - complete: Task is finished

Respond in JSON format:
{{
  "reasoning": "your step-by-step analysis",
  "action": "use_tool|generate_code|analyze_results|complete",
  "details": {{
    "tool": "tool_name if using tool",
    "parameters": {{}},
    "code_type": "if generating code"
  }},
  "confidence": 0.0-1.0
}}
"""
        return prompt

    def _parse_reasoning_output(self, output: str) -> Dict[str, Any]:
        """Parse reasoning output into structured decision"""
        try:
            # Try to extract JSON from response
            json_match = output.find('{')
            if json_match != -1:
                json_end = output.rfind('}') + 1
                json_str = output[json_match:json_end]
                decision = json.loads(json_str)
                return decision
        except:
            pass

        # Fallback: basic parsing
        return {
            'reasoning': output,
            'action': 'generate_response',
            'details': {},
            'confidence': 0.5
        }

    async def _execute_action(
        self,
        decision: Dict,
        task: str,
        context: Dict,
        model: Optional[str]
    ) -> Dict[str, Any]:
        """Execute the decided action"""
        action = decision.get('action', 'generate_response')
        details = decision.get('details', {})

        result = {
            'tool_calls': [],
            'tool_results': [],
            'response': None,
            'error': None
        }

        try:
            if action == 'use_tool':
                # Execute tool
                tool_name = details.get('tool')
                params = details.get('parameters', {})

                if tool_name:
                    tool_result = await self.tool_caller.execute_tool_calls([{
                        'tool': tool_name,
                        'parameters': params
                    }])

                    result['tool_calls'] = [{'tool': tool_name, 'parameters': params}]
                    result['tool_results'] = tool_result

            elif action == 'generate_code' or action == 'generate_response':
                # Generate response using load balancer
                # This would integrate with existing code generation
                result['response'] = f"[Generated response for {action}]"

            elif action == 'complete':
                result['response'] = "Task marked as complete by agent"

        except Exception as e:
            logger.error(f"Action execution failed: {e}")
            result['error'] = str(e)

        return result

    async def _analyze_step_results(
        self,
        task: str,
        step: AgentStep,
        context: Dict
    ) -> Dict[str, Any]:
        """Analyze if the step accomplished its goal and if task is complete"""

        # Simple heuristic for now - can be enhanced with reasoning
        has_error = step.error is not None
        has_results = bool(step.tool_results or step.response)

        # Check if this was a completion action
        if step.action == 'complete':
            return {
                'task_complete': True,
                'message': 'Agent marked task as complete'
            }

        # If we have results and no errors, consider making progress
        if has_results and not has_error:
            return {
                'task_complete': False,  # Could add more sophisticated check
                'message': 'Step completed successfully, continuing...'
            }

        # If we have errors, not complete
        if has_error:
            return {
                'task_complete': False,
                'message': f'Step encountered error: {step.error}'
            }

        return {
            'task_complete': False,
            'message': 'Step results unclear, continuing...'
        }
