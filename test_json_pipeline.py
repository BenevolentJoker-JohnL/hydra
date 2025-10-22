#!/usr/bin/env python3
"""
Test JSON pipeline with various inputs
"""

import asyncio
import json
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from core.logging_config import configure_logging
from core.json_pipeline import (
    JSONPipeline, JSONExtractor, SchemaGenerator,
    CodeResponseSchema, ExplanationResponseSchema, AnalysisResponseSchema,
    extract_code_blocks
)
from models.ollama_manager import OllamaLoadBalancer
from core.orchestrator import ModelOrchestrator
from pydantic import BaseModel, Field
from typing import List, Dict, Optional

# Configure logging
configure_logging(verbose=True)

# Test responses to process
TEST_RESPONSES = [
    # Valid JSON
    '{"code": "def hello():\\n    print(\\"Hello\\")", "language": "python"}',
    
    # JSON in markdown
    '''```json
    {
        "explanation": "This is a test",
        "key_points": ["point1", "point2"],
        "confidence": 0.95
    }
    ```''',
    
    # Mixed content with code
    '''Here's the solution:
    
    ```python
    def factorial(n):
        if n <= 1:
            return 1
        return n * factorial(n - 1)
    ```
    
    This function calculates factorial recursively.''',
    
    # Key-value pairs
    '''Response type: code
    Language: python
    Confidence: 0.8
    Code: print("test")''',
    
    # Invalid JSON that needs correction
    '{code: "test", language: python, confidence: high}',
    
    # Plain text
    'This is just plain text response without any structure.',
]

class CustomTestSchema(BaseModel):
    """Custom schema for testing"""
    test_name: str
    test_result: bool
    score: float = Field(ge=0, le=100)
    details: Optional[str] = None
    errors: List[str] = Field(default_factory=list)

async def test_json_extraction():
    """Test JSON extraction from various formats"""
    logger.info("=== Testing JSON Extraction ===")
    
    extractor = JSONExtractor()
    
    for i, response in enumerate(TEST_RESPONSES):
        logger.info(f"\nTest {i+1}: Processing response of {len(response)} chars")
        
        extracted = extractor.extract_json(response)
        
        if extracted:
            logger.success(f"✅ Extracted JSON with {len(extracted)} keys")
            logger.debug(f"Keys: {list(extracted.keys())}")
        else:
            logger.warning(f"❌ Failed to extract JSON")
        
        # Also test code block extraction
        code_blocks = extract_code_blocks(response)
        if code_blocks:
            logger.info(f"📝 Found {len(code_blocks)} code blocks")

async def test_schema_generation():
    """Test dynamic schema generation"""
    logger.info("\n=== Testing Schema Generation ===")
    
    generator = SchemaGenerator()
    
    test_cases = [
        ("Write a function to calculate fibonacci", {}),
        ("Explain how recursion works", {}),
        ("Analyze this code for performance", {}),
        ("Call the search tool with query 'test'", {"tool": "search"}),
        ("Generate data", {"expected_fields": {"name": "str", "age": "int", "active": "bool"}}),
    ]
    
    for prompt, context in test_cases:
        schema = generator.generate_schema(prompt, context)
        logger.info(f"Prompt: '{prompt[:50]}...' → Schema: {schema.__name__}")

async def test_json_pipeline_basic():
    """Test basic JSON pipeline functionality"""
    logger.info("\n=== Testing JSON Pipeline (No Model) ===")
    
    pipeline = JSONPipeline()
    
    # Test with code response
    code_response = '''```python
def add(a, b):
    return a + b
```
This function adds two numbers.'''
    
    result = await pipeline.process(
        response=code_response,
        prompt="Write an add function",
        context={},
        schema=CodeResponseSchema
    )
    
    logger.info(f"Pipeline result keys: {list(result.keys())}")
    if 'code' in result:
        logger.success(f"✅ Code extracted: {len(result['code'])} chars")
    
    # Test with custom schema
    test_response = '{"test_name": "unit_test", "test_result": true, "score": 95.5}'
    
    result = await pipeline.process(
        response=test_response,
        prompt="Run test",
        context={},
        schema=CustomTestSchema
    )
    
    logger.info(f"Custom schema result: {result}")

