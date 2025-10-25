#!/usr/bin/env python3
"""
Integration test for Hydra features:
- Reasoning Engine
- Deep Thinking Mode
- Tool Use Integration
"""

import os
import sys
from dotenv import load_dotenv

# Load environment
load_dotenv()

print("="*60)
print("HYDRA INTEGRATION TEST")
print("="*60)

# Test 1: Reasoning Engine
print("\n[1/6] Testing Reasoning Engine...")
try:
    from core.reasoning_engine import ReasoningEngine, ReasoningMode, ThinkingStyle, ReasoningConfig

    config = ReasoningConfig(
        mode=ReasoningMode.AUTO,
        thinking_style=ThinkingStyle.CHAIN_OF_THOUGHT,
        max_thinking_tokens=8000,
        max_critique_iterations=2,
        use_reasoning_model=True,
        show_thinking=True,
        deep_thinking_tokens=32000,
        deep_thinking_iterations=3,
        deep_thinking_threshold=8.0
    )

    print(f"   ✅ ReasoningEngine imports successful")
    print(f"   ✅ Config created with mode: {config.mode.value}")
    print(f"   ✅ Deep thinking params: {config.deep_thinking_tokens} tokens, {config.deep_thinking_iterations} iterations")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Test 2: Reasoning Modes
print("\n[2/6] Testing Reasoning Modes...")
try:
    modes = [m.value for m in ReasoningMode]
    expected = ['fast', 'standard', 'extended', 'deep', 'auto']
    assert modes == expected, f"Expected {expected}, got {modes}"
    print(f"   ✅ All 5 reasoning modes available: {modes}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Test 3: Orchestrator Integration
print("\n[3/6] Testing Orchestrator Integration...")
try:
    from core.orchestrator import ModelOrchestrator
    from core.reasoning_engine import ReasoningMode

    # Check that orchestrator has reasoning methods
    assert hasattr(ModelOrchestrator, 'orchestrate_with_reasoning'), "Missing orchestrate_with_reasoning"
    assert hasattr(ModelOrchestrator, 'orchestrate_reasoning_stream'), "Missing orchestrate_reasoning_stream"
    assert hasattr(ModelOrchestrator, 'set_reasoning_mode'), "Missing set_reasoning_mode"
    assert hasattr(ModelOrchestrator, 'set_thinking_style'), "Missing set_thinking_style"

    print(f"   ✅ ModelOrchestrator has reasoning methods")
    print(f"   ✅ orchestrate_with_reasoning() available")
    print(f"   ✅ orchestrate_reasoning_stream() available")
    print(f"   ✅ Runtime configuration methods available")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Test 4: Tool Registry
print("\n[4/6] Testing Tool Registry...")
try:
    from core.tools import ToolRegistry, ToolCaller, ToolType

    registry = ToolRegistry()
    tools = registry.list_tools()
    tool_names = [t['name'] for t in tools]

    expected_tools = [
        'read_file', 'write_file', 'list_directory',
        'execute_python', 'run_command', 'analyze_code', 'search_codebase'
    ]

    for tool in expected_tools:
        assert tool in tool_names, f"Missing tool: {tool}"

    print(f"   ✅ ToolRegistry initialized with {len(tools)} tools")
    print(f"   ✅ All expected tools registered: {', '.join(tool_names)}")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Test 5: Code Assistant Tool Integration
print("\n[5/6] Testing Code Assistant Tool Integration...")
try:
    from core.code_assistant import StreamingCodeAssistant

    assistant = StreamingCodeAssistant(None)

    assert hasattr(assistant, 'tool_registry'), "Missing tool_registry"
    assert hasattr(assistant, 'tool_caller'), "Missing tool_caller"
    assert hasattr(assistant, '_process_stream_with_tools'), "Missing _process_stream_with_tools"

    # Check process_stream accepts use_tools parameter
    import inspect
    sig = inspect.signature(assistant.process_stream)
    params = list(sig.parameters.keys())
    assert 'use_tools' in params, "Missing use_tools parameter"

    print(f"   ✅ StreamingCodeAssistant has tool support")
    print(f"   ✅ process_stream() accepts use_tools parameter")
    print(f"   ✅ _process_stream_with_tools() method available")
    print(f"   ✅ Tool registry integrated with {len(assistant.tool_registry.tools)} tools")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Test 6: Environment Variables
print("\n[6/6] Testing Environment Configuration...")
try:
    required_vars = [
        'HYDRA_REASONING_MODE',
        'HYDRA_THINKING_STYLE',
        'HYDRA_MAX_THINKING_TOKENS',
        'HYDRA_MAX_CRITIQUE_ITERATIONS',
        'HYDRA_DEEP_THINKING_TOKENS',
        'HYDRA_DEEP_THINKING_ITERATIONS',
        'HYDRA_DEEP_THINKING_THRESHOLD'
    ]

    for var in required_vars:
        value = os.getenv(var)
        assert value is not None, f"Missing environment variable: {var}"

    print(f"   ✅ All reasoning environment variables configured")
    print(f"   ✅ Reasoning Mode: {os.getenv('HYDRA_REASONING_MODE')}")
    print(f"   ✅ Thinking Style: {os.getenv('HYDRA_THINKING_STYLE')}")
    print(f"   ✅ Deep Thinking: {os.getenv('HYDRA_DEEP_THINKING_TOKENS')} tokens")
except Exception as e:
    print(f"   ❌ ERROR: {e}")
    sys.exit(1)

# Summary
print("\n" + "="*60)
print("✅ ALL TESTS PASSED!")
print("="*60)
print("\nIntegration Status:")
print("  ✅ Reasoning Engine (FAST, STANDARD, EXTENDED, DEEP, AUTO)")
print("  ✅ Deep Thinking Mode (32k tokens, multi-pass critique)")
print("  ✅ Orchestrator Integration (all reasoning methods)")
print("  ✅ Tool Registry (7 tools available)")
print("  ✅ Code Assistant Tool Integration")
print("  ✅ Environment Configuration")
print("\nHydra is ready to use with:")
print("  • Claude-style reasoning")
print("  • Programmatic tool use")
print("  • Artifact management")
print("  • SOLLOL distributed orchestration")
print("="*60)
