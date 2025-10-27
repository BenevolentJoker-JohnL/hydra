# SOLLOL-Hydra Routing Modes Design

## Overview

SOLLOL-Hydra needs three distinct routing modes to handle different task requirements:

### 1. **FAST Mode** (Performance-First)
**Current default behavior**

**When to use:**
- User-facing interactive responses
- Real-time chat
- Time-sensitive tasks

**Routing logic:**
```python
Priority order:
1. GPU nodes with most VRAM available
2. Lowest current load
3. Prefer local node (network latency)
4. Fastest historical response times

Fallback: CPU only if all GPUs busy/failed
```

**Example:**
```python
response = await sollol.generate(
    model="qwen3:14b",
    prompt="Explain this code",
    routing_mode="FAST",  # Default
    priority=10  # Urgent
)
```

---

### 2. **RELIABLE Mode** (Stability-First)
**NEW - Optimize for success rate over speed**

**When to use:**
- Critical production tasks
- Long-running generation
- Tasks that can't afford to retry
- When debugging/analyzing complex code

**Routing logic:**
```python
Priority order:
1. Nodes with highest success rate (>98%)
2. Nodes with stable response times (low variance)
3. Nodes with longest uptime
4. GPU or CPU doesn't matter if both reliable

Track reliability metrics:
- Success rate (successful completions / total requests)
- Timeout rate
- Error rate
- Response time variance
```

**Example:**
```python
response = await sollol.generate(
    model="mixtral:8x7b",
    prompt="Generate production code for payment processing",
    routing_mode="RELIABLE",
    priority=8,
    min_success_rate=0.98  # Only use nodes with 98%+ success
)
```

---

### 3. **ASYNC Mode** (Resource-Efficient)
**NEW - Intentional CPU offloading for non-urgent tasks**

**When to use:**
- Background documentation generation
- Non-blocking code analysis
- Batch processing
- Test generation
- Pre-warming embeddings/caches

**Routing logic:**
```python
Priority order:
1. CPU nodes (intentionally free up GPU)
2. Nodes with lowest current load
3. Can queue if all busy
4. Remote nodes OK (no local preference)

CPU selection criteria:
- Model fits in CPU RAM
- Task doesn't require real-time response
- Downstream can handle async results
```

**Example:**
```python
# Fire and forget - results delivered via callback
task_id = await sollol.generate_async(
    model="qwen3:1.7b",
    prompt="Generate unit tests for all files in /src",
    routing_mode="ASYNC",
    priority=2,  # Low priority
    prefer_cpu=True,  # Intentionally use CPU
    callback=handle_test_results
)

# Or with await for result
result = await sollol.wait_for_task(task_id)
```

---

## Implementation Requirements

### 1. Node Reliability Tracking

```python
class NodeReliabilityTracker:
    """Track success rates and reliability metrics per node"""

    def __init__(self):
        self.node_stats = {
            # node_id: {
            #     'total_requests': 0,
            #     'successful': 0,
            #     'failed': 0,
            #     'timeouts': 0,
            #     'response_times': [],  # Last 100
            #     'success_rate': 1.0,
            #     'avg_response_time': 0,
            #     'response_time_variance': 0,
            #     'uptime_start': datetime
            # }
        }

    def record_request(self, node_id, success, response_time, error_type=None):
        """Record request outcome"""
        pass

    def get_success_rate(self, node_id) -> float:
        """Get success rate for node"""
        pass

    def get_most_reliable_nodes(self, min_success_rate=0.95) -> List[str]:
        """Get nodes sorted by reliability"""
        pass
```

### 2. Routing Mode Enum

```python
from enum import Enum

class RoutingMode(Enum):
    FAST = "fast"           # Performance-first (current default)
    RELIABLE = "reliable"   # Stability-first
    ASYNC = "async"         # Resource-efficient, can use CPU

class TaskPriority(Enum):
    URGENT = 10      # User waiting
    HIGH = 8         # Important but not blocking
    NORMAL = 5       # Default
    LOW = 2          # Background/batch
    DEFERRED = 0     # Run when resources available
```

### 3. Enhanced generate() Method

```python
async def generate(
    self,
    model: str,
    prompt: str,
    routing_mode: RoutingMode = RoutingMode.FAST,
    priority: int = 5,
    prefer_cpu: bool = False,  # For ASYNC mode
    min_success_rate: float = 0.0,  # For RELIABLE mode
    async_callback: Optional[Callable] = None,  # For ASYNC mode
    **kwargs
) -> Dict[str, Any]:
    """
    Generate with mode-aware routing.

    FAST mode: Optimize for speed (GPU-first, local, fastest nodes)
    RELIABLE mode: Optimize for success (proven stable nodes, track reliability)
    ASYNC mode: Optimize for resource efficiency (CPU OK, queue OK, non-blocking)
    """

    # Select node based on mode
    if routing_mode == RoutingMode.FAST:
        node = self._select_fastest_node(model, prefer_local=True)

    elif routing_mode == RoutingMode.RELIABLE:
        node = self._select_most_reliable_node(model, min_success_rate)

    elif routing_mode == RoutingMode.ASYNC:
        node = self._select_async_node(model, prefer_cpu=prefer_cpu)

    # Execute with tracking
    result = await self._execute_with_tracking(node, model, prompt, priority)

    return result
```

### 4. Mode-Specific Node Selection

