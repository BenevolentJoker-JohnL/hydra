#!/bin/bash

echo "🐉 Fixing Hydra PostgreSQL Setup"
echo "================================="
echo ""
echo "This script will:"
echo "1. Update the hydra user password"
echo "2. Create hydra_db if it doesn't exist"
echo "3. Set proper permissions"
echo ""

# First, let's drop and recreate the user to ensure clean state
sudo -u postgres psql << 'EOF'
-- Drop existing connections to hydra_db if any
SELECT pg_terminate_backend(pid)
FROM pg_stat_activity
WHERE datname = 'hydra_db' AND pid <> pg_backend_pid();

-- Drop user if exists (cascade)
DROP DATABASE IF EXISTS hydra_db;
DROP USER IF EXISTS hydra;

-- Create user with password
CREATE USER hydra WITH PASSWORD 'hydra_password';

-- Create database
CREATE DATABASE hydra_db OWNER hydra;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;

-- Connect to hydra_db
\c hydra_db

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO hydra;

-- Try to create vector extension if available
CREATE EXTENSION IF NOT EXISTS vector;

-- Show results
\du hydra
\l hydra_db
EOF

echo ""
echo "Testing connection with new credentials..."

# Test the connection
export PGPASSWORD='hydra_password'
psql -h localhost -U hydra -d hydra_db -c "SELECT version();" 2>&1

if [ $? -eq 0 ]; then
    echo "✅ PostgreSQL setup successful!"
    echo ""
    echo "Updating .env file..."
    
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
    
    echo "✅ .env file updated"
    echo ""
    echo "You can now run:"
    echo "  python main.py api    # Start API server"
    echo "  python main.py ui     # Start Web UI"
else
    echo "❌ Connection test failed"
    echo ""
    echo "Please check if PostgreSQL is running:"
    echo "  sudo systemctl status postgresql"
    echo ""
    echo "If needed, restart PostgreSQL:"
    echo "  sudo systemctl restart postgresql"
fi