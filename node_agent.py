#!/usr/bin/env python3
"""
⚠️ DEPRECATION NOTICE ⚠️

This file (node_agent.py) is DEPRECATED and NO LONGER NEEDED with SOLLOL integration.

SOLLOL provides automatic node discovery - no manual node agents required!
- Zero-configuration setup
- Auto-discovers all Ollama instances on the network
- Automatic health monitoring
- No manual node registration needed

Please use SOLLOL's auto-discovery instead.

This file is kept for backward compatibility and reference only.
To use SOLLOL: main.py now automatically discovers nodes via SOLLOLIntegration.

===== LEGACY DOCUMENTATION BELOW =====

Hydra Node Agent - Run on each CPU/RAM node for distributed computing
This agent manages local Ollama instance and reports to central coordinator
"""

import asyncio
import psutil
import platform
import socket
import os
import sys
import json
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional, List
from contextlib import asynccontextmanager
import httpx
from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import uvicorn
from loguru import logger

# Configure logging
logger.remove()
logger.add(sys.stderr, level="INFO", format="<green>{time:HH:mm:ss}</green> | <level>{level}</level> | {message}")

class NodeConfig(BaseModel):
    """Node configuration"""
    node_id: str = socket.gethostname()
    node_type: str = "cpu"  # cpu, gpu, or hybrid
    ollama_host: str = "http://localhost:11434"
    coordinator_host: str = "http://localhost:8001"
    port: int = 8002
    max_concurrent_tasks: int = 3
    reserved_memory_gb: float = 2.0  # Reserve 2GB for system
    model_cache_size: int = 5  # Max models to keep loaded

class NodeStatus(BaseModel):
    """Current node status"""
    node_id: str
    node_type: str
    cpu_count: int
    cpu_percent: float
    memory_total_gb: float
    memory_available_gb: float
    memory_percent: float
    disk_free_gb: float
    active_models: List[str]
    active_tasks: int
    ollama_healthy: bool
    uptime: float
    last_heartbeat: str

class TaskRequest(BaseModel):
    """Task request from coordinator"""
    task_id: str
    model: str
    prompt: str
    temperature: float = 0.7
    max_tokens: int = 2048
    stream: bool = False

