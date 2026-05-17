"""Tests for backend.profile.profile_agent.

Uses monkeypatching to control llm_harness.call output — no network or DB.
Tests cover: happy path, dry-run fixture, schema validation, None prior profile.
"""

from __future__ import annotations

import uuid
from unittest.mock import MagicMock

import pytest

from backend.profile.profile_agent import extract
from backend.profile.types import UserProfile
from backend.llm.types import LLMResponse


def _profile(**overrides) -> UserProfile:
    defaults = dict(
        constraints=["no horror"],
        preferences=["slow burn"],
        attitudes=["exploratory"],
        summary="Prefers slow, contemplative films without horror.",
    )
    defaults.update(overrides)
    return UserProfile(**defaults)


def _llm_response(parsed: UserProfile) -> LLMResponse:
    return LLMResponse(
        content=parsed.model_dump_json(),
        input_tokens=15,
        output_tokens=30,
        latency_ms=120.0,
        parsed=parsed,
    )


def _call(**overrides):
    kwargs = dict(
        session_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        turn_number=1,
        user_message="I want something slow and contemplative, no horror please",
        prior_profile=None,
        recent_turns=[],
    )
    kwargs.update(overrides)
    return extract(**kwargs)


class TestHappyPath:
    """Profile agent returns a validated UserProfile from the LLM response."""

    def test_returns_user_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = _profile()
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call()
        assert isinstance(result, UserProfile)

    def test_constraints_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = _profile(constraints=["no sci-fi", "English only"])
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call()
        assert result.constraints == ["no sci-fi", "English only"]

    def test_preferences_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = _profile(preferences=["ensemble casts", "70s aesthetics"])
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call()
        assert result.preferences == ["ensemble casts", "70s aesthetics"]

    def test_attitudes_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = _profile(attitudes=["decisive"])
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call()
        assert result.attitudes == ["decisive"]

    def test_summary_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        summary = "Wants slow, quiet dramas. Hates horror."
        profile = _profile(summary=summary)
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call()
        assert result.summary == summary


class TestFirstTurnNoPriorProfile:
    """extract() accepts prior_profile=None on the first turn."""

    def test_none_prior_profile_accepted(self, monkeypatch: pytest.MonkeyPatch) -> None:
        profile = _profile(constraints=[], preferences=[], attitudes=[], summary="")
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call(prior_profile=None)
        assert isinstance(result, UserProfile)

    def test_first_turn_can_produce_non_empty_profile(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        profile = _profile(constraints=["no horror"])
        monkeypatch.setattr(
            "backend.profile.profile_agent.llm_harness.call",
            lambda **_kw: _llm_response(profile),
        )
        result = _call(prior_profile=None)
        assert "no horror" in result.constraints


class TestHarnessCallArgs:
    """The harness is called with the expected step_type and schema."""

    def test_step_type_is_profile_extract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_call(**kw):
            captured.update(kw)
            return _llm_response(_profile())

        monkeypatch.setattr("backend.profile.profile_agent.llm_harness.call", fake_call)
        _call()
        assert captured["step_type"] == "profile_extract"

    def test_response_schema_is_user_profile(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict = {}

        def fake_call(**kw):
            captured.update(kw)
            return _llm_response(_profile())

        monkeypatch.setattr("backend.profile.profile_agent.llm_harness.call", fake_call)
        _call()
        assert captured["response_schema"] is UserProfile


class TestDryRunFixture:
    """The dry-run fixture for profile_extract validates against UserProfile schema."""

    def test_dry_run_returns_user_profile(self) -> None:
        from backend.llm import llm_harness

        result = llm_harness.call(
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            config_hash="deadbeef",
            model_and_version="gpt-4o-mini",
            seed=0,
            max_tokens=256,
            step_type="profile_extract",
            messages=[{"role": "system", "content": "test"}],
            prompt_hash="cafef00d",
            cost_limit_usd=1.0,
            accumulated_cost_usd=0.0,
            dry_run=True,
            response_schema=UserProfile,
        )
        assert isinstance(result.parsed, UserProfile)
