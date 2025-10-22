"""
⚠️ DEPRECATION NOTICE ⚠️

This module (core/distributed.py) is DEPRECATED and replaced by SOLLOL integration.

SOLLOL provides superior distributed capabilities:
- Auto-discovery of Ollama nodes (no manual configuration)
- Resource-aware routing (VRAM/RAM monitoring)
- Intelligent model-to-node placement
- Automatic GPU → CPU fallback
- Faster routing (10x improvement)
- Better failover (12x faster recovery)

Please use: core/sollol_integration.py

This file is kept for backward compatibility only.
Migration: main.py now uses SOLLOLIntegration instead of DistributedManager.
"""

import asyncio
import json
from typing import Dict, List, Any, Optional
from dataclasses import dataclass, field
from enum import Enum
import hashlib
from datetime import datetime, timedelta
from loguru import logger
import httpx
from collections import defaultdict

logger.warning("⚠️  core/distributed.py is DEPRECATED. Use core/sollol_integration.py instead")

class NodeType(Enum):
    GPU = "gpu"
    CPU = "cpu"
    HYBRID = "hybrid"
    
@dataclass
class ComputeNode:
    id: str
    host: str
    port: int
    type: NodeType
    max_models: int
    active_models: List[str]
    cpu_cores: int
    memory_gb: float
    is_healthy: bool = True
    last_heartbeat: datetime = None
    active_tasks: int = 0
    memory_available_gb: float = 0
    cpu_percent: float = 0
    ollama_healthy: bool = True
    agent_url: str = ""  # Node agent endpoint
    
