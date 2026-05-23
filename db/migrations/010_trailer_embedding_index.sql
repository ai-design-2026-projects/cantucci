-- Add IVFFlat index for trailer_embedding to support fast vector similarity search.
-- Partial index (WHERE trailer_embedding IS NOT NULL) matches the pattern used for
-- review_embedding and avoids indexing the many rows with no trailer.
CREATE INDEX IF NOT EXISTS movies_trailer_embedding_idx
    ON movies USING ivfflat (trailer_embedding vector_cosine_ops) WITH (lists = 100)
    WHERE trailer_embedding IS NOT NULL;
