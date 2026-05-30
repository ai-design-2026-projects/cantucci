-- Migration 014: persist suggestion text and axis_concept_id on messages
-- Both were previously ephemeral (not stored); this makes them durable across reloads.

ALTER TABLE messages
    ADD COLUMN suggestion TEXT,
    ADD COLUMN axis_concept_id UUID REFERENCES concepts(id) ON DELETE SET NULL;
