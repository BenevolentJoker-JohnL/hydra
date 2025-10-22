#!/bin/bash

# Hydra Host Node Script - Main Coordinator Setup
# This runs on the main PC (10.9.66.90) to coordinate all worker nodes

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Host configuration
HOST_IP="10.9.66.90"
COORDINATOR_PORT="8001"
API_PORT="8000"

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

# Function to setup PostgreSQL and Redis
setup_databases() {
    print_color "$YELLOW" "🗄️  Setting up PostgreSQL and Redis..."
    
    # Install PostgreSQL and Redis if not present
    if ! command_exists psql; then
        print_color "$YELLOW" "Installing PostgreSQL..."
        sudo apt-get update
        sudo apt-get install -y postgresql postgresql-contrib
    fi
    
    if ! command_exists redis-cli; then
        print_color "$YELLOW" "Installing Redis..."
        sudo apt-get install -y redis-server
    fi
    
    # Setup PostgreSQL
    print_color "$YELLOW" "Configuring PostgreSQL..."
    sudo -u postgres psql <<EOF 2>/dev/null || true
CREATE USER hydra WITH PASSWORD 'hydra123';
CREATE DATABASE hydra_db OWNER hydra;
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;
EOF
    
    # Start services
    sudo systemctl enable postgresql redis-server
    sudo systemctl start postgresql redis-server
    
    print_color "$GREEN" "✅ Databases configured"
}

# Function to setup Python environment
setup_python() {
    print_color "$YELLOW" "🐍 Setting up Python environment..."
    
    cd ~/hydra
    
    # Create virtual environment if needed
    if [ ! -d "venv" ]; then
        python3 -m venv venv
    fi
    
    source venv/bin/activate
    
    # Install requirements
    pip install --upgrade pip
    pip install -r requirements.txt
    
    print_color "$GREEN" "✅ Python environment ready"
}

# Function to configure host
configure_host() {
    print_color "$YELLOW" "⚙️  Configuring host node..."
    
    cd ~/hydra
    
    # Create .env file with host configuration
    cat > .env <<EOF
# Hydra Host Configuration
DATABASE_URL=postgresql://hydra:hydra123@localhost/hydra_db
REDIS_URL=redis://localhost:6379
COORDINATOR_PORT=$COORDINATOR_PORT
API_PORT=$API_PORT
HOST_IP=$HOST_IP

# Worker nodes will register here
NODE_REGISTRATION_ENDPOINT=http://$HOST_IP:$COORDINATOR_PORT/nodes/register

# Ollama on this machine (if running)
LOCAL_OLLAMA=http://localhost:11434

# Known worker nodes (will auto-discover more)
# Add your worker IPs here as they come online
WORKER_NODE_1=10.9.66.154
# WORKER_NODE_2=10.9.66.XXX
# WORKER_NODE_3=10.9.66.XXX
# WORKER_NODE_4=10.9.66.XXX
EOF
    
    print_color "$GREEN" "✅ Host configured at $HOST_IP:$COORDINATOR_PORT"
}

# Function to create systemd service for API
create_service() {
    print_color "$YELLOW" "🔧 Creating systemd service..."
    
    SERVICE_FILE="/etc/systemd/system/hydra-host.service"
    
    sudo tee $SERVICE_FILE > /dev/null <<EOF
[Unit]
Description=Hydra Host Node (Main Coordinator)
After=network.target postgresql.service redis-server.service

[Service]
Type=simple
User=$USER
WorkingDirectory=$HOME/hydra
Environment="PATH=$HOME/hydra/venv/bin:$PATH"
ExecStart=$HOME/hydra/venv/bin/python main.py api
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
    
    sudo systemctl daemon-reload
    sudo systemctl enable hydra-host
    
    print_color "$GREEN" "✅ Systemd service created"
}

# Function to start host
start_host() {
    print_color "$YELLOW" "🚀 Starting Hydra host node..."
    
    cd ~/hydra
    
    if [ -f "/etc/systemd/system/hydra-host.service" ]; then
        sudo systemctl start hydra-host
        sleep 3
        
        # Check if running
        if sudo systemctl is-active --quiet hydra-host; then
            print_color "$GREEN" "✅ Hydra host is running!"
            print_color "$BLUE" "   API: http://$HOST_IP:$COORDINATOR_PORT"
            print_color "$BLUE" "   Logs: sudo journalctl -u hydra-host -f"
            
            # Automatically start monitoring in a new terminal if available
            if command -v gnome-terminal > /dev/null 2>&1; then
                gnome-terminal -- bash -c "cd ~/hydra/scripts && python monitor_cluster.py; exec bash" &
                print_color "$GREEN" "📊 Monitor opened in new window!"
            elif command -v xterm > /dev/null 2>&1; then
                xterm -e "cd ~/hydra/scripts && python monitor_cluster.py" &
                print_color "$GREEN" "📊 Monitor opened in new window!"
            else
                print_color "$YELLOW" "📊 To monitor: cd ~/hydra/scripts && python monitor_cluster.py"
            fi
        else
            print_color "$RED" "❌ Failed to start host"
            sudo journalctl -u hydra-host -n 20
        fi
    else
        # Run in foreground for debugging
        print_color "$YELLOW" "Running in foreground mode..."
        source venv/bin/activate
        python main.py api
    fi
}

