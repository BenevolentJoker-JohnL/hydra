#!/usr/bin/env python3
"""
Node Simulation Script
Simulates multiple distributed nodes locally for testing
"""

import asyncio
import sys
import os
import socket
import random
from datetime import datetime
import httpx
from typing import List, Dict
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from loguru import logger
from fastapi import FastAPI
import uvicorn
from threading import Thread
import psutil


class SimulatedNode:
    """Simulated compute node for testing"""
    
    def __init__(self, node_id: str, port: int, node_type: str = "cpu"):
        self.node_id = node_id
        self.port = port
        self.node_type = node_type
        self.app = FastAPI()
        self.active_tasks = 0
        self.models = []
        self.start_time = datetime.now()
        self.setup_routes()
        
    def setup_routes(self):
        """Setup FastAPI routes"""
        
        @self.app.get("/health")
        async def health():
            return self.get_status()
        
        @self.app.get("/status")
        async def status():
            return self.get_status()
        
        @self.app.post("/execute")
        async def execute(task: Dict):
            """Simulate task execution"""
            self.active_tasks += 1
            
            # Simulate processing time
            await asyncio.sleep(random.uniform(0.5, 2.0))
            
            response = {
                "task_id": task.get("task_id", "unknown"),
                "node_id": self.node_id,
                "model": task.get("model", "tinyllama"),
                "response": f"Simulated response from {self.node_id}",
                "elapsed_time": random.uniform(1.0, 5.0),
                "completed_at": datetime.now().isoformat()
            }
            
            self.active_tasks -= 1
            return response
        
        @self.app.post("/pull/{model}")
        async def pull_model(model: str):
            """Simulate model pulling"""
            await asyncio.sleep(1)  # Simulate download time
            if model not in self.models:
                self.models.append(model)
            return {"status": "success", "model": model}
        
        @self.app.get("/models")
        async def list_models():
            """List available models"""
            return {
                "models": [
                    {"name": model, "size": f"{random.randint(1,10)}GB"}
                    for model in self.models
                ]
            }
    
    def get_status(self):
        """Get node status"""
        memory = psutil.virtual_memory()
        
        return {
            "node_id": self.node_id,
            "node_type": self.node_type,
            "cpu_count": psutil.cpu_count(),
            "cpu_percent": psutil.cpu_percent(interval=0.1),
            "memory_total_gb": memory.total / (1024**3),
            "memory_available_gb": memory.available / (1024**3),
            "memory_percent": memory.percent,
            "disk_free_gb": psutil.disk_usage('/').free / (1024**3),
            "active_models": self.models,
            "active_tasks": self.active_tasks,
            "ollama_healthy": True,  # Always healthy in simulation
            "uptime": (datetime.now() - self.start_time).total_seconds(),
            "last_heartbeat": datetime.now().isoformat()
        }
    
    def run(self):
        """Run the simulated node"""
        uvicorn.run(self.app, host="0.0.0.0", port=self.port, log_level="error")


