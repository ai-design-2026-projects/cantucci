"""Tests for backend/ambiguity/ambiguity_agent.py.

Parse-contract tests verify the agent raises LLMParseError on bad output.
Shape tests verify the returned AmbiguityQuestion fields.
"""

import uuid
from unittest.mock import patch

import pytest

from backend.ambiguity import ambiguity_agent
from backend.models.ambiguity import AmbiguityQuestion
from backend.models.clusters import ClusterAssignment, ClusterSnapshot
from backend.models.llm import LLMParseError, LLMResponse


_SESSION_ID = uuid.uuid4()
_RUN_ID = uuid.uuid4()
_TURN_ID = uuid.uuid4()

_COMMON = dict(
    session_id=_SESSION_ID,
    run_id=_RUN_ID,
    turn_id=_TURN_ID,
    turn_number=1,
    user_query="Something tense and atmospheric",
    entropy_score=0.8,
    prior_questions=[],
    config_hash="abc12345",
    model_version="gpt-4o-mini",
)


def _snapshot(name: str = "Thriller") -> ClusterSnapshot:
    return ClusterSnapshot(
        id=uuid.uuid4(),
        name=name,
        description=f"Films in the {name} genre",
        level=0,
        parent_cluster_id=None,
        assignments=[ClusterAssignment(movie_id=1, score=0.9, excluded=False)],
    )


class TestGenerateQuestionShape:
    def test_returns_ambiguity_question(self):
        cid = uuid.uuid4()
        fake = LLMResponse(
            content=f'{{"question_text": "Do you want recent films?", '
                     f'"ui_format": "binary", "cluster_refs": ["{cid}"]}}',
            input_tokens=10,
            output_tokens=10,
            latency_ms=50.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=fake):
            result = ambiguity_agent.generate_question(
                clusters=[_snapshot()], **_COMMON
            )

        assert isinstance(result, AmbiguityQuestion)
        assert isinstance(result.question_text, str) and result.question_text
        assert isinstance(result.ui_format, str) and result.ui_format
        assert isinstance(result.cluster_refs, list)

    def test_cluster_refs_are_uuids(self):
        cid = uuid.uuid4()
        fake = LLMResponse(
            content=f'{{"question_text": "Q?", "ui_format": "choice", '
                     f'"cluster_refs": ["{cid}"]}}',
            input_tokens=10,
            output_tokens=10,
            latency_ms=50.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=fake):
            result = ambiguity_agent.generate_question(
                clusters=[_snapshot()], **_COMMON
            )

        assert result.cluster_refs == [cid]

    def test_invalid_cluster_ref_uuid_skipped(self):
        fake = LLMResponse(
            content='{"question_text": "Q?", "ui_format": "binary", '
                    '"cluster_refs": ["not-a-uuid"]}',
            input_tokens=10,
            output_tokens=10,
            latency_ms=50.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=fake):
            result = ambiguity_agent.generate_question(
                clusters=[_snapshot()], **_COMMON
            )

        assert result.cluster_refs == []


class TestGenerateQuestionParseErrors:
    def test_invalid_json_raises(self):
        bad = LLMResponse(
            content="not json",
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                ambiguity_agent.generate_question(clusters=[_snapshot()], **_COMMON)

    def test_missing_question_text_raises(self):
        bad = LLMResponse(
            content='{"ui_format": "binary", "cluster_refs": []}',
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                ambiguity_agent.generate_question(clusters=[_snapshot()], **_COMMON)

    def test_missing_cluster_refs_raises(self):
        bad = LLMResponse(
            content='{"question_text": "Q?", "ui_format": "binary"}',
            input_tokens=5,
            output_tokens=5,
            latency_ms=10.0,
        )
        with patch("backend.ambiguity.ambiguity_agent.llm_harness.call", return_value=bad):
            with pytest.raises(LLMParseError):
                ambiguity_agent.generate_question(clusters=[_snapshot()], **_COMMON)
