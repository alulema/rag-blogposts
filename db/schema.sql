-- Esquema del vector store del demo RAG (Postgres 16 + pgvector).
-- Fuente única de verdad del schema: lo usan tanto la ingesta (db/dump.sql) como la app.
-- El índice HNSW se crea DESPUÉS de los INSERT en dump.sql (build más rápido).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS chunks (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT        NOT NULL,
    title       TEXT        NOT NULL,
    lang        TEXT        NOT NULL CHECK (lang IN ('en', 'es')),
    published   DATE,
    chunk_index INTEGER     NOT NULL,
    content     TEXT        NOT NULL,
    embedding   vector(384) NOT NULL
);
