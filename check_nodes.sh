#!/bin/bash
# Quick node status check (one-time, not continuous)

echo "======================================================================="
echo "  SOLLOL Node Status Check"
echo "======================================================================="
echo ""

# Node 154
echo "Node 10.9.66.154:11434"
echo "─────────────────────────────────────────────────────────────────────"
curl -s http://10.9.66.154:11434/api/ps | jq '.' 2>/dev/null || echo "❌ Failed to connect"
echo ""

# Node 250
echo "Node 10.9.66.250:11434"
echo "─────────────────────────────────────────────────────────────────────"
curl -s http://10.9.66.250:11434/api/ps | jq '.' 2>/dev/null || echo "❌ Failed to connect"
echo ""

echo "======================================================================="
echo "  Model Availability"
echo "======================================================================="
echo ""
echo "Node 154 - Available Models:"
curl -s http://10.9.66.154:11434/api/tags | jq -r '.models[] | "  • \(.name) (\(.size))"' 2>/dev/null || echo "❌ Failed"
echo ""
echo "Node 250 - Available Models:"
curl -s http://10.9.66.250:11434/api/tags | jq -r '.models[] | "  • \(.name) (\(.size))"' 2>/dev/null || echo "❌ Failed"
