# Resource-Aware Routing in Hydra

## Overview

Hydra leverages **SOLLOL's intelligent resource-aware routing** to automatically distribute model inference across nodes based on:

1. **Real-time VRAM availability** (GPU monitoring)
2. **Node health status**
3. **Model loading status**
4. **Historical performance metrics**
5. **Request priority**

When your host node doesn't have enough resources, requests are **automatically routed** to nodes that can handle them.

## How It Works

### SOLLOL's Built-in Intelligence

SOLLOL monitors all nodes every 30 seconds and tracks:
- Free VRAM (with 200MB safety buffer)
- Loaded models per node
- Node response times
- GPU vs CPU capabilities
- Network latency

When you make a request, SOLLOL:
1. Analyzes resource requirements
2. Checks which nodes have the model loaded
3. Evaluates available VRAM
4. Routes to the optimal node
5. Falls back if the selected node fails

### Hydra's Integration Layer

Hydra adds these capabilities on top of SOLLOL:

```python
# Explicit node selection
response = await sollol.generate(
    model="llama3.2:70b",
    prompt="Your prompt here",
    node_id="gpu-node-1"  # Request specific node
)

# Resource constraints
response = await sollol.generate(
    model="llama3.2:70b",
    prompt="Your prompt here",
    min_vram_gb=32.0,  # Require at least 32GB VRAM
    prefer_local=False  # Don't prefer localhost
)

# Priority-based routing
response = await sollol.generate(
    model="llama3.2:70b",
    prompt="Your prompt here",
    priority=10  # 1-10 scale, higher = better resources
)
```

## Usage Examples

### Example 1: Automatic Routing (Default)

```python
from core.sollol_integration import SOLLOLIntegration

# Initialize
sollol = SOLLOLIntegration()
await sollol.initialize()

# Let SOLLOL decide everything
response = await sollol.generate(
    model="qwen3:14b",
    prompt="Write a Python function to sort a list",
    temperature=0.7
)

print(f"Response from: {response['node_url']}")
print(f"Routing: {response['routing_decision']['reason']}")
```

**Result**: SOLLOL automatically routes to the best available node.

### Example 2: Resource-Constrained Routing

```python
# Request a large model with specific VRAM requirements
response = await sollol.generate(
    model="llama3.1:70b",
    prompt="Analyze this code...",
    min_vram_gb=40.0,  # Need 40GB+ VRAM
    prefer_local=True   # Try localhost first
)

print(f"Selected node: {response['node_id']}")
print(f"Reason: {response['routing_decision']['reason']}")
```

**What happens**:
1. Hydra checks localhost VRAM
2. If localhost has <40GB available → routes to another node
3. If localhost has ≥40GB available → uses localhost
4. Falls back to SOLLOL's intelligent routing if no nodes qualify

### Example 3: Explicit Node Selection

```python
# Get available nodes
nodes = sollol.get_node_resources()
for node in nodes:
    print(f"{node['id']}: {node['vram_available_gb']:.1f}GB VRAM available")

# Select specific node
response = await sollol.generate(
    model="qwen3:14b",
    prompt="Your prompt",
    node_id="10.9.66.250"  # Explicit node
)
```

**What happens**:
1. Hydra attempts to use the requested node
2. If node is unhealthy or unavailable → falls back to SOLLOL routing
3. Logs show the routing decision

### Example 4: Multi-Model Distributed Processing

```python
# Distribute different models across nodes
tasks = [
    {"model": "qwen3:1.7b", "prompt": "Quick task 1"},
    {"model": "qwen3:14b", "prompt": "Complex task 2"},
    {"model": "llama3.1:70b", "prompt": "Heavy task 3"}
]

results = await sollol.distribute_task(
    task={"prompts": [t["prompt"] for t in tasks]},
    models=[t["model"] for t in tasks]
)

for result in results:
    print(f"{result['model']} → {result['node_url']}")
```

**What happens**:
- Small models (1.7b) → CPU nodes or any available node
- Medium models (14b) → Nodes with moderate VRAM
- Large models (70b) → Nodes with high VRAM
- SOLLOL automatically balances the load

### Example 5: Priority-Based Routing

```python
# High-priority urgent request
urgent_response = await sollol.generate(
    model="qwen3:14b",
    prompt="Urgent request",
    priority=10  # Highest priority
)

# Low-priority background task
background_response = await sollol.generate(
    model="qwen3:14b",
    prompt="Background task",
    priority=1  # Lowest priority
)
```

**What happens**:
- Priority 10 → Gets best available resources
- Priority 1 → May wait or use less optimal node
- SOLLOL queues and schedules based on priority

## Monitoring Resources

### View Current Node Status

```python
# Get real-time resource information
nodes = sollol.get_node_resources()

for node in nodes:
    print(f"\n📍 Node: {node['id']}")
    print(f"   Status: {'✅ Healthy' if node['healthy'] else '❌ Unhealthy'}")
    print(f"   Type: {node['type'].upper()}")
    print(f"   VRAM: {node['vram_available_gb']:.1f}GB / {node['vram_total_mb']/1024:.1f}GB")
    print(f"   Models loaded: {node['models_loaded_count']}")
    if node['models_loaded']:
        print(f"   - {', '.join(node['models_loaded'][:3])}")
```

### Check Cluster Statistics

```python
stats = sollol.get_cluster_stats()

print(f"Total nodes: {stats['total_nodes']}")
print(f"Healthy nodes: {stats['healthy_nodes']}")
print(f"GPU nodes: {stats['gpu_nodes']}")
print(f"CPU nodes: {stats['cpu_nodes']}")
```

