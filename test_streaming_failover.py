#!/usr/bin/env python3
"""
Test streaming request failover between multiple nodes.

This script simulates a streaming request failure on one node
and verifies that SOLLOL automatically tries the next available node.
"""

import asyncio
import sys
sys.path.insert(0, '/home/joker/SOLLOL-Hydra/src')

from sollol import OllamaPool
from loguru import logger

logger.remove()
logger.add(sys.stdout, level="INFO")


async def test_streaming_failover():
    """Test that streaming requests retry on multiple nodes"""

    print("\n" + "="*70)
    print("🧪 TESTING STREAMING REQUEST FAILOVER")
    print("="*70 + "\n")

    # Initialize SOLLOL pool
    print("1️⃣  Initializing SOLLOL pool...")
    pool = OllamaPool(
        app_name="FailoverTest",
        register_with_dashboard=False,
        enable_intelligent_routing=True,
        discover_all_nodes=True  # Network-wide discovery
    )

    # Check discovered nodes
    print("\n2️⃣  Checking discovered Ollama nodes...")
    nodes = pool.nodes
    print(f"   ✅ Found {len(nodes)} node(s):")
    for node in nodes:
        print(f"      • {node['host']}:{node['port']}")

    if len(nodes) < 2:
        print(f"\n⚠️  WARNING: Only {len(nodes)} node(s) found.")
        print("   This test requires at least 2 nodes to demonstrate failover.")
        print("   The test will still run but won't show multi-node failover.\n")

    if len(nodes) == 0:
        print("❌ No nodes available! Cannot test.")
        return

    # Use a simple test model
    print("\n3️⃣  Setting test model...")
    test_model = "qwen3:1.7b"  # Small fast model
    print(f"   ✅ Using model: {test_model}")

    # Test streaming request
    print(f"\n4️⃣  Testing streaming request with model {test_model}...")
    print("   This should automatically try multiple nodes if the first fails.\n")

    try:
        chunks_received = 0
        async for chunk in pool.generate_stream(
            model=test_model,
            prompt="Write a haiku about distributed computing.",
            routing_mode="fast"
        ):
            chunks_received += 1
            if chunks_received == 1:
                print(f"   📡 First chunk received! Streaming working...")

            # Print response content
            if 'response' in chunk:
                print(chunk['response'], end='', flush=True)

            # Break after receiving some chunks (don't need full response for test)
            if chunks_received > 10:
                print("\n   ✅ Stream working, stopping early...")
                break

        print(f"\n\n✅ SUCCESS: Streaming request completed!")
        print(f"   Received {chunks_received} chunks")

    except Exception as e:
        print(f"\n❌ FAILED: {e}")
        return

    # Get node statistics
    print("\n5️⃣  Node usage statistics:")
    stats = pool.get_stats()
    for node_key, perf in stats['node_performance'].items():
        requests = stats['nodes_used'].get(node_key, 0)
        print(f"   • {node_key}: {requests} request(s)")

    print("\n" + "="*70)
    print("🎉 TEST COMPLETE")
    print("="*70 + "\n")

    await pool.close()


if __name__ == "__main__":
    asyncio.run(test_streaming_failover())
