"""Tests for backend/decision/decision_agent.py.

dry_run tests skip LLM calls; entropy + relevance are exercised with
real cluster data.  Parse-contract tests verify the agent rejects
malformed LLM output.
"""

import uuid
from unittest.mock import patch

import pytest

from backend.decision import decision_agent
from backend.models.clusters import ClusterAssignment, ClusterSnapshot
from backend.models.decision import DecisionAction, DecisionResult
from backend.models.llm import LLMParseError, LLMResponse


_SESSION_ID = uuid.uuid4()
_RUN_ID = uuid.uuid4()
_TURN_ID = uuid.uuid4()

_COMMON = dict(
    session_id=_SESSION_ID,
    run_id=_RUN_ID,
    turn_id=_TURN_ID,
    turn_number=1,
    user_query="I want a tense sci-fi thriller",
    config_hash="abc12345",
    model_version="gpt-4o-mini",
)


def _snapshot(name: str = "Sci-Fi", n_assignments: int = 3) -> ClusterSnapshot:
    return ClusterSnapshot(
        id=uuid.uuid4(),
        name=name,
        description=f"Films about {name.lower()}",
        level=0,
        parent_cluster_id=None,
        assignments=[
            ClusterAssignment(movie_id=i, score=0.8 - i * 0.1, excluded=False)
            for i in range(n_assignments)
        ],
    )


class TestDecideNoClustersFastPath:
    def test_returns_continue_without_llm_call(self):
        result = decision_agent.decide(clusters=[], **_COMMON)
        assert result.action == DecisionAction.continue_
        assert result.entropy_score == 1.0

    def test_rationale_mentions_no_clusters(self):
        result = decision_agent.decide(clusters=[], **_COMMON)
        assert "no clusters" in result.rationale.lower()


class TestDecideWithClusters:
    def test_returns_decision_result_on_recommend(self):
        fake_response = LLMResponse(
            content='{"action": "recommend", "rationale": "high relevance", '
                    '"entropy_score": 0.3, "best_cluster_id": null}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=50.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=fake_response):
            result = decision_agent.decide(clusters=[_snapshot()], **_COMMON)

        assert result.action == DecisionAction.recommend
        assert isinstance(result.entropy_score, float)

    def test_returns_decision_result_on_continue(self):
        fake_response = LLMResponse(
            content='{"action": "continue", "rationale": "ambiguous", '
                    '"entropy_score": 0.9, "best_cluster_id": null}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=50.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=fake_response):
            result = decision_agent.decide(clusters=[_snapshot()], **_COMMON)

        assert result.action == DecisionAction.continue_

    def test_best_cluster_id_parsed_when_present(self):
        cid = uuid.uuid4()
        fake_response = LLMResponse(
            content=f'{{"action": "recommend", "rationale": "ok", '
                    f'"entropy_score": 0.2, "best_cluster_id": "{cid}"}}',
            input_tokens=10,
            output_tokens=5,
            latency_ms=50.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=fake_response):
            result = decision_agent.decide(clusters=[_snapshot()], **_COMMON)

        assert result.best_cluster_id == cid


class TestDecideParseErrors:
    def test_invalid_json_raises_llm_parse_error(self):
        bad = LLMResponse(
            content="not json at all",
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                decision_agent.decide(clusters=[_snapshot()], **_COMMON)

    def test_missing_action_field_raises_llm_parse_error(self):
        bad = LLMResponse(
            content='{"rationale": "ok", "entropy_score": 0.5}',
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                decision_agent.decide(clusters=[_snapshot()], **_COMMON)

    def test_invalid_action_value_raises_llm_parse_error(self):
        bad = LLMResponse(
            content='{"action": "unknown", "rationale": "ok", "entropy_score": 0.5}',
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.decision.decision_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                decision_agent.decide(clusters=[_snapshot()], **_COMMON)
