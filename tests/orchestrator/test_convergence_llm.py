"""Tests for the LLM convergence gate (check_llm_convergence).

Uses monkeypatching to control llm_harness.call output, so no network or DB
is required. Tests cover the three decision branches: proceed, natural_end,
clarify_drift.
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock

import pytest

from backend.convergence.tools.llm_gate import check_llm_convergence
from backend.convergence.types import ConvergenceAction, ConvergenceCheckResponse
from backend.llm.types import LLMResponse


def _cfg(max_turns: int = 15, max_recommendations: int = 5) -> MagicMock:
    """Return a minimal Settings-like object."""
    cfg = MagicMock()
    cfg.models.strong.name = "gpt-4o-mini"
    cfg.models.strong.provider = "openai"
    cfg.models.strong.seed = 42
    cfg.models.strong.max_tokens = 256
    cfg.session.max_turns = max_turns
    cfg.session.max_recommendations = max_recommendations
    cfg.session.cost_limit_usd = 5.0
    return cfg


def _llm_response(parsed: ConvergenceCheckResponse) -> LLMResponse:
    """Wrap a ConvergenceCheckResponse in a minimal LLMResponse."""
    return LLMResponse(
        content=parsed.model_dump_json(),
        input_tokens=10,
        output_tokens=20,
        latency_ms=100.0,
        parsed=parsed,
    )


def _call(**overrides: Any):
    """Invoke check_llm_convergence with sensible defaults."""
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
    return check_llm_convergence(**kwargs)


class TestProceedDecision:
    """Gate returns proceed when the model judges the conversation should continue."""

    def test_proceed_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(decision="proceed", reason="oracle still exploring")
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.action is ConvergenceAction.proceed
        assert result.reply is None

    def test_proceed_carries_reason(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(decision="proceed", reason="no closing signal")
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert "no closing signal" in result.reason


class TestNaturalEndDecision:
    """Gate returns natural_end when the model detects the oracle wrapping up."""

    def test_natural_end_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(
            decision="natural_end",
            reason="oracle said thanks and bye",
            farewell_reply="Thanks for exploring with us! Enjoy the film.",
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(user_message="Thanks, that's all I needed. Bye!")
        assert result.action is ConvergenceAction.natural_end

    def test_natural_end_uses_farewell_reply(self, monkeypatch: pytest.MonkeyPatch) -> None:
        farewell = "Thanks for exploring with CinePal! Enjoy your film."
        parsed = ConvergenceCheckResponse(
            decision="natural_end",
            reason="explicit close",
            farewell_reply=farewell,
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply == farewell

    def test_natural_end_fallback_reply_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(
            decision="natural_end",
            reason="explicit close",
            farewell_reply=None,
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply is not None
        assert len(result.reply) > 0


class TestClarifyDriftDecision:
    """Gate returns clarify_drift when the model detects a preference contradiction."""

    def test_clarify_drift_action(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(
            decision="clarify_drift",
            reason="oracle said no horror then asked for horror",
            drift_topic="horror",
            prior_statement="I don't like horror movies",
            current_statement="I want to watch a horror film tonight",
            clarify_reply="Earlier you said you don't like horror — did your preference change?",
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call(user_message="I want to watch a horror film tonight")
        assert result.action is ConvergenceAction.clarify_drift

    def test_clarify_drift_populates_fields(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(
            decision="clarify_drift",
            reason="contradiction on genre",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror tonight",
            clarify_reply="Which do you prefer?",
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.drift_topic == "horror"
        assert result.prior_statement == "no horror"
        assert result.current_statement == "horror tonight"
        assert result.reply == "Which do you prefer?"

    def test_clarify_drift_fallback_reply_when_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        parsed = ConvergenceCheckResponse(
            decision="clarify_drift",
            reason="contradiction",
            drift_topic="genre",
            prior_statement="no action",
            current_statement="I want action",
            clarify_reply=None,
        )
        monkeypatch.setattr(
            "backend.convergence.tools.llm_gate.llm_harness.call",
            lambda **_kw: _llm_response(parsed),
        )
        result = _call()
        assert result.reply is not None
        assert len(result.reply) > 0


class TestDryRunFixture:
    """The dry-run fixture for convergence_check validates against the schema."""

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
            step_type="convergence_check",
            messages=[{"role": "system", "content": "test"}],
            prompt_hash="cafef00d",
            cost_limit_usd=1.0,
            accumulated_cost_usd=0.0,
            dry_run=True,
            response_schema=ConvergenceCheckResponse,
        )
        assert isinstance(result.parsed, ConvergenceCheckResponse)
        assert result.parsed.decision == "proceed"
