"""
Claude-Style Reasoning Engine for Local Models

Implements chain-of-thought, extended thinking, self-critique, and automatic
reasoning mode selection similar to Claude's reasoning capabilities.
"""

from enum import Enum
from dataclasses import dataclass
from typing import Dict, List, Optional, Any, AsyncGenerator
from loguru import logger
import re
import asyncio


class ReasoningMode(Enum):
    """Reasoning modes inspired by Claude's capabilities"""
    FAST = "fast"                    # Direct response, no thinking
    STANDARD = "standard"            # Basic chain-of-thought
    EXTENDED = "extended"            # Deep reasoning with QwQ/thinking models
    DEEP_THINKING = "deep"           # Maximum thinking budget, multi-pass critique
    AUTO = "auto"                    # Automatically select based on complexity


class ThinkingStyle(Enum):
    """Different thinking/reasoning approaches"""
    CHAIN_OF_THOUGHT = "cot"         # Step-by-step reasoning
    TREE_OF_THOUGHT = "tot"          # Explore multiple reasoning paths
    SELF_CRITIQUE = "critique"       # Generate then critique
    ITERATIVE_REFINEMENT = "refine"  # Multiple passes with improvement


@dataclass
class ReasoningConfig:
    """Configuration for reasoning behavior"""
    mode: ReasoningMode = ReasoningMode.AUTO
    thinking_style: ThinkingStyle = ThinkingStyle.CHAIN_OF_THOUGHT
    max_thinking_tokens: int = 8000   # Budget for thinking
    max_critique_iterations: int = 2   # Self-critique loops
    temperature: float = 0.7           # Reasoning temperature
    use_reasoning_model: bool = True   # Use specialized reasoning model (QwQ)
    show_thinking: bool = True         # Show thinking process to user
    thinking_prefix: str = "<thinking>"
    thinking_suffix: str = "</thinking>"

    # Deep thinking mode parameters
    deep_thinking_tokens: int = 32000  # Maximum tokens for deep thinking
    deep_thinking_iterations: int = 3  # Multi-pass critique for deep thinking
    deep_thinking_threshold: float = 8.0  # Complexity score to trigger deep thinking


