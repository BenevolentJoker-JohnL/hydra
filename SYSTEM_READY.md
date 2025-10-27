# 🎉 HYDRA SYSTEM READY - 30 Minute Timeout Configured

**Date:** 2025-10-25
**Status:** ✅ RUNNING WITH CLEAN CACHE
**Log File:** `/tmp/hydra_verified_clean.log`

## ✅ Current System Status

### Services Running
- ✅ **Hydra UI:** http://localhost:8501 (or http://10.9.66.154:8501)
- ✅ **SOLLOL Dashboard:** http://localhost:8080 (or http://10.9.66.154:8080)
- ✅ **2 Ollama Nodes Discovered:**
  - 10.9.66.154:11434 (CPU-only)
  - 10.9.66.250:11434 (CPU-only, faster)

### Configuration Verified
- ✅ **Timeout:** 1800 seconds (30 minutes)
- ✅ **Routing Mode:** ASYNC (parallel distribution)
- ✅ **Models Available:** qwen2.5-coder:14b on both nodes
- ✅ **Python Bytecode Cache:** CLEARED
- ✅ **Streamlit Cache:** CLEARED

## 🔍 How to Verify Timeout is Working

When you make a request in the Hydra UI, watch for this critical log entry:

```
🕐 Streaming request timeout set to 1800s (30.0 minutes)
```

**To monitor in real-time:**
```bash
tail -f /tmp/hydra_verified_clean.log | grep -E "(🕐|timeout|completed|failed|routing)"
```

### What You Should See

**✅ With correct timeout (new code):**
```
🕐 Streaming request timeout set to 1800s (30.0 minutes)
🌊 Streaming from 10.9.66.250:11434...
✅ Model qwen2.5-coder:14b completed in 458.32s on http://10.9.66.250:11434
```

**❌ With old cached code (BAD):**
```
# Missing: 🕐 Streaming request timeout log
❌ All 2 nodes failed for streaming request: All nodes exhausted
# Timeout after ~3 minutes
```

## 🚨 If You Still See Short Timeout

**The cache wasn't fully cleared. Run:**

```bash
# 1. Kill everything
pkill -9 -f streamlit

# 2. Nuclear cache clear
find /home/joker/SOLLOL-Hydra -name "*.pyc" -delete 2>/dev/null
find /home/joker/SOLLOL-Hydra -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
find /home/joker/hydra -name "*.pyc" -delete 2>/dev/null
find /home/joker/hydra -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null
rm -rf ~/.streamlit/cache /tmp/streamlit-* ~/.cache/streamlit 2>/dev/null

# 3. Verify the code is correct
python3 -c "
import os
os.environ['SOLLOL_REQUEST_TIMEOUT'] = '1800'
from sollol import OllamaPool
import inspect

pool = OllamaPool(app_name='Test')
print(f'Pool timeout: {pool.session.timeout}')

source = inspect.getsource(OllamaPool._make_streaming_request)
if 'Streaming request timeout set to' in source:
    print('✅ Timeout log code is present')
else:
    print('❌ Old code still loaded!')
"

# 4. Only now start Streamlit
streamlit run app.py --server.address=0.0.0.0
```

## 📊 Expected Performance

### 14B Model on CPU (qwen2.5-coder:14b)

**First request (cold start - loading model to RAM):**
- Time: 5-10 minutes
- Timeout: Will wait up to 30 minutes ✅

**Subsequent requests (warm - model in RAM):**
- Simple task: 3-7 minutes
- Complex code generation: 8-15 minutes
- Timeout: Will wait up to 30 minutes ✅

**If timeout occurs:**
- After 30 minutes: Request will fail with timeout error
- ASYNC mode will automatically try the other node first

### 3B Model (qwen2.5-coder:3b)

**For testing/quick tasks:**
- Node .250: ~4.8 seconds
- Node .154: ~6.2 seconds
- Will complete well within timeout

## 🔄 Routing Behavior

### Initial Requests (No Performance Data)
- Random jitter distributes across both nodes
- Pool collects latency data from each request

