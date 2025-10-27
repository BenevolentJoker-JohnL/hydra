# Python Bytecode Cache Issue - CRITICAL 🚨

## The Problem

Python caches compiled bytecode (`.pyc` files) for faster imports. When we edit SOLLOL's source code, **Streamlit can load the OLD cached bytecode** instead of the new code, causing:

- ❌ Timeout still ~3 minutes instead of 30 minutes
- ❌ Missing debug logs (`🕐 Streaming request timeout set to...`)
- ❌ Old routing logic without performance improvements

## Evidence from Your Session

Your Streamlit logs showed:
```
15:53:06 - Started request
15:55:55 - Failed (~2 min 49 sec) ❌ NOT 30 minutes!
```

**Missing log that should appear:**
```
🕐 Streaming request timeout set to 1800s (30.0 minutes)
```

This proves Streamlit loaded **old cached bytecode without our timeout fixes**.

## The Root Cause

When you run `streamlit run app.py` directly:
1. Python checks for cached `.pyc` files in `__pycache__/`
2. If cache exists and is newer than source, **Python uses the cache**
3. Streamlit process keeps modules in memory for the session
4. Our edits to `/home/joker/SOLLOL-Hydra/src/sollol/pool.py` are IGNORED

## The Solution

### ✅ Use the Clean Startup Script

**Always** start Hydra with:
```bash
./start_hydra_clean.sh
```

This script:
1. Kills existing Streamlit processes
2. Clears ALL Python bytecode cache
3. Clears Streamlit cache
4. Verifies timeout configuration
5. Verifies pool has correct timeout
6. Only then starts Streamlit

### ❌ DO NOT use these commands:
```bash
streamlit run app.py          # ❌ May load cached code
./START_HYDRA.sh              # ❌ Doesn't clear cache
python -m streamlit run app.py # ❌ May load cached code
```

## Manual Cache Clearing (if needed)

If you must start Streamlit manually:

```bash
# 1. Kill all Streamlit
pkill -9 -f streamlit

# 2. Clear SOLLOL bytecode
find /home/joker/SOLLOL-Hydra -name "*.pyc" -delete
find /home/joker/SOLLOL-Hydra -type d -name __pycache__ -exec rm -rf {} +

# 3. Clear Hydra bytecode
find /home/joker/hydra -name "*.pyc" -delete
find /home/joker/hydra -type d -name __pycache__ -exec rm -rf {} +

# 4. Clear Streamlit cache
rm -rf ~/.streamlit/cache /tmp/streamlit-* ~/.cache/streamlit

# 5. Verify before starting
python3 -c "
from dotenv import load_dotenv
import os
load_dotenv()
from sollol import OllamaPool
pool = OllamaPool(app_name='Test')
print(f'Pool timeout: {pool.session.timeout}')
print('Expected: Timeout(connect=10.0, read=1800.0, write=1800.0, pool=1800.0)')
"

# 6. Only NOW start Streamlit
streamlit run app.py
```

## How to Verify It's Working

When Streamlit starts with the **correct code**, you'll see:

```
🕐 Streaming request timeout set to 1800s (30.0 minutes)
```

in the logs when you make a request.

**If you DON'T see this log**, you're running old cached code!

## Why This Happens

### Python Import Caching
- First import: Python compiles `.py` → `.pyc`, stores in `__pycache__/`
- Subsequent imports: Python checks if `.pyc` is newer than `.py`
- If `.pyc` is newer: **Uses cached bytecode** (faster but WRONG if we edited source)

### Streamlit Module Caching
- Streamlit keeps imported modules in memory
- Even if you clear bytecode, Streamlit may have the old module loaded
- Must restart Streamlit process to force reimport

### Editable Install (`pip install -e`)
- SOLLOL installed with `pip install -e /home/joker/SOLLOL-Hydra`
- Changes to source should be immediate
- BUT Python still caches bytecode in `__pycache__/`
- Must clear cache after editing SOLLOL source

## File Locations

**Bytecode cache locations:**
```
/home/joker/SOLLOL-Hydra/src/sollol/__pycache__/
/home/joker/SOLLOL-Hydra/src/sollol/__pycache__/pool.cpython-310.pyc  ← OLD timeout code
/home/joker/hydra/__pycache__/
/home/joker/hydra/core/__pycache__/
```

**Streamlit cache:**
```
~/.streamlit/cache/
~/.cache/streamlit/
/tmp/streamlit-*/
```

## Testing the Fix

After starting with `./start_hydra_clean.sh`:

1. Make a request in Hydra UI
2. Check the logs for:
   ```
   🕐 Streaming request timeout set to 1800s (30.0 minutes)
   ```
3. If request takes >3 minutes, it should continue up to 30 minutes
4. Watch for node selection logs with performance scores

## Summary

**Problem:** Bytecode cache = old code = short timeout
**Solution:** `./start_hydra_clean.sh` = clean cache = new code = 30min timeout
**Verification:** Look for `🕐 Streaming request timeout` log

**ALWAYS use `./start_hydra_clean.sh` after editing SOLLOL code!**