class NodeAgent:
    """Agent that runs on each distributed node"""
    
    def __init__(self, config: NodeConfig):
        self.config = config
        self.node_id = config.node_id
        self.start_time = datetime.now()
        self.active_tasks = {}
        self.loaded_models = set()
        self.ollama_client = None
        # No timeout for coordinator client - let operations complete
        self.coordinator_client = httpx.AsyncClient(timeout=None)
        
    async def initialize(self):
        """Initialize node agent"""
        logger.info(f"🚀 Initializing node agent: {self.node_id}")
        
        # Check Ollama installation
        if not await self.check_ollama():
            logger.warning("Ollama not running, attempting to start...")
            await self.start_ollama()
        
        # Register with coordinator
        await self.register_with_coordinator()
        
        # Start background tasks
        asyncio.create_task(self.heartbeat_loop())
        asyncio.create_task(self.resource_monitor_loop())
        asyncio.create_task(self.model_manager_loop())
        
        logger.success(f"✅ Node agent initialized: {self.node_id}")
    
    async def check_ollama(self) -> bool:
        """Check if Ollama is running"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.config.ollama_host}/api/tags")
                return response.status_code == 200
        except:
            return False
    
    async def start_ollama(self):
        """Start Ollama service"""
        try:
            # Try systemd first
            subprocess.run(["systemctl", "--user", "start", "ollama"], check=False)
            await asyncio.sleep(3)
            
            if not await self.check_ollama():
                # Try direct command
                subprocess.Popen(["ollama", "serve"], 
                               stdout=subprocess.DEVNULL, 
                               stderr=subprocess.DEVNULL)
                await asyncio.sleep(5)
            
            if await self.check_ollama():
                logger.success("✅ Ollama started successfully")
            else:
                logger.error("❌ Failed to start Ollama")
        except Exception as e:
            logger.error(f"Error starting Ollama: {e}")
    
    async def get_node_status(self) -> NodeStatus:
        """Get current node status"""
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        # Get loaded models from Ollama
        loaded_models = []
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.config.ollama_host}/api/ps")
                if response.status_code == 200:
                    models_data = response.json()
                    loaded_models = [m['name'] for m in models_data.get('models', [])]
        except:
            pass
        
        uptime = (datetime.now() - self.start_time).total_seconds()
        
        return NodeStatus(
            node_id=self.node_id,
            node_type=self.config.node_type,
            cpu_count=psutil.cpu_count(),
            cpu_percent=cpu_percent,
            memory_total_gb=memory.total / (1024**3),
            memory_available_gb=memory.available / (1024**3),
            memory_percent=memory.percent,
            disk_free_gb=disk.free / (1024**3),
            active_models=loaded_models,
            active_tasks=len(self.active_tasks),
            ollama_healthy=await self.check_ollama(),
            uptime=uptime,
            last_heartbeat=datetime.now().isoformat()
        )
    
    async def register_with_coordinator(self):
        """Register this node with the coordinator"""
        try:
            status = await self.get_node_status()
            response = await self.coordinator_client.post(
                f"{self.config.coordinator_host}/nodes/register",
                json={
                    "node_id": self.node_id,
                    "node_type": self.config.node_type,
                    "host": socket.gethostbyname(socket.gethostname()),
                    "port": self.config.port,
                    "status": status.model_dump()
                }
            )
            if response.status_code == 200:
                logger.success(f"✅ Registered with coordinator")
            else:
                logger.warning(f"Registration failed: {response.status_code}")
        except Exception as e:
            logger.error(f"Failed to register: {e}")
    
    async def heartbeat_loop(self):
        """Send periodic heartbeat to coordinator"""
        while True:
            try:
                status = await self.get_node_status()
                await self.coordinator_client.post(
                    f"{self.config.coordinator_host}/nodes/{self.node_id}/heartbeat",
                    json=status.model_dump()
                )
                # Only log heartbeat failures, not successes
            except Exception as e:
                logger.warning(f"Heartbeat failed: {e}")
            
            await asyncio.sleep(60)  # Every 60 seconds instead of 30
    
    async def resource_monitor_loop(self):
        """Monitor resource usage and adjust capacity"""
        while True:
            memory = psutil.virtual_memory()
            available_gb = memory.available / (1024**3)
            
            # If memory is low, unload some models
            if available_gb < self.config.reserved_memory_gb:
                logger.warning(f"⚠️ Low memory: {available_gb:.1f}GB available")
                await self.unload_least_used_model()
            
            # Check CPU throttling
            cpu_percent = psutil.cpu_percent(interval=1)
            if cpu_percent > 90:
                logger.warning(f"⚠️ High CPU usage: {cpu_percent}%")
                # Could implement task throttling here
            
            await asyncio.sleep(10)
    
    async def model_manager_loop(self):
        """Manage model loading and unloading"""
        while True:
            try:
                # Get list of models from Ollama
                async with httpx.AsyncClient() as client:
                    response = await client.get(f"{self.config.ollama_host}/api/ps")
                    if response.status_code == 200:
                        models_data = response.json()
                        loaded = {m['name'] for m in models_data.get('models', [])}
                        self.loaded_models = loaded
                        
                        # If too many models loaded, unload oldest
                        if len(loaded) > self.config.model_cache_size:
                            await self.unload_least_used_model()
            except Exception as e:
                logger.error(f"Model manager error: {e}")
            
            await asyncio.sleep(60)
    
    async def unload_least_used_model(self):
        """Unload the least recently used model"""
        # This is a simplified version - would need usage tracking
        if self.loaded_models:
            model = list(self.loaded_models)[0]
            try:
                async with httpx.AsyncClient() as client:
                    # Ollama doesn't have direct unload, but we can work around it
                    logger.info(f"Would unload model: {model}")
            except:
                pass
    
    async def check_model_exists(self, model: str) -> bool:
        """Check if a model exists locally"""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(f"{self.config.ollama_host}/api/tags")
                if response.status_code == 200:
                    models = response.json().get('models', [])
                    return any(m['name'] == model or m['name'].startswith(f"{model}:") for m in models)
        except:
            return False
        return False
    
    async def pull_model(self, model: str) -> bool:
        """Pull a model if not available"""
        try:
            logger.info(f"📥 Pulling model: {model}")
            
            # Check if model already exists
            if await self.check_model_exists(model):
                logger.info(f"✅ Model {model} already exists")
                return True
            
            # Pull the model
            process = await asyncio.create_subprocess_exec(
                "ollama", "pull", model,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode == 0:
                logger.success(f"✅ Pulled model: {model}")
                return True
            else:
                logger.error(f"Failed to pull {model}: {stderr.decode()}")
                return False
                
        except Exception as e:
            logger.error(f"Error pulling model: {e}")
            return False
    
    async def execute_task(self, task: TaskRequest) -> Dict:
        """Execute a task from the coordinator"""
        logger.info(f"📋 Executing task: {task.task_id} with model: {task.model}")
        
        # Check if we have capacity
        if len(self.active_tasks) >= self.config.max_concurrent_tasks:
            raise HTTPException(status_code=503, detail="Node at capacity")
        
        # Check if model exists locally first
        model_exists = await self.check_model_exists(task.model)
        
        # If model doesn't exist, pull it dynamically
        if not model_exists:
            logger.info(f"📥 Model {task.model} not found locally, pulling dynamically...")
            if not await self.pull_model(task.model):
                raise HTTPException(status_code=404, detail=f"Model {task.model} not available")
        
        # Track task
        self.active_tasks[task.task_id] = {
            "started": datetime.now(),
            "model": task.model
        }
        
        try:
            # Execute with Ollama
            # No timeout - resource constrained systems need time
            async with httpx.AsyncClient(timeout=None) as client:
                if task.stream:
                    # Streaming response
                    response = await client.post(
                        f"{self.config.ollama_host}/api/generate",
                        json={
                            "model": task.model,
                            "prompt": task.prompt,
                            "temperature": task.temperature,
                            "num_predict": task.max_tokens,
                            "stream": True
                        },
                        # Already set to None - good for resource constrained systems
                        timeout=None
                    )
                    
                    # Return streaming response
                    async def stream_generator():
                        async for line in response.aiter_lines():
                            if line:
                                yield line + b'\n'
                    
                    return StreamingResponse(stream_generator(), media_type="text/event-stream")
                else:
                    # Non-streaming response
                    response = await client.post(
                        f"{self.config.ollama_host}/api/generate",
                        json={
                            "model": task.model,
                            "prompt": task.prompt,
                            "temperature": task.temperature,
                            "num_predict": task.max_tokens,
                            "stream": False
                        }
                    )
                    
                    if response.status_code == 200:
                        result = response.json()
                        elapsed = (datetime.now() - self.active_tasks[task.task_id]["started"]).total_seconds()
                        
                        logger.success(f"✅ Task {task.task_id} completed in {elapsed:.2f}s")
                        
                        return {
                            "task_id": task.task_id,
                            "node_id": self.node_id,
                            "model": task.model,
                            "response": result.get("response", ""),
                            "elapsed_time": elapsed,
                            "completed_at": datetime.now().isoformat()
                        }
                    else:
                        raise HTTPException(status_code=response.status_code, 
                                          detail="Ollama generation failed")
                        
        except Exception as e:
            logger.error(f"Task {task.task_id} failed: {e}")
            raise
        finally:
            # Clean up task tracking
            if task.task_id in self.active_tasks:
                del self.active_tasks[task.task_id]

# Global agent instance
agent: Optional[NodeAgent] = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan context manager for startup/shutdown"""
    # Startup
    global agent
    config = NodeConfig(
        node_id=os.getenv("NODE_ID", socket.gethostname()),
        node_type=os.getenv("NODE_TYPE", "cpu"),
        ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434"),
        coordinator_host=os.getenv("COORDINATOR_HOST", "http://localhost:8001"),
        port=int(os.getenv("NODE_PORT", "8002"))
    )
    agent = NodeAgent(config)
    await agent.initialize()
    
    yield  # Server is running
    
    # Shutdown
    logger.info("Shutting down node agent...")
    if agent.coordinator_client:
        await agent.coordinator_client.aclose()

