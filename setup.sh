#!/bin/bash

echo "🐉 Hydra Setup Script"
echo "===================="

echo "Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo "Creating data directories..."
mkdir -p data

echo "Setting up environment file..."
if [ ! -f .env ]; then
    cp .env.example .env
    echo "Please edit .env with your configuration"
fi

echo "Checking Ollama installation..."
if command -v ollama &> /dev/null; then
    echo "✓ Ollama found"
    echo "Installed models:"
    ollama list
else
    echo "✗ Ollama not found. Please install Ollama first."
    echo "Visit: https://ollama.ai"
fi

echo ""
echo "Setup complete! Next steps:"
echo "1. Edit .env with your database credentials and node IPs"
echo "2. Ensure PostgreSQL, Redis are running"
echo "3. Pull required Ollama models on all nodes"
echo "4. Run: python main.py api (for API server)"
echo "5. Run: python main.py ui (for web interface)"