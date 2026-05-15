"""
Unit tests for backend/cluster/tools/cluster_describer.py.

Patches llm_harness.call so no live API calls are made.
"""

import json
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from backend.cluster.tools.cluster_describer import describe
from backend.llm.types import LLMParseError


_SESSION_ID = uuid4()
_RUN_ID = uuid4()
_TURN_ID = uuid4()

_PAYLOAD = [
    {
        "cluster_index": 0,
        "top_titles": ["Blade Runner", "The Matrix"],
        "top_genres": ["Science Fiction"],
        "sample_overviews": ["A detective hunts synthetic humans."],
    },
    {
        "cluster_index": 1,
        "top_titles": ["Amélie", "Before Sunrise"],
        "top_genres": ["Romance", "Drama"],
        "sample_overviews": ["A whimsical woman helps strangers find love."],
    },
]


class TestDescribeDryRun:
    def test_dry_run_returns_placeholders_without_llm_call(self):
        result = describe(
            clusters_payload=_PAYLOAD,
            user_query="sci-fi films",
            reformulated_query="sci-fi with existential dread",
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            turn_id=_TURN_ID,
            dry_run=True,
        )

        assert len(result) == 2
        assert result[0] == ("Cluster 0", "dry-run description")
        assert result[1] == ("Cluster 1", "dry-run description")

    def test_dry_run_empty_payload_returns_empty(self):
        result = describe(
            clusters_payload=[],
            user_query="anything",
            reformulated_query="anything",
            session_id=_SESSION_ID,
            run_id=_RUN_ID,
            turn_id=_TURN_ID,
            dry_run=True,
        )
        assert result == []


class TestDescribeLLM:
    def _call(self, llm_content: str):
        mock_response = MagicMock()
        mock_response.content = llm_content
        with patch("backend.cluster.tools.cluster_describer.llm_harness.call", return_value=mock_response):
            return describe(
                clusters_payload=_PAYLOAD,
                user_query="films about identity",
                reformulated_query="identity and humanity films",
                session_id=_SESSION_ID,
                run_id=_RUN_ID,
                turn_id=_TURN_ID,
                dry_run=False,
            )

    def test_valid_response_parsed_correctly(self):
        payload = json.dumps([
            {"name": "Neon Dystopia", "description": "Bleak futures shaped by corporate control."},
            {"name": "Tender Parisian Romance", "description": "Intimate love stories in European streets."},
        ])
        result = self._call(payload)

        assert result == [
            ("Neon Dystopia", "Bleak futures shaped by corporate control."),
            ("Tender Parisian Romance", "Intimate love stories in European streets."),
        ]

    def test_invalid_json_raises_llm_parse_error(self):
        with pytest.raises(LLMParseError):
            self._call("not json at all")

    def test_non_list_raises_llm_parse_error(self):
        with pytest.raises(LLMParseError):
            self._call(json.dumps({"name": "X", "description": "Y"}))

    def test_wrong_length_raises_llm_parse_error(self):
        payload = json.dumps([{"name": "Only One", "description": "Just one."}])
        with pytest.raises(LLMParseError):
            self._call(payload)

    def test_missing_name_field_raises_llm_parse_error(self):
        payload = json.dumps([
            {"description": "No name field here."},
            {"name": "Good", "description": "Fine."},
        ])
        with pytest.raises(LLMParseError):
            self._call(payload)