async def test_json_pipeline_with_correction():
    """Test JSON pipeline with model correction"""
    logger.info("\n=== Testing JSON Pipeline with Model Correction ===")
    
    # Initialize with load balancer
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    pipeline = JSONPipeline(lb)
    
    # Test with invalid JSON that needs correction
    invalid_response = '''
    The code is:
    function: factorial
    parameters: n
    returns: number
    implementation: recursive
    '''
    
    try:
        result = await pipeline.process(
            response=invalid_response,
            prompt="Write a factorial function",
            context={},
            schema=CodeResponseSchema
        )
        
        logger.info(f"Corrected result: {json.dumps(result, indent=2)[:200]}...")
        
        if 'response_type' in result:
            logger.success(f"✅ Successfully standardized to JSON with type: {result['response_type']}")
            
    except Exception as e:
        logger.error(f"Pipeline with correction failed: {e}")

async def test_orchestrator_json():
    """Test orchestrator with JSON output"""
    logger.info("\n=== Testing Orchestrator JSON Output ===")
    
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    orchestrator = ModelOrchestrator(lb)
    
    test_prompts = [
        "Write a simple hello world function",
        "Explain what recursion is",
        "Analyze the time complexity of bubble sort"
    ]
    
    for prompt in test_prompts:
        try:
            logger.info(f"\nProcessing: '{prompt}'")
            
            result = await orchestrator.orchestrate_json(
                prompt=prompt,
                context={}
            )
            
            # Check result structure
            logger.info(f"Result keys: {list(result.keys())}")
            
            if 'orchestration' in result:
                logger.info(f"Task ID: {result['orchestration']['task_id']}")
                logger.info(f"Complexity: {result['orchestration']['complexity']}")
            
            if 'response_type' in result:
                logger.success(f"✅ Response type: {result['response_type']}")
                
        except Exception as e:
            logger.error(f"Orchestrator JSON failed for '{prompt}': {e}")

async def test_streaming_json():
    """Test JSON pipeline with streaming"""
    logger.info("\n=== Testing Streaming JSON Pipeline ===")
    
    from core.json_pipeline import StreamingJSONPipeline
    
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    pipeline = StreamingJSONPipeline(lb)
    
    # Create a mock stream
    async def mock_stream():
        chunks = [
            {'chunk': '```python\n'},
            {'chunk': 'def test():\n'},
            {'chunk': '    return "Hello"\n'},
            {'chunk': '```\n'},
            {'chunk': 'This is a test function.', 'done': True}
        ]
        for chunk in chunks:
            yield chunk
            await asyncio.sleep(0.1)
    
    try:
        async for update in pipeline.process_stream(
            mock_stream(),
            prompt="Write a test function",
            schema=CodeResponseSchema
        ):
            if update['status'] == 'collecting':
                logger.debug(f"Collecting... {update['chars_collected']} chars")
            elif update['status'] == 'complete':
                logger.success(f"✅ Stream processing complete")
                logger.info(f"Final result type: {update['result'].get('response_type')}")
                
    except Exception as e:
        logger.error(f"Streaming JSON pipeline failed: {e}")

async def main():
    """Run all tests"""
    logger.info("🚀 Starting JSON Pipeline Tests\n")
    
    # Run tests
    await test_json_extraction()
    await test_schema_generation()
    await test_json_pipeline_basic()
    
    # Tests requiring models
    try:
        await test_json_pipeline_with_correction()
        await test_orchestrator_json()
        await test_streaming_json()
    except Exception as e:
        logger.warning(f"Model-dependent tests skipped: {e}")
    
    logger.success("\n✅ JSON Pipeline tests complete!")

if __name__ == "__main__":
    asyncio.run(main())