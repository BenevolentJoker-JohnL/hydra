-- Create database and fix permissions
CREATE DATABASE hydra_db;
ALTER USER hydra WITH PASSWORD 'hydra_password';
ALTER DATABASE hydra_db OWNER TO hydra;
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;

-- Connect to the new database
\c hydra_db

-- Grant schema permissions
GRANT ALL ON SCHEMA public TO hydra;

-- Show confirmation
\echo 'Database created successfully!'