# Model Availability Across Nodes

## Issue Discovered
SOLLOL correctly tried only one node because `qwen2.5-coder:14b` only exists on 10.9.66.154.

## Node Model Inventory

### Node 10.9.66.154 (More model variety)
**Code Models:**
- ✓ qwen2.5-coder:7b (both)
- ✓ qwen2.5-coder:3b (both)  
- ✓ qwen2.5-coder:1.5b (both)
- ✓ deepseek-coder-v2:latest (both)
- ✓ deepseek-coder:latest (both)
- ✓ qwen2.5-coder:14b (ONLY HERE - causes timeout on CPU)
- ✓ deepseek-coder-v2:16b (ONLY HERE)
- ✓ deepseek-coder:33b (ONLY HERE)
- ✓ starcoder2:15b (ONLY HERE)

### Node 10.9.66.250 (Smaller model set)
**Code Models:**
- ✓ qwen2.5-coder:7b (both)
- ✓ qwen2.5-coder:3b (both)
- ✓ qwen2.5-coder:1.5b (both)
- ✓ qwen2.5-coder:0.5b (ONLY HERE)
- ✓ deepseek-coder-v2:latest (both)
- ✓ deepseek-coder:6.7b (ONLY HERE)
- ✓ deepseek-coder:latest (both)

## Optimal Configuration for Parallel Routing

### Current Priority (UPDATED)
```bash
HYDRA_CODE_MODELS=qwen2.5-coder:7b,qwen2.5-coder:3b,deepseek-coder-v2:latest,qwen2.5-coder:1.5b,deepseek-coder:6.7b
```

**Rationale:**
1. **qwen2.5-coder:7b** - Available on both, good quality, CPU-friendly
2. **qwen2.5-coder:3b** - Available on both, faster fallback
3. **deepseek-coder-v2:latest** (15.7B) - Available on both, best quality
4. **qwen2.5-coder:1.5b** - Available on both, fastest fallback
5. **deepseek-coder:6.7b** - Only on 10.9.66.250, secondary fallback

## Why Parallel Routing Failed

**Problem:**
```
User requests code generation
→ Hydra selects: qwen2.5-coder:14b (first in list)
→ SOLLOL discovers: Only available on 10.9.66.154
→ Routes to 10.9.66.154
→ 14B model on CPU times out (5 minutes)
→ No other node has the model
→ Request fails: "All 2 nodes failed"
```

**Solution:**
Use models available on **both nodes** for true parallel distribution.

## Performance Expectations

| Model | Size | Both Nodes? | CPU Time | Quality |
|-------|------|-------------|----------|---------|
| qwen2.5-coder:7b | 7.6B | ✅ | 1-2 min | Excellent |
| qwen2.5-coder:3b | 3.1B | ✅ | 30-60s | Good |
| deepseek-coder-v2 | 15.7B | ✅ | 2-4 min | Best |
| qwen2.5-coder:1.5b | 1.5B | ✅ | 15-30s | Fast |

## Recommendations

### For True Parallel Processing
Always use models available on both nodes so SOLLOL can distribute load.

### To Use Larger Models (14B+)
Either:
1. Pull missing models to 10.9.66.250:
   ```bash
   ssh 10.9.66.250
   ollama pull qwen2.5-coder:14b
   ```

2. OR accept single-node routing for those models

### Current Status
✅ Configuration updated for parallel-compatible models
✅ All 5 primary models support parallel routing
