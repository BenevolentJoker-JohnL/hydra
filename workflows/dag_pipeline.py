from prefect import flow, task, get_run_logger
from prefect.task_runners import ConcurrentTaskRunner
from typing import List, Any, Optional
import asyncio
import json
from datetime import timedelta
from loguru import logger

# Use lowercase dict/list for Pydantic v2 compatibility
# typing.Dict causes issues with Prefect 2.20+ and Pydantic v2

@task(retries=3, retry_delay_seconds=10, cache_key_fn=lambda x: x.get('cache_key'))
async def analyze_code_request(request: dict) -> dict:
    flow_logger = get_run_logger()
    flow_logger.info(f"Analyzing request: {request.get('prompt', '')[:100]}...")
    
    # Log to console
    logger.info(f"🎯 Starting generation: {request.get('prompt', '')[:50]}...")
    
    # Also log to terminal if available
    try:
        import streamlit as st
        if hasattr(st.session_state, 'terminal'):
            from ..ui.terminal import GenerationLogger
            term_logger = GenerationLogger(st.session_state.terminal)
            term_logger.start_generation(request.get('prompt', ''), task_id=request.get('cache_key'))
    except:
        pass
    
    from ..core.orchestrator import ModelOrchestrator, TaskComplexity
    from ..models.ollama_manager import OllamaLoadBalancer
    import os
    
    hosts = [
        os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        f"http://{os.getenv('GPU_NODE_HOST', 'localhost')}:11434",
        f"http://{os.getenv('CPU_NODE_1_HOST', '192.168.1.100')}:11434",
        f"http://{os.getenv('CPU_NODE_2_HOST', '192.168.1.101')}:11434",
        f"http://{os.getenv('CPU_NODE_3_HOST', '192.168.1.102')}:11434"
    ]
    
    lb = OllamaLoadBalancer([h for h in hosts if h])
    orchestrator = ModelOrchestrator(lb)
    
    complexity = await orchestrator.analyze_task(
        request['prompt'],
        request.get('context', {})
    )
    
    return {
        **request,
        'complexity': complexity.value,
        'task_id': f"task_{asyncio.get_event_loop().time()}"
    }

@task(retries=2)
async def decompose_into_subtasks(analyzed_request: dict) -> list[dict]:
    logger = get_run_logger()
    logger.info(f"Decomposing task {analyzed_request['task_id']}")
    
    from ..core.orchestrator import ModelOrchestrator, OrchestrationTask, TaskComplexity
    from ..models.ollama_manager import OllamaLoadBalancer
    import os
    
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    orchestrator = ModelOrchestrator(lb)
    
    task = OrchestrationTask(
        id=analyzed_request['task_id'],
        prompt=analyzed_request['prompt'],
        complexity=TaskComplexity[analyzed_request['complexity'].upper()],
        context=analyzed_request.get('context', {})
    )
    
    subtasks = await orchestrator.decompose_task(task)
    
    for i, subtask in enumerate(subtasks):
        subtask['id'] = f"{task.id}_sub_{i}"
        subtask['parent_task'] = task.id
        
    return subtasks

@task(retries=3)
async def execute_subtask(subtask: dict, model_pool: list[str]) -> dict:
    logger = get_run_logger()
    logger.info(f"Executing subtask {subtask['id']} with {len(model_pool)} models")
    
    from ..models.ollama_manager import OllamaLoadBalancer, ModelPool
    import os
    
    hosts = [
        os.getenv('OLLAMA_HOST', 'http://localhost:11434'),
        f"http://{os.getenv('GPU_NODE_HOST', 'localhost')}:11434",
        f"http://{os.getenv('CPU_NODE_1_HOST', '192.168.1.100')}:11434"
    ]
    
    lb = OllamaLoadBalancer([h for h in hosts if h])
    pool = ModelPool(lb, {'temperature': 0.7, 'top_p': 0.95})
    
    responses = await pool.get_diverse_responses(
        subtask['subtask'],
        model_pool,
        max_concurrent=3
    )
    
    return {
        'subtask_id': subtask['id'],
        'prompt': subtask['subtask'],
        'responses': responses
    }

