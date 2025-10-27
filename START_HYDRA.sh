#!/bin/bash
# Hydra Startup Script with Dashboard URLs

clear
echo "======================================================================"
echo "  🐉 HYDRA - Starting with SOLLOL Distributed Processing"
echo "======================================================================"
echo ""

# Get the primary IP
IP=$(hostname -I | awk '{print $1}')

echo "📍 Server IP: $IP"
echo ""
echo "Starting Streamlit..."
echo ""

# Start streamlit
streamlit run app.py &
STREAMLIT_PID=$!

# Wait for startup
sleep 5

echo ""
echo "======================================================================"
echo "  ✅ HYDRA IS RUNNING"
echo "======================================================================"
echo ""
echo "🌐 Access URLs:"
echo ""
echo "   Hydra UI:        http://$IP:8501"
echo "   Hydra UI (local): http://localhost:8501"
echo ""
echo "   Dashboard:       http://$IP:8080"
echo "   Dashboard (local): http://localhost:8080"
echo ""
echo "======================================================================"
echo ""
echo "📊 Monitoring:"
echo "   ./monitor_nodes.sh     - Real-time node monitor"
echo "   ./check_nodes.sh       - Quick status check"
echo ""
echo "⏱️  Timeout: 30 minutes for 14B models"
echo "🔄 Routing: Parallel ASYNC across 2 nodes"
echo ""
echo "======================================================================"
echo ""
echo "Press Ctrl+C to stop Streamlit (PID: $STREAMLIT_PID)"
echo ""

# Wait for Streamlit
wait $STREAMLIT_PID
