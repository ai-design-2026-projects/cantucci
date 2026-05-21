"""Unit tests for deterministic recommendation rendering.

Pure Python, no DB, no Docker, no LLM.
"""

from __future__ import annotations

from uuid import uuid4

from backend.cluster.domain import ClusterAssignment
from backend.repository.sessions import ClusterRow
from backend.routers.dto.sessions.builders import render_recommendation


def _cluster(assignments: list[ClusterAssignment]) -> ClusterRow:
    return ClusterRow(
        id=uuid4(),
        name="Needle drops and neon",
        description="Stylish, music-forward picks.",
        level=0,
        parent_cluster_id=None,
        assignments=assignments,
    )


def test_render_recommendation_excludes_marked_assignments() -> None:
    reply = render_recommendation(
        best_cluster=_cluster(
            [
                ClusterAssignment(movie_id=1, score=0.9, excluded=False, title="Shown"),
                ClusterAssignment(movie_id=2, score=1.0, excluded=True, title="Hidden"),
            ]
        ),
        top_k=5,
    )

    assert "Shown" in reply
    assert "Hidden" not in reply


def test_render_recommendation_sorts_by_descending_score() -> None:
    reply = render_recommendation(
        best_cluster=_cluster(
            [
                ClusterAssignment(movie_id=1, score=0.2, excluded=False, title="Low"),
                ClusterAssignment(movie_id=2, score=0.8, excluded=False, title="High"),
                ClusterAssignment(movie_id=3, score=0.5, excluded=False, title="Mid"),
            ]
        ),
        top_k=3,
    )

    assert reply.index("- High") < reply.index("- Mid") < reply.index("- Low")


def test_render_recommendation_respects_top_k() -> None:
    reply = render_recommendation(
        best_cluster=_cluster(
            [
                ClusterAssignment(movie_id=1, score=0.9, excluded=False, title="One"),
                ClusterAssignment(movie_id=2, score=0.8, excluded=False, title="Two"),
                ClusterAssignment(movie_id=3, score=0.7, excluded=False, title="Three"),
            ]
        ),
        top_k=2,
    )

    assert "One" in reply
    assert "Two" in reply
    assert "Three" not in reply


def test_render_recommendation_falls_back_to_movie_id_when_title_missing() -> None:
    reply = render_recommendation(
        best_cluster=_cluster(
            [
                ClusterAssignment(movie_id=42, score=0.9, excluded=False, title=None),
            ]
        ),
        top_k=1,
    )

    assert "- 42" in reply
