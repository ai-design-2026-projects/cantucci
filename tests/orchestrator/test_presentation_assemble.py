"""Unit tests for ``assemble_session_dto`` — the projection from
``SessionRow`` (internal read-side dataclass) to ``SessionDto`` (HTTP DTO).

Pure Python, no DB, no Docker, no LLM. ``api_movies.fetch_movies_dto`` is
monkeypatched so we can also assert the batching contract.
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import UUID, uuid4

import pytest

from backend.api.types import (
    ClusterAssignment,
    ClusterRow,
    SessionRow,
    StepType,
    TurnRow,
)
from backend.orchestrator.utils import presentation


def _cfg(top_k: int = 3) -> SimpleNamespace:
    """Minimal stand-in for ``Settings`` — only ``cfg.session.recommendation_top_k`` is read."""
    return SimpleNamespace(session=SimpleNamespace(recommendation_top_k=top_k))


def _movie_dict(movie_id: int) -> dict:
    """Shape matches ``api_movies.fetch_movies_dto`` output (one dict per movie)."""
    return {
        "id": movie_id,
        "title": f"Movie {movie_id}",
        "release_year": 2024,
        "runtime": 100.0,
        "vote_average": 7.0,
        "vote_count": 100,
        "bayesian_rating": 7.0,
        "overview": "",
        "poster_url": None,
        "genres": [],
        "director": None,
        "top_cast": [],
        "original_language": "en",
    }


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

    def _fake_fetch(ids: list[int]) -> list[dict]:
        calls.append(ids)
        return []

    monkeypatch.setattr(presentation.api_movies, "fetch_movies_dto", _fake_fetch)

    state = presentation.assemble_session_dto(_full([]), _cfg())

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
        "fetch_movies_dto",
        lambda ids: [_movie_dict(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([turn]), _cfg(top_k=3))

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
        "fetch_movies_dto",
        lambda ids: [_movie_dict(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([show, stop]), _cfg())

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
        "fetch_movies_dto",
        lambda ids: [_movie_dict(mid) for mid in ids],
    )

    state = presentation.assemble_session_dto(_full([ask]), _cfg())

    assert state.turns[0].recommendation is None


def test_movie_fetch_is_batched_once_across_all_show_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All movie ids across every show turn are fetched in a single call."""
    show_a = _turn(StepType.show, clusters=[_cluster([1, 2])], turn_number=1)
    show_b = _turn(StepType.show, clusters=[_cluster([2, 3])], turn_number=2)
    ask = _turn(StepType.ask, turn_number=3)

    calls: list[list[int]] = []

    def _fake_fetch(ids: list[int]) -> list[dict]:
        calls.append(list(ids))
        return [_movie_dict(mid) for mid in ids]

    monkeypatch.setattr(presentation.api_movies, "fetch_movies_dto", _fake_fetch)

    presentation.assemble_session_dto(_full([show_a, show_b, ask]), _cfg(top_k=2))

    assert len(calls) == 1
    # Deduplicated union of every show turn's top-K ids
    assert sorted(calls[0]) == [1, 2, 3]


def test_session_dto_exposes_public_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """SessionDto exposes turn_count, first_user_message, and cluster_snapshot."""
    monkeypatch.setattr(
        presentation.api_movies, "fetch_movies_dto", lambda ids: [],
    )

    state = presentation.assemble_session_dto(_full([]), _cfg())

    serialized = state.model_dump()
    assert "turn_count" in serialized
    assert "first_user_message" in serialized
    assert "cluster_snapshot" in serialized
    assert serialized["turn_count"] == 0
    assert serialized["first_user_message"] is None
    assert serialized["cluster_snapshot"] == []
