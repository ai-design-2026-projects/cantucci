ALTER TABLE messages
    ADD COLUMN cost_usd FLOAT NOT NULL DEFAULT 0.0;

ALTER TABLE conversations
    ADD COLUMN accumulated_cost_usd FLOAT NOT NULL DEFAULT 0.0;
