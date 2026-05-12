-- Enable pgvector for VECTOR columns and ANN search.
-- Enable pgcrypto for gen_random_uuid() used as the default PK strategy.
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
