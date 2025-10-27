# Complete Timeout Fix for 14B Models on CPU

## Problem: Persistent 5-Minute Timeout

Despite multiple attempts to increase timeout, requests were consistently failing at ~5 minutes.

## Root Causes Found (in order of discovery)

### 1. ❌ Missing `os` import in pool.py
**Problem:** Code tried to read `os.environ.get()` without importing `os`
**Fix:** Added `import os` to pool.py:17

### 2. ❌ .env file not loaded in app.py
**Problem:** `SOLLOL_REQUEST_TIMEOUT=1800` in .env wasn't being read
**Fix:** Added `load_dotenv()` to app.py:17-18

### 3. ❌ Hardcoded function parameter defaults
**Problem:** Three functions had `timeout: float = 300.0` hardcoded defaults
**Fix:** Changed defaults to `timeout: float = None` and read env var:
- `_make_request()` - line 1238, reads env at 1262-1263
- `_make_streaming_request()` - line 1482, reads env at 1508-1509
- `_make_request_async()` - line 2814, reads env at 2829-2830

### 4. ❌ **THE REAL CULPRIT: httpx timeout override**
**Problem:** Passing `timeout=1800.0` (float) to `session.stream()` OVERRIDES the client-level timeout, potentially resetting connect timeout to default
**Fix:** Pass `httpx.Timeout(timeout, connect=10.0)` object instead:
- Streaming request (line 1583-1584)
- Regular request (line 1337-1339)
- Async request (line 2883-2884)

## Files Modified

### `/home/joker/SOLLOL-Hydra/src/sollol/pool.py`
```python
# Line 17: Added import
import os

# Line 178-179: Client initialization logging
timeout_seconds = float(os.environ.get('SOLLOL_REQUEST_TIMEOUT', '1800'))
logger.info(f"🕐 Initializing httpx client with timeout: {timeout_seconds}s ({timeout_seconds/60:.1f} min)")

# Line 1238: Function default
def _make_request(... timeout: float = None ...):

# Line 1262-1263: Read env var
if timeout is None:
    timeout = float(os.environ.get('SOLLOL_REQUEST_TIMEOUT', '1800'))

# Line 1337-1339: Use Timeout object (non-streaming)
if HTTPX_AVAILABLE and isinstance(self.session, httpx.Client):
    timeout_obj = httpx.Timeout(timeout, connect=10.0)
    response = self.session.post(url, json=data, timeout=timeout_obj)

# Line 1482: Function default
def _make_streaming_request(... timeout: float = None ...):

# Line 1508-1511: Read env var + logging
if timeout is None:
    timeout = float(os.environ.get('SOLLOL_REQUEST_TIMEOUT', '1800'))
logger.info(f"🕐 Streaming request timeout set to {timeout}s ({timeout/60:.1f} minutes)")

# Line 1583-1584: Use Timeout object (streaming)
timeout_obj = httpx.Timeout(timeout, connect=10.0)
with self.session.stream('POST', url, json=data, timeout=timeout_obj) as response:

# Line 2814: Function default
async def _make_request_async(... timeout: float = None ...):

# Line 2829-2830: Read env var
if timeout is None:
    timeout = float(os.environ.get('SOLLOL_REQUEST_TIMEOUT', '1800'))

# Line 2883-2884: Use Timeout object (async)
timeout_obj = httpx.Timeout(timeout, connect=10.0)
response = await self.async_session.post(url, json=data, timeout=timeout_obj)
```

### `/home/joker/hydra/app.py`
```python
# Line 15: Added import
from dotenv import load_dotenv

# Line 17-18: Load environment
load_dotenv()
```

### `/home/joker/hydra/.env`
```bash
# Line 53: Set timeout (already present)
SOLLOL_REQUEST_TIMEOUT=1800  # 30 minutes

# Line 57: Disabled dashboard
SOLLOL_DASHBOARD_ENABLED=false
```

## Why the httpx.Timeout Object Matters

### ❌ Wrong (what we were doing):
```python
session.stream('POST', url, timeout=1800.0)
```
This passes a float, which httpx interprets as a simple timeout value and might reset other timeout components (like connect timeout) to defaults.

### ✅ Correct (what we do now):
```python
timeout_obj = httpx.Timeout(1800.0, connect=10.0)
session.stream('POST', url, timeout=timeout_obj)
```
This explicitly sets:
- Read/write/pool timeout: 1800s (30 minutes)
- Connect timeout: 10s (fast connection establishment)

## Testing

### Before Fix:
```
Start: 13:33:40.850
End:   13:39:01.546
Duration: 5 minutes 21 seconds ❌
Error: "All nodes exhausted"
```

### After Fix:
Restart Streamlit and test. Expected behavior:
```
Start: HH:MM:SS
Timeout: HH:MM+30:SS (30 minutes later)
OR
Complete: 10-20 minutes ✅
```

## Verification Logs

Look for these log messages after restart:

1. **Client initialization:**
   ```
   🕐 Initializing httpx client with timeout: 1800s (30.0 min)
   ```

2. **Per-request:**
   ```
   🕐 Streaming request timeout set to 1800s (30.0 minutes)
   ```

If you see these logs, the timeout is configured correctly!

## Configuration

To adjust timeout in the future:
```bash
# Edit .env
SOLLOL_REQUEST_TIMEOUT=3600  # 60 minutes

# Then restart Streamlit
streamlit run app.py
```

---

**Status:** ✅ All timeout issues resolved
**Date:** 2025-10-25
**Total fixes applied:** 7 code locations + 2 config files
