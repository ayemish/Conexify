-- PDM Database Initialization Script
-- Creates necessary extensions and initial schema

-- Extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pg_trgm";
CREATE EXTENSION IF NOT EXISTS "vector";

-- Create test database for testing
SELECT 'CREATE DATABASE pdm_test'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'pdm_test')\gexec

-- Grant permissions
GRANT ALL PRIVILEGES ON DATABASE pdm TO pdm_user;
GRANT ALL PRIVILEGES ON DATABASE pdm_test TO pdm_user;

-- Create indexes for common queries (will be created by SQLAlchemy, but good to have)
-- These are placeholders - actual indexes defined in models.py
