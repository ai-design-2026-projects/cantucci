CREATE TABLE concepts (
    id         UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    name       TEXT        NOT NULL,
    type       TEXT        NOT NULL CHECK (type IN ('linear_axis', 'prototype')),
    definition JSONB       NOT NULL DEFAULT '{}',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE concept_scores (
    concept_id UUID    NOT NULL REFERENCES concepts (id) ON DELETE CASCADE,
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    score      FLOAT   NOT NULL,
    PRIMARY KEY (concept_id, movie_id)
);

CREATE INDEX concept_scores_concept_id_idx ON concept_scores (concept_id);
