-- Fix PostgreSQL setup for Hydra
ALTER USER hydra WITH PASSWORD 'hydra_password';

-- Create database if not exists
SELECT 'CREATE DATABASE hydra_db OWNER hydra'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'hydra_db')\gexec

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;

-- Connect to hydra_db and create extensions
\c hydra_db

-- Create extensions if not exists
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO hydra;

-- Show confirmation
\echo 'PostgreSQL setup complete!'
\echo 'User: hydra'
\echo 'Database: hydra_db'
\echo 'Password: hydra_password'