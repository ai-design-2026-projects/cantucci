"""Unit tests for should_retrieve policy (RetrievalDecision).

Pure-Python, no DB, no Docker, no LLM.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from backend.orchestrator.tools.policy import RetrievalDecision, should_retrieve


def _feedback(turn_id: uuid.UUID, feedback_type: str) -> MagicMock:
    """Return a minimal FeedbackEntry-like object."""
    f = MagicMock()
    f.turn_id = turn_id
    f.feedback_type = feedback_type
    return f


def _turn(turn_id: uuid.UUID | None = None, user_message: str = "some message") -> MagicMock:
    """Return a minimal TurnDetail-like object."""
    t = MagicMock()
    t.id = turn_id or uuid.uuid4()
    t.user_message = user_message
    return t


def _full(turns: list, feedback: list) -> MagicMock:
    """Return a minimal SessionFull-like object."""
    f = MagicMock()
    f.turns = turns
    f.feedback = feedback
    return f


class TestFirstTurn:
    """Always retrieve on the first turn using the current oracle message."""

    def test_retrieve_true(self) -> None:
        full = _full(turns=[], feedback=[])
        result = should_retrieve(full, "I want something fun")
        assert result.retrieve is True

    def test_query_is_user_message(self) -> None:
        full = _full(turns=[], feedback=[])
        result = should_retrieve(full, "I want something fun")
        assert result.query == "I want something fun"


class TestNoPriorDrift:
    """Reuse prior candidates when no resolve_drift feedback exists."""

    def test_retrieve_false_no_feedback(self) -> None:
        turn_id = uuid.uuid4()
        full = _full(turns=[_turn(turn_id)], feedback=[])
        result = should_retrieve(full, "give me something new")
        assert result.retrieve is False
        assert result.query is None

    def test_retrieve_false_unrelated_feedback(self) -> None:
        turn_id = uuid.uuid4()
        fb = _feedback(turn_id, "accept")
        full = _full(turns=[_turn(turn_id)], feedback=[fb])
        result = should_retrieve(full, "give me something new")
        assert result.retrieve is False

    def test_retrieve_false_constraint_feedback(self) -> None:
        turn_id = uuid.uuid4()
        fb = _feedback(turn_id, "constraint")
        full = _full(turns=[_turn(turn_id)], feedback=[fb])
        result = should_retrieve(full, "give me something new")
        assert result.retrieve is False

    def test_drift_feedback_on_older_turn_does_not_trigger(self) -> None:
        older_id = uuid.uuid4()
        prev_id = uuid.uuid4()
        fb = _feedback(older_id, "resolve_drift")
        full = _full(turns=[_turn(older_id), _turn(prev_id)], feedback=[fb])
        result = should_retrieve(full, "something please")
        assert result.retrieve is False


class TestPostDriftRetrieval:
    """Retrieve using the drift turn's user_message after a resolve_drift feedback row."""

    def test_retrieve_true_after_drift(self) -> None:
        turn_id = uuid.uuid4()
        fb = _feedback(turn_id, "resolve_drift")
        full = _full(turns=[_turn(turn_id, "I want romance films")], feedback=[fb])
        result = should_retrieve(full, "yes that's right")
        assert result.retrieve is True

    def test_query_is_drift_turn_user_message(self) -> None:
        turn_id = uuid.uuid4()
        fb = _feedback(turn_id, "resolve_drift")
        full = _full(turns=[_turn(turn_id, "I want romance films")], feedback=[fb])
        result = should_retrieve(full, "yes that's right")
        assert result.query == "I want romance films"

    def test_query_is_not_current_message(self) -> None:
        turn_id = uuid.uuid4()
        fb = _feedback(turn_id, "resolve_drift")
        full = _full(turns=[_turn(turn_id, "I want romance films")], feedback=[fb])
        result = should_retrieve(full, "yes that's right")
        assert result.query != "yes that's right"
