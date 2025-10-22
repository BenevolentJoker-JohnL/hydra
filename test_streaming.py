#!/usr/bin/env python3
"""
Test streaming responses
"""

import asyncio
import os
import sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from loguru import logger
from core.logging_config import configure_logging
from models.ollama_manager import OllamaLoadBalancer
from core.orchestrator import ModelOrchestrator

# Configure logging
configure_logging(verbose=True)

async def test_streaming():
    logger.info("🚀 Testing streaming responses")
    
    # Initialize components
    hosts = [os.getenv('OLLAMA_HOST', 'http://localhost:11434')]
    lb = OllamaLoadBalancer(hosts)
    orchestrator = ModelOrchestrator(lb)
    
    prompt = "Write a simple Python function that calculates factorial"
    
    # Test 1: Basic streaming from load balancer
    logger.info("=== Test 1: Basic Streaming ===")
    try:
        full_response = ""
        chunk_count = 0
        
        async for chunk in lb.generate_stream(
            model="tinyllama",
            prompt=prompt,
            temperature=0.7
        ):
            if 'response' in chunk:
                full_response += chunk['response']
                chunk_count += 1
                
                # Print first few chunks to show streaming
                if chunk_count <= 5:
                    logger.debug(f"Chunk {chunk_count}: {chunk['response'][:50]}...")
                
                if chunk.get('done', False):
                    logger.success(f"✅ Streaming completed: {chunk_count} chunks, {len(full_response)} chars")
                    
    except Exception as e:
        logger.error(f"❌ Streaming failed: {e}")
    
    # Test 2: Orchestrator streaming
    logger.info("\n=== Test 2: Orchestrator Streaming ===")
    try:
        full_response = ""
        chunk_count = 0
        
        async for chunk_data in orchestrator.orchestrate_stream(prompt):
            if 'chunk' in chunk_data:
                full_response += chunk_data['chunk']
                chunk_count += 1
                
                # Show streaming progress
                if chunk_count % 10 == 0:
                    logger.info(f"📝 Received {chunk_count} chunks, {len(full_response)} chars so far...")
                
                if chunk_data.get('done', False):
                    logger.success(f"✅ Orchestrator streaming completed")
                    logger.info(f"   Task ID: {chunk_data.get('task_id')}")
                    logger.info(f"   Complexity: {chunk_data.get('complexity')}")
                    logger.info(f"   Total chunks: {chunk_count}")
                    logger.info(f"   Response length: {len(full_response)} chars")
                    
    except Exception as e:
        logger.error(f"❌ Orchestrator streaming failed: {e}")
    
    # Test 3: Compare streaming vs non-streaming performance
    logger.info("\n=== Test 3: Performance Comparison ===")
    
    # Non-streaming
    import time
    start = time.time()
    try:
        result = await orchestrator.orchestrate(prompt)
        non_stream_time = time.time() - start
        logger.info(f"⏱️  Non-streaming took: {non_stream_time:.2f}s")
    except Exception as e:
        logger.error(f"Non-streaming failed: {e}")
    
    # Streaming (time to first token)
    start = time.time()
    first_token_time = None
    try:
        async for chunk_data in orchestrator.orchestrate_stream(prompt):
            if first_token_time is None and 'chunk' in chunk_data:
                first_token_time = time.time() - start
                logger.info(f"⚡ Time to first token (streaming): {first_token_time:.2f}s")
            
            if chunk_data.get('done', False):
                total_stream_time = time.time() - start
                logger.info(f"⏱️  Total streaming time: {total_stream_time:.2f}s")
                break
                
    except Exception as e:
        logger.error(f"Streaming performance test failed: {e}")
    
    logger.success("\n✅ Streaming tests complete!")

if __name__ == "__main__":
    asyncio.run(test_streaming())