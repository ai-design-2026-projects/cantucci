CREATE TABLE cluster_snapshots (
    id              UUID        PRIMARY KEY DEFAULT gen_random_uuid(),
    conversation_id UUID        REFERENCES conversations (id) ON DELETE CASCADE,
    parent_id       UUID        REFERENCES cluster_snapshots (id) ON DELETE SET NULL,
    operation       TEXT        NOT NULL,
    params          JSONB       NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE clusters (
    id                  UUID    PRIMARY KEY DEFAULT gen_random_uuid(),
    cluster_snapshot_id UUID    NOT NULL REFERENCES cluster_snapshots (id) ON DELETE CASCADE,
    label               TEXT    NOT NULL,
    summary             TEXT,
    exemplar_movie_ids  JSONB   NOT NULL DEFAULT '[]',
    parent_cluster_id   UUID    REFERENCES clusters (id) ON DELETE SET NULL
);

CREATE TABLE cluster_memberships (
    cluster_id  UUID    NOT NULL REFERENCES clusters (id) ON DELETE CASCADE,
    movie_id    INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    probability FLOAT   NOT NULL,
    PRIMARY KEY (cluster_id, movie_id)
);

CREATE INDEX cluster_snapshots_conversation_id_idx ON cluster_snapshots (conversation_id);
CREATE INDEX cluster_memberships_cluster_id_idx    ON cluster_memberships (cluster_id);
CREATE INDEX cluster_memberships_movie_id_idx      ON cluster_memberships (movie_id);
