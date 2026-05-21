-- Allow clusters.label to be NULL so that root clusters ingested from the
-- offline pipeline can be persisted without a label and labeled lazily by
-- the labeling agent on first conversation access.
ALTER TABLE clusters ALTER COLUMN label DROP NOT NULL;
