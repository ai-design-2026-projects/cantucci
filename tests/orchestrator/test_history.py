"""Unit tests for orchestrator history-inspection helpers and
ClusterRow's type-conversion classmethod.

Pure Python, no DB, no Docker, no LLM.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from backend.cluster.domain import ClusterAssignment
from backend.orchestrator.domain import StepType
from backend.repository.sessions import ClusterRow, TurnRow
from backend.orchestrator.utils.history import prior_questions


def _turn(
    *,
    step_type: str | None,
    assistant_message: str | None,
) -> TurnRow:
    return TurnRow(
        id=uuid4(),
        turn_number=1,
        user_message="user",
        assistant_message=assistant_message,
        step_type=step_type,
        converged=False,
        clusters=[],
        created_at=datetime.now(timezone.utc),
    )


def test_prior_questions_returns_ask_messages_in_order() -> None:
    turns = [
        _turn(step_type=StepType.ask.value, assistant_message="First question?"),
        _turn(step_type=StepType.ask.value, assistant_message="Second question?"),
    ]

    assert prior_questions(turns) == ["First question?", "Second question?"]


def test_prior_questions_ignores_non_ask_and_empty_messages() -> None:
    turns = [
        _turn(step_type=StepType.show.value, assistant_message="Recommendation"),
        _turn(step_type=StepType.stop.value, assistant_message="Goodbye"),
        _turn(step_type=StepType.ask.value, assistant_message=None),
        _turn(step_type=StepType.ask.value, assistant_message=""),
        _turn(step_type=StepType.ask.value, assistant_message="Useful question?"),
    ]

    assert prior_questions(turns) == ["Useful question?"]


def test_cluster_snapshot_to_spec_preserves_cluster_fields() -> None:
    parent_id = uuid4()
    snapshot = ClusterRow(
        id=uuid4(),
        name="Quiet dread",
        description="Slow, unsettling films",
        level=1,
        parent_cluster_id=parent_id,
        assignments=[],
    )

    spec = snapshot.to_spec()

    assert spec.name == "Quiet dread"
    assert spec.description == "Slow, unsettling films"
    assert spec.level == 1
    assert spec.parent_cluster_id == parent_id


def test_cluster_snapshot_to_spec_converts_assignments() -> None:
    snapshot = ClusterRow(
        id=uuid4(),
        name="Noir",
        description=None,
        level=0,
        parent_cluster_id=None,
        assignments=[
            ClusterAssignment(movie_id=10, score=0.9, excluded=False, title="A"),
            ClusterAssignment(movie_id=20, score=0.4, excluded=True, title="B"),
        ],
    )

    spec = snapshot.to_spec()

    assert spec.assignments == [(10, 0.9, False), (20, 0.4, True)]


def test_cluster_snapshot_to_spec_sets_centroid_to_none() -> None:
    snapshot = ClusterRow(
        id=uuid4(),
        name="Anything",
        description=None,
        level=0,
        parent_cluster_id=None,
        assignments=[],
    )

    assert snapshot.to_spec().centroid is None