### SOLLOL Dashboard

Access real-time monitoring at: `http://localhost:8080`

The dashboard shows:
- Node health and status
- VRAM usage per node
- Request routing decisions
- Performance metrics
- Model loading status

## Configuration

### Environment Variables

```bash
# .env
SOLLOL_DISCOVERY_ENABLED=true
SOLLOL_DISCOVERY_TIMEOUT=10
SOLLOL_VRAM_MONITORING=true
SOLLOL_DASHBOARD_ENABLED=true
SOLLOL_DASHBOARD_PORT=8080
```

### Python Configuration

```python
config = {
    'discovery_enabled': True,
    'enable_vram_monitoring': True,
    'enable_dashboard': True,
    'dashboard_port': 8080,
    'health_check_interval': 120  # seconds
}

sollol = SOLLOLIntegration(config=config)
```

## Routing Decision Flow

```
Request arrives
     |
     v
[Hydra Integration Layer]
     |
     ├─> Explicit node requested?
     │   ├─> Yes → Check if healthy
     │   │   ├─> Healthy → Use it
     │   │   └─> Unhealthy → Continue
     │   └─> No → Continue
     |
     ├─> Resource constraints specified?
     │   ├─> Yes → Filter nodes by VRAM/requirements
     │   └─> No → Use all nodes
     |
     ├─> Prefer local?
     │   ├─> Yes & localhost qualifies → Prefer localhost
     │   └─> No or doesn't qualify → Continue
     |
     v
[SOLLOL Intelligent Routing]
     |
     ├─> Check node health status
     ├─> Check VRAM availability
     ├─> Check model loading status
     ├─> Check historical performance
     ├─> Apply priority weighting
     |
     v
Select optimal node
     |
     v
Execute request
     |
     ├─> Success → Return response
     └─> Failure → Try next best node
```

## Error Handling

### Insufficient Resources

```python
try:
    response = await sollol.generate(
        model="llama3.1:70b",
        prompt="Your prompt",
        min_vram_gb=100.0  # Impossible requirement
    )
except Exception as e:
    print(f"No nodes with sufficient resources: {e}")
    # Fallback: try without constraints
    response = await sollol.generate(
        model="llama3.2:3b",  # Smaller model
        prompt="Your prompt"
    )
```

### Node Failure During Request

SOLLOL automatically handles this:
1. Detects node failure
2. Marks node as unhealthy
3. Retries on next best node
4. Updates routing decisions

### All Nodes Unavailable

```python
try:
    response = await sollol.generate(model="qwen3:14b", prompt="test")
except Exception as e:
    print(f"All nodes unavailable: {e}")
    # Check cluster status
    stats = sollol.get_cluster_stats()
    print(f"Healthy nodes: {stats['healthy_nodes']}/{stats['total_nodes']}")
```

## Best Practices

### 1. Use Priority for Critical Requests

```python
# Production user request
await sollol.generate(model="qwen3:14b", prompt=user_query, priority=9)

# Background analysis
await sollol.generate(model="qwen3:14b", prompt=analysis, priority=3)
```

### 2. Specify Resource Requirements for Large Models

```python
# 70B models typically need 40GB+ VRAM
await sollol.generate(
    model="llama3.1:70b",
    prompt=prompt,
    min_vram_gb=40.0  # Explicit requirement
)
```

### 3. Let SOLLOL Handle Routing by Default

```python
# ✅ Good: Let SOLLOL decide
response = await sollol.generate(model="qwen3:14b", prompt=prompt)

# ⚠️ Use sparingly: Explicit node selection
response = await sollol.generate(model="qwen3:14b", prompt=prompt, node_id="specific-node")
```

### 4. Monitor Resource Usage

```python
# Periodic resource checks
async def monitor_resources():
    while True:
        nodes = sollol.get_node_resources()
        for node in nodes:
            if node['vram_available_gb'] < 2.0:  # Low VRAM warning
                logger.warning(f"Node {node['id']} low on VRAM: {node['vram_available_gb']:.1f}GB")
        await asyncio.sleep(60)
```

### 5. Use Streaming for Long Responses

```python
# Streaming reduces memory pressure
async for chunk in sollol.generate_stream(
    model="llama3.1:70b",
    prompt="Write a long story..."
):
    print(chunk.get('response', ''), end='')
```

## Troubleshooting

### Check Why a Node Wasn't Selected

```python
response = await sollol.generate(model="qwen3:14b", prompt="test")
print(response['routing_decision'])
# Output: {'requested_node': None, 'selected_node': 'auto', 'reason': 'SOLLOL intelligent routing (automatic)'}
```

### View VRAM Usage

```python
nodes = sollol.get_node_resources()
for node in nodes:
    vram_used = node['vram_total_mb'] - node['vram_available_mb']
    vram_percent = (vram_used / node['vram_total_mb'] * 100) if node['vram_total_mb'] > 0 else 0
    print(f"{node['id']}: {vram_percent:.1f}% VRAM used")
```

### Force Localhost for Testing

```python
response = await sollol.generate(
    model="qwen3:1.7b",
    prompt="test",
    node_id="localhost"
)
```

## Summary

- **SOLLOL handles all the intelligence** - VRAM monitoring, health checks, performance tracking
- **Hydra adds convenience layers** - explicit node selection, resource constraints, preference hints
- **Automatic fallback** - If your host node lacks resources, SOLLOL routes elsewhere
- **Real-time monitoring** - Dashboard and API provide full visibility
- **Priority system** - Control resource allocation for different request types

For most use cases, just call `generate()` and let SOLLOL's intelligence handle everything!
