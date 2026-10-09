-- Version history: every content change and every delete snapshots the prior
-- row, so a bad overwrite by any client (several AI apps write to the same
-- store, and same-name `remember` updates in place) or a mistaken `forget`
-- stays recoverable. Done in a trigger rather than in MemoryStore so every
-- write path is covered, manual SQL included.
--
-- Only changes to what a memory says are versioned. Usage bumps (recall),
-- embedding backfills, and `related` edits (including the scrub `forget`
-- runs across other memories) are bookkeeping, not content.

CREATE TABLE memory_versions (
    id             BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    name           TEXT NOT NULL,
    description    TEXT NOT NULL,
    content        TEXT NOT NULL,
    type           TEXT NOT NULL,
    category       TEXT NOT NULL,
    source_app     TEXT NOT NULL,
    related        TEXT[] NOT NULL DEFAULT '{}',
    -- When this version was written (the row's updated_at at the time)...
    written_at     TIMESTAMPTZ NOT NULL,
    -- ...and when it stopped being current, and why.
    superseded_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    reason         TEXT NOT NULL CHECK (reason IN ('updated', 'forgotten'))
);

CREATE INDEX memory_versions_name_idx ON memory_versions (name, superseded_at DESC);

CREATE FUNCTION memories_snapshot() RETURNS trigger AS $$
BEGIN
    INSERT INTO memory_versions
        (name, description, content, type, category, source_app, related,
         written_at, reason)
    VALUES
        (OLD.name, OLD.description, OLD.content, OLD.type, OLD.category,
         OLD.source_app, OLD.related, OLD.updated_at,
         CASE TG_OP WHEN 'DELETE' THEN 'forgotten' ELSE 'updated' END);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memories_snapshot_on_update
    AFTER UPDATE ON memories
    FOR EACH ROW
    WHEN (OLD.description IS DISTINCT FROM NEW.description
          OR OLD.content IS DISTINCT FROM NEW.content
          OR OLD.type IS DISTINCT FROM NEW.type
          OR OLD.category IS DISTINCT FROM NEW.category)
    EXECUTE FUNCTION memories_snapshot();

CREATE TRIGGER memories_snapshot_on_delete
    AFTER DELETE ON memories
    FOR EACH ROW
    EXECUTE FUNCTION memories_snapshot();
