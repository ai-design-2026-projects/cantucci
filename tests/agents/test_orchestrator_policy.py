"""Tests for pure policy helpers in backend/orchestrator/orchestrator.py.

All helpers are stateless functions — no DB, no LLM calls.
"""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.api.types import ClusterAssignment, ClusterSnapshot, TurnDetail
from backend.decision.types import DecisionAction, DecisionResult
from backend.orchestrator.orchestrator import (
    _build_refined_query,
    _classify_feedback,
    _convergence_policy,
    _is_duplicate_question,
    _prior_questions,
)


def _turn(
    turn_number: int = 1,
    user_message: str = "hello",
    assistant_message: str | None = "reply",
    step_type: str | None = "show",
    converged: bool = False,
) -> TurnDetail:
    return TurnDetail(
        id=uuid.uuid4(),
        turn_number=turn_number,
        user_message=user_message,
        assistant_message=assistant_message,
        step_type=step_type,
        converged=converged,
        clusters=[],
        created_at=datetime.now(timezone.utc),
    )


def _decision(
    action: DecisionAction = DecisionAction.recommend,
    best_cluster_id: uuid.UUID | None = None,
) -> DecisionResult:
    return DecisionResult(
        action=action,
        best_cluster_id=best_cluster_id,
        rationale="test",
        entropy_score=0.5,
    )


class TestBuildRefinedQuery:
    def test_first_turn_returns_user_message(self):
        assert _build_refined_query([], "space opera") == "space opera"

    def test_second_turn_prepends_original(self):
        turns = [_turn(user_message="sci-fi action")]
        result = _build_refined_query(turns, "more explosions")
        assert result == "sci-fi action. more explosions"

    def test_same_message_as_original_no_duplication(self):
        turns = [_turn(user_message="sci-fi action")]
        result = _build_refined_query(turns, "sci-fi action")
        assert result == "sci-fi action"


class TestConvergencePolicy:
    def test_not_enough_show_turns_returns_false(self):
        turns = [_turn(step_type="show")]
        assert _convergence_policy(turns, convergence_turns=2) is False

    def test_enough_show_turns_returns_true(self):
        turns = [_turn(step_type="show"), _turn(step_type="show")]
        assert _convergence_policy(turns, convergence_turns=2) is True

    def test_ask_turn_doesnt_count(self):
        turns = [_turn(step_type="ask"), _turn(step_type="show")]
        assert _convergence_policy(turns, convergence_turns=2) is False

    def test_empty_turns_returns_false(self):
        assert _convergence_policy([], convergence_turns=1) is False


class TestClassifyFeedback:
    def test_first_turn_is_global_constraint(self):
        level, ftype, target = _classify_feedback([], "I like action", _decision())
        assert (level, ftype) == ("global", "constraint")
        assert target is None

    def test_response_to_ask_with_positive_words_is_accept(self):
        prior = [_turn(step_type="ask")]
        level, ftype, _ = _classify_feedback(prior, "yes that looks good", _decision())
        assert (level, ftype) == ("cluster", "accept")

    def test_response_to_ask_with_negative_words_is_reject(self):
        prior = [_turn(step_type="ask")]
        level, ftype, _ = _classify_feedback(prior, "no that's wrong", _decision())
        assert (level, ftype) == ("cluster", "reject")

    def test_response_to_show_is_global_constraint(self):
        prior = [_turn(step_type="show")]
        level, ftype, target = _classify_feedback(prior, "add more comedy", _decision())
        assert (level, ftype) == ("global", "constraint")

    def test_accept_carries_best_cluster_target(self):
        cid = uuid.uuid4()
        prior = [_turn(step_type="ask")]
        _, _, target = _classify_feedback(prior, "yes", _decision(best_cluster_id=cid))
        assert target == str(cid)


class TestIsDuplicateQuestion:
    def test_exact_match_returns_true(self):
        turns = [_turn(step_type="ask", assistant_message="Do you prefer drama?")]
        assert _is_duplicate_question("Do you prefer drama?", turns) is True

    def test_no_match_returns_false(self):
        turns = [_turn(step_type="ask", assistant_message="Do you prefer drama?")]
        assert _is_duplicate_question("What era?", turns) is False

    def test_show_turn_not_considered(self):
        turns = [_turn(step_type="show", assistant_message="Some question text")]
        assert _is_duplicate_question("Some question text", turns) is False

    def test_empty_turns_returns_false(self):
        assert _is_duplicate_question("anything", []) is False


class TestPriorQuestions:
    def test_collects_ask_messages(self):
        turns = [
            _turn(step_type="ask", assistant_message="Q1"),
            _turn(step_type="show", assistant_message="R1"),
            _turn(step_type="ask", assistant_message="Q2"),
        ]
        assert _prior_questions(turns) == ["Q1", "Q2"]

    def test_skips_none_assistant_message(self):
        turns = [_turn(step_type="ask", assistant_message=None)]
        assert _prior_questions(turns) == []

    def test_empty_turns_returns_empty(self):
        assert _prior_questions([]) == []
