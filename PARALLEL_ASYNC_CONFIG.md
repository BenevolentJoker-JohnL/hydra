# Hydra Parallel Async Configuration

## Overview
Hydra is now configured for **parallel async distributed processing** across two heterogeneous nodes:
- **Node 1** (10.9.66.154): Can handle models up to 30B+ parameters
- **Node 2** (10.9.66.250): Can handle models up to 70B parameters

## SOLLOL Routing Configuration

### Default Routing Mode: `ASYNC`
```bash
SOLLOL_DEFAULT_ROUTING_MODE=async
```

**Benefits:**
- Distributes workload across both nodes in parallel
- Uses both CPU and GPU resources efficiently
- Non-blocking task execution
- Optimizes for resource efficiency over raw speed

### Available Routing Modes

| Mode | When to Use | Priority |
|------|-------------|----------|
| `fast` | Interactive responses, real-time chat | Speed > all |
| `reliable` | Critical tasks, production code | Stability > speed |
| `async` | Background tasks, parallel processing | Efficiency > speed |

## Model Tier Configuration

Models are configured in **priority order** - SOLLOL routes to the most capable available node:

### Code Models (CPU-optimized with powerful node support)
```
1. qwen2.5-coder:7b        → Powerful node preferred
2. deepseek-coder-v2:latest (15.7B) → Powerful node
3. codellama:13b           → Powerful node
4. qwen2.5-coder:3b        → Either node
5. deepseek-coder:6.7b     → Either node
6. qwen2.5-coder:1.5b      → Light node fallback
```

### Reasoning Models
```
Primary:  qwen3:14b        → Powerful node preferred
Math:     qwen3:14b        → Powerful node preferred
Light:    qwen3:1.7b       → Light node
```

### General-Purpose Models
```
1. llama3.1:70b    → Most capable node only
2. mistral:latest  → Either node
3. llama3.2:3b     → Either node
4. qwen3:8b        → Either node
```

## Parallel Execution Settings

```bash
SOLLOL_PARALLEL_REQUESTS=true
SOLLOL_MAX_CONCURRENT_REQUESTS=4
```

**Behavior:**
- Up to 4 requests can process simultaneously
- SOLLOL automatically load balances across both nodes
- Each node handles what it can support best

## VRAM/Resource Monitoring

```bash
SOLLOL_VRAM_MONITORING=true
SOLLOL_MIN_VRAM_MB=100
```

**How it works:**
- Monitors available resources on each node
- Routes large models to nodes with sufficient capacity
- Gracefully handles CPU-only nodes (no false warnings)

## Reasoning Engine Settings

```bash
HYDRA_REASONING_MODE=auto              # Adaptive reasoning level
HYDRA_REASONING_MODEL=qwen3:14b        # 14B for quality reasoning
HYDRA_USE_REASONING_MODEL=true         # Enabled
HYDRA_MAX_THINKING_TOKENS=6000         # Balanced for CPU
HYDRA_DEEP_THINKING_THRESHOLD=9.5      # Only for hardest problems
```

**Performance:**
- Auto mode adapts to task complexity
- Uses qwen3:14B on powerful node for thinking
- Deep thinking mode available but conservative (9.5/10 threshold)

## How Parallel Async Works

### Example: Code Generation Task

1. **User requests code generation**
2. **Hydra selects model tier**: `qwen2.5-coder:7b`
3. **SOLLOL ASYNC routing**:
   - Checks both nodes' current load
   - Routes to least busy node with model available
   - Doesn't block on GPU - can use CPU if more efficient
4. **Parallel execution**: Multiple requests run simultaneously
5. **Result streaming**: User sees output as it's generated

### Node Selection Logic (ASYNC mode)

```python
Priority:
1. CPU nodes (intentionally free up resources)
2. Nodes with lowest current load
3. Can queue if all busy
4. Remote nodes OK (no local preference)
```

## Testing the Configuration

After restart, verify parallel routing:

```python
# In Hydra UI, submit multiple tasks simultaneously:
# - Task 1: Generate Python function
# - Task 2: Analyze code complexity
# - Task 3: Create unit tests

# Watch the logs to see:
# ✅ Tasks distributed across both nodes
# ✅ Different models selected based on node capability
# ✅ Parallel execution (both nodes active)
```

## Performance Tips

### For Best Throughput
```python
# Use async routing with background tasks
routing_mode="async"
priority=2  # Low priority = more parallel friendly
```

### For Best Quality
```python
# Use reliable routing with powerful models
routing_mode="reliable"
model="llama3.1:70b"  # Routes to most capable node
min_success_rate=0.98
```

### For Best Speed
```python
# Use fast routing with local preference
routing_mode="fast"
priority=10  # Urgent
model="qwen3:1.7b"  # Small, fast model
```

## Restart Instructions

```bash
# 1. Stop current Streamlit (Ctrl+C in terminal)

# 2. Restart with new config
streamlit run app.py

# 3. Watch for log messages:
#    ✅ SOLLOL discovered 2 nodes
#    ✅ Default routing mode: ASYNC
#    ✅ VRAM monitoring: enabled
```

## Monitoring

**SOLLOL Dashboard**: http://localhost:8080
- Real-time node status
- Request distribution
- Performance metrics
- Routing decisions

**Streamlit UI**: http://localhost:8501
- Task submissions
- Response streaming
- Model selection

---

**Configuration applied**: {{ date }}
**Status**: Ready for restart
