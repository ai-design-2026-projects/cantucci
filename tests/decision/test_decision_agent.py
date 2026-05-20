"""Unit tests for the Decision Agent.

Uses the LLM harness dry_run mode (no live LLM calls). Each test exercises the
agent's behaviour given a fixture response, verifying that:
  - The merged continue action carries a question in the returned DecisionResult.
  - The empty-clusters short-circuit never calls the harness.
  - Schema validation rejects a continue response without a question.
"""

from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.cluster.domain import ClusterAssignment
from backend.repository.sessions import ClusterRow
from backend.decision import decision_agent
from backend.decision.types import DecisionAction, DecisionResult


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _cluster(name: str = "Drama", n: int = 3) -> ClusterRow:
    c = MagicMock(spec=ClusterRow)
    c.id = uuid.uuid4()
    c.name = name
    c.description = "Intense dramas"
    c.level = 0
    c.parent_cluster_id = None
    c.assignments = [
        MagicMock(spec=ClusterAssignment, title=f"Film {i}", movie_id=uuid.uuid4(), score=float(i + 1), excluded=False)
        for i in range(n)
    ]
    return c


def _cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.models.strong.name = "gpt-4o-mini"
    cfg.models.strong.provider = "openai"
    cfg.models.strong.seed = 42
    cfg.models.strong.max_tokens = 256
    cfg.session.max_turns = 15
    cfg.session.cost_limit_usd = 5.0
    cfg.session.recommendation_top_k = 3
    return cfg


async def _call_decide(clusters: list[ClusterRow] | None = None, **kwargs: Any) -> DecisionResult:
    """Call decide() with all required fields mocked."""
    return await decision_agent.decide(
        session_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        turn_number=1,
        user_query="something contemplative",
        clusters=clusters if clusters is not None else [_cluster(), _cluster("Thriller")],
        **kwargs,
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestEmptyClustersShortCircuit:
    """Empty cluster list short-circuits to continue with no LLM call."""

    async def test_returns_continue(self) -> None:
        with patch("backend.decision.decision_agent.llm_harness") as mock_harness:
            result = await _call_decide(clusters=[])
        assert result.action == DecisionAction.continue_
        mock_harness.call.assert_not_called()

    async def test_entropy_is_one(self) -> None:
        with patch("backend.decision.decision_agent.llm_harness"):
            result = await _call_decide(clusters=[])
        assert result.entropy_score == 1.0

    async def test_no_question_text(self) -> None:
        with patch("backend.decision.decision_agent.llm_harness"):
            result = await _call_decide(clusters=[])
        assert result.question_text is None


class TestDryRunFixture:
    """The fixture at tests/fixtures/dry_run/decision_route.json is valid and
    the agent returns a well-formed DecisionResult with a question."""

    async def test_fixture_parses_correctly(self) -> None:
        fixture_path = Path(__file__).parents[1] / "fixtures" / "dry_run" / "decision_route.json"
        data = json.loads(fixture_path.read_text())
        assert data["action"] in {"recommend", "continue"}
        if data["action"] == "continue":
            assert data["question"] is not None
            assert "text" in data["question"]

    async def test_continue_fixture_returns_question_in_result(self) -> None:
        with (
            patch("backend.decision.decision_agent.get_settings", return_value=_cfg()),
            patch("backend.decision.decision_agent.get_config_hash", return_value="deadbeef"),
        ):
            result = await _call_decide()

        assert result.action == DecisionAction.continue_
        assert result.question_text is not None
        assert len(result.question_text) > 0

    async def test_result_has_entropy_score(self) -> None:
        with (
            patch("backend.decision.decision_agent.get_settings", return_value=_cfg()),
            patch("backend.decision.decision_agent.get_config_hash", return_value="deadbeef"),
        ):
            result = await _call_decide()

        assert isinstance(result.entropy_score, float)
        assert 0.0 <= result.entropy_score <= 1.0


class TestSchemaValidation:
    """A continue response without a question field must fail validation."""

    async def test_continue_without_question_raises(self) -> None:
        bad_fixture = json.dumps({
            "action": "continue",
            "best_cluster_id": None,
            "rationale": "needs more info",
            "entropy_score": 0.7,
            "question": None,
        })
        from backend.decision.types import DecisionResponse
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DecisionResponse.model_validate_json(bad_fixture)

    async def test_recommend_with_question_raises(self) -> None:
        bad_fixture = json.dumps({
            "action": "recommend",
            "best_cluster_id": 0,
            "rationale": "clear winner",
            "entropy_score": 0.2,
            "question": {"text": "oops", "cluster_refs": []},
        })
        from backend.decision.types import DecisionResponse
        from pydantic import ValidationError
        with pytest.raises(ValidationError):
            DecisionResponse.model_validate_json(bad_fixture)


class TestPriorQuestionsPassthrough:
    """prior_questions are accepted without error (content goes into the prompt)."""

    async def test_accepts_prior_questions_list(self) -> None:
        with (
            patch("backend.decision.decision_agent.get_settings", return_value=_cfg()),
            patch("backend.decision.decision_agent.get_config_hash", return_value="deadbeef"),
        ):
            result = await _call_decide(prior_questions=["Do you want a happy ending?"])

        assert isinstance(result, DecisionResult)
