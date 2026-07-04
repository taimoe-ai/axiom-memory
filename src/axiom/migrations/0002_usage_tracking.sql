-- Retrieval strengthens memory (Hebbian): track how often and how recently each
-- memory is recalled. This is the substrate for later ranking decay (retrieval-
-- based forgetting) and consolidation. Deliberately distinct from updated_at
-- (content last changed) and created_at (first stored): a memory can be recalled
-- often without its content ever changing.
ALTER TABLE memories
    ADD COLUMN use_count    INT NOT NULL DEFAULT 0,
    -- NULL means never recalled yet; distinguishes "cold" from "used once".
    ADD COLUMN last_used_at TIMESTAMPTZ;
