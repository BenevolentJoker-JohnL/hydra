#!/usr/bin/env python3
"""Fix Ollama connectivity issues"""

import asyncio
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from models.ollama_manager import OllamaLoadBalancer
from loguru import logger

async def test_and_fix():
    """Test and fix Ollama connectivity"""
    
    hosts = [
        'http://localhost:11434',
        # 'http://192.168.1.100:11434'  # Comment out if not available
    ]
    
    lb = OllamaLoadBalancer(hosts)
    
    # Force all hosts to be healthy initially
    print("Resetting health status...")
    for host in hosts:
        lb.health_status[host] = True
        print(f"  {host}: Marked as healthy")
    
    # Test connectivity
    print("\nTesting connectivity...")
    for host in hosts:
        is_healthy = await lb.check_health(host)
        print(f"  {host}: {'✅ Healthy' if is_healthy else '❌ Unhealthy'}")
        lb.health_status[host] = is_healthy
    
    # Get best host
    best = lb.get_best_host()
    print(f"\nBest host: {best if best else 'None available!'}")
    
    if best:
        # Try a simple generation
        print("\nTesting generation...")
        try:
            client = lb.client_pool[best]
            response = await client.generate(
                model='tinyllama',
                prompt='Say hello',
                stream=False
            )
            print(f"✅ Generation successful!")
            print(f"Response: {response.get('response', '')[:100]}")
        except Exception as e:
            print(f"❌ Generation failed: {e}")
    
    return lb

if __name__ == "__main__":
    lb = asyncio.run(test_and_fix())
    print("\nDone! Health status:", dict(lb.health_status))