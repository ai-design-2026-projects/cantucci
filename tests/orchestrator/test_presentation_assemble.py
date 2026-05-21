"""Unit tests for ``assemble_session_dto`` — the projection from
``SessionRow`` (internal read-side dataclass) to ``SessionDto`` (HTTP DTO).

Pure Python, no DB, no Docker, no LLM. ``api_movies.fetch_movie_details`` is
monkeypatched so we can also assert the batching contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from backend.cluster.domain import ClusterAssignment
from backend.orchestrator.domain import StepType
from backend.repository.movies.types import MovieDetailsRow
from backend.repository.sessions.types import ClusterRow, SessionRow, TurnRow
from backend.routers.dto.sessions import builders as presentation


def _movie_details_row(movie_id: int) -> MovieDetailsRow:
    """Minimal ``MovieDetailsRow`` for tests."""
    return MovieDetailsRow(
        id=movie_id,
        title=f"Movie {movie_id}",
        release_year=2024,
        runtime=100.0,
        vote_average=7.0,
        vote_count=100,
        bayesian_rating=7.0,
        overview="",
        poster_url=None,
        genres=[],
        director=None,
        top_cast=[],
        original_language="en",
    )


def _cluster(movie_ids: list[int]) -> ClusterRow:
    return ClusterRow(
        id=uuid4(),
        name="test cluster",
        description=None,
        level=1,
        parent_cluster_id=None,
        assignments=[
            ClusterAssignment(movie_id=mid, score=0.9 - i * 0.1, excluded=False, title=None)
            for i, mid in enumerate(movie_ids)
        ],
    )


def _turn(
    step_type: StepType | None,
    *,
    clusters: list[ClusterRow] | None = None,
    turn_number: int = 1,
    converged: bool = False,
) -> TurnRow:
    return TurnRow(
        id=uuid4(),
        turn_number=turn_number,
        user_message="hi",
        assistant_message="reply",
        step_type=step_type.value if step_type else None,
        converged=converged,
        clusters=clusters or [],
        created_at=datetime.now(timezone.utc),
    )


def _full(turns: list[TurnRow]) -> SessionRow:
    now = datetime.now(timezone.utc)
    return SessionRow(
        session_id=uuid4(),
        run_id=uuid4(),
        seed=42,
        config_hash="deadbeef",
        model_version="claude-test",
        status="active",
        preference_profile=None,
        turns=turns,
        cluster_snapshot=[],
        feedback=[],
        metrics=None,
        judge_scores=[],
        created_at=now,
        updated_at=now,
        max_turns=15,
    )


def test_empty_session_yields_empty_turns(monkeypatch: pytest.MonkeyPatch) -> None:
    """No turns ⇒ no movie fetch and an empty SessionDto.turns list."""
    calls: list[list[int]] = []

    def _fake_fetch(ids: list[int]) -> list[MovieDetailsRow]:
        calls.append(ids)
        return []

    monkeypatch.setattr(presentation.api_movies, "fetch_movie_details", _fake_fetch)

    state = presentation.assemble_session_dto(_full([]))

    assert state.turns == []
    assert calls == []  # no movies to fetch ⇒ no call


def test_show_turn_hydrates_recommendation_in_score_order(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A show turn produces a RecommendationDto with films sorted by score desc."""
    cluster = _cluster([10, 11, 12])
    turn = _turn(StepType.show, clusters=[cluster])

    monkeypatch.setattr(
        presentation.api_movies,
        "fetch_movie_details",
        lambda ids: [_movie_details_row(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([turn]))

    assert len(state.turns) == 1
    rec = state.turns[0].recommendation
    assert rec is not None
    assert [f.id for f in rec.films] == [10, 11, 12]


def test_stop_turn_inherits_last_show_recommendation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stop turn following a show turn surfaces the show turn's recommendation."""
    show = _turn(StepType.show, clusters=[_cluster([20, 21])], turn_number=1)
    stop = _turn(StepType.stop, turn_number=2)

    monkeypatch.setattr(
        presentation.api_movies,
        "fetch_movie_details",
        lambda ids: [_movie_details_row(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([show, stop]))

    show_rec = state.turns[0].recommendation
    stop_rec = state.turns[1].recommendation
    assert show_rec is not None
    assert stop_rec is not None
    assert [f.id for f in stop_rec.films] == [f.id for f in show_rec.films]


def test_ask_turn_carries_no_recommendation(monkeypatch: pytest.MonkeyPatch) -> None:
    """An ask turn (clarifying question) has ``recommendation=None``."""
    ask = _turn(StepType.ask)
    monkeypatch.setattr(
        presentation.api_movies,
        "fetch_movie_details",
        lambda ids: [_movie_details_row(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([ask]))

    assert state.turns[0].recommendation is None


def test_movie_fetch_is_batched_once_across_all_show_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All movie ids across every show turn are fetched in a single call."""
    show_a = _turn(StepType.show, clusters=[_cluster([1, 2])], turn_number=1)
    show_b = _turn(StepType.show, clusters=[_cluster([2, 3])], turn_number=2)
    ask = _turn(StepType.ask, turn_number=3)

    calls: list[list[int]] = []

    def _fake_fetch(ids: list[int]) -> list[MovieDetailsRow]:
        calls.append(list(ids))
        return [_movie_details_row(mid) for mid in ids]

    monkeypatch.setattr(presentation.api_movies, "fetch_movie_details", _fake_fetch)

    presentation.assemble_session_dto(_full([show_a, show_b, ask]))

    assert len(calls) == 1
    # Deduplicated union of every show turn's top-K ids
    assert sorted(calls[0]) == [1, 2, 3]


def test_session_dto_exposes_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SessionDto exposes turn_count, first_user_message, and cluster_snapshot."""
    monkeypatch.setattr(
        presentation.api_movies, "fetch_movie_details", lambda ids: [],
    )

    state = presentation.assemble_session_dto(_full([]))

    serialized = state.model_dump()
    assert "turn_count" in serialized
    assert "first_user_message" in serialized
    assert "cluster_snapshot" in serialized
    assert serialized["turn_count"] == 0
    assert serialized["first_user_message"] is None
    assert serialized["cluster_snapshot"] == []
