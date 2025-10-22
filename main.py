#!/usr/bin/env python3

import asyncio
import os
import sys
import json
from pathlib import Path
from contextlib import asynccontextmanager
from dotenv import load_dotenv
from loguru import logger
from core.logging_config import configure_logging
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from typing import Dict, List, Optional

load_dotenv()

from db.connections import db_manager
from core.memory import HierarchicalMemory
from core.orchestrator import ModelOrchestrator
from core.sollol_integration import SOLLOLIntegration
from workflows.dag_pipeline import code_generation_pipeline

# Legacy imports kept for backward compatibility if needed
# from core.distributed import DistributedManager
# from models.ollama_manager import OllamaLoadBalancer, ModelPool

class CodeRequest(BaseModel):
    prompt: str
    context: Optional[Dict] = None
    models: Optional[List[str]] = None
    temperature: float = 0.7
    max_tokens: int = 2048

class SystemStatus(BaseModel):
    status: str
    components: Dict

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("🚀 Initializing Hydra system with SOLLOL...")
    await db_manager.initialize()

    global sollol, orchestrator, memory, load_balancer, distributed_manager

    # Initialize SOLLOL with configuration from environment variables
    sollol_config = {
        'discovery_enabled': os.getenv('SOLLOL_DISCOVERY_ENABLED', 'true').lower() == 'true',
        'discovery_timeout': int(os.getenv('SOLLOL_DISCOVERY_TIMEOUT', '10')),
        'health_check_interval': int(os.getenv('SOLLOL_HEALTH_CHECK_INTERVAL', '120')),
        'enable_vram_monitoring': os.getenv('SOLLOL_VRAM_MONITORING', 'true').lower() == 'true',
        'enable_dashboard': os.getenv('SOLLOL_DASHBOARD_ENABLED', 'true').lower() == 'true',
        'dashboard_port': int(os.getenv('SOLLOL_DASHBOARD_PORT', '8080')),
        'log_level': os.getenv('SOLLOL_LOG_LEVEL', 'INFO').upper()
    }

    logger.info(f"SOLLOL Configuration: discovery={sollol_config['discovery_enabled']}, "
                f"dashboard={'enabled' if sollol_config['enable_dashboard'] else 'disabled'} "
                f"(port {sollol_config['dashboard_port']})")

    # Create SOLLOL integration (replaces both OllamaLoadBalancer and DistributedManager)
    sollol = SOLLOLIntegration(config=sollol_config)
    await sollol.initialize()

    # Create aliases for backward compatibility
    load_balancer = sollol  # Acts as OllamaLoadBalancer
    distributed_manager = sollol  # Acts as DistributedManager

    # Initialize orchestrator with SOLLOL
    orchestrator = ModelOrchestrator(load_balancer)
    memory = HierarchicalMemory(db_manager)

    # Start background tasks
    health_check_task = asyncio.create_task(sollol.periodic_health_check())
    memory_migration_task = asyncio.create_task(memory.tier_migration())

    logger.success("✨ Hydra system initialized successfully with SOLLOL")
    logger.info(f"📊 Discovered {len(sollol.hosts)} Ollama nodes")

    if sollol.dashboard_enabled and sollol.dashboard:
        logger.info(f"🎨 SOLLOL Dashboard: http://localhost:{sollol.dashboard_port}")
        logger.info(f"📡 Hydra API: http://localhost:8001")
        logger.info(f"🌐 Hydra UI: Run 'python main.py ui' in another terminal")

    yield

    # Shutdown
    health_check_task.cancel()
    memory_migration_task.cancel()

    await sollol.close()
    await db_manager.close()
    logger.info("🔌 Hydra system shutdown complete")