class NodeSimulator:
    """Manages multiple simulated nodes"""
    
    def __init__(self, coordinator_url: str = "http://localhost:8001"):
        self.coordinator_url = coordinator_url
        self.nodes = []
        self.threads = []
        
    def create_node(self, node_id: str, port: int, node_type: str = "cpu"):
        """Create a simulated node"""
        node = SimulatedNode(node_id, port, node_type)
        self.nodes.append(node)
        
        # Run in thread
        thread = Thread(target=node.run, daemon=True)
        thread.start()
        self.threads.append(thread)
        
        logger.info(f"🚀 Started simulated node: {node_id} on port {port}")
        return node
    
    async def register_nodes(self):
        """Register all nodes with coordinator"""
        async with httpx.AsyncClient(timeout=10) as client:
            for node in self.nodes:
                try:
                    # Get node status
                    status = node.get_status()
                    
                    # Register with coordinator
                    response = await client.post(
                        f"{self.coordinator_url}/nodes/register",
                        json={
                            "node_id": node.node_id,
                            "node_type": node.node_type,
                            "host": "localhost",
                            "port": node.port,
                            "status": status
                        }
                    )
                    
                    if response.status_code == 200:
                        logger.success(f"✅ Registered {node.node_id} with coordinator")
                    else:
                        logger.error(f"❌ Failed to register {node.node_id}: {response.status_code}")
                        
                except Exception as e:
                    logger.error(f"Error registering {node.node_id}: {e}")
    
    async def send_heartbeats(self):
        """Send periodic heartbeats from all nodes"""
        async with httpx.AsyncClient(timeout=10) as client:
            while True:
                for node in self.nodes:
                    try:
                        status = node.get_status()
                        await client.post(
                            f"{self.coordinator_url}/nodes/{node.node_id}/heartbeat",
                            json=status
                        )
                        logger.debug(f"💗 Heartbeat sent from {node.node_id}")
                    except Exception as e:
                        logger.warning(f"Heartbeat failed for {node.node_id}: {e}")
                
                await asyncio.sleep(30)
    
    async def simulate_workload(self):
        """Simulate varying workloads on nodes"""
        models = ["tinyllama", "phi", "gemma:2b", "qwen2.5:1.5b"]
        
        while True:
            # Randomly select a node and model
            node = random.choice(self.nodes)
            model = random.choice(models)
            
            # Simulate pulling model if not present
            if model not in node.models:
                node.models.append(model)
                logger.info(f"📥 {node.node_id} pulled model: {model}")
            
            # Simulate task execution
            node.active_tasks = random.randint(0, 3)
            
            await asyncio.sleep(random.uniform(5, 15))
    
    async def monitor_cluster(self):
        """Monitor cluster status"""
        async with httpx.AsyncClient() as client:
            while True:
                try:
                    # Get cluster stats
                    response = await client.get(f"{self.coordinator_url}/stats")
                    if response.status_code == 200:
                        stats = response.json()
                        cluster = stats.get("cluster", {})
                        
                        logger.info(f"""
📊 Cluster Status:
   Total Nodes: {cluster.get('total_nodes', 0)}
   Healthy Nodes: {cluster.get('healthy_nodes', 0)}
   GPU Nodes: {cluster.get('gpu_nodes', 0)}
   CPU Nodes: {cluster.get('cpu_nodes', 0)}
   Active Models: {cluster.get('active_models', 0)}
                        """)
                        
                except Exception as e:
                    logger.warning(f"Failed to get cluster stats: {e}")
                
                await asyncio.sleep(60)


async def main():
    """Main simulation runner"""
    import argparse
    
    parser = argparse.ArgumentParser(description="Simulate distributed nodes")
    parser.add_argument("--nodes", type=int, default=3, help="Number of nodes to simulate")
    parser.add_argument("--gpu-nodes", type=int, default=1, help="Number of GPU nodes")
    parser.add_argument("--start-port", type=int, default=8010, help="Starting port for nodes")
    parser.add_argument("--coordinator", default="http://localhost:8001", help="Coordinator URL")
    parser.add_argument("--workload", action="store_true", help="Simulate workload")
    parser.add_argument("--monitor", action="store_true", help="Monitor cluster")
    
    args = parser.parse_args()
    
    logger.info(f"""
╔══════════════════════════════════════╗
║     🐉 Hydra Node Simulator          ║
╠══════════════════════════════════════╣
║ Simulating {args.nodes} nodes               ║
║ GPU Nodes: {args.gpu_nodes}                    ║
║ Starting Port: {args.start_port}            ║
║ Coordinator: {args.coordinator:<24} ║
╚══════════════════════════════════════╝
    """)
    
    simulator = NodeSimulator(args.coordinator)
    
    # Create GPU nodes
    for i in range(args.gpu_nodes):
        simulator.create_node(
            f"sim-gpu-{i+1}",
            args.start_port + i,
            "gpu"
        )
    
    # Create CPU nodes
    for i in range(args.nodes - args.gpu_nodes):
        simulator.create_node(
            f"sim-cpu-{i+1}",
            args.start_port + args.gpu_nodes + i,
            "cpu"
        )
    
    # Wait for nodes to start
    await asyncio.sleep(2)
    
    # Register nodes with coordinator
    await simulator.register_nodes()
    
    # Start background tasks
    tasks = [
        asyncio.create_task(simulator.send_heartbeats())
    ]
    
    if args.workload:
        tasks.append(asyncio.create_task(simulator.simulate_workload()))
    
    if args.monitor:
        tasks.append(asyncio.create_task(simulator.monitor_cluster()))
    
    # Keep running
    try:
        await asyncio.gather(*tasks)
    except KeyboardInterrupt:
        logger.info("🛑 Shutting down simulator...")
        for task in tasks:
            task.cancel()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Simulator stopped")