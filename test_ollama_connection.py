#!/usr/bin/env python3
"""Test Ollama connection and diagnose issues"""

import asyncio
import ollama
from loguru import logger

async def test_connection():
    """Test Ollama connection"""
    hosts = [
        'http://localhost:11434',
        'http://192.168.1.100:11434'
    ]
    
    for host in hosts:
        print(f"\n Testing {host}...")
        try:
            client = ollama.AsyncClient(host=host)
            models = await client.list()
            print(f"✅ Connected! Found {len(models.get('models', []))} models")
            
            # Test a simple generation
            print("Testing generation...")
            response = await client.generate(
                model='tinyllama',
                prompt='Say hello',
                stream=False
            )
            print(f"✅ Generation successful: {response.get('response', '')[:50]}")
            
        except Exception as e:
            print(f"❌ Failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_connection())