app = FastAPI(title="Hydra API", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check() -> SystemStatus:
    components = {
        "database": {
            "postgres": db_manager.postgres_pool is not None,
            "redis": db_manager.redis_client is not None,
            "sqlite": db_manager.sqlite_conn is not None,
            "chroma": db_manager.chroma_client is not None
        },
        "ollama": {
            "healthy_hosts": len([h for h in load_balancer.hosts if load_balancer.health_status[h]])
        },
        "distributed": distributed_manager.get_cluster_stats()
    }
    
    return SystemStatus(
        status="healthy" if all(components["database"].values()) else "degraded",
        components=components
    )

@app.post("/generate")
async def generate_code(request: CodeRequest):
    try:
        cached = await memory.retrieve(request.prompt)
        if cached:
            logger.info("Returning cached response")
            return cached
            
        result = await code_generation_pipeline({
            "prompt": request.prompt,
            "context": request.context or {},
            "temperature": request.temperature,
            "max_tokens": request.max_tokens
        })
        
        await memory.store(
            key=request.prompt,
            content=result,
            metadata={"models": request.models} if request.models else {}
        )
        
        return result
        
    except Exception as e:
        logger.error(f"Generation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/orchestrate")
async def orchestrate_task(request: CodeRequest):
    try:
        result = await orchestrator.orchestrate(
            prompt=request.prompt,
            context=request.context
        )
        return result
    except Exception as e:
        logger.error(f"Orchestration failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/generate/stream")
async def generate_code_stream(request: CodeRequest):
    """Stream code generation response"""
    async def stream_generator():
        try:
            # Stream from orchestrator
            full_response = ""
            async for chunk_data in orchestrator.orchestrate_stream(
                prompt=request.prompt,
                context=request.context
            ):
                if 'chunk' in chunk_data:
                    full_response += chunk_data['chunk']
                    # Stream as Server-Sent Events format
                    yield f"data: {json.dumps({'chunk': chunk_data['chunk'], 'done': chunk_data.get('done', False)})}\n\n"
            
            # Store in memory after completion
            await memory.store(
                key=request.prompt,
                content={'response': full_response},
                metadata={"models": request.models} if request.models else {}
            )
            
            # Send final message
            yield f"data: {json.dumps({'done': True, 'full_response': full_response})}\n\n"
            
        except Exception as e:
            logger.error(f"Stream generation failed: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",  # Disable Nginx buffering
        }
    )

@app.get("/models")
async def list_models():
    available_models = []
    for host in load_balancer.hosts:
        if load_balancer.health_status[host]:
            try:
                client = load_balancer.client_pool[host]
                models = await client.list()
                for model in models.get('models', []):
                    if model['name'] not in [m['name'] for m in available_models]:
                        available_models.append({
                            'name': model['name'],
                            'host': host,
                            'size': model.get('size', 'unknown')
                        })
            except:
                pass
    return available_models

@app.get("/stats")
async def get_statistics():
    return {
        "cluster": distributed_manager.get_cluster_stats(),
        "load_balancer": {
            "request_counts": dict(load_balancer.request_counts),
            "health_status": dict(load_balancer.health_status)
        },
        "memory": {
            "cache_items": await memory.db.redis_client.dbsize() if memory.db.redis_client else 0
        }
    }

# Node management endpoints
@app.post("/nodes/register")
async def register_node(node_data: Dict):
    """Register a new compute node"""
    success = await distributed_manager.register_node(node_data)
    if success:
        return {"status": "registered", "node_id": node_data.get("node_id")}
    else:
        raise HTTPException(status_code=400, detail="Failed to register node")

@app.post("/nodes/{node_id}/heartbeat")
async def node_heartbeat(node_id: str, status: Dict):
    """Receive heartbeat from node"""
    await distributed_manager.handle_heartbeat(node_id, status)
    return {"status": "received"}

@app.get("/nodes")
async def list_nodes():
    """List all registered nodes"""
    nodes = []
    for node_id, node in distributed_manager.nodes.items():
        nodes.append({
            "id": node.id,
            "type": node.type.value,
            "host": node.host,
            "healthy": node.is_healthy,
            "active_tasks": node.active_tasks,
            "memory_available": node.memory_available_gb,
            "cpu_percent": node.cpu_percent,
            "last_heartbeat": node.last_heartbeat.isoformat() if node.last_heartbeat else None
        })
    return {"nodes": nodes}

@app.delete("/nodes/{node_id}")
async def remove_node(node_id: str):
    """Remove a node from the cluster"""
    if node_id in distributed_manager.nodes:
        del distributed_manager.nodes[node_id]
        return {"status": "removed", "node_id": node_id}
    else:
        raise HTTPException(status_code=404, detail="Node not found")

def run_api():
    # Configure logging for API mode
    configure_logging(verbose=False)
    logger.info("🚀 Starting Hydra API...")
    
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8001,
        reload=True,
        log_level="info"
    )

def run_streamlit():
    import subprocess
    import sys
    
    # Configure logging for UI mode
    configure_logging(verbose=True)
    logger.info("🚀 Starting Hydra UI...")
    
    # Check if streamlit is installed
    try:
        import streamlit
        subprocess.run([sys.executable, "-m", "streamlit", "run", "app.py"])
    except ImportError:
        logger.error("Streamlit not installed. Please run: pip install streamlit")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "api":
        run_api()
    elif len(sys.argv) > 1 and sys.argv[1] == "ui":
        run_streamlit()
    else:
        print("Hydra - Intelligent Code Synthesis System")
        print("\nUsage:")
        print("  python main.py api    - Run the API server")
        print("  python main.py ui     - Run the Streamlit UI")
        print("\nOr run both in separate terminals for full functionality")