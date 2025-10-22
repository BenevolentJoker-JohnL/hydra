#!/bin/bash

# Hydra Worker Node Deployment Script
# Rapid deployment for worker nodes connecting to main coordinator

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default to main coordinator at 10.9.66.90
COORDINATOR_HOST="${COORDINATOR_HOST:-http://10.9.66.90:8001}"
NODE_TYPE="${NODE_TYPE:-cpu}"
NODE_PORT="${NODE_PORT:-8002}"
OLLAMA_PORT="${OLLAMA_PORT:-11434}"

# Quick deployment mode by default
QUICK_MODE="${QUICK_MODE:-false}"

# Function to print colored output
print_color() {
    color=$1
    message=$2
    echo -e "${color}${message}${NC}"
}

# Function to check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to install Ollama
install_ollama() {
    print_color "$YELLOW" "📦 Installing and configuring Ollama..."
    
    if command_exists ollama; then
        print_color "$GREEN" "✅ Ollama already installed"
    else
        # Install Ollama
        curl -fsSL https://ollama.ai/install.sh | sh
    fi
    
    # Configure Ollama for network access
    print_color "$YELLOW" "Configuring Ollama for network access..."
    
    # Create systemd override directory
    sudo mkdir -p /etc/systemd/system/ollama.service.d/
    
    # Create override config for network access
    sudo tee /etc/systemd/system/ollama.service.d/override.conf > /dev/null <<EOF
[Service]
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF
    
    # Reload and restart Ollama
    sudo systemctl daemon-reload
    sudo systemctl enable ollama
    sudo systemctl restart ollama
    
    # Wait for Ollama to start
    sleep 3
    
    # Verify it's listening on network
    if netstat -tln | grep -q "0.0.0.0:11434"; then
        print_color "$GREEN" "✅ Ollama configured for network access"
    else
        print_color "$YELLOW" "⚠️ Ollama may not be accessible over network"
        print_color "$YELLOW" "   Try: OLLAMA_HOST=0.0.0.0:11434 ollama serve"
    fi
    
    print_color "$GREEN" "✅ Ollama installed and configured"
}

# Function to setup Python environment
setup_python() {
    print_color "$YELLOW" "🐍 Setting up Python environment..."
    
    # Check Python version
    if ! command_exists python3; then
        print_color "$RED" "❌ Python 3 not found. Please install Python 3.8+"
        exit 1
    fi
    
    # Ensure we're in the hydra_node directory
    mkdir -p ~/hydra_node
    cd ~/hydra_node
    
    # Create virtual environment if it doesn't exist
    if [ ! -d "venv" ]; then
        python3 -m venv venv
        print_color "$GREEN" "✅ Virtual environment created"
    else
        print_color "$GREEN" "✅ Virtual environment already exists"
    fi
    
    # Activate virtual environment
    if [ -f "venv/bin/activate" ]; then
        source venv/bin/activate
    else
        print_color "$RED" "❌ Failed to find venv activation script"
        exit 1
    fi
    
    # Install dependencies
    pip install --upgrade pip
    pip install fastapi uvicorn httpx psutil loguru pydantic PyYAML
    
    print_color "$GREEN" "✅ Python environment ready"
}

# Function to download node agent
download_agent() {
    print_color "$YELLOW" "📥 Downloading node agent..."
    
    # Create directory for Hydra
    mkdir -p ~/hydra_node
    cd ~/hydra_node
    
    # Always copy the latest version from hydra if available
    if [ -f "$HOME/hydra/node_agent.py" ]; then
        cp "$HOME/hydra/node_agent.py" .
        print_color "$GREEN" "✅ Copied latest node_agent.py from ~/hydra/"
    elif [ -f "../node_agent.py" ]; then
        cp ../node_agent.py .
        print_color "$GREEN" "✅ Copied node_agent.py from parent directory"
    elif [ -f "../../node_agent.py" ]; then
        cp ../../node_agent.py .
        print_color "$GREEN" "✅ Copied node_agent.py from hydra root"
    else
        # Check if we already have it
        if [ -f "node_agent.py" ]; then
            print_color "$YELLOW" "⚠️  Using existing node_agent.py (may be outdated)"
            print_color "$YELLOW" "    To update: cp ~/hydra/node_agent.py ~/hydra_node/"
        else
            print_color "$RED" "❌ node_agent.py not found!"
            print_color "$YELLOW" "    From the hydra directory run:"
            print_color "$YELLOW" "    cp node_agent.py ~/hydra_node/"
        fi
    fi
    
    # Also copy memory_manager.py if available
    if [ -f "$HOME/hydra/core/memory_manager.py" ]; then
        mkdir -p core
        cp "$HOME/hydra/core/memory_manager.py" core/
        print_color "$GREEN" "✅ Copied memory_manager.py"
    fi
    
    print_color "$GREEN" "✅ Node agent setup complete"
}

