#!/usr/bin/env python3

import asyncio
import redis
import asyncpg
import os
from dotenv import load_dotenv
from loguru import logger

load_dotenv()

async def test_connections():
    print("Testing database connections...")
    
    # Test Redis
    try:
        r = redis.Redis(
            host=os.getenv('REDIS_HOST', 'localhost'),
            port=int(os.getenv('REDIS_PORT', 6379)),
            db=int(os.getenv('REDIS_DB', 0))
        )
        r.ping()
        print("✓ Redis connection successful")
    except Exception as e:
        print(f"✗ Redis connection failed: {e}")
    
    # Test PostgreSQL
    try:
        conn = await asyncpg.connect(
            host=os.getenv('POSTGRES_HOST', 'localhost'),
            port=int(os.getenv('POSTGRES_PORT', 5432)),
            user=os.getenv('POSTGRES_USER', 'hydra'),
            password=os.getenv('POSTGRES_PASSWORD', 'hydra_password'),
            database=os.getenv('POSTGRES_DB', 'hydra_db')
        )
        await conn.close()
        print("✓ PostgreSQL connection successful")
    except Exception as e:
        print(f"✗ PostgreSQL connection failed: {e}")
        print("  Try running: sudo -u postgres psql -c \"CREATE USER hydra WITH PASSWORD 'hydra_password'; CREATE DATABASE hydra_db OWNER hydra;\"")
    
    print("\nIf PostgreSQL fails, you can:")
    print("1. Use your existing postgres user/password")
    print("2. Create the hydra user manually")
    print("3. Run without PostgreSQL (will use SQLite as fallback)")

if __name__ == "__main__":
    asyncio.run(test_connections())