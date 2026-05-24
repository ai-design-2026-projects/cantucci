CREATE TABLE genres (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL UNIQUE
);

CREATE TABLE people (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL
);

CREATE TABLE keywords (
    id   SERIAL PRIMARY KEY,
    name TEXT   NOT NULL UNIQUE
);

CREATE TABLE movies (
    id                INTEGER     PRIMARY KEY,
    title             TEXT        NOT NULL,
    original_title    TEXT,
    release_year      INTEGER,
    runtime           FLOAT,
    vote_average      FLOAT,
    vote_count        INTEGER,
    bayesian_rating   FLOAT,
    overview          TEXT,
    tagline           TEXT,
    poster_path       TEXT,
    original_language TEXT,
    composite_text    TEXT,
    reviews_text      TEXT,
    text_embedding        VECTOR(1024),
    review_embedding      VECTOR(1024),
    trailer_youtube_key   TEXT,
    trailer_embedding     VECTOR(1024),
    umap_x            FLOAT,
    umap_y            FLOAT
);

CREATE TABLE movie_genres (
    movie_id  INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    genre_id  INTEGER NOT NULL REFERENCES genres (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE cast_members (
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id  INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    cast_order INTEGER,
    PRIMARY KEY (movie_id, person_id)
);

CREATE TABLE crew_members (
    movie_id  INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    person_id INTEGER NOT NULL REFERENCES people (id) ON DELETE CASCADE,
    job       TEXT    NOT NULL,
    PRIMARY KEY (movie_id, person_id, job)
);

CREATE TABLE movie_keywords (
    movie_id   INTEGER NOT NULL REFERENCES movies (id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords (id) ON DELETE CASCADE,
    PRIMARY KEY (movie_id, keyword_id)
);

CREATE INDEX movies_text_embedding_idx
    ON movies USING ivfflat (text_embedding vector_cosine_ops) WITH (lists = 100);

CREATE INDEX movies_review_embedding_idx
    ON movies USING ivfflat (review_embedding vector_cosine_ops) WITH (lists = 100)
    WHERE review_embedding IS NOT NULL;