# Function to show status
show_status() {
    print_color "$YELLOW" "📊 Host Status:"
    echo ""
    
    # Check services
    print_color "$BLUE" "Services:"
    echo -n "  PostgreSQL: "
    if systemctl is-active --quiet postgresql; then
        print_color "$GREEN" "✓ Running"
    else
        print_color "$RED" "✗ Stopped"
    fi
    
    echo -n "  Redis: "
    if systemctl is-active --quiet redis-server; then
        print_color "$GREEN" "✓ Running"
    else
        print_color "$RED" "✗ Stopped"
    fi
    
    echo -n "  Hydra API: "
    if curl -s "http://localhost:$COORDINATOR_PORT/health" > /dev/null 2>&1; then
        print_color "$GREEN" "✓ Running"
    else
        print_color "$RED" "✗ Not responding"
    fi
    
    # Show connected nodes
    echo ""
    print_color "$BLUE" "Connected Nodes:"
    if curl -s "http://localhost:$COORDINATOR_PORT/nodes" > /dev/null 2>&1; then
        curl -s "http://localhost:$COORDINATOR_PORT/nodes" | python3 -m json.tool 2>/dev/null || echo "  No nodes connected yet"
    else
        echo "  API not available"
    fi
    
    # Network info
    echo ""
    print_color "$BLUE" "Network Configuration:"
    echo "  Host IP: $HOST_IP"
    echo "  API Port: $COORDINATOR_PORT"
    echo "  Registration URL: http://$HOST_IP:$COORDINATOR_PORT/nodes/register"
}

# Function to monitor cluster
monitor_cluster() {
    print_color "$YELLOW" "📊 Starting cluster monitor..."
    cd ~/hydra/scripts
    
    if [ -f "monitor_cluster.py" ]; then
        source ../venv/bin/activate
        python monitor_cluster.py
    else
        print_color "$RED" "Monitor script not found"
    fi
}

# Function to deploy to worker
deploy_to_worker() {
    WORKER_IP=$1
    
    if [ -z "$WORKER_IP" ]; then
        read -p "Enter worker IP address: " WORKER_IP
    fi
    
    print_color "$YELLOW" "🚀 Deploying to worker $WORKER_IP..."
    
    # Copy deployment script to worker
    print_color "$BLUE" "Copying files to $WORKER_IP..."
    ssh $USER@$WORKER_IP "mkdir -p ~/hydra_deploy"
    scp ~/hydra/scripts/deploy_node.sh $USER@$WORKER_IP:~/hydra_deploy/
    scp ~/hydra/node_agent.py $USER@$WORKER_IP:~/hydra_deploy/
    
    # Run deployment on worker
    print_color "$BLUE" "Running deployment on $WORKER_IP..."
    ssh $USER@$WORKER_IP "cd ~/hydra_deploy && chmod +x deploy_node.sh && ./deploy_node.sh --auto --coordinator http://$HOST_IP:$COORDINATOR_PORT"
    
    print_color "$GREEN" "✅ Worker $WORKER_IP deployed"
}

# Main menu
show_menu() {
    echo ""
    print_color "$GREEN" "╔══════════════════════════════════════╗"
    print_color "$GREEN" "║    🐉 Hydra Host Node Manager        ║"
    print_color "$GREEN" "║         Main PC: $HOST_IP         ║"
    print_color "$GREEN" "╚══════════════════════════════════════╝"
    echo ""
    echo "1) Quick Setup (Everything)"
    echo "2) Start Host Services"
    echo "3) Stop Host Services"
    echo "4) Show Status"
    echo "5) Monitor Cluster"
    echo "6) Deploy to Worker Node"
    echo "7) Setup Databases Only"
    echo "8) Configure Host Only"
    echo "9) View Logs"
    echo "0) Exit"
    echo ""
}

# Parse command line arguments
case "${1:-}" in
    start)
        start_host
        exit 0
        ;;
    stop)
        sudo systemctl stop hydra-host
        print_color "$GREEN" "✅ Host stopped"
        exit 0
        ;;
    status)
        show_status
        exit 0
        ;;
    monitor)
        monitor_cluster
        exit 0
        ;;
    deploy)
        deploy_to_worker "$2"
        exit 0
        ;;
    quick)
        print_color "$GREEN" "🚀 Running quick setup..."
        setup_databases
        setup_python
        configure_host
        create_service
        start_host
        show_status
        print_color "$GREEN" "✅ Host setup complete!"
        print_color "$YELLOW" ""
        print_color "$YELLOW" "Next steps:"
        print_color "$YELLOW" "1. Deploy to workers: ./host_node.sh deploy <WORKER_IP>"
        print_color "$YELLOW" "2. Monitor cluster: ./host_node.sh monitor"
        exit 0
        ;;
esac

# Interactive menu
while true; do
    show_menu
    read -p "Select an option: " choice
    
    case $choice in
        1)
            setup_databases
            setup_python
            configure_host
            create_service
            start_host
            show_status
            print_color "$GREEN" "✅ Complete setup done!"
            ;;
        2)
            start_host
            ;;
        3)
            sudo systemctl stop hydra-host
            print_color "$GREEN" "✅ Host stopped"
            ;;
        4)
            show_status
            ;;
        5)
            monitor_cluster
            exit 0
            ;;
        6)
            deploy_to_worker
            ;;
        7)
            setup_databases
            ;;
        8)
            configure_host
            ;;
        9)
            print_color "$YELLOW" "📜 Viewing logs (Ctrl+C to exit)..."
            sudo journalctl -u hydra-host -f
            ;;
        0|q|Q)
            print_color "$GREEN" "👋 Goodbye!"
            exit 0
            ;;
        *)
            print_color "$RED" "Invalid option"
            ;;
    esac
    
    if [ "$choice" != "5" ] && [ "$choice" != "9" ]; then
        echo ""
        read -p "Press Enter to continue..."
    fi
done