class ReasoningPrompts:
    """Prompt templates for different reasoning modes"""

    @staticmethod
    def chain_of_thought(task: str, context: Optional[str] = None) -> str:
        """Chain-of-thought prompt template"""
        return f"""Think through this step-by-step before answering.

Task: {task}
{f'Context: {context}' if context else ''}

Please reason through this carefully:
1. Break down the problem
2. Consider each step
3. Think about edge cases
4. Arrive at a solution

Use <thinking>your reasoning here</thinking> tags to show your thought process.
Then provide your final answer."""

    @staticmethod
    def extended_thinking(task: str, context: Optional[str] = None) -> str:
        """Extended thinking prompt for complex reasoning"""
        return f"""This is a complex task that requires deep, careful reasoning.

Task: {task}
{f'Context: {context}' if context else ''}

Take your time to think through this thoroughly:

<thinking>
Consider multiple approaches:
1. What are the key constraints and requirements?
2. What are different ways to solve this?
3. What are the trade-offs of each approach?
4. What edge cases or failure modes exist?
5. What is the most robust solution?

Reason through each step carefully, questioning your assumptions.
</thinking>

After your thorough analysis, provide your final answer."""

    @staticmethod
    def self_critique(response: str, original_task: str) -> str:
        """Prompt for self-critique of previous response"""
        return f"""Review and critique the following response to improve it.

Original Task: {original_task}

Previous Response:
{response}

<thinking>
Critically evaluate this response:
1. Are there any errors or inaccuracies?
2. Are there missing important details?
3. Could the explanation be clearer?
4. Are there better approaches?
5. What improvements can be made?
</thinking>

Provide an improved version that addresses any issues found."""

    @staticmethod
    def tree_of_thought(task: str, num_paths: int = 3) -> str:
        """Tree-of-thought: explore multiple reasoning paths"""
        return f"""Explore multiple different approaches to solve this task.

Task: {task}

<thinking>
Generate {num_paths} different approaches:

Approach 1:
[Detailed reasoning for first approach]
Pros:
Cons:

Approach 2:
[Detailed reasoning for second approach]
Pros:
Cons:

Approach 3:
[Detailed reasoning for third approach]
Pros:
Cons:

Evaluation:
[Compare approaches and select the best]
</thinking>

Implement the best approach."""

    @staticmethod
    def deep_thinking(task: str, context: Optional[str] = None) -> str:
        """Deep thinking prompt for maximum reasoning depth"""
        return f"""This is a highly complex task that requires your deepest, most thorough reasoning.
Take your time and think through this comprehensively.

Task: {task}
{f'Context: {context}' if context else ''}

<thinking>
You have a large thinking budget. Use it wisely to explore this problem deeply.

Phase 1: Problem Understanding
- What is the core problem or goal?
- What are all the constraints and requirements?
- What assumptions am I making?
- What edge cases or failure modes exist?
- What don't I know or understand yet?

Phase 2: Solution Exploration
- What are at least 3-5 different approaches?
- For each approach:
  * How would it work?
  * What are the pros and cons?
  * What could go wrong?
  * What resources would it need?

Phase 3: Deep Analysis
- Which approach is most promising and why?
- What are the critical success factors?
- How can I make this solution more robust?
- What optimizations are possible?
- How does this scale or generalize?

Phase 4: Implementation Planning
- What are the exact steps needed?
- What's the order of operations?
- Where might I need to be extra careful?
- What testing or validation is needed?

Phase 5: Self-Critique
- What assumptions did I make that might be wrong?
- What did I overlook or not consider?
- How could this solution be improved?
- What are the weakest parts of my reasoning?

After this thorough analysis, provide your best solution.
</thinking>"""

    @staticmethod
    def task_complexity_analysis(task: str) -> str:
        """Analyze task complexity to determine reasoning mode"""
        return f"""Analyze the complexity of this task to determine the appropriate reasoning approach.

Task: {task}

Rate this task on these dimensions (1-10):
- Complexity: How many steps or components?
- Ambiguity: How clear are the requirements?
- Novelty: How unique or creative does the solution need to be?
- Risk: How critical is correctness?

Respond with JSON:
{{
  "complexity": <1-10>,
  "ambiguity": <1-10>,
  "novelty": <1-10>,
  "risk": <1-10>,
  "recommended_mode": "fast|standard|extended|deep",
  "reasoning": "brief explanation"
}}"""


