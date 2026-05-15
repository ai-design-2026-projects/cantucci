"""Integration tests for the film-exclusion path through the retrieval system.

Covers, against the real mini-catalogue fixture:
  - ``api.movies.resolve_titles_to_ids`` fuzzy-matches titles and stems
  - ``api.movies.vector_search(exclude_ids=...)`` actually drops the listed IDs
  - ``retrieval.agent.retrieve(exclude_titles=...)`` plumbs everything together

The mini catalogue is small (~200 rows) and content-dependent, so the tests
discover representative titles at runtime rather than hard-coding film names
that may not exist in the artifact.
"""

from __future__ import annotations

import psycopg

from backend.api import movies as api_movies
from backend.retrieval import agent as retrieval_agent


def _sample_title(db_url: str) -> tuple[int, str]:
    """Return any ``(id, title)`` row from the catalogue for use as a test probe."""
    with psycopg.connect(db_url) as conn:
        row = conn.execute(
            "SELECT id, title FROM movies ORDER BY id LIMIT 1"
        ).fetchone()
    assert row is not None, "mini catalogue is empty"
    return int(row[0]), str(row[1])


def _shared_word_title_pair(db_url: str) -> tuple[str, list[int]]:
    """Find a word that appears in >=2 catalogue titles; return (word, matching_ids).

    Falls back to ``None`` results if no shared word exists (highly unlikely in
    a ~200-row mini catalogue but defensive).
    """
    with psycopg.connect(db_url) as conn:
        rows = conn.execute("SELECT id, title FROM movies").fetchall()

    # Build a word → [ids] index; pick the first word with multiple IDs.
    from collections import defaultdict

    index: dict[str, list[int]] = defaultdict(list)
    skip = {"the", "a", "an", "of", "and", "or", "to", "in", "for"}
    for row_id, title in rows:
        for raw in title.split():
            word = "".join(ch for ch in raw if ch.isalnum()).lower()
            if len(word) >= 4 and word not in skip:
                index[word].append(int(row_id))
    for word, ids in index.items():
        if len(ids) >= 2:
            return word, ids
    return "", []


def test_resolve_titles_to_ids_matches_exact_title(db_url: str, mini_catalogue: int) -> None:
    """A full title in the catalogue resolves to (at least) its own ID."""
    movie_id, title = _sample_title(db_url)
    ids = api_movies.resolve_titles_to_ids([title])
    assert movie_id in ids


def test_resolve_titles_to_ids_expands_shared_substring(
    db_url: str, mini_catalogue: int
) -> None:
    """A stem shared by several titles returns every matching catalogue ID."""
    word, expected_ids = _shared_word_title_pair(db_url)
    if not word:
        # The mini catalogue happens to have no shared substantive words.
        return
    ids = api_movies.resolve_titles_to_ids([word])
    for expected in expected_ids:
        assert expected in ids


def test_resolve_titles_to_ids_unknown_returns_empty(
    db_url: str, mini_catalogue: int
) -> None:
    """A bogus title resolves to an empty list (no error)."""
    ids = api_movies.resolve_titles_to_ids(["znotarealtitleq0q0q0"])
    assert ids == []


def test_resolve_titles_to_ids_strips_leading_the(
    db_url: str, mini_catalogue: int
) -> None:
    """A leading ``"The "`` is stripped so titles stored without the article still match."""
    movie_id, title = _sample_title(db_url)
    # Probe the resolver with "The <title>" — the strip-the rule means we
    # search for "%<title>%", which will match the original row.
    ids = api_movies.resolve_titles_to_ids([f"The {title}"])
    assert movie_id in ids


def test_resolve_titles_to_ids_empty_input(db_url: str, mini_catalogue: int) -> None:
    """Empty list short-circuits without hitting the DB."""
    assert api_movies.resolve_titles_to_ids([]) == []
    assert api_movies.resolve_titles_to_ids([""]) == []


def test_vector_search_excludes_ids(db_url: str, mini_catalogue: int) -> None:
    """An ID passed in ``exclude_ids`` is absent from the result set."""
    from backend.settings import get_settings
    import numpy as np

    dim = get_settings().representation.embedding_dim
    probe = np.zeros(dim, dtype=np.float32)
    probe[0] = 1.0

    baseline = api_movies.vector_search(probe, k=5)
    assert baseline, "expected non-empty baseline"
    target_id = baseline[0].movie_id

    filtered = api_movies.vector_search(probe, k=5, exclude_ids=[target_id])
    returned_ids = {h.movie_id for h in filtered}
    assert target_id not in returned_ids


def test_retrieval_agent_excludes_titles_end_to_end(
    db_url: str, mini_catalogue: int
) -> None:
    """retrieval_agent.retrieve with exclude_titles drops matching films from candidates."""
    _, sample_title = _sample_title(db_url)
    result = retrieval_agent.retrieve(
        query="a contemplative film about identity and memory",
        k=10,
        exclude_titles=[sample_title],
    )
    returned_titles = {c.title for c in result.candidates}
    assert sample_title not in returned_titles
    assert result.excluded_films == [sample_title]
    assert result.excluded_movie_ids, "expected fuzzy-match to resolve the sample title"