# Function to configure node
configure_node() {
    print_color "$YELLOW" "⚙️  Configuring node..."
    
    # Ensure we're in the hydra_node directory
    cd ~/hydra_node
    
    # Get node ID (hostname by default)
    NODE_ID="${NODE_ID:-$(hostname)}"
    
    # Detect if GPU is available
    if command_exists nvidia-smi && nvidia-smi > /dev/null 2>&1; then
        NODE_TYPE="gpu"
        print_color "$GREEN" "🎮 GPU detected, setting node type to GPU"
    fi
    
    # Create configuration file
    cat > node_config.json <<EOF
{
    "node_id": "$NODE_ID",
    "node_type": "$NODE_TYPE",
    "coordinator_host": "$COORDINATOR_HOST",
    "ollama_host": "http://localhost:$OLLAMA_PORT",
    "port": $NODE_PORT,
    "max_concurrent_tasks": 3
}
EOF
    
    print_color "$GREEN" "✅ Node configured"
    echo "Node ID: $NODE_ID"
    echo "Type: $NODE_TYPE"
    echo "Coordinator: $COORDINATOR_HOST"
}

# Function to create systemd service
create_service() {
    print_color "$YELLOW" "🔧 Creating systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/hydra-node.service"
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Hydra Node Agent
After=network.target ollama.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/hydra_node
Environment="NODE_ID=$NODE_ID"
Environment="NODE_TYPE=$NODE_TYPE"
Environment="COORDINATOR_HOST=$COORDINATOR_HOST"
Environment="NODE_PORT=$NODE_PORT"
ExecStart=$HOME/hydra_node/venv/bin/python node_agent.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    # Reload systemd and enable service
    sudo systemctl daemon-reload
    sudo systemctl enable hydra-node
    
    print_color "$GREEN" "✅ Systemd service created"
}

# Function to pull common models
pull_models() {
    print_color "$YELLOW" "📥 Pulling common models..."
    
    # Wait for Ollama to be ready
    sleep 5
    
    # Check if Ollama is running
    if ! command_exists ollama; then
        print_color "$RED" "❌ Ollama not found. Please install Ollama first"
        return 1
    fi
    
    # Pull lightweight models suitable for CPU nodes
    if [ "$NODE_TYPE" == "cpu" ]; then
        print_color "$YELLOW" "Pulling CPU-optimized models..."
        ollama pull tinyllama || print_color "$YELLOW" "⚠️  Failed to pull tinyllama"
        ollama pull phi || print_color "$YELLOW" "⚠️  Failed to pull phi"
        ollama pull gemma:2b || print_color "$YELLOW" "⚠️  Failed to pull gemma:2b"
        ollama pull qwen2.5:1.5b || print_color "$YELLOW" "⚠️  Failed to pull qwen2.5:1.5b"
    else
        # GPU nodes can handle larger models
        print_color "$YELLOW" "Pulling GPU-optimized models..."
        ollama pull llama2:7b || print_color "$YELLOW" "⚠️  Failed to pull llama2:7b"
        ollama pull codellama:7b || print_color "$YELLOW" "⚠️  Failed to pull codellama:7b"
        ollama pull mistral:7b || print_color "$YELLOW" "⚠️  Failed to pull mistral:7b"
        ollama pull qwen2.5-coder:7b || print_color "$YELLOW" "⚠️  Failed to pull qwen2.5-coder:7b"
    fi
    
    print_color "$GREEN" "✅ Models pulled (or attempted)"
}

