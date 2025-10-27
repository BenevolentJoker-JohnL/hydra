#!/bin/bash
# SOLLOL Node Monitoring Script
# Real-time monitoring of distributed Ollama nodes

clear
echo "======================================================================="
echo "  SOLLOL Distributed Node Monitor"
echo "  Monitoring: 10.9.66.154:11434 and 10.9.66.250:11434"
echo "  Press Ctrl+C to stop"
echo "======================================================================="
echo ""

while true; do
    clear
    echo "======================================================================="
    echo "  SOLLOL Node Monitor - $(date '+%Y-%m-%d %H:%M:%S')"
    echo "======================================================================="
    echo ""

    # Node 154 Status
    echo "┌─────────────────────────────────────────────────────────────────────┐"
    echo "│ NODE: 10.9.66.154:11434                                             │"
    echo "└─────────────────────────────────────────────────────────────────────┘"

    node154_status=$(curl -s http://10.9.66.154:11434/api/ps 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "✅ Status: ONLINE"

        # Check if any models are loaded
        models_loaded=$(echo "$node154_status" | jq -r '.models[]?.name // empty' 2>/dev/null)
        if [ -n "$models_loaded" ]; then
            echo "📦 Models Currently Loaded:"
            echo "$node154_status" | jq -r '.models[] | "   • \(.name) - \(.size_vram // .size) - Expires: \(.expires_at // "N/A")"' 2>/dev/null
        else
            echo "💤 No models currently loaded (idle)"
        fi
    else
        echo "❌ Status: OFFLINE or UNREACHABLE"
    fi

    echo ""

    # Node 250 Status
    echo "┌─────────────────────────────────────────────────────────────────────┐"
    echo "│ NODE: 10.9.66.250:11434                                             │"
    echo "└─────────────────────────────────────────────────────────────────────┘"

    node250_status=$(curl -s http://10.9.66.250:11434/api/ps 2>/dev/null)
    if [ $? -eq 0 ]; then
        echo "✅ Status: ONLINE"

        # Check if any models are loaded
        models_loaded=$(echo "$node250_status" | jq -r '.models[]?.name // empty' 2>/dev/null)
        if [ -n "$models_loaded" ]; then
            echo "📦 Models Currently Loaded:"
            echo "$node250_status" | jq -r '.models[] | "   • \(.name) - \(.size_vram // .size) - Expires: \(.expires_at // "N/A")"' 2>/dev/null
        else
            echo "💤 No models currently loaded (idle)"
        fi
    else
        echo "❌ Status: OFFLINE or UNREACHABLE"
    fi

    echo ""
    echo "======================================================================="
    echo "  Available Models on Each Node"
    echo "======================================================================="

    # Quick model count
    count_154=$(curl -s http://10.9.66.154:11434/api/tags 2>/dev/null | jq -r '.models | length' 2>/dev/null)
    count_250=$(curl -s http://10.9.66.250:11434/api/tags 2>/dev/null | jq -r '.models | length' 2>/dev/null)

    echo "Node 154: $count_154 models available"
    echo "Node 250: $count_250 models available"

    echo ""
    echo "Refreshing in 5 seconds... (Ctrl+C to stop)"
    sleep 5
done
