"""Tests for backend.state.tools.llm_gate (check_llm_state)."""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.state.tools.llm_gate import check_llm_state
from backend.state.types import StateAction, StateCheckResponse
from backend.llm.types import LLMResponse


def _cfg(max_turns: int = 15, max_recommendations: int = 5) -> MagicMock:
    cfg = MagicMock()
    cfg.models.strong.name = "gpt-4o-mini"
    cfg.models.strong.provider = "openai"
    cfg.models.strong.seed = 42
    cfg.models.strong.max_tokens = 256
    cfg.session.max_turns = max_turns
    cfg.session.max_recommendations = max_recommendations
    cfg.session.cost_limit_usd = 5.0
    return cfg


def _llm_response(parsed: StateCheckResponse) -> LLMResponse:
    return LLMResponse(
        content=parsed.model_dump_json(),
        input_tokens=10,
        output_tokens=20,
        latency_ms=100.0,
        parsed=parsed,
    )


def _call(**overrides: Any):
    kwargs: dict[str, Any] = dict(
        session_id=uuid.uuid4(),
        run_id=uuid.uuid4(),
        turn_id=uuid.uuid4(),
        turn_number=1,
        user_message="I want something fun to watch tonight",
        preference_profile=None,
        recent_turns=[],
        show_count=0,
        cfg=_cfg(),
    )
    kwargs.update(overrides)
    return check_llm_state(**kwargs)


class TestProceedDecision:
    def test_proceed_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(decision="proceed", reason="oracle still exploring")
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.action is StateAction.proceed
        assert result.reply is None

    def test_proceed_carries_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(decision="proceed", reason="no closing signal")
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert "no closing signal" in result.reason


class TestNaturalEndDecision:
    def test_natural_end_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="natural_end",
            reason="oracle said thanks and bye",
            farewell_reply="Thanks for exploring with us! Enjoy the film.",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(user_message="Thanks, that's all I needed. Bye!")
        assert result.action is StateAction.natural_end

    def test_natural_end_uses_farewell_reply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        farewell = "Thanks for exploring with CinePal! Enjoy your film."
        parsed = StateCheckResponse(
            decision="natural_end",
            reason="explicit close",
            farewell_reply=farewell,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply == farewell

    def test_natural_end_fallback_reply_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="natural_end",
            reason="explicit close",
            farewell_reply=None,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply is not None
        assert len(result.reply) > 0


class TestClarifyDriftDecision:
    def test_clarify_drift_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="clarify_drift",
            reason="oracle said no horror then asked for horror",
            drift_topic="horror",
            prior_statement="I don't like horror movies",
            current_statement="I want to watch a horror film tonight",
            clarify_reply="Earlier you said you don't like horror — did your preference change?",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(user_message="I want to watch a horror film tonight")
        assert result.action is StateAction.clarify_drift

    def test_clarify_drift_populates_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="clarify_drift",
            reason="contradiction on genre",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror tonight",
            clarify_reply="Which do you prefer?",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.drift_topic == "horror"
        assert result.prior_statement == "no horror"
        assert result.current_statement == "horror tonight"
        assert result.reply == "Which do you prefer?"

    def test_clarify_drift_fallback_reply_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="clarify_drift",
            reason="contradiction",
            drift_topic="genre",
            prior_statement="no action",
            current_statement="I want action",
            clarify_reply=None,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply is not None
        assert len(result.reply) > 0


class TestDriftConfirmedDecision:
    def test_drift_confirmed_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="drift_confirmed",
            reason="oracle said yes I changed my mind",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(
            user_message="Yes, I changed my mind, show me horror",
            in_drift_clarification_state=True,
        )
        assert result.action is StateAction.drift_confirmed
        assert result.reply is None

    def test_drift_confirmed_carries_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="drift_confirmed",
            reason="oracle explicitly confirmed genre change",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(in_drift_clarification_state=True)
        assert "oracle explicitly confirmed genre change" in result.reason


class TestDriftDismissedDecision:
    def test_drift_dismissed_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="drift_dismissed",
            reason="oracle clarified they meant supernatural drama, not horror",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(
            user_message="No I meant supernatural drama, not horror",
            in_drift_clarification_state=True,
        )
        assert result.action is StateAction.drift_dismissed
        assert result.reply is None

    def test_drift_dismissed_carries_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="drift_dismissed",
            reason="oracle corrected misunderstanding",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(in_drift_clarification_state=True)
        assert "oracle corrected misunderstanding" in result.reason


class TestReRetrieveDecision:
    """Gate returns re_retrieve when oracle signals all recommended films already seen."""

    def test_re_retrieve_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="re_retrieve",
            reason="oracle stated they have already watched all recommended films",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(
            user_message="I've already seen all of those, can you find something I haven't watched?",
            recommended_last_turn=["Film A", "Film B", "Film C"],
        )
        assert result.action is StateAction.re_retrieve
        assert result.reply is None

    def test_re_retrieve_carries_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(
            decision="re_retrieve",
            reason="oracle explicitly stated seen all films",
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(recommended_last_turn=["Film A"])
        assert "oracle explicitly stated seen all films" in result.reason

    def test_seen_films_and_recommended_passed_to_prompt(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(decision="proceed", reason="ok")
        captured: dict = {}

        def mock_load_prompt(name: str, ctx: dict):
            captured.update(ctx)
            return ("system text", "deadbeef")

        monkeypatch.setattr(
            "backend.state.tools.llm_gate.load_prompt",
            mock_load_prompt,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        _call(
            recommended_last_turn=["Film A", "Film B"],
            seen_films=["Film C", "Film D"],
        )
        assert captured.get("recommended_last_turn") == ["Film A", "Film B"]
        assert captured.get("seen_films") == ["Film C", "Film D"]


class TestDriftClarificationStateFlag:
    def test_flag_passed_without_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(decision="proceed", reason="ambiguous")
        captured: dict = {}

        def mock_load_prompt(name: str, ctx: dict):
            captured.update(ctx)
            return ("system text", "deadbeef")

        monkeypatch.setattr(
            "backend.state.tools.llm_gate.load_prompt",
            mock_load_prompt,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        _call(in_drift_clarification_state=True)
        assert captured.get("in_drift_clarification_state") is True

    def test_flag_false_by_default(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = StateCheckResponse(decision="proceed", reason="normal turn")
        captured: dict = {}

        def mock_load_prompt(name: str, ctx: dict):
            captured.update(ctx)
            return ("system text", "deadbeef")

        monkeypatch.setattr(
            "backend.state.tools.llm_gate.load_prompt",
            mock_load_prompt,
        )
        monkeypatch.setattr(
            "backend.state.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        _call()
        assert captured.get("in_drift_clarification_state") is False


class TestDryRunFixture:
    """The dry-run fixture for state_check validates against the schema."""

    def test_fixture_validates(self) -> None:
        from backend.llm import llm_harness

        result = llm_harness.call(
            run_id=uuid.uuid4(),
            session_id=uuid.uuid4(),
            turn_id=uuid.uuid4(),
            config_hash="deadbeef",
            model_and_version="gpt-4o-mini",
            seed=0,
            max_tokens=256,
            step_type="state_check",
            messages=[{"role": "system", "content": "test"}],
            prompt_hash="cafef00d",
            cost_limit_usd=1.0,
            accumulated_cost_usd=0.0,
            dry_run=True,
            response_schema=StateCheckResponse,
        )
        assert isinstance(result.parsed, StateCheckResponse)
        assert result.parsed.decision == "proceed"