# Create FastAPI app with lifespan
app = FastAPI(title="Hydra Node Agent", version="1.0.0", lifespan=lifespan)

@app.get("/health")
async def health():
    """Health check endpoint - minimal logging"""
    if agent:
        # Don't call expensive get_node_status for simple health checks
        return {"status": "healthy", "node_id": agent.node_id}
    else:
        raise HTTPException(status_code=503, detail="Agent not initialized")

@app.get("/status")
async def get_status():
    """Get detailed node status"""
    if agent:
        return await agent.get_node_status()
    raise HTTPException(status_code=503, detail="Agent not initialized")

@app.post("/execute")
async def execute_task(task: TaskRequest):
    """Execute a task assigned by coordinator"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    return await agent.execute_task(task)

@app.post("/pull/{model}")
async def pull_model(model: str):
    """Pull a specific model"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    success = await agent.pull_model(model)
    if success:
        return {"status": "success", "model": model}
    else:
        raise HTTPException(status_code=500, detail=f"Failed to pull {model}")

@app.get("/models")
async def list_models():
    """List available models on this node"""
    if not agent:
        raise HTTPException(status_code=503, detail="Agent not initialized")
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{agent.config.ollama_host}/api/tags")
            if response.status_code == 200:
                return response.json()
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/tasks")
async def get_active_tasks():
    """Get list of active tasks"""
    if agent:
        return {"active_tasks": agent.active_tasks}
    return {"active_tasks": {}}

