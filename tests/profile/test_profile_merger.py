"""Tests for backend.profile.tools.profile_merger — pure Python, no LLM/DB."""

from __future__ import annotations

from unittest.mock import MagicMock

from backend.profile.tools.profile_merger import build_prompt_vars


def _turn(user: str, assistant: str = "", step_type: str = "ask") -> MagicMock:
    t = MagicMock()
    t.user_message = user
    t.assistant_message = assistant
    t.step_type = step_type
    return t


class TestFirstTurn:
    """When prior_profile is None the helper returns safe empty defaults."""

    def test_prior_profile_defaults_to_empty_lists(self) -> None:
        result = build_prompt_vars(
            user_message="I want something fun",
            prior_profile=None,
            recent_turns=[],
        )
        prior = result["prior_profile"]
        assert prior["constraints"] == []
        assert prior["preferences"] == []
        assert prior["attitudes"] == []
        assert prior["summary"] == ""

    def test_user_message_passed_through(self) -> None:
        result = build_prompt_vars(
            user_message="looking for a comedy",
            prior_profile=None,
            recent_turns=[],
        )
        assert result["user_message"] == "looking for a comedy"

    def test_recent_turns_empty_when_no_turns(self) -> None:
        result = build_prompt_vars(
            user_message="x", prior_profile=None, recent_turns=[]
        )
        assert result["recent_turns"] == []


class TestWithPriorProfile:
    """When prior_profile is a dict it is forwarded as-is."""

    def test_prior_profile_forwarded(self) -> None:
        profile = {
            "constraints": ["no horror"],
            "preferences": ["slow burn"],
            "attitudes": ["decisive"],
            "summary": "Likes slow drama",
        }
        result = build_prompt_vars(
            user_message="something new", prior_profile=profile, recent_turns=[]
        )
        assert result["prior_profile"] is profile

    def test_prior_profile_partial_dict_not_overwritten(self) -> None:
        profile = {"constraints": ["no subtitles"], "preferences": [], "attitudes": [], "summary": ""}
        result = build_prompt_vars(
            user_message="x", prior_profile=profile, recent_turns=[]
        )
        assert result["prior_profile"]["constraints"] == ["no subtitles"]


class TestRecentTurns:
    """Recent turns are serialised into simple dicts for the template."""

    def test_turns_serialised(self) -> None:
        turns = [_turn("hello", "Hi!", "ask"), _turn("thanks", "Welcome", "show")]
        result = build_prompt_vars(
            user_message="x", prior_profile=None, recent_turns=turns
        )
        assert len(result["recent_turns"]) == 2
        assert result["recent_turns"][0] == {"user": "hello", "assistant": "Hi!", "step_type": "ask"}
        assert result["recent_turns"][1] == {"user": "thanks", "assistant": "Welcome", "step_type": "show"}

    def test_none_assistant_message_becomes_empty_string(self) -> None:
        turn = MagicMock()
        turn.user_message = "hi"
        turn.assistant_message = None
        turn.step_type = "ask"
        result = build_prompt_vars(
            user_message="x", prior_profile=None, recent_turns=[turn]
        )
        assert result["recent_turns"][0]["assistant"] == ""

    def test_none_step_type_becomes_unknown(self) -> None:
        turn = MagicMock()
        turn.user_message = "hi"
        turn.assistant_message = "hello"
        turn.step_type = None
        result = build_prompt_vars(
            user_message="x", prior_profile=None, recent_turns=[turn]
        )
        assert result["recent_turns"][0]["step_type"] == "unknown"
