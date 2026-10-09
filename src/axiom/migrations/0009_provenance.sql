-- Provenance: whether a memory is something the user said ('stated') or a
-- conclusion an AI drew from indirect evidence ('inferred'). Inferred
-- memories rank lower in recall and come back labelled, so a client treats
-- them as hypotheses to confirm rather than as facts about the user.
-- Existing memories cannot be audited after the fact and are backfilled as
-- 'stated'.

ALTER TABLE memories ADD COLUMN provenance TEXT NOT NULL DEFAULT 'stated'
    CHECK (provenance IN ('stated', 'inferred'));

ALTER TABLE memory_versions ADD COLUMN provenance TEXT NOT NULL DEFAULT 'stated';

CREATE OR REPLACE FUNCTION memories_snapshot() RETURNS trigger AS $$
BEGIN
    INSERT INTO memory_versions
        (name, description, content, type, category, source_app, related,
         provenance, written_at, reason)
    VALUES
        (OLD.name, OLD.description, OLD.content, OLD.type, OLD.category,
         OLD.source_app, OLD.related, OLD.provenance, OLD.updated_at,
         CASE TG_OP WHEN 'DELETE' THEN 'forgotten' ELSE 'updated' END);
    RETURN NULL;
END;
$$ LANGUAGE plpgsql;

-- Confirming an inferred memory (inferred -> stated) changes what it claims,
-- so it is versioned like a content change.
DROP TRIGGER memories_snapshot_on_update ON memories;
CREATE TRIGGER memories_snapshot_on_update
    AFTER UPDATE ON memories
    FOR EACH ROW
    WHEN (OLD.description IS DISTINCT FROM NEW.description
          OR OLD.content IS DISTINCT FROM NEW.content
          OR OLD.type IS DISTINCT FROM NEW.type
          OR OLD.category IS DISTINCT FROM NEW.category
          OR OLD.provenance IS DISTINCT FROM NEW.provenance)
    EXECUTE FUNCTION memories_snapshot();
