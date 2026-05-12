-- Catalogue tables: populated once at ingest time, read-only during session runtime.
-- See docs/specifications/architecture/data_schema.md §Catalogue tables.

-- collections must exist before movies (FK: movies.collection_id → collections.id)
CREATE TABLE collections (
    id            BIGINT  PRIMARY KEY,
    name          TEXT    NOT NULL,
    poster_path   TEXT,
    backdrop_path TEXT
);

CREATE TABLE movies (
    id               BIGINT       PRIMARY KEY,
    imdb_id          VARCHAR(12)  UNIQUE,
    title            TEXT         NOT NULL,
    original_title   TEXT,
    original_language VARCHAR(10),
    overview         TEXT,
    tagline          TEXT,
    release_date     DATE,
    release_year     SMALLINT     GENERATED ALWAYS AS (EXTRACT(YEAR FROM release_date)::SMALLINT) STORED,
    runtime          FLOAT,
    budget           BIGINT,
    revenue          BIGINT,
    popularity       FLOAT,
    vote_average     FLOAT,
    vote_count       INTEGER,
    bayesian_rating  FLOAT,
    status           VARCHAR(30),
    adult            BOOLEAN      DEFAULT FALSE,
    video            BOOLEAN      DEFAULT FALSE,
    poster_path      TEXT,
    homepage         TEXT,
    collection_id    BIGINT       REFERENCES collections(id),
    embedding        VECTOR(384)  NOT NULL
);

CREATE INDEX ON movies USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
CREATE INDEX ON movies (release_year);
CREATE INDEX ON movies (original_language);
CREATE INDEX ON movies (vote_count);

CREATE TABLE genres (
    id    INTEGER     PRIMARY KEY,
    name  VARCHAR(50) NOT NULL
);

CREATE TABLE movie_genres (
    movie_id  BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    genre_id  INTEGER NOT NULL REFERENCES genres(id),
    PRIMARY KEY (movie_id, genre_id)
);

CREATE TABLE people (
    id      BIGINT   PRIMARY KEY,
    name    TEXT     NOT NULL,
    -- 0 = unspecified, 1 = female, 2 = male
    gender  SMALLINT
);

CREATE TABLE cast_members (
    movie_id   BIGINT      NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id  BIGINT      NOT NULL REFERENCES people(id),
    character  TEXT,
    cast_order SMALLINT,
    credit_id  VARCHAR(30),
    PRIMARY KEY (movie_id, person_id, credit_id)
);

CREATE INDEX ON cast_members (person_id);

CREATE TABLE crew_members (
    movie_id   BIGINT      NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    person_id  BIGINT      NOT NULL REFERENCES people(id),
    department VARCHAR(50),
    job        VARCHAR(100),
    credit_id  VARCHAR(30),
    PRIMARY KEY (movie_id, person_id, credit_id)
);

CREATE INDEX ON crew_members (person_id);
CREATE INDEX ON crew_members (job);

CREATE TABLE keywords (
    id    INTEGER PRIMARY KEY,
    name  TEXT    NOT NULL
);

CREATE TABLE movie_keywords (
    movie_id   BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    keyword_id INTEGER NOT NULL REFERENCES keywords(id),
    PRIMARY KEY (movie_id, keyword_id)
);

CREATE TABLE production_companies (
    id    BIGINT PRIMARY KEY,
    name  TEXT   NOT NULL
);

CREATE TABLE movie_companies (
    movie_id   BIGINT NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    company_id BIGINT NOT NULL REFERENCES production_companies(id),
    PRIMARY KEY (movie_id, company_id)
);

CREATE TABLE languages (
    iso_639_1 CHAR(2) PRIMARY KEY,
    name      TEXT    NOT NULL
);

CREATE TABLE movie_spoken_languages (
    movie_id  BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    iso_639_1 CHAR(2) NOT NULL REFERENCES languages(iso_639_1),
    PRIMARY KEY (movie_id, iso_639_1)
);

CREATE TABLE countries (
    iso_3166_1 CHAR(2) PRIMARY KEY,
    name       TEXT    NOT NULL
);

CREATE TABLE movie_countries (
    movie_id   BIGINT  NOT NULL REFERENCES movies(id) ON DELETE CASCADE,
    iso_3166_1 CHAR(2) NOT NULL REFERENCES countries(iso_3166_1),
    PRIMARY KEY (movie_id, iso_3166_1)
);