```python
def _select_fastest_node(self, model, prefer_local=True):
    """Current behavior - GPU first, local preference"""
    # Existing logic
    pass

def _select_most_reliable_node(self, model, min_success_rate=0.95):
    """Select most reliable node even if slower"""
    candidates = []

    for node_id, node in self.nodes.items():
        if not node['is_healthy']:
            continue

        # Get reliability metrics
        success_rate = self.reliability_tracker.get_success_rate(node_id)
        if success_rate < min_success_rate:
            continue

        # Check if model fits
        if not self._model_fits_on_node(model, node):
            continue

        candidates.append({
            'node': node,
            'success_rate': success_rate,
            'response_variance': self.reliability_tracker.get_variance(node_id)
        })

    # Sort by success rate, then by low variance
    candidates.sort(key=lambda x: (x['success_rate'], -x['response_variance']), reverse=True)

    return candidates[0]['node'] if candidates else None

def _select_async_node(self, model, prefer_cpu=False):
    """Select node for async/background tasks - CPU is OK"""
    candidates = []

    for node_id, node in self.nodes.items():
        if not node['is_healthy']:
            continue

        # For async mode, CPU nodes are preferred (free up GPU)
        if prefer_cpu and node['type'] == 'cpu':
            # Check if model fits in RAM
            if self._model_fits_on_node(model, node):
                candidates.insert(0, node)  # Prioritize CPU
        else:
            candidates.append(node)

    # Sort by current load (lowest first)
    candidates.sort(key=lambda n: self._get_node_load(n['id']))

    return candidates[0] if candidates else None
```

---

## Use Case Examples

### Use Case 1: Real-time Chat (FAST)
```python
# User is waiting for response
response = await sollol.generate(
    model="qwen3:14b",
    prompt=user_message,
    routing_mode=RoutingMode.FAST,
    priority=TaskPriority.URGENT
)
# Routes to: Fastest GPU, preferably local
```

### Use Case 2: Production Code Generation (RELIABLE)
```python
# Critical task, can't afford errors or timeouts
response = await sollol.generate(
    model="mixtral:8x7b",
    prompt="Generate payment processing module",
    routing_mode=RoutingMode.RELIABLE,
    priority=TaskPriority.HIGH,
    min_success_rate=0.98
)
# Routes to: Most stable node (CPU or GPU), proven track record
```

### Use Case 3: Background Documentation (ASYNC)
```python
# Non-urgent, free up GPU for interactive tasks
task = await sollol.generate_async(
    model="qwen3:1.7b",
    prompt="Generate docstrings for all Python files",
    routing_mode=RoutingMode.ASYNC,
    priority=TaskPriority.LOW,
    prefer_cpu=True,
    callback=save_documentation
)
# Routes to: CPU node, queues if busy, non-blocking
```

### Use Case 4: Mixed Workload
```python
# Orchestrator intelligently routes based on task type
async def handle_request(request):
    if request.type == "chat":
        return await sollol.generate(..., routing_mode=RoutingMode.FAST)

    elif request.type == "production_code":
        return await sollol.generate(..., routing_mode=RoutingMode.RELIABLE)

    elif request.type == "background_analysis":
        return await sollol.generate_async(..., routing_mode=RoutingMode.ASYNC)
```

---

## Integration Points

### 1. ModelOrchestrator
```python
# core/orchestrator.py

def _get_routing_mode(self, task_type: str, complexity: float) -> RoutingMode:
    """Determine routing mode based on task characteristics"""

    if task_type in ["chat", "quick_question"]:
        return RoutingMode.FAST

    elif task_type in ["production_code", "security_review"]:
        return RoutingMode.RELIABLE

    elif task_type in ["documentation", "test_generation", "analysis"]:
        return RoutingMode.ASYNC

    # Complexity-based
    if complexity > 8.0:
        return RoutingMode.RELIABLE  # Complex = need reliability
    elif complexity < 3.0:
        return RoutingMode.ASYNC  # Simple = can be background
    else:
        return RoutingMode.FAST  # Default
```

### 2. ReasoningEngine
```python
# core/reasoning_engine.py

async def reason(self, task, mode):
    # Deep thinking (complex, critical) = RELIABLE
    if mode == ReasoningMode.DEEP_THINKING:
        routing = RoutingMode.RELIABLE
        priority = TaskPriority.HIGH

    # Fast thinking (simple, quick) = FAST
    elif mode == ReasoningMode.FAST:
        routing = RoutingMode.FAST
        priority = TaskPriority.URGENT

    # Extended thinking (background OK) = ASYNC
    elif mode == ReasoningMode.EXTENDED:
        routing = RoutingMode.ASYNC
        priority = TaskPriority.NORMAL
```

---

## Benefits

1. **Resource Optimization**
   - GPU freed for urgent tasks
   - CPU utilized for suitable workloads
   - Better overall throughput

2. **Reliability**
   - Critical tasks get most stable nodes
   - Track and avoid problematic nodes
   - Lower failure rates

3. **User Experience**
   - Interactive tasks stay fast
   - Background tasks don't block
   - Predictable performance

4. **Cost Efficiency**
   - Run what you can on CPU
   - Save GPU for GPU-necess tasks
   - Better node utilization

---

## Next Steps

1. Implement `NodeReliabilityTracker` class
2. Add `RoutingMode` enum to sollol_integration.py
3. Enhance `generate()` with mode parameter
4. Implement mode-specific node selection
5. Add async task queue system
6. Integrate with ModelOrchestrator
7. Add UI indicators for routing mode
8. Create tests for each mode
