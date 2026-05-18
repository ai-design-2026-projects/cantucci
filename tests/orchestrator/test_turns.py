"""Unit tests for the canned turn emitters in orchestrator/terminal_paths.py.

No DB, no Docker, no LLM. api_sessions calls are patched.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from backend.api.types import StepType
from backend.orchestrator.terminal_paths import (
    emit_drift_clarification,
    emit_early_clarification,
)
from backend.state.types import StateAction, StateDecision


def _decision(reply: str | None = None, drift_topic: str | None = None) -> StateDecision:
    return StateDecision(
        action=StateAction.clarify_drift,
        reason="test drift",
        reply=reply,
        drift_topic=drift_topic,
        prior_statement=None,
        current_statement=None,
    )


@pytest.fixture()
def patched_sessions(monkeypatch: pytest.MonkeyPatch):
    """Patch both api_sessions helpers and return mocks."""
    append = MagicMock()
    write = MagicMock()
    monkeypatch.setattr("backend.orchestrator.terminal_paths.api_sessions.append_turn", append)
    monkeypatch.setattr("backend.orchestrator.terminal_paths.api_sessions.write_feedback", write)
    return append, write


class TestEmitEarlyClarification:
    """emit_early_clarification writes a constraint feedback row and returns step_type=ask."""

    def test_returns_step_type_ask(self, patched_sessions) -> None:
        result = emit_early_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=1,
            user_message="something weird",
        )
        assert result.step_type is StepType.ask

    def test_converged_false(self, patched_sessions) -> None:
        result = emit_early_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=1,
            user_message="something weird",
        )
        assert result.converged is False

    def test_appends_turn(self, patched_sessions) -> None:
        append, _ = patched_sessions
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        emit_early_clarification(
            session_id=session_id,
            turn_id=turn_id,
            turn_number=3,
            user_message="mystery",
        )
        append.assert_called_once()
        call_kwargs = append.call_args.kwargs
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["turn_id"] == turn_id
        assert call_kwargs["step_type"] == StepType.ask.value
        assert call_kwargs["converged"] is False

    def test_writes_constraint_feedback(self, patched_sessions) -> None:
        _, write = patched_sessions
        emit_early_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=1,
            user_message="something",
        )
        write.assert_called_once()
        call_kwargs = write.call_args.kwargs
        assert call_kwargs["feedback_level"] == "global"
        assert call_kwargs["feedback_type"] == "constraint"
        assert call_kwargs["target_id"] is None

    def test_reply_contains_clarification_prompt(self, patched_sessions) -> None:
        result = emit_early_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=1,
            user_message="hmm",
        )
        assert "couldn't find films" in result.assistant_message


class TestEmitDriftClarification:
    """emit_drift_clarification writes a resolve_drift feedback row and returns step_type=ask."""

    def test_returns_step_type_ask(self, patched_sessions) -> None:
        result = emit_drift_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=2,
            user_message="I want horror",
            decision=_decision(reply="Which do you prefer?"),
        )
        assert result.step_type is StepType.ask

    def test_converged_false(self, patched_sessions) -> None:
        result = emit_drift_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=2,
            user_message="I want horror",
            decision=_decision(reply="Which do you prefer?"),
        )
        assert result.converged is False

    def test_uses_decision_reply(self, patched_sessions) -> None:
        result = emit_drift_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=2,
            user_message="I want horror",
            decision=_decision(reply="Earlier you said no horror — has that changed?"),
        )
        assert result.assistant_message == "Earlier you said no horror — has that changed?"

    def test_fallback_reply_when_none(self, patched_sessions) -> None:
        result = emit_drift_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=2,
            user_message="I want horror",
            decision=_decision(reply=None),
        )
        assert result.assistant_message is not None
        assert len(result.assistant_message) > 0

    def test_writes_resolve_drift_feedback(self, patched_sessions) -> None:
        _, write = patched_sessions
        emit_drift_clarification(
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            turn_number=2,
            user_message="I want horror",
            decision=_decision(),
        )
        write.assert_called_once()
        call_kwargs = write.call_args.kwargs
        assert call_kwargs["feedback_level"] == "global"
        assert call_kwargs["feedback_type"] == "resolve_drift"
        assert call_kwargs["target_id"] is None

    def test_appends_turn_with_correct_ids(self, patched_sessions) -> None:
        append, _ = patched_sessions
        session_id = uuid.uuid4()
        turn_id = uuid.uuid4()
        emit_drift_clarification(
            session_id=session_id,
            turn_id=turn_id,
            turn_number=2,
            user_message="I want horror",
            decision=_decision(),
        )
        append.assert_called_once()
        call_kwargs = append.call_args.kwargs
        assert call_kwargs["session_id"] == session_id
        assert call_kwargs["turn_id"] == turn_id
