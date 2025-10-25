import asyncio
import json
import os
from typing import Dict, List, Any, Optional
from enum import Enum
from dataclasses import dataclass
from loguru import logger
import yaml
from .json_pipeline import JSONPipeline, CodeResponseSchema, AnalysisResponseSchema
from .config_loader import load_model_config
from .reasoning_engine import ReasoningEngine, ReasoningMode, ThinkingStyle, ReasoningConfig

class TaskComplexity(Enum):
    SIMPLE = "simple"
    MODERATE = "moderate"
    COMPLEX = "complex"

@dataclass
class OrchestrationTask:
    id: str
    prompt: str
    complexity: TaskComplexity
    context: Dict[str, Any]
    dependencies: List[str] = None
    results: Optional[Dict] = None
    
class ModelOrchestrator:
    def __init__(self, load_balancer, config_path: str = "config/models.yaml"):
        self.lb = load_balancer
        # Load config with environment variable overrides
        self.config = load_model_config(config_path)
        self.light_model = self.config['orchestrators']['light']['model']
        self.heavy_model = self.config['orchestrators']['heavy']['model']
        self.json_pipeline = JSONPipeline(load_balancer)

        # Initialize reasoning engine with config from environment
        reasoning_config = self._load_reasoning_config()
        self.reasoning_engine = ReasoningEngine(load_balancer, reasoning_config)

        logger.info(f"🤖 ModelOrchestrator initialized: light={self.light_model}, heavy={self.heavy_model}")
        logger.info(f"🧠 Reasoning mode: {reasoning_config.mode.value}, style: {reasoning_config.thinking_style.value}")

    def _load_reasoning_config(self) -> ReasoningConfig:
        """Load reasoning configuration from environment variables"""
        mode_str = os.getenv('HYDRA_REASONING_MODE', 'auto').lower()
        style_str = os.getenv('HYDRA_THINKING_STYLE', 'cot').lower()

        # Map strings to enums
        mode_map = {
            'fast': ReasoningMode.FAST,
            'standard': ReasoningMode.STANDARD,
            'extended': ReasoningMode.EXTENDED,
            'deep': ReasoningMode.DEEP_THINKING,
            'auto': ReasoningMode.AUTO
        }
        style_map = {
            'cot': ThinkingStyle.CHAIN_OF_THOUGHT,
            'tot': ThinkingStyle.TREE_OF_THOUGHT,
            'critique': ThinkingStyle.SELF_CRITIQUE,
            'refine': ThinkingStyle.ITERATIVE_REFINEMENT
        }

        return ReasoningConfig(
            mode=mode_map.get(mode_str, ReasoningMode.AUTO),
            thinking_style=style_map.get(style_str, ThinkingStyle.CHAIN_OF_THOUGHT),
            max_thinking_tokens=int(os.getenv('HYDRA_MAX_THINKING_TOKENS', '8000')),
            max_critique_iterations=int(os.getenv('HYDRA_MAX_CRITIQUE_ITERATIONS', '2')),
            use_reasoning_model=os.getenv('HYDRA_USE_REASONING_MODEL', 'true').lower() == 'true',
            show_thinking=os.getenv('HYDRA_SHOW_THINKING', 'true').lower() == 'true',
            # Deep thinking parameters
            deep_thinking_tokens=int(os.getenv('HYDRA_DEEP_THINKING_TOKENS', '32000')),
            deep_thinking_iterations=int(os.getenv('HYDRA_DEEP_THINKING_ITERATIONS', '3')),
            deep_thinking_threshold=float(os.getenv('HYDRA_DEEP_THINKING_THRESHOLD', '8.0'))
        )
        
    async def analyze_task(self, prompt: str, context: Dict = None) -> TaskComplexity:
        analysis_prompt = f"""Analyze this task complexity. Respond with only: SIMPLE, MODERATE, or COMPLEX

Task: {prompt}
Context: {json.dumps(context) if context else 'None'}

Criteria:
- SIMPLE: Single step, straightforward, no dependencies
- MODERATE: 2-3 steps, some context needed, minimal dependencies  
- COMPLEX: Multiple steps, heavy context, multiple dependencies"""

        response = await self.lb.generate(
            model=self.light_model,
            prompt=analysis_prompt,
            temperature=0.3
        )
        
        complexity_str = response['response'].strip().upper()
        return TaskComplexity.__members__.get(complexity_str, TaskComplexity.MODERATE)
        
    async def decompose_task(self, task: OrchestrationTask) -> List[Dict]:
        orchestrator = self.heavy_model if task.complexity == TaskComplexity.COMPLEX else self.light_model
        
        decompose_prompt = f"""Decompose this task into subtasks. Return JSON array of subtasks.

Task: {task.prompt}
Complexity: {task.complexity.value}
Context: {json.dumps(task.context)}

Return format:
[
  {{"subtask": "description", "model_type": "code|reasoning|general", "dependencies": []}}
]"""

        response = await self.lb.generate(
            model=orchestrator,
            prompt=decompose_prompt,
            temperature=0.5
        )
        
        try:
            subtasks = json.loads(response['response'])
            return subtasks
        except:
            logger.warning("Failed to parse subtasks, using single task")
            return [{
                "subtask": task.prompt,
                "model_type": "general",
                "dependencies": []
            }]
            
    async def route_to_models(self, subtask: Dict) -> List[str]:
        model_type = subtask.get('model_type', 'general')
        
        if model_type == 'code':
            models = self.config['code_synthesis']['primary']
            return models[:5]
        elif model_type == 'reasoning':
            return [self.config['code_synthesis']['specialized']['reasoning']]
        elif model_type == 'math':
            return [self.config['code_synthesis']['specialized']['math']]
        else:
            return self.config['general'][:3]
            
    async def orchestrate_stream(self, prompt: str, context: Dict = None):
        """Stream orchestrated response"""
        task = OrchestrationTask(
            id=f"task_{asyncio.get_event_loop().time()}",
            prompt=prompt,
            complexity=await self.analyze_task(prompt, context),
            context=context or {}
        )
        
        # Log to console
        logger.info(f"🧠 Streaming task complexity: {task.complexity.value}")
        
        if task.complexity == TaskComplexity.SIMPLE:
            # For simple tasks, stream directly from one model
            models = await self.route_to_models({"model_type": "general"})
            
            async for chunk in self.lb.generate_stream(
                model=models[0],
                prompt=prompt
            ):
                if 'response' in chunk:
                    yield {
                        'task_id': task.id,
                        'complexity': task.complexity.value,
                        'chunk': chunk['response'],
                        'done': chunk.get('done', False)
                    }
        else:
            # For complex tasks, we need to decompose and synthesize
            # This is harder to stream, so we'll stream the synthesis phase
            subtasks = await self.decompose_task(task)
            logger.info(f"📝 Streaming synthesis of {len(subtasks)} subtasks")
            
            results = []
            for subtask in subtasks:
                models = await self.route_to_models(subtask)
                subtask_results = []
                
                for model in models:
                    try:
                        response = await self.lb.generate(
                            model=model,
                            prompt=subtask['subtask']
                        )
                        subtask_results.append({
                            "model": model,
                            "response": response['response']
                        })
                    except Exception as e:
                        logger.error(f"Model {model} failed on subtask: {e}")
                        
                results.append({
                    "subtask": subtask['subtask'],
                    "results": subtask_results
                })
            
            # Stream the synthesis
            synthesis_prompt = f"""Synthesize these results into a coherent response for the original task.

Original task: {task.prompt}

Results from subtasks:
{json.dumps(results, indent=2)}

Provide a unified, high-quality response that combines the best aspects of all results."""

            orchestrator = self.heavy_model if task.complexity == TaskComplexity.COMPLEX else self.light_model
            
            async for chunk in self.lb.generate_stream(
                model=orchestrator,
                prompt=synthesis_prompt,
                temperature=0.4
            ):
                if 'response' in chunk:
                    yield {
                        'task_id': task.id,
                        'complexity': task.complexity.value,
                        'chunk': chunk['response'],
                        'subtasks': len(results),
                        'done': chunk.get('done', False)
                    }
    
    async def orchestrate(self, prompt: str, context: Dict = None) -> Dict:
        task = OrchestrationTask(
            id=f"task_{asyncio.get_event_loop().time()}",
            prompt=prompt,
            complexity=await self.analyze_task(prompt, context),
            context=context or {}
        )
        
        # Log to console with emoji
        logger.info(f"🧠 Task complexity: {task.complexity.value}")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_orchestration("analyze_task", f"complexity: {task.complexity.value}")
        except:
            pass
        
        if task.complexity == TaskComplexity.SIMPLE:
            models = await self.route_to_models({"model_type": "general"})
            response = await self.lb.generate(
                model=models[0],
                prompt=prompt
            )
            return {
                "task_id": task.id,
                "complexity": task.complexity.value,
                "response": response['response']
            }
            
        subtasks = await self.decompose_task(task)
        
        # Log to console
        logger.info(f"📝 Decomposed into {len(subtasks)} subtasks")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_orchestration("decompose_task", f"{len(subtasks)} subtasks")
        except:
            pass
        
        results = []
        
        for subtask in subtasks:
            models = await self.route_to_models(subtask)
            subtask_results = []
            
            for model in models:
                try:
                    response = await self.lb.generate(
                        model=model,
                        prompt=subtask['subtask']
                    )
                    subtask_results.append({
                        "model": model,
                        "response": response['response']
                    })
                except Exception as e:
                    logger.error(f"Model {model} failed on subtask: {e}")
                    
            results.append({
                "subtask": subtask['subtask'],
                "results": subtask_results
            })
            
        synthesized = await self.synthesize_results(results, task)
        
        # Log to console
        logger.success(f"✨ Synthesis complete for task {task.id}")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_orchestration("synthesis_complete", f"task {task.id}")
        except:
            pass
        
        return {
            "task_id": task.id,
            "complexity": task.complexity.value,
            "subtasks": results,
            "synthesized": synthesized
        }
        
    async def synthesize_results(self, results: List[Dict], task: OrchestrationTask) -> str:
        synthesis_prompt = f"""Synthesize these results into a coherent response for the original task.

Original task: {task.prompt}

Results from subtasks:
{json.dumps(results, indent=2)}

Provide a unified, high-quality response that combines the best aspects of all results."""

        orchestrator = self.heavy_model if task.complexity == TaskComplexity.COMPLEX else self.light_model
        
        response = await self.lb.generate(
            model=orchestrator,
            prompt=synthesis_prompt,
            temperature=0.4
        )
        
        return response['response']
    
    async def orchestrate_with_reasoning(
        self,
        prompt: str,
        context: Dict = None,
        mode: Optional[ReasoningMode] = None
    ) -> Dict:
        """
        Orchestrate task with Claude-style reasoning.

        Args:
            prompt: The task prompt
            context: Optional context dictionary
            mode: Override reasoning mode (FAST, STANDARD, EXTENDED, AUTO)

        Returns:
            Dict with 'response', 'thinking', 'mode_used', 'model_used', etc.
        """
        logger.info(f"🧠 Orchestrating with reasoning: {prompt[:60]}...")

        # Use reasoning engine
        result = await self.reasoning_engine.reason(
            task=prompt,
            context=context,
            mode=mode
        )

        return result

    async def orchestrate_reasoning_stream(
        self,
        prompt: str,
        context: Dict = None,
        mode: Optional[ReasoningMode] = None
    ):
        """
        Stream orchestrated response with reasoning/thinking process.

        Yields chunks with:
        - 'chunk': text content
        - 'type': 'thinking' | 'response' | 'metadata'
        - 'done': boolean
        """
        logger.info(f"🧠 Streaming with reasoning: {prompt[:60]}...")

        async for chunk in self.reasoning_engine.reason_stream(
            task=prompt,
            context=context,
            mode=mode
        ):
            yield chunk

    def set_reasoning_mode(self, mode: ReasoningMode):
        """Change reasoning mode at runtime"""
        self.reasoning_engine.config.mode = mode
        logger.info(f"🎯 Reasoning mode changed to: {mode.value}")

    def set_thinking_style(self, style: ThinkingStyle):
        """Change thinking style at runtime"""
        self.reasoning_engine.config.thinking_style = style
        logger.info(f"🎨 Thinking style changed to: {style.value}")

    def update_reasoning_config(self, **kwargs):
        """Update reasoning configuration parameters"""
        self.reasoning_engine.update_config(**kwargs)

    async def orchestrate_json(self, prompt: str, context: Dict = None) -> Dict:
        """Orchestrate task and return standardized JSON output"""
        task = OrchestrationTask(
            id=f"task_{asyncio.get_event_loop().time()}",
            prompt=prompt,
            complexity=await self.analyze_task(prompt, context),
            context=context or {}
        )

        logger.info(f"🧠 Orchestrating with JSON output - complexity: {task.complexity.value}")

        # Get response based on complexity
        if task.complexity == TaskComplexity.SIMPLE:
            models = await self.route_to_models({"model_type": "general"})
            response = await self.lb.generate(
                model=models[0],
                prompt=prompt
            )
            raw_response = response['response']
        else:
            # Complex task - decompose and synthesize
            subtasks = await self.decompose_task(task)
            results = []

            for subtask in subtasks:
                models = await self.route_to_models(subtask)
                subtask_results = []

                for model in models:
                    try:
                        response = await self.lb.generate(
                            model=model,
                            prompt=subtask['subtask']
                        )
                        subtask_results.append({
                            "model": model,
                            "response": response['response']
                        })
                    except Exception as e:
                        logger.error(f"Model {model} failed: {e}")

                results.append({
                    "subtask": subtask['subtask'],
                    "results": subtask_results
                })

            raw_response = await self.synthesize_results(results, task)

        # Process through JSON pipeline
        json_result = await self.json_pipeline.process(
            response=raw_response,
            prompt=prompt,
            context=context
        )

        # Add orchestration metadata
        json_result['orchestration'] = {
            'task_id': task.id,
            'complexity': task.complexity.value,
            'subtasks_count': len(task.dependencies) if task.dependencies else 0
        }

        return json_result