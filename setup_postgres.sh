#!/bin/bash

echo "🐉 Hydra PostgreSQL Setup"
echo "========================"

# Check if PostgreSQL is installed
if ! command -v psql &> /dev/null; then
    echo "PostgreSQL not found. Installing..."
    sudo apt update
    sudo apt install -y postgresql postgresql-contrib
fi

echo "Setting up PostgreSQL database and user..."

# Create database and user
sudo -u postgres psql << EOF
-- Create user
CREATE USER hydra WITH PASSWORD 'hydra_password';

-- Create database
CREATE DATABASE hydra_db OWNER hydra;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;

-- Connect to hydra_db and create extensions
\c hydra_db
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Show created databases and users
\l
\du
EOF

echo ""
echo "PostgreSQL setup complete!"
echo ""
echo "Database Details:"
echo "  Database: hydra_db"
echo "  User: hydra"
echo "  Password: hydra_password"
echo "  Host: localhost"
echo "  Port: 5432"
echo ""
echo "Creating .env file with database credentials..."

# Create .env file
cat > .env << 'EOL'
# Database Configuration
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=hydra
POSTGRES_PASSWORD=hydra_password
POSTGRES_DB=hydra_db

REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

SQLITE_PATH=./data/hydra.db
CHROMA_PATH=./data/chroma

# Ollama Configuration
OLLAMA_HOST=http://localhost:11434

# Node Configuration (update with your actual IPs)
GPU_NODE_HOST=localhost
CPU_NODE_1_HOST=localhost
CPU_NODE_2_HOST=localhost
CPU_NODE_3_HOST=localhost

# Logging
LOG_LEVEL=INFO
EOL

echo ".env file created successfully!"
echo ""
echo "Next steps:"
echo "1. Ensure Redis is running: sudo systemctl start redis-server"
echo "2. Ensure Ollama is running: ollama serve"
echo "3. Update CPU_NODE_* hosts in .env if using distributed nodes"
echo "4. Run: python main.py api"