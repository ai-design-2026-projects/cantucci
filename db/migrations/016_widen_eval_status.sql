-- Widen status columns on eval_sessions and runs from VARCHAR(20) to VARCHAR(40).
-- VARCHAR(20) truncates 'finished_misbehaviour' (22 chars).
ALTER TABLE eval_sessions ALTER COLUMN status TYPE VARCHAR(40);
ALTER TABLE runs ALTER COLUMN status TYPE VARCHAR(40);
ALTER TABLE runs ALTER COLUMN condition TYPE VARCHAR(40);
ALTER TABLE eval_sessions ALTER COLUMN condition TYPE VARCHAR(40);