def run_node_agent():
    """Run the node agent"""
    import argparse
    parser = argparse.ArgumentParser(description="Hydra Node Agent")
    parser.add_argument("--node-id", default=socket.gethostname(), help="Node identifier")
    parser.add_argument("--type", default="cpu", choices=["cpu", "gpu", "hybrid"], help="Node type")
    parser.add_argument("--port", type=int, default=8002, help="Agent port")
    parser.add_argument("--coordinator", default="http://localhost:8001", help="Coordinator URL")
    parser.add_argument("--ollama", default="http://localhost:11434", help="Ollama URL")
    
    args = parser.parse_args()
    
    # Set environment variables
    os.environ["NODE_ID"] = args.node_id
    os.environ["NODE_TYPE"] = args.type
    os.environ["NODE_PORT"] = str(args.port)
    os.environ["COORDINATOR_HOST"] = args.coordinator
    os.environ["OLLAMA_HOST"] = args.ollama
    
    logger.info(f"""
    ╔══════════════════════════════════════╗
    ║     🐉 Hydra Node Agent Starting     ║
    ╠══════════════════════════════════════╣
    ║ Node ID: {args.node_id:<28} ║
    ║ Type: {args.type:<31} ║
    ║ Port: {args.port:<31} ║
    ║ Coordinator: {args.coordinator:<24} ║
    ╚══════════════════════════════════════╝
    """)
    
    # Configure logging to reduce health check spam
    import logging
    
    # Create custom filter to suppress health check logs
    class HealthCheckFilter(logging.Filter):
        def filter(self, record):
            # Filter out health check requests from access logs
            return "/health" not in record.getMessage()
    
    # Apply filter to uvicorn access logger
    access_logger = logging.getLogger("uvicorn.access")
    access_logger.addFilter(HealthCheckFilter())
    access_logger.setLevel(logging.WARNING)
    
    uvicorn.run(app, host="0.0.0.0", port=args.port, log_level="warning")

if __name__ == "__main__":
    run_node_agent()