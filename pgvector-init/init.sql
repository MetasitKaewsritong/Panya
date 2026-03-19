CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS documents (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    metadata JSONB,
    collection VARCHAR(255) NOT NULL,
    hash VARCHAR(64) UNIQUE NOT NULL,
    embedding VECTOR(1024),
    document_source VARCHAR(1024) NOT NULL DEFAULT '',
    page_number INTEGER NOT NULL DEFAULT 0,
    brand VARCHAR(255) NOT NULL DEFAULT '',
    model_subbrand VARCHAR(255) NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_hnsw_embedding ON documents USING hnsw (embedding vector_l2_ops);
CREATE INDEX IF NOT EXISTS idx_collection ON documents (collection);
CREATE INDEX IF NOT EXISTS idx_documents_lookup ON documents (collection, document_source, page_number);
CREATE INDEX IF NOT EXISTS idx_documents_brand_model ON documents (brand, model_subbrand);

CREATE TABLE IF NOT EXISTS pdf_pages (
    id SERIAL PRIMARY KEY,
    document_source VARCHAR(1024) NOT NULL,
    page_number INTEGER NOT NULL,
    brand VARCHAR(255) NOT NULL DEFAULT '',
    model_subbrand VARCHAR(255) NOT NULL DEFAULT '',
    collection_name VARCHAR(255) NOT NULL,
    metadata JSONB,
    image_data BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (document_source, page_number, collection_name, brand, model_subbrand)
);

CREATE INDEX IF NOT EXISTS idx_pdf_pages_lookup
ON pdf_pages (collection_name, document_source, page_number, brand, model_subbrand);