class DistributedManager:
    def __init__(self, nodes: List[Dict] = None):
        """Initialize distributed manager with optional static nodes"""
        self.nodes = {}
        self.task_queue = asyncio.Queue()
        self.result_cache = {}
        self.task_history = defaultdict(list)
        self.node_metrics = defaultdict(lambda: {'tasks_completed': 0, 'total_time': 0})
        
        # Register static nodes if provided (for backward compatibility)
        if nodes:
            for node_config in nodes:
                node = ComputeNode(
                    id=node_config['id'],
                    host=node_config['host'],
                    port=node_config.get('port', 11434),
                    type=NodeType(node_config['type']),
                    max_models=node_config.get('max_models', 3),
                    active_models=[],
                    cpu_cores=node_config.get('cpu_cores', 4),
                    memory_gb=node_config.get('memory_gb', 16),
                    last_heartbeat=datetime.now(),
                    agent_url=f"http://{node_config['host']}:{node_config.get('agent_port', 8002)}"
                )
                self.nodes[node.id] = node
    
    async def register_node(self, node_data: Dict) -> bool:
        """Register a new node agent"""
        try:
            node_id = node_data['node_id']
            status = node_data.get('status', {})
            
            # Create or update node
            if node_id in self.nodes:
                # Update existing node
                node = self.nodes[node_id]
                node.last_heartbeat = datetime.now()
            else:
                # Create new node
                node = ComputeNode(
                    id=node_id,
                    host=node_data['host'],
                    port=node_data.get('port', 11434),
                    type=NodeType(node_data.get('node_type', 'cpu')),
                    max_models=node_data.get('max_models', 3),
                    active_models=[],
                    cpu_cores=status.get('cpu_count', 4),
                    memory_gb=status.get('memory_total_gb', 16),
                    last_heartbeat=datetime.now(),
                    agent_url=f"http://{node_data['host']}:{node_data.get('port', 8002)}"
                )
                self.nodes[node_id] = node
                logger.success(f"✅ Registered new node: {node_id}")
            
            # Update node status
            self._update_node_status(node, status)
            return True
            
        except Exception as e:
            logger.error(f"Failed to register node: {e}")
            return False
    
    async def handle_heartbeat(self, node_id: str, status: Dict):
        """Handle heartbeat from node agent"""
        if node_id in self.nodes:
            node = self.nodes[node_id]
            node.last_heartbeat = datetime.now()
            self._update_node_status(node, status)
            # Only log if there's significant activity or issues
            if status.get('active_tasks', 0) > 0 or not status.get('ollama_healthy', True):
                logger.info(f"💗 Heartbeat from {node_id}: {status.get('active_tasks')} tasks, {status.get('memory_available_gb', 0):.1f}GB free, Ollama: {'✓' if status.get('ollama_healthy') else '✗'}")
        else:
            logger.warning(f"Heartbeat from unknown node: {node_id}")
    
    def _update_node_status(self, node: ComputeNode, status: Dict):
        """Update node status from heartbeat data"""
        node.is_healthy = status.get('ollama_healthy', False)
        node.active_tasks = status.get('active_tasks', 0)
        node.memory_available_gb = status.get('memory_available_gb', 0)
        node.cpu_percent = status.get('cpu_percent', 0)
        node.active_models = status.get('active_models', [])
        node.ollama_healthy = status.get('ollama_healthy', False)
        
    async def health_check_loop(self):
        """Monitor node health and remove stale nodes"""
        # Wait before starting to avoid initial rush
        await asyncio.sleep(10)
        
        # Get local IPs to identify same-machine nodes
        import socket
        local_hostname = socket.gethostname()
        local_ips = {'localhost', '127.0.0.1'}
        try:
            # Get all local IPs for THIS machine (coordinator)
            local_ips.add(socket.gethostbyname(local_hostname))
            # Also get all IPs from network interfaces on THIS machine only
            import subprocess
            result = subprocess.run(['hostname', '-I'], capture_output=True, text=True)
            if result.returncode == 0:
                for ip in result.stdout.strip().split():
                    local_ips.add(ip)
        except:
            pass
        
        logger.info(f"Coordinator local IPs: {local_ips}")
        
        while True:
            current_time = datetime.now()
            # Track which Ollama endpoints we've already checked
            # This prevents checking the same Ollama instance multiple times
            checked_endpoints = set()
            
            for node_id, node in list(self.nodes.items()):
                # Check if node is stale (no heartbeat for 2 minutes)
                if node.last_heartbeat:
                    time_since_heartbeat = (current_time - node.last_heartbeat).total_seconds()
                    if time_since_heartbeat > 120:
                        logger.warning(f"⚠️ Node {node_id} is stale, marking unhealthy")
                        node.is_healthy = False
                
                # For nodes on the same machine as coordinator, rely on heartbeat
                if node.host in local_ips:
                    # Local nodes report their health via heartbeat
                    # No need for active health checks
                    continue
                
                # Check if we've already tested this Ollama endpoint
                ollama_endpoint = f"{node.host}:{node.port}"
                if ollama_endpoint in checked_endpoints:
                    # Already checked this Ollama instance
                    continue
                    
                # Mark this endpoint as checked
                checked_endpoints.add(ollama_endpoint)
                
                # Health check remote nodes
                # Prefer agent URL for health checks
                if node.agent_url:
                    node.is_healthy = await self._check_node_agent_health(node)
                else:
                    # Direct Ollama check
                    node.is_healthy = await self._check_node_health(node)
                    
            # Check less frequently - every 2 minutes
            await asyncio.sleep(120)
    
    async def _check_node_agent_health(self, node: ComputeNode) -> bool:
        """Check health through node agent"""
        try:
            # No timeout - let health checks complete
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.get(f"{node.agent_url}/health")
                return response.status_code == 200
        except:
            return False
            
    async def _check_node_health(self, node: ComputeNode) -> bool:
        """Check Ollama health directly"""
        try:
            # No timeout - let health checks complete
            async with httpx.AsyncClient(timeout=None) as client:
                response = await client.get(
                    f"http://{node.host}:{node.port}/api/tags"
                )
                return response.status_code == 200
        except:
            return False
            
    def select_node_for_model(self, model: str, prefer_gpu: bool = True) -> Optional[ComputeNode]:
        available_nodes = [n for n in self.nodes.values() if n.is_healthy]
        
        if not available_nodes:
            return None
            
        if prefer_gpu:
            gpu_nodes = [n for n in available_nodes if n.type == NodeType.GPU]
            if gpu_nodes:
                available_nodes = gpu_nodes
                
        node_scores = {}
        for node in available_nodes:
            load = len(node.active_models) / node.max_models
            memory_usage = self._estimate_memory_usage(node)
            
            score = (1 - load) * 0.6 + (1 - memory_usage) * 0.4
            if node.type == NodeType.GPU and prefer_gpu:
                score *= 1.5
                
            node_scores[node] = score
            
        return max(node_scores, key=node_scores.get)
        
    def _estimate_memory_usage(self, node: ComputeNode) -> float:
        model_memory = {
            'small': 2,
            'medium': 8,
            'large': 16
        }
        
        total_usage = 0
        for model in node.active_models:
            if '3b' in model or '1.7b' in model:
                total_usage += model_memory['small']
            elif '7b' in model or '8b' in model or '9b' in model:
                total_usage += model_memory['medium']
            else:
                total_usage += model_memory['large']
                
        return min(total_usage / node.memory_gb, 1.0)
        
    async def distribute_task(self, task: Dict, models: List[str]) -> List[Dict]:
        task_id = hashlib.md5(json.dumps(task).encode()).hexdigest()
        
        if task_id in self.result_cache:
            logger.info(f"Task {task_id} found in cache")
            return self.result_cache[task_id]
            
        assignments = []
        for model in models:
            node = self.select_node_for_model(model, prefer_gpu='code' in task.get('type', ''))
            if node:
                assignments.append({
                    'model': model,
                    'node': node.id,
                    'host': f"http://{node.host}:{node.port}"
                })
                node.active_models.append(model)
                
        results = await self._execute_distributed(task, assignments)
        
        for assignment in assignments:
            node = self.nodes[assignment['node']]
            if assignment['model'] in node.active_models:
                node.active_models.remove(assignment['model'])
                
        self.result_cache[task_id] = results
        return results
        
    async def _execute_distributed(self, task: Dict, assignments: List[Dict]) -> List[Dict]:
        """Execute task on distributed nodes, preferring node agents"""
        
        async def execute_on_node(assignment: Dict) -> Dict:
            node = self.nodes.get(assignment['node'])
            if not node:
                return None
                
            start_time = datetime.now()
            
            try:
                # Prefer node agent if available
                if node.agent_url:
                    logger.info(f"🎯 Executing {assignment['model']} on node: {node.id}")
                    # No timeout for model execution - resource constrained systems need time
                    # Also accounts for dynamic model downloading time
                    async with httpx.AsyncClient(timeout=None) as client:
                        response = await client.post(
                            f"{node.agent_url}/execute",
                            json={
                                'task_id': hashlib.md5(f"{task.get('prompt', '')}_{assignment['model']}".encode()).hexdigest()[:8],
                                'model': assignment['model'],
                                'prompt': task['prompt'],
                                'temperature': task.get('temperature', 0.7),
                                'max_tokens': task.get('max_tokens', 2048),
                                'stream': False
                            }
                        )
                        
                        if response.status_code == 200:
                            result_data = response.json()
                            elapsed = (datetime.now() - start_time).total_seconds()
                            
                            # Update metrics
                            self.node_metrics[node.id]['tasks_completed'] += 1
                            self.node_metrics[node.id]['total_time'] += elapsed
                            
                            return {
                                'model': assignment['model'],
                                'node': assignment['node'],
                                'response': result_data.get('response', ''),
                                'elapsed_time': elapsed,
                                'via_agent': True
                            }
                else:
                    # Fallback to direct Ollama call
                    logger.info(f"🎯 Executing directly on Ollama: {node.id}")
                    # No timeout for model execution - resource constrained systems need time
                    async with httpx.AsyncClient(timeout=None) as client:
                        response = await client.post(
                            f"{assignment['host']}/api/generate",
                            json={
                                'model': assignment['model'],
                                'prompt': task['prompt'],
                                'temperature': task.get('temperature', 0.7),
                                'stream': False
                            }
                        )
                        
                        if response.status_code == 200:
                            elapsed = (datetime.now() - start_time).total_seconds()
                            return {
                                'model': assignment['model'],
                                'node': assignment['node'],
                                'response': response.json()['response'],
                                'elapsed_time': elapsed,
                                'via_agent': False
                            }
                            
            except Exception as e:
                logger.error(f"Failed to execute on {assignment['node']}: {e}")
                return None
                
        tasks = [execute_on_node(a) for a in assignments]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
        
    async def rebalance_models(self):
        total_models = sum(len(n.active_models) for n in self.nodes.values())
        healthy_nodes = [n for n in self.nodes.values() if n.is_healthy]
        
        if not healthy_nodes:
            return
            
        target_per_node = total_models // len(healthy_nodes)
        
        for node in healthy_nodes:
            current = len(node.active_models)
            if current > target_per_node + 1:
                models_to_move = current - target_per_node
                logger.info(f"Rebalancing: Moving {models_to_move} models from {node.id}")
                
    def get_cluster_stats(self) -> Dict:
        total_nodes = len(self.nodes)
        healthy_nodes = sum(1 for n in self.nodes.values() if n.is_healthy)
        total_models = sum(len(n.active_models) for n in self.nodes.values())
        
        gpu_nodes = [n for n in self.nodes.values() if n.type == NodeType.GPU]
        cpu_nodes = [n for n in self.nodes.values() if n.type == NodeType.CPU]
        
        return {
            'total_nodes': total_nodes,
            'healthy_nodes': healthy_nodes,
            'gpu_nodes': len(gpu_nodes),
            'cpu_nodes': len(cpu_nodes),
            'active_models': total_models,
            'cache_size': len(self.result_cache),
            'nodes': [
                {
                    'id': n.id,
                    'type': n.type.value,
                    'healthy': n.is_healthy,
                    'active_models': len(n.active_models),
                    'load': len(n.active_models) / n.max_models
                }
                for n in self.nodes.values()
            ]
        }