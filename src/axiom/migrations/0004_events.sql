-- Episodic layer: cheap, append-only, one-line ambient events ("asked about
-- miso soup", "discussed Gemini Enterprise architecture"). Deliberately
-- separate from memories: no name, no curation, no dedup screening, never
-- part of recall ranking. Their only reader is `axiom review`, which clusters
-- recent events by trigram similarity and reports recurring patterns as
-- promotion candidates for a real memory. Old events are pruned on write
-- (see MemoryStore.log_event) — this layer is designed to forget.

CREATE TABLE events (
    id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    -- One short line describing what happened, absolute wording.
    content     TEXT NOT NULL CHECK (length(content) BETWEEN 1 AND 500),
    -- Which client logged it (claude-code, chatgpt, gemini-cli, ...).
    source_app  TEXT NOT NULL DEFAULT 'unknown',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX events_trgm_idx ON events USING GIN (content gin_trgm_ops);
CREATE INDEX events_created_at_idx ON events (created_at);