### After 2-3 Requests (Performance Data Collected)
- **Node .250 will be preferred** (faster: 4.8s vs 6.2s)
- ASYNC mode uses performance-based scoring
- Lower latency = higher score

### Automatic Failover
- If node times out or fails → tries other node
- If both fail → tries fallback models in order:
  1. qwen2.5-coder:14b
  2. deepseek-coder-v2:latest
  3. codellama:13b
  4. etc.

## 📝 All Fixes Applied

### 1. Timeout Configuration (`/home/joker/SOLLOL-Hydra/src/sollol/pool.py`)
- ✅ Added `import os` (line 17)
- ✅ httpx client reads `SOLLOL_REQUEST_TIMEOUT` env var (line 178)
- ✅ `_make_request()` uses env var when timeout=None (lines 1262-1263)
- ✅ `_make_streaming_request()` uses env var when timeout=None (lines 1530-1533)
- ✅ `_make_request_async()` uses env var when timeout=None (lines 2829-2830)
- ✅ httpx calls use `Timeout` objects instead of floats (lines 1354, 1604, 2883)
- ✅ Added timeout logging: `🕐 Streaming request timeout set to...` (line 1533)

### 2. Routing Performance (`/home/joker/SOLLOL-Hydra/src/sollol/pool.py`)
- ✅ ASYNC mode uses latency-based scoring (lines 1198-1212)
- ✅ Random jitter for initial load balancing when no perf data (lines 1204-1208)
- ✅ Success rate scoring (line 1212)

### 3. Environment Loading (`/home/joker/hydra/app.py`)
- ✅ Added `load_dotenv()` BEFORE importing SOLLOL (line 18)

### 4. Dashboard Startup (`/home/joker/hydra/core/sollol_integration.py`)
- ✅ Dashboard runs in background thread (lines 206-212)
- ✅ Bound to `0.0.0.0` for network access (line 208)

## 🎯 Test Plan

### Test 1: Quick Test (3B model)
1. Go to Hydra UI: http://localhost:8501
2. Enter prompt: "Write a hello world in Python"
3. Select model: qwen2.5-coder:3b
4. Expected: Completes in ~5 seconds
5. Check logs for node selection

### Test 2: Full Timeout Test (14B model)
1. Go to Hydra UI: http://localhost:8501
2. Enter complex prompt: "Write a complete REST API server in Python with authentication, database, and error handling"
3. Select model: qwen2.5-coder:14b
4. Expected:
   - See `🕐 Streaming request timeout set to 1800s` in logs
   - Request runs for 5-15 minutes
   - Completes successfully without timeout
5. Monitor: `tail -f /tmp/hydra_verified_clean.log | grep -E "(🕐|completed|routing)"`

### Test 3: Routing Distribution
1. Make 3-4 requests with qwen2.5-coder:3b
2. Watch logs for node selection
3. After initial random distribution, should prefer .250

## 📁 Important Files

### Configuration
- `/home/joker/hydra/.env` - Environment variables (timeout, routing mode)
- `/home/joker/hydra/config/models.yaml` - Model definitions

### Logs
- `/tmp/hydra_verified_clean.log` - Current Streamlit logs
- Monitor with: `tail -f /tmp/hydra_verified_clean.log`

### Documentation
- `TIMEOUT_FIX_STATUS.md` - Verification status
- `TIMEOUT_CONFIGURATION.md` - Technical details
- `CACHE_ISSUE_SOLUTION.md` - Why cache clearing is critical
- `SYSTEM_READY.md` - This file

### Scripts
- `start_hydra_clean.sh` - Clean startup (has heredoc issue, use manual method above)
- `monitor_nodes.sh` - Real-time node monitoring
- `check_nodes.sh` - Quick node status

## 🚀 Ready to Use!

The system is configured and running with:
- ✅ 30-minute timeout
- ✅ ASYNC parallel routing
- ✅ Performance-based node selection
- ✅ Clean Python bytecode (no cache issues)
- ✅ Both nodes with 14B models

**Start making requests and the timeout will be 30 minutes!**

Watch the logs to verify you see the `🕐 Streaming request timeout set to 1800s` message.
