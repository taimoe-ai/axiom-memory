-- Procedural memory: how-to workflows and behavioural rules ("when X, do Y"),
-- as opposed to declarative facts. Content convention (enforced by client
-- instructions, not schema): a trigger condition, the steps, and a one-line
-- why. Procedural memories decay slower than everything else in recall
-- ranking — skills stay valid even when unused (see MemoryStore.recall).

ALTER TABLE memories DROP CONSTRAINT memories_type_check;
ALTER TABLE memories ADD CONSTRAINT memories_type_check
    CHECK (type IN ('preference', 'fact', 'project', 'state', 'reference', 'procedural'));
