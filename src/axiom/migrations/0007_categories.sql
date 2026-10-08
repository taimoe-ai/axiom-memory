-- Thematic domain categorization matching Claude's memory model:
-- 'you' (user profile, communication preferences, personal habits),
-- 'people' (colleagues, clients, collaborators, contacts),
-- 'areas' (ongoing projects, products, companies, ventures),
-- 'topics' (domain expertise, workflows, guidelines, investing, technical stacks).

ALTER TABLE memories ADD COLUMN category TEXT;

-- Backfill existing rows:
-- preference -> you
-- project -> areas
-- everything else -> topics
UPDATE memories SET category = CASE
    WHEN type = 'preference' THEN 'you'
    WHEN type = 'project' THEN 'areas'
    ELSE 'topics'
END WHERE category IS NULL;

ALTER TABLE memories ALTER COLUMN category SET NOT NULL;
ALTER TABLE memories ADD CONSTRAINT memories_category_check
    CHECK (category IN ('you', 'people', 'areas', 'topics'));

CREATE INDEX memories_category_idx ON memories (category);
