-- Semantic recall: pgvector column for Gemini embeddings (768 dims,
-- normalized, cosine). Requires the pgvector extension — the compose db
-- image must be pgvector/pgvector:pg17 (same PostgreSQL major, existing
-- data volume carries over unchanged).
--
-- NULL embedding means "not embedded yet" (written while the embedding API
-- was down, or before this migration): those rows still match lexically and
-- are picked up by `axiom embed`.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE memories ADD COLUMN embedding vector(768);

CREATE INDEX memories_embedding_idx ON memories
    USING hnsw (embedding vector_cosine_ops);