# Function to start node agent
start_node() {
    print_color "$YELLOW" "🚀 Starting node agent..."
    
    # Ensure we're in the hydra_node directory
    cd ~/hydra_node
    
    if [ -f "/etc/systemd/system/hydra-node.service" ]; then
        sudo systemctl start hydra-node
        print_color "$GREEN" "✅ Node agent started as service"
        print_color "$YELLOW" "View logs with: sudo journalctl -u hydra-node -f"
    else
        # Check if node_agent.py exists
        if [ ! -f "node_agent.py" ]; then
            print_color "$RED" "❌ node_agent.py not found! Please run full setup (option 1) first"
            return 1
        fi
        
        # Run directly
        if [ -f "venv/bin/activate" ]; then
            source venv/bin/activate
        else
            print_color "$RED" "❌ Virtual environment not found! Please run full setup (option 1) first"
            return 1
        fi
        
        print_color "$GREEN" "Starting node agent in foreground..."
        print_color "$YELLOW" "Press Ctrl+C to stop"
        
        # Run in foreground so user can see output
        python node_agent.py \
            --node-id "$NODE_ID" \
            --type "$NODE_TYPE" \
            --port $NODE_PORT \
            --coordinator "$COORDINATOR_HOST"
    fi
}

# Function to stop node agent
stop_node() {
    print_color "$YELLOW" "🛑 Stopping node agent..."
    
    if [ -f "/etc/systemd/system/hydra-node.service" ]; then
        sudo systemctl stop hydra-node
    else
        pkill -f "node_agent.py" || true
    fi
    
    print_color "$GREEN" "✅ Node agent stopped"
}

# Function to show node status
show_status() {
    print_color "$YELLOW" "📊 Node Status:"
    
    if [ -f "/etc/systemd/system/hydra-node.service" ]; then
        sudo systemctl status hydra-node --no-pager
    fi
    
    # Check if agent is responding
    if curl -s "http://localhost:$NODE_PORT/health" > /dev/null 2>&1; then
        print_color "$GREEN" "✅ Agent is responding"
        curl -s "http://localhost:$NODE_PORT/status" | python3 -m json.tool
    else
        print_color "$RED" "❌ Agent is not responding"
    fi
}

# Function for quick deployment
quick_deploy() {
    print_color "$GREEN" "╔══════════════════════════════════════╗"
    print_color "$GREEN" "║   🚀 Hydra Quick Worker Deployment   ║"
    print_color "$GREEN" "╚══════════════════════════════════════╝"
    print_color "$BLUE" "Coordinator: $COORDINATOR_HOST"
    print_color "$BLUE" "Node Type: $NODE_TYPE"
    echo ""
    
    # Run all setup steps automatically
    print_color "$YELLOW" "Starting rapid deployment..."
    
    install_ollama
    setup_python
    download_agent
    configure_node
    
    # Skip model pulling - let host request models dynamically
    print_color "$YELLOW" "📥 Skipping model downloads - will pull dynamically as needed"
    
    create_service
    start_node
    
    # Test connection to coordinator
    sleep 3
    if curl -s "http://localhost:$NODE_PORT/health" > /dev/null 2>&1; then
        print_color "$GREEN" "✅ Worker node is running!"
        print_color "$GREEN" "✅ Connected to coordinator at $COORDINATOR_HOST"
        
        # Show node info
        echo ""
        print_color "$BLUE" "Node Information:"
        curl -s "http://localhost:$NODE_PORT/status" | python3 -m json.tool 2>/dev/null | head -20
    else
        print_color "$YELLOW" "⚠️ Node started but health check failed"
    fi
    
    print_color "$GREEN" ""
    print_color "$GREEN" "✅ Worker deployment complete!"
    print_color "$YELLOW" "View logs: sudo journalctl -u hydra-node -f"
}

