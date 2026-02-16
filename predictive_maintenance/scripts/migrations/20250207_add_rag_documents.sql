-- Add pgvector extension and RAG documents table

CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "vector";

CREATE TABLE IF NOT EXISTS pdm_rag_documents (
    id UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    doc_id VARCHAR(32) UNIQUE NOT NULL,
    asset_id VARCHAR(100),
    site_id VARCHAR(100),
    doc_type VARCHAR(50) NOT NULL,
    content TEXT NOT NULL,
    doc_metadata JSONB DEFAULT '{}'::jsonb,
    embedding VECTOR(1536),
    embedding_dim INTEGER DEFAULT 1536,
    created_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW(),
    updated_at TIMESTAMP WITHOUT TIME ZONE DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS ix_pdm_rag_doc_type ON pdm_rag_documents (doc_type);
CREATE INDEX IF NOT EXISTS ix_pdm_rag_asset_type ON pdm_rag_documents (asset_id, doc_type);
CREATE INDEX IF NOT EXISTS ix_pdm_rag_site ON pdm_rag_documents (site_id);
