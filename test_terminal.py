#!/usr/bin/env python3
"""
Test script to verify terminal logging integration
"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from models.ollama_manager import OllamaLoadBalancer, ModelPool
from core.orchestrator import ModelOrchestrator
from core.code_synthesis import CodeSynthesizer
from core.memory import HierarchicalMemory
from core.tools import ToolRegistry, ToolCaller
from db.connections import db_manager

async def test_terminal_logging():
    print("Testing terminal logging integration...")
    
    # Initialize components
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    
    # Initialize mock terminal in session state
    class MockTerminal:
        def __init__(self):
            self.logs = []
            
        def log(self, message, level="INFO", source="System"):
            entry = f"[{level}] [{source}] {message}"
            self.logs.append(entry)
            print(entry)
    
    # Create mock streamlit session state
    class MockSessionState:
        def __init__(self):
            self.terminal = MockTerminal()
    
    import streamlit as st
    st.session_state = MockSessionState()
    
    # Test 1: Model call logging
    print("\n=== Test 1: Model Call Logging ===")
    try:
        response = await lb.generate(
            model="tinyllama",
            prompt="Write a hello world function",
            temperature=0.7
        )
        print(f"Model response received: {len(response.get('response', ''))} chars")
    except Exception as e:
        print(f"Model call failed (expected if no model): {e}")
    
    # Test 2: Memory operation logging
    print("\n=== Test 2: Memory Operation Logging ===")
    await db_manager.initialize()
    memory = HierarchicalMemory(db_manager)
    
    stored = await memory.store(
        key="test_key",
        content={"test": "data"},
        metadata={"type": "test"}
    )
    print(f"Memory store result: {stored}")
    
    # Test 3: Tool call logging
    print("\n=== Test 3: Tool Call Logging ===")
    registry = ToolRegistry()
    caller = ToolCaller(registry)
    
    tool_calls = [
        {"tool": "read_file", "arguments": {"path": "test.txt"}}
    ]
    
    results = await caller.execute_tool_calls(tool_calls)
    print(f"Tool execution results: {results}")
    
    # Test 4: Orchestration logging
    print("\n=== Test 4: Orchestration Logging ===")
    orchestrator = ModelOrchestrator(lb)
    
    try:
        result = await orchestrator.orchestrate(
            prompt="Write a simple function",
            context={"language": "python"}
        )
        print(f"Orchestration result: task_id={result.get('task_id')}")
    except Exception as e:
        print(f"Orchestration failed (expected if no model): {e}")
    
    # Test 5: Code synthesis logging
    print("\n=== Test 5: Code Synthesis Logging ===")
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
    print(f"Synthesis confidence: {synthesis_result.get('confidence')}")
    
    # Print all terminal logs
    print("\n=== Terminal Log Summary ===")
    terminal = st.session_state.terminal
    print(f"Total logs collected: {len(terminal.logs)}")
    for log in terminal.logs[-10:]:
        print(log)
    
    print("\n✅ Terminal logging integration test complete!")
    
    # Cleanup
    await db_manager.close()

if __name__ == "__main__":
    asyncio.run(test_terminal_logging())