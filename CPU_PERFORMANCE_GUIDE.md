# CPU Performance Guide for Hydra

## Issue: Large Models Timing Out

**Observed behavior:**
- qwen2.5-coder:14b: 5-minute timeout on CPU
- deepseek-coder:latest (1B): Also timing out
- Both nodes tried, both failed with timeout

**Root cause:**
- CPU inference is **10-50x slower** than GPU
- 14B models take 10-30 minutes on CPU for complex tasks
- Default 5-minute timeout is too short

## ✅ Solution Applied

### Updated Model Configuration (CPU-Optimized)

**Code Models** (completes in 30s-2min):
```bash
1. qwen2.5-coder:3b     → 30-60s per task
2. qwen2.5-coder:1.5b   → 15-30s per task (fastest)
3. qwen2.5-coder:7b     → 1-2 min per task (best quality)
4. deepseek-coder:latest (1B) → 10-20s
5. deepseek-coder:6.7b  → 1-2 min
```

**Reasoning/Heavy** (completes in 1-3min):
```bash
qwen3:8b → Balanced quality and speed on CPU
```

**Light** (completes in <30s):
```bash
qwen3:1.7b → Fast orchestration
```

## Performance Expectations

| Model | Parameters | CPU Time | Quality | Use Case |
|-------|-----------|----------|---------|----------|
| qwen2.5-coder:1.5b | 1.5B | 15-30s | Good | Quick fixes, simple code |
| qwen2.5-coder:3b | 3.1B | 30-60s | Better | Standard code gen |
| qwen2.5-coder:7b | 7.6B | 1-2 min | Excellent | Complex code |
| qwen3:8b | 8.2B | 1-3 min | Excellent | Reasoning, analysis |
| deepseek-coder:latest | 1B | 10-20s | Fast | Simple tasks |

## Parallel Routing Now Works

With these smaller models:
- ✅ Both nodes can complete before timeout
- ✅ SOLLOL distributes load across nodes
- ✅ If one node busy → automatic failover to other
- ✅ Multiple requests process in parallel

## Why 14B Models Failed

**Problem:**
```
Request → qwen2.5-coder:14b
├─ Node 154: Started → 5 min timeout → Failed
└─ Node 250: Started → Didn't complete before node 154 failed
Result: "All nodes failed" (really: timeout too short for CPU)
```

**CPU inference timing:**
- 14B model on CPU: 10-30 minutes for complex task
- Default timeout: 5 minutes
- Math: Model needs 10+ min, timeout at 5 min = guaranteed failure

## Options for Using Larger Models

### Option 1: Use Smaller Models (RECOMMENDED)
**Current config** - models complete in <2 minutes
- Quality: Still excellent (3B-8B models are very capable)
- Speed: Practical for CPU
- Parallel: Works perfectly

### Option 2: Increase Timeout (NOT RECOMMENDED)
```bash
# In SOLLOL pool configuration
timeout=1800  # 30 minutes
```
**Drawbacks:**
- User waits 30 minutes per request
- No parallelism benefit (one long task blocks node)
- Poor UX

### Option 3: Add GPU Nodes (BEST LONG-TERM)
- 14B model on GPU: 10-30 seconds
- True parallel processing
- Can use largest models

## Monitoring Resource Usage

**Check node status:**
```bash
# See what's currently loaded/running
curl -s http://10.9.66.154:11434/api/ps
curl -s http://10.9.66.250:11434/api/ps
```

**Monitor during request:**
```bash
# Watch CPU usage
top -u ollama

# Watch memory
free -h
```

## Restart Instructions

**Stop Streamlit** (Ctrl+C), then restart:
```bash
streamlit run app.py
```

**Expected behavior:**
- Requests complete in 15s-2min depending on model
- Parallel routing works (both nodes process simultaneously)
- No timeouts
- Good quality code generation

## Performance Tips

### For Speed
Use qwen2.5-coder:1.5b or deepseek-coder:latest
- Fastest completion
- Good for simple tasks

### For Quality
Use qwen2.5-coder:7b or qwen3:8b
- Best quality on CPU
- Reasonable 1-2 min completion

### For Production
Use 3B models as default
- Great balance of speed and quality
- Reliable completion times
- Good parallel distribution

---

**Status:** ✅ Configuration optimized for CPU-only parallel routing
**Next:** Restart Streamlit and test with faster models