# Main menu
show_menu() {
    echo ""
    print_color "$GREEN" "╔══════════════════════════════════════╗"
    print_color "$GREEN" "║    🐉 Hydra Worker Node Setup        ║"
    print_color "$GREEN" "╚══════════════════════════════════════╝"
    print_color "$BLUE" "Coordinator: $COORDINATOR_HOST"
    echo ""
    echo "1) Quick Deploy (Recommended)"
    echo "2) Full Setup (Install everything)"
    echo "3) Install Ollama only"
    echo "4) Setup Python environment"
    echo "5) Configure node"
    echo "6) Pull models"
    echo "7) Start node agent"
    echo "8) Stop node agent"
    echo "9) Show status"
    echo "0) Exit"
    echo ""
}

# Parse command line arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --coordinator)
            COORDINATOR_HOST="$2"
            shift 2
            ;;
        --type)
            NODE_TYPE="$2"
            shift 2
            ;;
        --port)
            NODE_PORT="$2"
            shift 2
            ;;
        --node-id)
            NODE_ID="$2"
            shift 2
            ;;
        --auto)
            AUTO_SETUP=true
            shift
            ;;
        --quick|-q)
            QUICK_MODE=true
            shift
            ;;
        --help|-h)
            echo "Hydra Worker Node Deployment Script"
            echo ""
            echo "Usage: ./deploy_node.sh [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --quick, -q              Quick deployment mode (fastest)"
            echo "  --auto                   Automatic full setup"
            echo "  --coordinator URL        Coordinator URL (default: http://10.9.66.90:8001)"
            echo "  --type TYPE              Node type: cpu/gpu (default: cpu)"
            echo "  --node-id ID             Node identifier (default: hostname)"
            echo "  --help, -h               Show this help"
            echo ""
            echo "Quick deployment for worker:"
            echo "  ./deploy_node.sh --quick"
            echo ""
            echo "Custom coordinator:"
            echo "  ./deploy_node.sh --quick --coordinator http://192.168.1.100:8001"
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Quick mode takes precedence
if [ "$QUICK_MODE" = true ]; then
    quick_deploy
    exit 0
fi

# Auto setup if requested
if [ "$AUTO_SETUP" = true ]; then
    print_color "$GREEN" "🚀 Running automatic setup..."
    install_ollama
    setup_python
    download_agent
    configure_node
    pull_models
    create_service
    start_node
    show_status
    print_color "$GREEN" "✅ Automatic setup complete!"
    exit 0
fi

# Interactive menu
while true; do
    show_menu
    read -p "Select an option: " choice
    
    case $choice in
        1)
            quick_deploy
            exit 0
            ;;
        2)
            install_ollama
            setup_python
            download_agent
            configure_node
            pull_models
            print_color "$GREEN" "✅ Full setup complete!"
            print_color "$YELLOW" ""
            print_color "$YELLOW" "Next steps:"
            print_color "$YELLOW" "  7 - Start the node agent now"
            print_color "$YELLOW" "  0 - Exit and start manually later"
            print_color "$YELLOW" ""
            read -p "What would you like to do? (7/0): " next_choice
            if [ "$next_choice" = "7" ]; then
                start_node
                exit 0
            elif [ "$next_choice" = "0" ]; then
                print_color "$GREEN" "Setup complete! Start the agent later with:"
                print_color "$GREEN" "  cd ~/hydra_node && source venv/bin/activate && python node_agent.py"
                exit 0
            fi
            ;;
        3)
            install_ollama
            print_color "$GREEN" "✅ Done!"
            ;;
        4)
            setup_python
            print_color "$GREEN" "✅ Done!"
            ;;
        5)
            configure_node
            print_color "$GREEN" "✅ Done!"
            ;;
        6)
            pull_models
            print_color "$GREEN" "✅ Done!"
            ;;
        7)
            start_node
            # Don't return to menu when starting node
            exit 0
            ;;
        8)
            stop_node
            print_color "$GREEN" "✅ Done!"
            ;;
        9)
            show_status
            ;;
        0|q|Q|exit|quit)
            print_color "$GREEN" "👋 Goodbye!"
            exit 0
            ;;
        *)
            print_color "$RED" "Invalid option"
            sleep 1
            continue
            ;;
    esac
    
    # Only show "Press Enter" for operations that should return to menu
    if [ "$choice" != "1" ] && [ "$choice" != "6" ]; then
        echo ""
        read -p "Press Enter to return to menu..."
    fi
done