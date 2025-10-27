#!/bin/bash
# Install code formatters and linters for Hydra

echo "📦 Installing Python formatters and linters..."

# Python formatters
pip install black autopep8 flake8 -q

# Check if Node.js is available
if command -v npm &> /dev/null; then
    echo "📦 Installing JavaScript formatters (optional)..."
    npm install -g prettier eslint 2>/dev/null || echo "⚠️  npm formatters failed (optional)"
else
    echo "ℹ️  Node.js not found - skipping JavaScript formatters (optional)"
fi

echo "✅ Formatter installation complete!"
echo ""
echo "Installed:"
which black && echo "  ✓ black (Python)"
which autopep8 && echo "  ✓ autopep8 (Python)"
which flake8 && echo "  ✓ flake8 (Python linter)"
which prettier 2>/dev/null && echo "  ✓ prettier (JS/TS)" || echo "  ✗ prettier (optional)"