class ReasoningEngine:
    """
    Main reasoning engine that implements Claude-style thinking for local models.
    """

    def __init__(self, load_balancer, config: Optional[ReasoningConfig] = None):
        """
        Initialize reasoning engine.

        Args:
            load_balancer: SOLLOL integration or model pool
            config: Reasoning configuration
        """
        self.lb = load_balancer
        self.config = config or ReasoningConfig()
        self.prompts = ReasoningPrompts()

        # Load reasoning model from config
        from .config_loader import load_model_config
        model_config = load_model_config()
        self.reasoning_model = model_config.get('code_synthesis', {}).get('specialized', {}).get('reasoning', 'qwq:32b')
        self.standard_model = model_config['orchestrators']['heavy']['model']
        self.fast_model = model_config['orchestrators']['light']['model']

        logger.info(f"🧠 ReasoningEngine initialized:")
        logger.info(f"   Mode: {self.config.mode.value}")
        logger.info(f"   Reasoning Model: {self.reasoning_model}")
        logger.info(f"   Standard Model: {self.standard_model}")
        logger.info(f"   Fast Model: {self.fast_model}")

    async def reason(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        mode: Optional[ReasoningMode] = None
    ) -> Dict[str, Any]:
        """
        Apply reasoning to a task.

        Args:
            task: The task to reason about
            context: Additional context
            mode: Override reasoning mode

        Returns:
            Dict with 'response', 'thinking', 'mode_used', 'model_used'
        """
        mode = mode or self.config.mode

        # Auto-select mode if needed
        if mode == ReasoningMode.AUTO:
            mode = await self._auto_select_mode(task)
            logger.info(f"🎯 Auto-selected reasoning mode: {mode.value}")

        # Route to appropriate reasoning function
        if mode == ReasoningMode.FAST:
            return await self._fast_reasoning(task, context)
        elif mode == ReasoningMode.STANDARD:
            return await self._standard_reasoning(task, context)
        elif mode == ReasoningMode.EXTENDED:
            return await self._extended_reasoning(task, context)
        elif mode == ReasoningMode.DEEP_THINKING:
            return await self._deep_thinking(task, context)

    async def reason_stream(
        self,
        task: str,
        context: Optional[Dict[str, Any]] = None,
        mode: Optional[ReasoningMode] = None
    ) -> AsyncGenerator[Dict[str, Any], None]:
        """
        Stream reasoning process.

        Yields chunks with 'chunk', 'type' ('thinking'|'response'), 'done'
        """
        mode = mode or self.config.mode

        # Auto-select mode if needed
        if mode == ReasoningMode.AUTO:
            mode = await self._auto_select_mode(task)
            yield {
                'chunk': f"[Selected {mode.value} reasoning mode]\n\n",
                'type': 'metadata',
                'done': False
            }

        # Route to streaming function
        if mode == ReasoningMode.FAST:
            async for chunk in self._fast_reasoning_stream(task, context):
                yield chunk
        elif mode == ReasoningMode.STANDARD:
            async for chunk in self._standard_reasoning_stream(task, context):
                yield chunk
        elif mode == ReasoningMode.EXTENDED:
            async for chunk in self._extended_reasoning_stream(task, context):
                yield chunk
        elif mode == ReasoningMode.DEEP_THINKING:
            async for chunk in self._deep_thinking_stream(task, context):
                yield chunk

    async def _auto_select_mode(self, task: str) -> ReasoningMode:
        """Automatically select reasoning mode based on task complexity"""
        analysis_prompt = self.prompts.task_complexity_analysis(task)

        try:
            response = await self.lb.generate(
                model=self.fast_model,
                prompt=analysis_prompt,
                temperature=0.3
            )

            # Parse JSON response
            import json
            result = json.loads(response['response'])

            complexity_score = (
                result['complexity'] +
                result['ambiguity'] +
                result['novelty'] +
                result['risk']
            ) / 4

            # Trigger deep thinking for very high complexity
            if complexity_score >= self.config.deep_thinking_threshold:
                logger.info(f"🧠 High complexity ({complexity_score:.1f}) - triggering DEEP_THINKING mode")
                return ReasoningMode.DEEP_THINKING
            elif complexity_score < 4:
                return ReasoningMode.FAST
            elif complexity_score < 7:
                return ReasoningMode.STANDARD
            else:
                return ReasoningMode.EXTENDED

        except Exception as e:
            logger.warning(f"Auto-selection failed, defaulting to STANDARD: {e}")
            return ReasoningMode.STANDARD

    async def _fast_reasoning(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Fast mode: direct response without explicit thinking"""
        context_str = context.get('context_text', '') if context else ''
        prompt = f"{task}\n\n{context_str}" if context_str else task

        response = await self.lb.generate(
            model=self.fast_model,
            prompt=prompt,
            temperature=self.config.temperature
        )

        return {
            'response': response['response'],
            'thinking': None,
            'mode_used': 'fast',
            'model_used': self.fast_model,
            'thinking_tokens': 0
        }

    async def _standard_reasoning(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Standard mode: chain-of-thought reasoning"""
        context_str = context.get('context_text', '') if context else ''
        cot_prompt = self.prompts.chain_of_thought(task, context_str)

        response = await self.lb.generate(
            model=self.standard_model,
            prompt=cot_prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.max_thinking_tokens
        )

        # Extract thinking and response
        thinking, clean_response = self._extract_thinking(response['response'])

        return {
            'response': clean_response,
            'thinking': thinking,
            'mode_used': 'standard',
            'model_used': self.standard_model,
            'thinking_tokens': len(thinking.split()) if thinking else 0
        }

    async def _extended_reasoning(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Extended mode: deep reasoning with self-critique"""
        context_str = context.get('context_text', '') if context else ''

        # Use reasoning model for extended thinking
        model = self.reasoning_model if self.config.use_reasoning_model else self.standard_model

        # Determine thinking style
        if self.config.thinking_style == ThinkingStyle.TREE_OF_THOUGHT:
            prompt = self.prompts.tree_of_thought(task)
        else:
            prompt = self.prompts.extended_thinking(task, context_str)

        logger.info(f"🤔 Extended reasoning with {model}...")

        # Initial reasoning
        response = await self.lb.generate(
            model=model,
            prompt=prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.max_thinking_tokens
        )

        thinking, initial_response = self._extract_thinking(response['response'])

        # Self-critique loop if enabled
        if self.config.thinking_style == ThinkingStyle.SELF_CRITIQUE:
            for iteration in range(self.config.max_critique_iterations):
                logger.info(f"🔍 Self-critique iteration {iteration + 1}...")

                critique_prompt = self.prompts.self_critique(initial_response, task)
                critique_response = await self.lb.generate(
                    model=model,
                    prompt=critique_prompt,
                    temperature=self.config.temperature
                )

                critique_thinking, improved_response = self._extract_thinking(critique_response['response'])

                # Append critique thinking
                if critique_thinking:
                    thinking = f"{thinking}\n\n[Critique {iteration + 1}]\n{critique_thinking}"

                initial_response = improved_response

        return {
            'response': initial_response,
            'thinking': thinking,
            'mode_used': 'extended',
            'model_used': model,
            'thinking_tokens': len(thinking.split()) if thinking else 0,
            'critique_iterations': self.config.max_critique_iterations if self.config.thinking_style == ThinkingStyle.SELF_CRITIQUE else 0
        }

    async def _fast_reasoning_stream(self, task: str, context: Optional[Dict] = None) -> AsyncGenerator:
        """Stream fast reasoning"""
        context_str = context.get('context_text', '') if context else ''
        prompt = f"{task}\n\n{context_str}" if context_str else task

        async for chunk in self.lb.generate_stream(
            model=self.fast_model,
            prompt=prompt,
            temperature=self.config.temperature
        ):
            if 'response' in chunk:
                yield {
                    'chunk': chunk['response'],
                    'type': 'response',
                    'done': chunk.get('done', False)
                }

    async def _standard_reasoning_stream(self, task: str, context: Optional[Dict] = None) -> AsyncGenerator:
        """Stream standard chain-of-thought reasoning"""
        context_str = context.get('context_text', '') if context else ''
        cot_prompt = self.prompts.chain_of_thought(task, context_str)

        thinking_buffer = ""
        response_buffer = ""
        in_thinking = False
        thinking_sent = False

        async for chunk in self.lb.generate_stream(
            model=self.standard_model,
            prompt=cot_prompt,
            temperature=self.config.temperature
        ):
            if 'response' in chunk:
                text = chunk['response']

                # Detect thinking tags
                if '<thinking>' in text and not in_thinking:
                    in_thinking = True
                    thinking_sent = False

                if in_thinking and not thinking_sent:
                    thinking_buffer += text
                    # Send thinking chunk
                    yield {
                        'chunk': text,
                        'type': 'thinking',
                        'done': False
                    }

                    if '</thinking>' in thinking_buffer:
                        in_thinking = False
                        thinking_sent = True
                else:
                    # Regular response
                    yield {
                        'chunk': text,
                        'type': 'response',
                        'done': chunk.get('done', False)
                    }

    async def _extended_reasoning_stream(self, task: str, context: Optional[Dict] = None) -> AsyncGenerator:
        """Stream extended reasoning with thinking process"""
        context_str = context.get('context_text', '') if context else ''
        model = self.reasoning_model if self.config.use_reasoning_model else self.standard_model

        if self.config.thinking_style == ThinkingStyle.TREE_OF_THOUGHT:
            prompt = self.prompts.tree_of_thought(task)
        else:
            prompt = self.prompts.extended_thinking(task, context_str)

        yield {
            'chunk': f"\n[Using {model} for extended reasoning]\n\n",
            'type': 'metadata',
            'done': False
        }

        in_thinking = False
        async for chunk in self.lb.generate_stream(
            model=model,
            prompt=prompt,
            temperature=self.config.temperature
        ):
            if 'response' in chunk:
                text = chunk['response']

                # Detect thinking sections
                if '<thinking>' in text:
                    in_thinking = True
                if '</thinking>' in text:
                    in_thinking = False

                chunk_type = 'thinking' if in_thinking or '<thinking>' in text or '</thinking>' in text else 'response'

                yield {
                    'chunk': text,
                    'type': chunk_type,
                    'done': chunk.get('done', False)
                }

    async def _deep_thinking(self, task: str, context: Optional[Dict] = None) -> Dict[str, Any]:
        """Deep thinking mode: maximum thinking budget with multi-pass critique"""
        context_str = context.get('context_text', '') if context else ''

        # Always use reasoning model for deep thinking
        model = self.reasoning_model

        prompt = self.prompts.deep_thinking(task, context_str)

        logger.info(f"🧠💭 Deep thinking with {model} (max {self.config.deep_thinking_tokens} tokens)...")

        # Initial deep reasoning
        response = await self.lb.generate(
            model=model,
            prompt=prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.deep_thinking_tokens
        )

        thinking, initial_response = self._extract_thinking(response['response'])

        # Multi-pass self-critique for deep thinking
        for iteration in range(self.config.deep_thinking_iterations):
            logger.info(f"🔍 Deep critique iteration {iteration + 1}/{self.config.deep_thinking_iterations}...")

            critique_prompt = self.prompts.self_critique(initial_response, task)
            critique_response = await self.lb.generate(
                model=model,
                prompt=critique_prompt,
                temperature=self.config.temperature,
                max_tokens=self.config.deep_thinking_tokens
            )

            critique_thinking, improved_response = self._extract_thinking(critique_response['response'])

            # Append critique thinking
            if critique_thinking:
                thinking = f"{thinking}\n\n[Deep Critique {iteration + 1}]\n{critique_thinking}"

            initial_response = improved_response

        logger.success(f"✨ Deep thinking complete after {self.config.deep_thinking_iterations} critique passes")

        return {
            'response': initial_response,
            'thinking': thinking,
            'mode_used': 'deep_thinking',
            'model_used': model,
            'thinking_tokens': len(thinking.split()) if thinking else 0,
            'critique_iterations': self.config.deep_thinking_iterations,
            'token_budget': self.config.deep_thinking_tokens
        }

    async def _deep_thinking_stream(self, task: str, context: Optional[Dict] = None) -> AsyncGenerator:
        """Stream deep thinking with maximum reasoning"""
        context_str = context.get('context_text', '') if context else ''
        model = self.reasoning_model

        prompt = self.prompts.deep_thinking(task, context_str)

        yield {
            'chunk': f"\n[🧠 Deep Thinking Mode - Using {model} with {self.config.deep_thinking_tokens} token budget]\n\n",
            'type': 'metadata',
            'done': False
        }

        in_thinking = False
        async for chunk in self.lb.generate_stream(
            model=model,
            prompt=prompt,
            temperature=self.config.temperature,
            max_tokens=self.config.deep_thinking_tokens
        ):
            if 'response' in chunk:
                text = chunk['response']

                # Detect thinking sections
                if '<thinking>' in text:
                    in_thinking = True
                if '</thinking>' in text:
                    in_thinking = False

                chunk_type = 'thinking' if in_thinking or '<thinking>' in text or '</thinking>' in text else 'response'

                yield {
                    'chunk': text,
                    'type': chunk_type,
                    'done': chunk.get('done', False)
                }

    def _extract_thinking(self, response: str) -> tuple[Optional[str], str]:
        """Extract thinking section from response"""
        thinking_patterns = [
            (r'<thinking>(.*?)</thinking>', '<thinking>', '</thinking>'),
            (r'\[Thinking\](.*?)\[/Thinking\]', '[Thinking]', '[/Thinking]'),
            (r'<\|thinking\|>(.*?)<\|/thinking\|>', '<|thinking|>', '<|/thinking|>'),
        ]

        for pattern, prefix, suffix in thinking_patterns:
            matches = re.findall(pattern, response, re.DOTALL | re.IGNORECASE)
            if matches:
                thinking = matches[0].strip()
                # Remove thinking section from response
                clean_response = re.sub(pattern, '', response, flags=re.DOTALL | re.IGNORECASE).strip()
                return thinking, clean_response

        return None, response

    def update_config(self, **kwargs):
        """Update reasoning configuration"""
        for key, value in kwargs.items():
            if hasattr(self.config, key):
                setattr(self.config, key, value)
                logger.info(f"Updated reasoning config: {key} = {value}")
