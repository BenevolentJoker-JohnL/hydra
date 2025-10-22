-- Quick fix: Just update the password
ALTER USER hydra WITH PASSWORD 'hydra_password';

-- Ensure database exists and is owned by hydra
ALTER DATABASE hydra_db OWNER TO hydra;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE hydra_db TO hydra;