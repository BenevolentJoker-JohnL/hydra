#!/usr/bin/env python3
"""
Test console logging output
"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from core.logging_config import configure_logging

# Configure verbose logging
configure_logging(verbose=True)

from models.ollama_manager import OllamaLoadBalancer, ModelPool
from core.orchestrator import ModelOrchestrator
from core.code_synthesis import CodeSynthesizer
from core.memory import HierarchicalMemory
from core.tools import ToolRegistry, ToolCaller
from db.connections import db_manager

async def test_console_logging():
    logger.info("🚀 Starting console logging test")
    
    # Initialize components
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    
    # Test 1: Model call logging
    logger.info("=== Test 1: Model Call Logging ===")
    try:
        # This will log to console even if it fails
        response = await lb.generate(
            model="tinyllama",
            prompt="Write a hello world function",
            temperature=0.7
        )
        logger.success(f"✅ Model response received: {len(response.get('response', ''))} chars")
    except Exception as e:
        logger.error(f"❌ Model call failed (expected if no model): {e}")
    
    # Test 2: Memory operation logging
    logger.info("=== Test 2: Memory Operation Logging ===")
    await db_manager.initialize()
    memory = HierarchicalMemory(db_manager)
    
    stored = await memory.store(
        key="test_key",
        content={"test": "data"},
        metadata={"type": "test"}
    )
    logger.info(f"📊 Memory store result: {stored}")
    
    # Test 3: Tool call logging
    logger.info("=== Test 3: Tool Call Logging ===")
    registry = ToolRegistry()
    caller = ToolCaller(registry)
    
    tool_calls = [
        {"tool": "read_file", "arguments": {"path": "test.txt"}}
    ]
    
    results = await caller.execute_tool_calls(tool_calls)
    logger.info(f"🔧 Tool execution results: {len(results)} tools executed")
    
    # Test 4: Orchestration logging
    logger.info("=== Test 4: Orchestration Logging ===")
    orchestrator = ModelOrchestrator(lb)
    
    try:
        result = await orchestrator.orchestrate(
            prompt="Write a simple function",
            context={"language": "python"}
        )
        logger.success(f"✨ Orchestration result: task_id={result.get('task_id')}")
    except Exception as e:
        logger.error(f"❌ Orchestration failed (expected if no model): {e}")
    
    # Test 5: Code synthesis logging
    logger.info("=== Test 5: Code Synthesis Logging ===")
    synthesizer = CodeSynthesizer()
    
    test_results = [
        {
            "responses": [
                {"model": "model1", "response": "def hello(): print('hi')"},
                {"model": "model2", "response": "def hello(): print('hello')"}
            ]
        }
    ]
    
    synthesis_result = await synthesizer.merge_responses(
        test_results,
        "Write a hello function"
    )
    logger.info(f"📊 Synthesis confidence: {synthesis_result.get('confidence')}")
    
    # Test different log levels
    logger.info("=== Testing Log Levels ===")
    logger.trace("This is a TRACE message")
    logger.debug("This is a DEBUG message")
    logger.info("This is an INFO message")
    logger.success("This is a SUCCESS message")
    logger.warning("This is a WARNING message")
    logger.error("This is an ERROR message")
    logger.critical("This is a CRITICAL message")
    
    logger.success("✅ Console logging test complete!")
    logger.info("Check logs/hydra_*.log for file output")
    
    # Cleanup
    await db_manager.close()

if __name__ == "__main__":
    asyncio.run(test_console_logging())