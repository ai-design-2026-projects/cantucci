"""Integration tests for the film-exclusion path through the retrieval system.

Covers, against the real mini-catalogue fixture:
  - ``api.movies.resolve_titles_to_ids`` fuzzy-matches titles and stems
  - ``api.movies.vector_search(exclude_ids=...)`` actually drops the listed IDs
  - ``retrieval.agent.retrieve`` plumbs reformulator exclusions through end-to-end

The mini catalogue is small (~200 rows) and content-dependent, so the tests
discover representative titles at runtime rather than hard-coding film names
that may not exist in the artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import psycopg

from backend.api import movies as api_movies
from backend.retrieval import agent as retrieval_agent
from backend.retrieval.types import ReformulatedQuery


def _sample_title(db_url: str) -> tuple[int, str]:
    """Return any ``(id, title)`` row from the catalogue for use as a test probe."""
    with psycopg.connect(db_url) as conn:
        row = conn.execute(
            "SELECT id, title FROM movies ORDER BY id LIMIT 1"
        ).fetchone()
    assert row is not None, "mini catalogue is empty"
    return int(row[0]), str(row[1])


def _sample_movie_ids(db_url: str, limit: int = 2) -> list[int]:
    """Return a few catalogue IDs in deterministic order."""
    with psycopg.connect(db_url) as conn:
        rows = conn.execute(
            "SELECT id FROM movies ORDER BY id LIMIT %s",
            (limit,),
        ).fetchall()
    ids = [int(row[0]) for row in rows]
    assert len(ids) == limit, "mini catalogue has fewer rows than expected"
    return ids


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


def test_vector_search_rejects_non_positive_k() -> None:
    """Invalid k values fail before any catalogue query runs."""
    for k in (0, -1):
        try:
            api_movies.vector_search([0.0], k=k)
        except ValueError as exc:
            assert f"k must be positive, got {k}" in str(exc)
        else:
            raise AssertionError("expected ValueError")


def test_fetch_metadata_empty_input_returns_empty() -> None:
    """Empty metadata requests short-circuit without DB work."""
    assert api_movies.fetch_metadata([]) == []


def test_fetch_metadata_preserves_order_and_omits_missing(
    db_url: str,
    mini_catalogue: int,
) -> None:
    """Metadata rows follow requested ID order and silently skip unknown IDs."""
    first, second = _sample_movie_ids(db_url, limit=2)

    result = api_movies.fetch_metadata([second, -1, first])

    assert [movie.movie_id for movie in result] == [second, first]


def test_fetch_embeddings_empty_input_returns_empty() -> None:
    """Empty embedding requests short-circuit without DB work."""
    assert api_movies.fetch_embeddings([]) == {}


def test_fetch_embeddings_returns_only_present_requested_ids(
    db_url: str,
    mini_catalogue: int,
) -> None:
    """Embedding lookup omits missing IDs and keeps present IDs keyed by movie ID."""
    first, second = _sample_movie_ids(db_url, limit=2)

    result = api_movies.fetch_embeddings([first, -1, second])

    assert set(result) == {first, second}
    assert all(result[movie_id] for movie_id in (first, second))


async def test_retrieval_agent_excludes_titles_end_to_end(
    db_url: str, mini_catalogue: int, monkeypatch
) -> None:
    """retrieve_from_message drops reformulator-emitted exclusions from candidates."""
    _, sample_title = _sample_title(db_url)

    # Stub the reformulator so we can pin the exclusion list deterministically.
    async def _fake_from_message(**_: object) -> ReformulatedQuery:
        return ReformulatedQuery(
            query="a contemplative film about identity and memory",
            excluded_films=[sample_title],
        )

    monkeypatch.setattr(
        "backend.retrieval.agent.query_reformulator.from_message",
        _fake_from_message,
    )

    result = await retrieval_agent.retrieve_from_message(
        user_query="something contemplative about identity and memory",
        k=10,
        session_id=uuid4(),
        run_id=uuid4(),
        turn_id=uuid4(),
        dry_run=True,
    )
    returned_titles = {c.title for c in result.candidates}
    assert sample_title not in returned_titles
    assert result.excluded_films == [sample_title]
    assert result.excluded_movie_ids, "expected fuzzy-match to resolve the sample title"
    assert result.reformulated_query == "a contemplative film about identity and memory"
    assert result.user_query == "something contemplative about identity and memory"


def test_reformulator_prompt_extracts_positive_mentions() -> None:
    """The v2 prompt must instruct the model to extract films from positive mentions too.

    Guards against silent reversion to the old negative-only rule, which would
    cause the system to recommend films the oracle just named as a reference.
    """
    prompt_path = (
        Path(__file__).resolve().parents[2]
        / "backend"
        / "retrieval"
        / "prompts"
        / "query_reformulate_v2.j2"
    )
    body = prompt_path.read_text()

    assert "regardless of sentiment" in body, (
        "extraction rule must cover both positive and negative mentions"
    )
    assert "*Positive* references" in body, (
        "extraction rule must explicitly call out positive references"
    )
    assert '"excluded_films": ["Interstellar"]' in body, (
        "examples must demonstrate that 'similar to Interstellar' excludes Interstellar"
    )


async def test_retrieval_agent_dry_run_returns_fixture_reformulation(
    db_url: str, mini_catalogue: int
) -> None:
    """In dry_run, retrieve_from_message reformulated_query matches the canned fixture's `query` field."""
    fixture_path = (
        Path(__file__).resolve().parents[2]
        / "tests"
        / "fixtures"
        / "dry_run"
        / "retrieval_reformulate.json"
    )
    expected = json.loads(fixture_path.read_text())["query"]

    result = await retrieval_agent.retrieve_from_message(
        user_query="anything",
        k=5,
        session_id=uuid4(),
        run_id=uuid4(),
        turn_id=uuid4(),
        dry_run=True,
    )
    assert result.reformulated_query == expected
    assert result.user_query == "anything"