@task(retries=2)
async def synthesize_code(subtask_results: list[dict], original_request: dict) -> dict:
    flow_logger = get_run_logger()
    flow_logger.info(f"Synthesizing {len(subtask_results)} subtask results")
    
    # Collect models for logging
    models = []
    for result in subtask_results:
        for resp in result.get('responses', []):
            if resp.get('model') not in models:
                models.append(resp.get('model'))
    
    # Log to console
    if models:
        logger.info(f"🔀 Synthesizing from {len(models)} models: {', '.join(models)}")
    
    # Also log to terminal if available
    try:
        import streamlit as st
        if hasattr(st.session_state, 'terminal'):
            from ..ui.terminal import GenerationLogger
            term_logger = GenerationLogger(st.session_state.terminal)
            term_logger.log_synthesis(models)
    except:
        pass
    
    from ..core.code_synthesis import CodeSynthesizer
    
    synthesizer = CodeSynthesizer()
    synthesized = await synthesizer.merge_responses(
        subtask_results,
        original_request['prompt']
    )
    
    return {
        'task_id': original_request['task_id'],
        'original_prompt': original_request['prompt'],
        'synthesized_code': synthesized['code'],
        'confidence': synthesized['confidence'],
        'explanations': synthesized.get('explanations', [])
    }

@task
async def store_in_memory(result: dict) -> bool:
    logger = get_run_logger()
    logger.info(f"Storing result for task {result['task_id']}")
    
    from ..core.memory import HierarchicalMemory
    from ..db.connections import db_manager
    
    await db_manager.initialize()
    memory = HierarchicalMemory(db_manager)
    
    stored = await memory.store(
        key=result['task_id'],
        content=result,
        metadata={
            'prompt': result['original_prompt'],
            'confidence': result['confidence'],
            'timestamp': asyncio.get_event_loop().time()
        },
        ttl=3600
    )
    
    return stored

@flow(task_runner=ConcurrentTaskRunner())
async def code_generation_pipeline(request: dict) -> dict:
    logger = get_run_logger()
    logger.info("Starting code generation pipeline")
    
    analyzed = await analyze_code_request(request)
    
    if analyzed['complexity'] == 'simple':
        from ..models.ollama_manager import OllamaLoadBalancer
        import os
        
        hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
        lb = OllamaLoadBalancer(hosts)
        
        response = await lb.generate(
            model='qwen2.5-coder:14b',
            prompt=request['prompt']
        )
        
        result = {
            'task_id': analyzed['task_id'],
            'original_prompt': request['prompt'],
            'synthesized_code': response['response'],
            'confidence': 0.85,
            'explanations': []
        }
    else:
        subtasks = await decompose_into_subtasks(analyzed)
        
        subtask_futures = []
        for subtask in subtasks:
            model_type = subtask.get('model_type', 'code')
            if model_type == 'code':
                models = ['qwen2.5-coder:14b', 'devstral:latest', 'codestral:latest']
            else:
                models = ['llama3.1:latest', 'tulu3:latest']
                
            future = execute_subtask.submit(subtask, models)
            subtask_futures.append(future)
            
        subtask_results = await asyncio.gather(*[f.result() for f in subtask_futures])
        
        result = await synthesize_code(subtask_results, analyzed)
        
    await store_in_memory(result)
    
    flow_logger.info(f"Pipeline completed for task {result['task_id']}")
    
    # Log to console
    logger.success(f"🎉 Pipeline completed for task {result['task_id']}")
    
    # Also log to terminal if available
    try:
        import streamlit as st
        if hasattr(st.session_state, 'terminal'):
            from ..ui.terminal import GenerationLogger
            term_logger = GenerationLogger(st.session_state.terminal)
            term_logger.log_success(f"Pipeline completed for task {result['task_id']}")
    except:
        pass
    
    return result

@flow
async def batch_code_generation(requests: list[dict]) -> list[dict]:
    logger = get_run_logger()
    logger.info(f"Processing batch of {len(requests)} requests")
    
    futures = []
    for request in requests:
        future = code_generation_pipeline.submit(request)
        futures.append(future)
        
    results = await asyncio.gather(*[f.result() for f in futures])
    return results