#!/bin/bash
# Clean Hydra Startup Script - Ensures no cached bytecode

echo "=========================================================================="
echo "  🐉 HYDRA - Clean Startup (No Cache)"
echo "=========================================================================="
echo ""

# Kill any existing Streamlit processes
echo "🛑 Stopping existing Streamlit processes..."
pkill -9 -f streamlit 2>/dev/null || true
sleep 2

# Clear Python bytecode cache
echo "🧹 Clearing Python bytecode cache..."
find /home/joker/SOLLOL-Hydra -name "*.pyc" -delete 2>/dev/null || true
find /home/joker/SOLLOL-Hydra -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
find /home/joker/hydra -name "*.pyc" -delete 2>/dev/null || true
find /home/joker/hydra -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

# Clear Streamlit cache
echo "🧹 Clearing Streamlit cache..."
rm -rf ~/.streamlit/cache /tmp/streamlit-* ~/.cache/streamlit 2>/dev/null || true

# Verify timeout configuration
echo ""
echo "🔍 Verifying configuration..."
TIMEOUT=$(python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('SOLLOL_REQUEST_TIMEOUT', 'NOT SET'))")
echo "   SOLLOL_REQUEST_TIMEOUT: $TIMEOUT seconds ($(echo "$TIMEOUT / 60" | bc) minutes)"

MODE=$(python3 -c "from dotenv import load_dotenv; import os; load_dotenv(); print(os.getenv('SOLLOL_DEFAULT_ROUTING_MODE', 'NOT SET'))")
echo "   SOLLOL_DEFAULT_ROUTING_MODE: $MODE"

# Verify pool timeout
echo ""
echo "🔍 Verifying pool timeout..."
python3 << 'VERIFY_POOL'
import sys
import os
from dotenv import load_dotenv
load_dotenv()

# Verify environment loaded
timeout = os.getenv('SOLLOL_REQUEST_TIMEOUT')
if timeout:
    print(f"   ✅ Environment: SOLLOL_REQUEST_TIMEOUT = {timeout}s")
else:
    print("   ❌ Environment: SOLLOL_REQUEST_TIMEOUT not set!")
    sys.exit(1)

# Verify pool uses it
from sollol import OllamaPool
pool = OllamaPool(app_name='Verification')
pool_timeout = pool.session.timeout

print(f"   ✅ Pool timeout: {pool_timeout}")

# Verify it's correct
if hasattr(pool_timeout, 'read') and pool_timeout.read == 1800.0:
    print("   ✅ Timeout correctly configured: 30 minutes")
else:
    print(f"   ❌ Timeout misconfigured: {pool_timeout}")
    sys.exit(1)

# Verify the logging code is present
import inspect
source = inspect.getsource(OllamaPool._make_streaming_request)
if 'Streaming request timeout set to' in source:
    print('   ✅ Timeout logging code present')
else:
    print('   ❌ Timeout logging code missing - old version!')
    sys.exit(1)
VERIFY_POOL

if [ $? -ne 0 ]; then
    echo ""
    echo "❌ Configuration verification failed!"
    echo "   Please check .env file and SOLLOL installation"
    exit 1
fi

echo ""
echo "=========================================================================="
echo "  ✅ All checks passed - Starting Streamlit"
echo "=========================================================================="
echo ""

# Get IP address
IP=$(hostname -I | awk '{print $1}')

# Start Streamlit
cd /home/joker/hydra
streamlit run app.py --server.address=0.0.0.0 2>&1 | tee /tmp/hydra_clean_startup.log

