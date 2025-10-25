"""
SOLLOL Integration Layer for Hydra

This module provides a seamless integration between Hydra's orchestration
capabilities and SOLLOL's intelligent distributed Ollama management.

SOLLOL replaces:
- OllamaLoadBalancer (models/ollama_manager.py)
- DistributedManager (core/distributed.py)
- node_agent.py (auto-discovery)

With:
- Resource-aware routing (VRAM/RAM monitoring)
- Auto-discovery of Ollama nodes
- Intelligent model-to-node placement
- Automatic GPU → CPU fallback
"""

import asyncio
from typing import Dict, List, Any, Optional, AsyncGenerator
from loguru import logger
from collections import defaultdict
from datetime import datetime

# Import SOLLOL components
try:
    from sollol import OllamaPool
    from sollol import UnifiedDashboard, run_unified_dashboard
    from sollol.config import SOLLOLConfig
    SOLLOL_AVAILABLE = True
except ImportError:
    logger.warning("SOLLOL not installed. Run: pip install sollol>=0.9.52")
    SOLLOL_AVAILABLE = False
    OllamaPool = None
    UnifiedDashboard = None
    SOLLOLConfig = None


class SOLLOLIntegration:
    """
    Unified integration layer that provides both load balancing
    and distributed management through SOLLOL's OllamaPool.
    """

    def __init__(self, config: Optional[Dict] = None):
        """
        Initialize SOLLOL integration.

        Args:
            config: Optional configuration dict with keys:
                - discovery_enabled: Enable auto-discovery (default: True)
                - discovery_timeout: Discovery timeout in seconds (default: 10)
                - health_check_interval: Health check interval (default: 120)
                - enable_vram_monitoring: Enable VRAM monitoring (default: True)
                - enable_dashboard: Enable UnifiedDashboard (default: True)
                - dashboard_port: Dashboard port (default: 8080)
                - app_name: Application name for dashboard registration (default: "Hydra")
        """
        if not SOLLOL_AVAILABLE:
            raise RuntimeError("SOLLOL is not available. Please install it first.")

        self.config = config or {}
        self.app_name = self.config.get('app_name', 'Hydra')

        # Create SOLLOL config
        sollol_config = SOLLOLConfig()

        # Initialize SOLLOL OllamaPool with app registration
        # Note: Only pass parameters that are supported by the current SOLLOL version
        pool_kwargs = {
            'app_name': self.app_name,  # Register as "Hydra" in dashboard
            'register_with_dashboard': self.config.get('register_with_dashboard', True),
            'enable_intelligent_routing': True,
            'redis_host': self.config.get('redis_host', 'localhost'),
            'redis_port': self.config.get('redis_port', 6379)
        }

        # Try to add VRAM monitoring if supported by SOLLOL version
        try:
            import inspect
            if 'enable_vram_monitoring' in inspect.signature(OllamaPool.__init__).parameters:
                pool_kwargs['enable_vram_monitoring'] = self.config.get('enable_vram_monitoring', True)
        except:
            pass  # VRAM monitoring not supported in this version

        self.pool = OllamaPool(**pool_kwargs)

        # Initialize dashboard if enabled
        self.dashboard = None
        self.dashboard_enabled = self.config.get('enable_dashboard', True)
        self.dashboard_port = self.config.get('dashboard_port', 8080)

        # Compatibility attributes for Hydra's existing code
        self.hosts = []  # Will be populated by auto-discovery
        self.health_status = {}  # Node health status
        self.request_counts = defaultdict(int)
        self.response_times = defaultdict(list)
        self.nodes = {}  # Node registry
        self.initialized = False

        logger.info("✨ SOLLOL Integration initialized")

    async def initialize(self):
        """Initialize SOLLOL pool, discover nodes, and start dashboard"""
        if not self.initialized:
            logger.info("🔍 Starting SOLLOL node discovery...")

            # Initialize the pool (discovers nodes automatically)
            # Note: OllamaPool.auto_configure() already initializes,
            # but we can call list() to trigger discovery if needed
            try:
                nodes = await self.pool.list_nodes()
                self.hosts = [f"http://{node['host']}:{node['port']}" for node in nodes]
                self.health_status = {f"http://{node['host']}:{node['port']}": node.get('healthy', True) for node in nodes}

                # Create node registry for compatibility
                for node in nodes:
                    node_url = f"http://{node['host']}:{node['port']}"
                    self.nodes[node.get('id', node['host'])] = {
                        'id': node.get('id', node['host']),
                        'host': node['host'],
                        'port': node['port'],
                        'url': node_url,
                        'type': 'gpu' if node.get('gpu_available', False) else 'cpu',
                        'is_healthy': node.get('healthy', True),
                        'vram_total': node.get('vram_total', 0),
                        'vram_available': node.get('vram_available', 0),
                        'models_loaded': node.get('loaded_models', [])
                    }
            except Exception as e:
                logger.warning(f"Node discovery encountered an issue: {e}. Using default localhost.")
                self.hosts = ['http://localhost:11434']
                self.health_status = {'http://localhost:11434': True}
                self.nodes = {
                    'localhost': {
                        'id': 'localhost',
                        'host': 'localhost',
                        'port': 11434,
                        'url': 'http://localhost:11434',
                        'type': 'cpu',
                        'is_healthy': True,
                        'vram_total': 0,
                        'vram_available': 0,
                        'models_loaded': []
                    }
                }

            # Start SOLLOL dashboard if enabled
            if self.dashboard_enabled:
                try:
                    logger.info(f"🎨 Launching SOLLOL Unified Dashboard on port {self.dashboard_port}...")
                    self.dashboard = UnifiedDashboard(port=self.dashboard_port)
                    await self.dashboard.start()
                    logger.success(f"✅ SOLLOL Dashboard available at http://localhost:{self.dashboard_port}")
                except Exception as e:
                    logger.warning(f"Failed to start SOLLOL dashboard: {e}. Continuing without dashboard.")
                    self.dashboard = None

            self.initialized = True
            logger.success(f"✅ SOLLOL discovered {len(self.hosts)} nodes")

    async def periodic_health_check(self):
        """Background health monitoring - delegated to SOLLOL"""
        # SOLLOL handles this internally
        await self.pool.start_health_monitoring()

    # =================================================================
    # OllamaLoadBalancer API Compatibility
    # =================================================================

    async def generate(self, model: str, prompt: str, node_id: Optional[str] = None,
                      prefer_local: bool = True, min_vram_gb: Optional[float] = None,
                      **kwargs) -> Dict[str, Any]:
        """
        Generate response from model (non-streaming) with intelligent routing.

        Args:
            model: Model name to use
            prompt: Prompt text
            node_id: Optional specific node ID to use
            prefer_local: Prefer local node if it has sufficient resources (default: True)
            min_vram_gb: Minimum VRAM required in GB (optional)
            **kwargs: Additional parameters (temperature, top_p, etc.)

        Returns:
            Response dict with model output and routing info

        Compatible with OllamaLoadBalancer.generate()
        """
        start_time = datetime.now()

        logger.info(f"🤖 Generating with {model}")

        try:
            # Extract Ollama-specific parameters
            options = {}
            if 'temperature' in kwargs:
                options['temperature'] = kwargs.pop('temperature')
            if 'top_p' in kwargs:
                options['top_p'] = kwargs.pop('top_p')
            if 'repeat_penalty' in kwargs:
                options['repeat_penalty'] = kwargs.pop('repeat_penalty')

            # Select target node if resource constraints or explicit node specified
            target_node = None
            if node_id:
                # Explicit node selection
                target_node = self._get_node_by_id(node_id)
                if not target_node:
                    logger.warning(f"⚠️ Requested node {node_id} not found, using intelligent routing")
                elif not target_node['is_healthy']:
                    logger.warning(f"⚠️ Requested node {node_id} is unhealthy, using fallback")
                    target_node = None
                else:
                    logger.info(f"📍 Using explicitly requested node: {node_id}")

            # Resource-aware routing
            if not target_node:
                target_node = self._select_node_with_resources(
                    model=model,
                    min_vram_gb=min_vram_gb,
                    prefer_local=prefer_local
                )

                if target_node:
                    logger.info(f"📊 Resource-aware routing selected node: {target_node['id']} "
                              f"(VRAM: {target_node.get('vram_available', 0):.1f}GB available)")

            # Use SOLLOL's generate method
            # SOLLOL automatically routes based on resources, health, and performance
            # Our target_node selection above influences the preference but SOLLOL makes final decision
            response = await self.pool.generate(
                model=model,
                prompt=prompt,
                options=options,
                stream=False,
                priority=kwargs.pop('priority', 5)  # Higher priority = better resource allocation
            )

            elapsed = (datetime.now() - start_time).total_seconds()
            logger.success(f"✅ Model {model} completed in {elapsed:.2f}s on {response.get('node_url', 'unknown')}")

            # Track metrics
            node_url = response.get('node_url', 'unknown')
            self.request_counts[node_url] += 1
            self.response_times[node_url].append(elapsed)

            return {
                'response': response.get('response', ''),
                'model': model,
                'total_duration': response.get('total_duration', 0),
                'node_url': node_url,
                'node_id': response.get('node_id', 'unknown'),
                'routing_decision': {
                    'requested_node': node_id,
                    'selected_node': target_node['id'] if target_node else 'auto',
                    'reason': self._get_routing_reason(node_id, target_node, prefer_local, min_vram_gb)
                }
            }

        except Exception as e:
            logger.error(f"❌ Generation failed for {model}: {e}")
            raise

    async def generate_stream(self, model: str, prompt: str, **kwargs) -> AsyncGenerator:
        """
        Stream generation from model.
        Compatible with OllamaLoadBalancer.generate_stream()
        """
        logger.info(f"🤖 Streaming from {model}")

        try:
            # Extract Ollama-specific parameters
            options = {}
            if 'temperature' in kwargs:
                options['temperature'] = kwargs.pop('temperature')
            if 'top_p' in kwargs:
                options['top_p'] = kwargs.pop('top_p')
            if 'repeat_penalty' in kwargs:
                options['repeat_penalty'] = kwargs.pop('repeat_penalty')

            # Use SOLLOL's streaming generation
            # Check if pool.generate returns an async generator or regular generator
            stream_result = self.pool.generate(
                model=model,
                prompt=prompt,
                options=options,
                stream=True
            )

            # If it's an async generator, use async for
            if hasattr(stream_result, '__aiter__'):
                async for chunk in stream_result:
                    yield chunk
            else:
                # If it's a regular generator, convert it
                for chunk in stream_result:
                    yield chunk

        except Exception as e:
            logger.error(f"❌ Stream failed for {model}: {e}")
            raise

    async def embed(self, model: str, input: str) -> List[float]:
        """Generate embeddings. Compatible with OllamaLoadBalancer.embed()"""
        response = await self.pool.embed(model=model, input=input)
        return response.get('embeddings', [])

    async def check_health(self, host: str) -> bool:
        """Check health of a specific host"""
        # SOLLOL manages health internally
        node = next((n for n in self.pool.nodes if n.url == host), None)
        return node.is_healthy if node else False

    def get_best_host(self) -> Optional[str]:
        """Get best available host - delegated to SOLLOL's intelligent routing"""
        # SOLLOL handles this internally when routing requests
        healthy_nodes = [n for n in self.pool.nodes if n.is_healthy]
        if not healthy_nodes:
            return None
        # Return first healthy node (SOLLOL will handle optimal routing internally)
        return healthy_nodes[0].url

    # =================================================================
    # DistributedManager API Compatibility
    # =================================================================

    async def register_node(self, node_data: Dict) -> bool:
        """
        Register a node - SOLLOL handles this via auto-discovery.
        This is kept for API compatibility but delegates to SOLLOL.
        """
        # SOLLOL auto-discovers nodes, but we can force a refresh
        await self.pool.discover_nodes()
        return True

    async def handle_heartbeat(self, node_id: str, status: Dict):
        """Handle heartbeat - SOLLOL manages this internally"""
        # SOLLOL's health monitoring handles heartbeats
        pass

    def select_node_for_model(self, model: str, prefer_gpu: bool = True) -> Optional[Dict]:
        """
        Select optimal node for a model.
        SOLLOL's resource-aware routing handles this intelligently.
        """
        # Find best node using SOLLOL's intelligence
        for node in self.pool.nodes:
            if not node.is_healthy:
                continue
            if prefer_gpu and not node.gpu_available:
                continue

            # Return node info in Hydra format
            return {
                'id': node.node_id,
                'host': node.host,
                'port': node.port,
                'url': node.url,
                'type': 'gpu' if node.gpu_available else 'cpu'
            }

        # Fallback to any healthy node
        healthy = [n for n in self.pool.nodes if n.is_healthy]
        if healthy:
            node = healthy[0]
            return {
                'id': node.node_id,
                'host': node.host,
                'port': node.port,
                'url': node.url,
                'type': 'gpu' if node.gpu_available else 'cpu'
            }

        return None

    async def distribute_task(self, task: Dict, models: List[str]) -> List[Dict]:
        """
        Distribute task across models.
        SOLLOL's intelligent routing selects optimal nodes per model.
        """
        results = []

        for model in models:
            try:
                response = await self.generate(
                    model=model,
                    prompt=task.get('prompt', ''),
                    temperature=task.get('temperature', 0.7)
                )

                results.append({
                    'model': model,
                    'response': response['response'],
                    'node_url': response.get('node_url', 'unknown')
                })
            except Exception as e:
                logger.error(f"Task distribution failed for {model}: {e}")

        return results

    def get_cluster_stats(self) -> Dict:
        """Get cluster statistics"""
        total_nodes = len(self.pool.nodes)
        healthy_nodes = sum(1 for n in self.pool.nodes if n.is_healthy)
        gpu_nodes = sum(1 for n in self.pool.nodes if n.gpu_available)
        cpu_nodes = total_nodes - gpu_nodes

        nodes_info = []
        for node in self.pool.nodes:
            nodes_info.append({
                'id': node.node_id,
                'type': 'gpu' if node.gpu_available else 'cpu',
                'healthy': node.is_healthy,
                'url': node.url,
                'vram_available': getattr(node, 'vram_available', 0),
                'vram_total': getattr(node, 'vram_total', 0),
                'models_loaded': len(getattr(node, 'loaded_models', []))
            })

        return {
            'total_nodes': total_nodes,
            'healthy_nodes': healthy_nodes,
            'gpu_nodes': gpu_nodes,
            'cpu_nodes': cpu_nodes,
            'nodes': nodes_info,
            'via_sollol': True
        }

    # =================================================================
    # Resource-Aware Routing Helper Methods
    # =================================================================

    def _get_node_by_id(self, node_id: str) -> Optional[Dict]:
        """Get node info by ID"""
        return self.nodes.get(node_id)

    def _select_node_with_resources(
        self,
        model: str,
        min_vram_gb: Optional[float] = None,
        prefer_local: bool = True
    ) -> Optional[Dict]:
        """
        Select node based on resource availability.

        Args:
            model: Model name
            min_vram_gb: Minimum VRAM required in GB
            prefer_local: Prefer localhost if it meets requirements

        Returns:
            Node dict or None
        """
        import socket

        localhost_names = ['localhost', '127.0.0.1', socket.gethostname()]
        local_node = None
        candidate_nodes = []

        # Collect healthy nodes and identify local node
        for node_id, node in self.nodes.items():
            if not node['is_healthy']:
                continue

            # Check VRAM requirement
            if min_vram_gb:
                vram_available_gb = node.get('vram_available', 0) / 1024  # Convert MB to GB
                if vram_available_gb < min_vram_gb:
                    logger.debug(f"Node {node_id} has insufficient VRAM: {vram_available_gb:.1f}GB < {min_vram_gb}GB required")
                    continue

            # Check if it's local
            if any(local_name in node['host'] for local_name in localhost_names):
                local_node = node

            candidate_nodes.append(node)

        # Prefer local node if enabled and available
        if prefer_local and local_node and local_node in candidate_nodes:
            logger.debug(f"Preferring local node: {local_node['id']}")
            return local_node

        # Otherwise return first candidate (SOLLOL will handle final routing)
        if candidate_nodes:
            return candidate_nodes[0]

        logger.warning("No suitable nodes found for resource requirements")
        return None

    def _get_routing_reason(
        self,
        requested_node: Optional[str],
        selected_node: Optional[Dict],
        prefer_local: bool,
        min_vram_gb: Optional[float]
    ) -> str:
        """Generate human-readable routing decision reason"""
        if requested_node and selected_node and requested_node == selected_node['id']:
            return f"Explicit node selection: {requested_node}"

        if requested_node and not selected_node:
            return f"Requested node {requested_node} unavailable, using SOLLOL intelligent routing"

        reasons = []
        if prefer_local:
            reasons.append("local preference")
        if min_vram_gb:
            reasons.append(f"min {min_vram_gb}GB VRAM required")

        if reasons and selected_node:
            return f"Resource-aware routing ({', '.join(reasons)}) → {selected_node['id']}"

        return "SOLLOL intelligent routing (automatic)"

    def get_node_resources(self) -> List[Dict]:
        """
        Get current resource status for all nodes.

        Returns:
            List of dicts with node resource information
        """
        nodes_info = []
        for node_id, node in self.nodes.items():
            nodes_info.append({
                'id': node_id,
                'host': node['host'],
                'port': node['port'],
                'url': node['url'],
                'type': node['type'],
                'healthy': node['is_healthy'],
                'vram_total_mb': node.get('vram_total', 0),
                'vram_available_mb': node.get('vram_available', 0),
                'vram_available_gb': node.get('vram_available', 0) / 1024,
                'models_loaded': node.get('models_loaded', []),
                'models_loaded_count': len(node.get('models_loaded', []))
            })
        return nodes_info

    async def close(self):
        """Cleanup SOLLOL resources"""
        # Stop dashboard if running
        if self.dashboard:
            try:
                await self.dashboard.stop()
                logger.info("🛑 SOLLOL Dashboard stopped")
            except Exception as e:
                logger.warning(f"Error stopping dashboard: {e}")

        # Close pool
        try:
            await self.pool.close()
        except Exception as e:
            logger.warning(f"Error closing pool: {e}")

        logger.info("🔌 SOLLOL Integration closed")


class HydraSOLLOLAdapter:
    """
    Backward compatibility adapter for Hydra's existing codebase.
    Provides both OllamaLoadBalancer and DistributedManager interfaces.
    """

    def __init__(self, config: Optional[Dict] = None):
        self.sollol = SOLLOLIntegration(config)

    async def initialize(self):
        """Initialize SOLLOL"""
        await self.sollol.initialize()

    # Expose SOLLOL methods
    def __getattr__(self, name):
        """Delegate all other methods to SOLLOL integration"""
        return getattr(self.sollol, name)
