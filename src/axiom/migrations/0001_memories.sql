-- Core memories table. Postgres is the source of truth; markdown exports are
-- a generated, read-only mirror (see axiom.export).

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE memories (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- Stable kebab-case slug; the public identifier used by update/forget.
    name        TEXT NOT NULL UNIQUE CHECK (name ~ '^[a-z0-9][a-z0-9-]{1,63}$'),
    -- One-line summary used for relevance decisions during recall.
    description TEXT NOT NULL,
    -- The fact itself, markdown. A curated statement, not a conversation log.
    content     TEXT NOT NULL,
    -- preference: durable taste/style. fact: durable personal fact.
    -- project: ongoing work context. state: expected to go stale (tools,
    -- versions, current setup). reference: pointer to an external resource.
    type        TEXT NOT NULL CHECK (type IN ('preference', 'fact', 'project', 'state', 'reference')),
    -- Which client wrote it (claude-code, chatgpt, gemini-cli, ...).
    source_app  TEXT NOT NULL DEFAULT 'unknown',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- 'simple' config: no language stemming, works acceptably for mixed
    -- English/Chinese content; trigram search below covers CJK substrings.
    search      tsvector GENERATED ALWAYS AS (
        to_tsvector('simple', name || ' ' || description || ' ' || content)
    ) STORED
);

CREATE INDEX memories_search_idx ON memories USING GIN (search);
CREATE INDEX memories_trgm_idx ON memories
    USING GIN ((name || ' ' || description || ' ' || content) gin_trgm_ops);
