-- Memory association: let a memory point to related memories by name, so recall
-- results can suggest neighbours the caller may also want to pull. Names are not
-- foreign-keyed on purpose — a link may be written before its target exists, and
-- a forgotten target should not block writes. Empty array means no links.
ALTER TABLE memories
    ADD COLUMN related TEXT[] NOT NULL DEFAULT '{}';
