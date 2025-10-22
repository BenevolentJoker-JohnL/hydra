import asyncio
import json
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from enum import Enum
import numpy as np
from loguru import logger

class MemoryTier(Enum):
    L1_CACHE = "l1_cache"      # Redis - Hot data, immediate access
    L2_CACHE = "l2_cache"      # SQLite - Recent data, fast access
    L3_STORAGE = "l3_storage"  # PostgreSQL - Persistent storage
    L4_ARCHIVE = "l4_archive"  # ChromaDB - Vector embeddings, semantic search

@dataclass
class MemoryItem:
    key: str
    content: Any
    metadata: Dict
    embedding: Optional[List[float]] = None
    access_count: int = 0
    last_accessed: datetime = None
    created_at: datetime = None
    tier: MemoryTier = MemoryTier.L1_CACHE
    ttl: Optional[int] = None
    
    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.now()
        if self.last_accessed is None:
            self.last_accessed = datetime.now()

class HierarchicalMemory:
    def __init__(self, db_manager, embedding_model: str = "mxbai-embed-large"):
        self.db = db_manager
        self.embedding_model = embedding_model
        self.tier_thresholds = {
            MemoryTier.L1_CACHE: timedelta(minutes=5),
            MemoryTier.L2_CACHE: timedelta(hours=1),
            MemoryTier.L3_STORAGE: timedelta(days=7),
            MemoryTier.L4_ARCHIVE: None
        }
        self.access_threshold = {
            MemoryTier.L1_CACHE: 10,
            MemoryTier.L2_CACHE: 5,
            MemoryTier.L3_STORAGE: 2,
            MemoryTier.L4_ARCHIVE: 0
        }
        
    async def store(self, key: str, content: Any, metadata: Dict = None, ttl: int = None) -> bool:
        metadata = metadata or {}
        memory_item = MemoryItem(
            key=key,
            content=content,
            metadata=metadata,
            ttl=ttl
        )
        
        hash_key = self._generate_key(key)
        
        # Log to console
        logger.debug(f"💾 Memory store: {key[:20]}... to L1_CACHE")
        
        # Also log to terminal if available
        try:
            import streamlit as st
            if hasattr(st.session_state, 'terminal'):
                from ..ui.terminal import GenerationLogger
                term_logger = GenerationLogger(st.session_state.terminal)
                term_logger.log_memory_operation("store", "L1_CACHE")
        except:
            pass
        
        try:
            await self._store_l1(hash_key, memory_item)
            
            if self._should_persist(memory_item):
                await self._store_l2(hash_key, memory_item)
                logger.debug(f"💾 Memory persist: {key[:20]}... to L2_CACHE")
                
                try:
                    if hasattr(st.session_state, 'terminal'):
                        term_logger.log_memory_operation("persist", "L2_CACHE")
                except:
                    pass
                
            return True
        except Exception as e:
            logger.error(f"Failed to store memory: {e}")
            return False
            
    async def retrieve(self, key: str) -> Optional[Any]:
        hash_key = self._generate_key(key)
        
        item = await self._retrieve_l1(hash_key)
        if item:
            await self._update_access_stats(hash_key, item)
            return item.content
            
        item = await self._retrieve_l2(hash_key)
        if item:
            await self._promote_to_l1(hash_key, item)
            await self._update_access_stats(hash_key, item)
            return item.content
            
        item = await self._retrieve_l3(hash_key)
        if item:
            if item.access_count > self.access_threshold[MemoryTier.L2_CACHE]:
                await self._promote_to_l2(hash_key, item)
            await self._update_access_stats(hash_key, item)
            return item.content
            
        return None
        
    async def semantic_search(self, query: str, top_k: int = 5) -> List[Tuple[str, float]]:
        try:
            from ..models.ollama_manager import OllamaLoadBalancer
            
            lb = OllamaLoadBalancer([os.getenv('OLLAMA_HOST', 'http://localhost:11434')])
            query_embedding = await lb.embed(self.embedding_model, query)
            
            collection = self.db.chroma_client.get_or_create_collection("memories")
            results = collection.query(
                query_embeddings=[query_embedding],
                n_results=top_k
            )
            
            return [(doc, score) for doc, score in zip(results['documents'][0], results['distances'][0])]
        except Exception as e:
            logger.error(f"Semantic search failed: {e}")
            return []
            
    async def _store_l1(self, key: str, item: MemoryItem):
        if not self.db.redis_client:
            return
            
        serialized = json.dumps({
            'content': item.content,
            'metadata': item.metadata,
            'access_count': item.access_count,
            'last_accessed': item.last_accessed.isoformat(),
            'created_at': item.created_at.isoformat()
        })
        
        if item.ttl:
            self.db.redis_client.setex(f"l1:{key}", item.ttl, serialized)
        else:
            self.db.redis_client.set(f"l1:{key}", serialized)
            
    async def _store_l2(self, key: str, item: MemoryItem):
        if not self.db.sqlite_conn:
            return
            
        await self.db.sqlite_conn.execute("""
            CREATE TABLE IF NOT EXISTS l2_cache (
                key TEXT PRIMARY KEY,
                content TEXT,
                metadata TEXT,
                access_count INTEGER,
                last_accessed TIMESTAMP,
                created_at TIMESTAMP
            )
        """)
        
        await self.db.sqlite_conn.execute("""
            INSERT OR REPLACE INTO l2_cache 
            (key, content, metadata, access_count, last_accessed, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            key,
            json.dumps(item.content),
            json.dumps(item.metadata),
            item.access_count,
            item.last_accessed.isoformat(),
            item.created_at.isoformat()
        ))
        await self.db.sqlite_conn.commit()
        
    async def _store_l3(self, key: str, item: MemoryItem):
        if not self.db.postgres_pool:
            return
            
        async with self.db.postgres_pool.acquire() as conn:
            await conn.execute("""
                CREATE TABLE IF NOT EXISTS l3_storage (
                    key TEXT PRIMARY KEY,
                    content JSONB,
                    metadata JSONB,
                    embedding vector(1024),
                    access_count INTEGER,
                    last_accessed TIMESTAMP,
                    created_at TIMESTAMP
                )
            """)
            
            await conn.execute("""
                INSERT INTO l3_storage 
                (key, content, metadata, access_count, last_accessed, created_at)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (key) DO UPDATE SET
                    content = EXCLUDED.content,
                    metadata = EXCLUDED.metadata,
                    access_count = EXCLUDED.access_count,
                    last_accessed = EXCLUDED.last_accessed
            """, key, item.content, item.metadata, item.access_count, 
            item.last_accessed, item.created_at)
            
    async def _retrieve_l1(self, key: str) -> Optional[MemoryItem]:
        if not self.db.redis_client:
            return None
            
        data = self.db.redis_client.get(f"l1:{key}")
        if data:
            # Handle both bytes and string data
            data_str = data.decode() if isinstance(data, bytes) else data
            parsed = json.loads(data_str)
            return MemoryItem(
                key=key,
                content=parsed['content'],
                metadata=parsed['metadata'],
                access_count=parsed['access_count'],
                last_accessed=datetime.fromisoformat(parsed['last_accessed']),
                created_at=datetime.fromisoformat(parsed['created_at']),
                tier=MemoryTier.L1_CACHE
            )
        return None
        
    async def _retrieve_l2(self, key: str) -> Optional[MemoryItem]:
        if not self.db.sqlite_conn:
            return None
            
        cursor = await self.db.sqlite_conn.execute(
            "SELECT * FROM l2_cache WHERE key = ?", (key,)
        )
        row = await cursor.fetchone()
        
        if row:
            return MemoryItem(
                key=key,
                content=json.loads(row[1]),
                metadata=json.loads(row[2]),
                access_count=row[3],
                last_accessed=datetime.fromisoformat(row[4]),
                created_at=datetime.fromisoformat(row[5]),
                tier=MemoryTier.L2_CACHE
            )
        return None
        
    async def _retrieve_l3(self, key: str) -> Optional[MemoryItem]:
        if not self.db.postgres_pool:
            return None
            
        async with self.db.postgres_pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT * FROM l3_storage WHERE key = $1", key
            )
            
            if row:
                return MemoryItem(
                    key=key,
                    content=row['content'],
                    metadata=row['metadata'],
                    access_count=row['access_count'],
                    last_accessed=row['last_accessed'],
                    created_at=row['created_at'],
                    tier=MemoryTier.L3_STORAGE
                )
        return None
        
    async def _promote_to_l1(self, key: str, item: MemoryItem):
        item.tier = MemoryTier.L1_CACHE
        await self._store_l1(key, item)
        
    async def _promote_to_l2(self, key: str, item: MemoryItem):
        item.tier = MemoryTier.L2_CACHE
        await self._store_l2(key, item)
        
    async def _update_access_stats(self, key: str, item: MemoryItem):
        item.access_count += 1
        item.last_accessed = datetime.now()
        
        if item.tier == MemoryTier.L1_CACHE:
            await self._store_l1(key, item)
        elif item.tier == MemoryTier.L2_CACHE:
            await self._store_l2(key, item)
        elif item.tier == MemoryTier.L3_STORAGE:
            await self._store_l3(key, item)
            
    def _should_persist(self, item: MemoryItem) -> bool:
        return item.access_count > 1 or len(str(item.content)) > 1000
        
    def _generate_key(self, key: str) -> str:
        return hashlib.sha256(key.encode()).hexdigest()
        
    async def tier_migration(self):
        while True:
            try:
                await self._migrate_cold_data()
                await asyncio.sleep(300)
            except Exception as e:
                logger.error(f"Tier migration failed: {e}")
                await asyncio.sleep(60)
                
    async def _migrate_cold_data(self):
        now = datetime.now()
        
        if self.db.redis_client:
            keys = self.db.redis_client.keys("l1:*")
            for key in keys:
                # Handle both bytes and string keys
                key_str = key.decode() if isinstance(key, bytes) else key
                
                data = self.db.redis_client.get(key)
                if data:
                    # Handle both bytes and string data
                    data_str = data.decode() if isinstance(data, bytes) else data
                    parsed = json.loads(data_str)
                    
                    last_accessed = datetime.fromisoformat(parsed['last_accessed'])
                    if now - last_accessed > self.tier_thresholds[MemoryTier.L1_CACHE]:
                        item = MemoryItem(
                            key=key_str.replace("l1:", ""),
                            content=parsed['content'],
                            metadata=parsed['metadata'],
                            access_count=parsed['access_count'],
                            last_accessed=last_accessed,
                            created_at=datetime.fromisoformat(parsed['created_at'])
                        )
                        await self._store_l2(key_str.replace("l1:", ""), item)
                        self.db.redis_client.delete(key)