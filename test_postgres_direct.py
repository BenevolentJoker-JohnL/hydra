#!/usr/bin/env python3

import asyncio
import asyncpg
import os
from dotenv import load_dotenv

load_dotenv()

async def test_direct():
    """Test PostgreSQL connection with different authentication methods"""
    
    configs = [
        {
            "name": "Current .env settings",
            "host": os.getenv('POSTGRES_HOST', 'localhost'),
            "port": int(os.getenv('POSTGRES_PORT', 5432)),
            "user": os.getenv('POSTGRES_USER', 'hydra'),
            "password": os.getenv('POSTGRES_PASSWORD', 'hydra_password'),
            "database": os.getenv('POSTGRES_DB', 'hydra_db')
        },
        {
            "name": "Direct hydra user",
            "host": "localhost",
            "port": 5432,
            "user": "hydra",
            "password": "hydra_password",
            "database": "hydra_db"
        },
        {
            "name": "Using postgres database",
            "host": "localhost",
            "port": 5432,
            "user": "hydra",
            "password": "hydra_password",
            "database": "postgres"
        }
    ]
    
    for config in configs:
        print(f"\nTesting: {config['name']}")
        try:
            conn = await asyncpg.connect(
                host=config['host'],
                port=config['port'],
                user=config['user'],
                password=config['password'],
                database=config['database']
            )
            version = await conn.fetchval('SELECT version()')
            await conn.close()
            print(f"  ✅ Success! PostgreSQL version: {version[:50]}...")
        except Exception as e:
            print(f"  ❌ Failed: {e}")
    
    print("\n" + "="*60)
    print("If all connections fail, run:")
    print("  ./setup_postgres_fix.sh")
    print("\nThis will recreate the user and database with correct settings.")

if __name__ == "__main__":
    asyncio.run(test_direct())