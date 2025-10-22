#!/usr/bin/env python3
"""
Distributed System Test Suite
Tests node registration, task distribution, and failover
"""

import asyncio
import pytest
import httpx
from datetime import datetime
from unittest.mock import Mock, patch, AsyncMock
import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.distributed import DistributedManager, ComputeNode, NodeType
from node_agent import NodeAgent, NodeConfig, TaskRequest


class TestDistributedManager:
    """Test distributed manager functionality"""
    
    @pytest.fixture
    async def manager(self):
        """Create a test distributed manager"""
        return DistributedManager()
    
    @pytest.mark.asyncio
    async def test_node_registration(self, manager):
        """Test registering a new node"""
        node_data = {
            'node_id': 'test-node-1',
            'host': '192.168.1.100',
            'port': 8002,
            'node_type': 'cpu',
            'status': {
                'cpu_count': 8,
                'memory_total_gb': 16,
                'memory_available_gb': 12,
                'cpu_percent': 25,
                'ollama_healthy': True,
                'active_models': [],
                'active_tasks': 0
            }
        }
        
        success = await manager.register_node(node_data)
        assert success == True
        assert 'test-node-1' in manager.nodes
        assert manager.nodes['test-node-1'].is_healthy == True
        
    @pytest.mark.asyncio
    async def test_heartbeat_handling(self, manager):
        """Test heartbeat updates node status"""
        # Register node first
        await manager.register_node({
            'node_id': 'test-node-2',
            'host': '192.168.1.101',
            'node_type': 'gpu',
            'status': {'memory_available_gb': 10}
        })
        
        # Send heartbeat with updated status
        await manager.handle_heartbeat('test-node-2', {
            'memory_available_gb': 8,
            'cpu_percent': 75,
            'active_tasks': 2,
            'ollama_healthy': True
        })
        
        node = manager.nodes['test-node-2']
        assert node.memory_available_gb == 8
        assert node.cpu_percent == 75
        assert node.active_tasks == 2
        
    @pytest.mark.asyncio
    async def test_node_selection(self, manager):
        """Test node selection for model deployment"""
        # Register multiple nodes
        nodes = [
            {'node_id': 'gpu-1', 'node_type': 'gpu', 'host': '192.168.1.100'},
            {'node_id': 'cpu-1', 'node_type': 'cpu', 'host': '192.168.1.101'},
            {'node_id': 'cpu-2', 'node_type': 'cpu', 'host': '192.168.1.102'},
        ]
        
        for node in nodes:
            await manager.register_node({
                **node,
                'status': {
                    'memory_available_gb': 10,
                    'ollama_healthy': True,
                    'active_models': [],
                    'active_tasks': 0
                }
            })
        
        # Test GPU preference for code models
        selected = manager.select_node_for_model('codellama', prefer_gpu=True)
        assert selected.id == 'gpu-1'
        
        # Test CPU selection when GPU not preferred
        selected = manager.select_node_for_model('tinyllama', prefer_gpu=False)
        assert selected.type == NodeType.CPU
        
    @pytest.mark.asyncio
    async def test_stale_node_detection(self, manager):
        """Test detection of stale nodes"""
        # Register node
        await manager.register_node({
            'node_id': 'stale-node',
            'host': '192.168.1.103',
            'node_type': 'cpu',
            'status': {'ollama_healthy': True}
        })
        
        # Simulate time passing without heartbeat
        from datetime import timedelta
        node = manager.nodes['stale-node']
        node.last_heartbeat = datetime.now() - timedelta(minutes=3)
        
        # Check health should mark as unhealthy
        with patch.object(manager, '_check_node_agent_health', return_value=False):
            await manager.health_check_loop()
            
        assert node.is_healthy == False
        
    @pytest.mark.asyncio
    async def test_task_distribution(self, manager):
        """Test distributing tasks across nodes"""
        # Register nodes
        for i in range(3):
            await manager.register_node({
                'node_id': f'worker-{i}',
                'host': f'192.168.1.{100+i}',
                'node_type': 'cpu',
                'status': {
                    'memory_available_gb': 8,
                    'ollama_healthy': True,
                    'active_models': [],
                    'active_tasks': 0
                }
            })
        
        # Mock execute_distributed
        with patch.object(manager, '_execute_distributed', new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = [
                {'model': 'tinyllama', 'response': 'test1'},
                {'model': 'phi', 'response': 'test2'}
            ]
            
            task = {'prompt': 'Test task', 'temperature': 0.7}
            models = ['tinyllama', 'phi']
            
            results = await manager.distribute_task(task, models)
            
            assert len(results) == 2
            assert results[0]['response'] == 'test1'
            
            # Check that models were assigned to nodes
            mock_exec.assert_called_once()
            
    @pytest.mark.asyncio
    async def test_cluster_stats(self, manager):
        """Test cluster statistics gathering"""
        # Register mixed node types
        await manager.register_node({
            'node_id': 'gpu-main',
            'host': '192.168.1.100',
            'node_type': 'gpu',
            'status': {'ollama_healthy': True, 'active_models': ['llama2']}
        })
        
        await manager.register_node({
            'node_id': 'cpu-worker',
            'host': '192.168.1.101', 
            'node_type': 'cpu',
            'status': {'ollama_healthy': False, 'active_models': []}
        })
        
        stats = manager.get_cluster_stats()
        
        assert stats['total_nodes'] == 2
        assert stats['healthy_nodes'] == 1
        assert stats['gpu_nodes'] == 1
        assert stats['cpu_nodes'] == 1
        assert stats['active_models'] == 1


class TestNodeAgent:
    """Test node agent functionality"""
    
    @pytest.fixture
    async def agent(self):
        """Create a test node agent"""
        config = NodeConfig(
            node_id='test-agent',
            node_type='cpu',
            ollama_host='http://localhost:11434',
            coordinator_host='http://localhost:8001',
            port=8002
        )
        return NodeAgent(config)
    
    @pytest.mark.asyncio
    async def test_node_status(self, agent):
        """Test getting node status"""
        with patch('psutil.cpu_percent', return_value=50.0), \
             patch('psutil.cpu_count', return_value=8), \
             patch('psutil.virtual_memory', return_value=Mock(
                 total=16*1024**3,
                 available=8*1024**3,
                 percent=50
             )), \
             patch('psutil.disk_usage', return_value=Mock(free=100*1024**3)), \
             patch.object(agent, 'check_ollama', new_callable=AsyncMock, return_value=True):
            
            status = await agent.get_node_status()
            
            assert status.node_id == 'test-agent'
            assert status.node_type == 'cpu'
            assert status.cpu_count == 8
            assert status.cpu_percent == 50.0
            assert status.memory_total_gb == pytest.approx(16, 0.1)
            assert status.memory_available_gb == pytest.approx(8, 0.1)
            assert status.ollama_healthy == True
            
    @pytest.mark.asyncio
    async def test_ollama_check(self, agent):
        """Test checking Ollama health"""
        with patch('httpx.AsyncClient') as mock_client:
            # Simulate healthy Ollama
            mock_response = Mock(status_code=200)
            mock_client.return_value.__aenter__.return_value.get.return_value = mock_response
            
            healthy = await agent.check_ollama()
            assert healthy == True
            
            # Simulate unhealthy Ollama
            mock_client.return_value.__aenter__.return_value.get.side_effect = Exception("Connection failed")
            healthy = await agent.check_ollama()
            assert healthy == False
            
    @pytest.mark.asyncio
    async def test_task_execution(self, agent):
        """Test executing a task"""
        task = TaskRequest(
            task_id='test-123',
            model='tinyllama',
            prompt='Hello world',
            temperature=0.7,
            max_tokens=100,
            stream=False
        )
        
        # Mock model availability
        agent.loaded_models = {'tinyllama'}
        
        with patch('httpx.AsyncClient') as mock_client:
            # Mock successful Ollama response
            mock_response = Mock(
                status_code=200,
                json=Mock(return_value={'response': 'Generated text'})
            )
            mock_client.return_value.__aenter__.return_value.post.return_value = mock_response
            
            result = await agent.execute_task(task)
            
            assert result['task_id'] == 'test-123'
            assert result['model'] == 'tinyllama'
            assert result['response'] == 'Generated text'
            assert 'elapsed_time' in result
            
    @pytest.mark.asyncio
    async def test_model_pulling(self, agent):
        """Test pulling a model"""
        with patch('asyncio.create_subprocess_exec', new_callable=AsyncMock) as mock_proc:
            # Mock successful pull
            mock_process = AsyncMock()
            mock_process.communicate.return_value = (b'Success', b'')
            mock_process.returncode = 0
            mock_proc.return_value = mock_process
            
            success = await agent.pull_model('tinyllama')
            assert success == True
            
            # Mock failed pull
            mock_process.returncode = 1
            mock_process.communicate.return_value = (b'', b'Error pulling model')
            
            success = await agent.pull_model('invalid-model')
            assert success == False
            
    @pytest.mark.asyncio
    async def test_capacity_limits(self, agent):
        """Test node capacity limits"""
        agent.config.max_concurrent_tasks = 2
        
        # Fill up task slots
        agent.active_tasks = {
            'task-1': {'started': datetime.now(), 'model': 'tinyllama'},
            'task-2': {'started': datetime.now(), 'model': 'phi'}
        }
        
        # Try to execute another task - should fail
        task = TaskRequest(
            task_id='task-3',
            model='gemma',
            prompt='Test',
            temperature=0.7
        )
        
        with pytest.raises(Exception) as exc_info:
            await agent.execute_task(task)
        assert "capacity" in str(exc_info.value).lower()
        
    @pytest.mark.asyncio
    async def test_coordinator_registration(self, agent):
        """Test registering with coordinator"""
        with patch.object(agent, 'get_node_status', new_callable=AsyncMock) as mock_status, \
             patch.object(agent.coordinator_client, 'post', new_callable=AsyncMock) as mock_post:
            
            mock_status.return_value = Mock(
                dict=Mock(return_value={'node_id': 'test', 'cpu_count': 8})
            )
            mock_post.return_value = Mock(status_code=200)
            
            await agent.register_with_coordinator()
            
            # Verify registration call was made
            mock_post.assert_called_once()
            call_args = mock_post.call_args
            assert '/nodes/register' in call_args[0][0]


@pytest.mark.asyncio
async def test_end_to_end_workflow():
    """Test complete workflow from registration to task execution"""
    
    # Create manager and agent
    manager = DistributedManager()
    config = NodeConfig(
        node_id='e2e-test',
        node_type='cpu',
        ollama_host='http://localhost:11434',
        coordinator_host='http://localhost:8001'
    )
    agent = NodeAgent(config)
    
    # Register node
    node_data = {
        'node_id': 'e2e-test',
        'host': 'localhost',
        'port': 8002,
        'node_type': 'cpu',
        'status': {
            'cpu_count': 4,
            'memory_total_gb': 8,
            'memory_available_gb': 6,
            'cpu_percent': 20,
            'ollama_healthy': True,
            'active_models': ['tinyllama'],
            'active_tasks': 0
        }
    }
    
    success = await manager.register_node(node_data)
    assert success == True
    
    # Select node for model
    selected = manager.select_node_for_model('tinyllama', prefer_gpu=False)
    assert selected is not None
    assert selected.id == 'e2e-test'
    
    # Simulate task execution
    with patch.object(manager, '_execute_distributed', new_callable=AsyncMock) as mock_exec:
        mock_exec.return_value = [
            {
                'model': 'tinyllama',
                'node': 'e2e-test',
                'response': 'Test successful',
                'elapsed_time': 1.5
            }
        ]
        
        task = {'prompt': 'End to end test', 'temperature': 0.5}
        results = await manager.distribute_task(task, ['tinyllama'])
        
        assert len(results) == 1
        assert results[0]['response'] == 'Test successful'
        assert results[0]['node'] == 'e2e-test'


if __name__ == "__main__":
    # Run tests
    print("🧪 Running Distributed System Tests...")
    pytest.main([__file__, '-v', '--asyncio-mode=auto'])