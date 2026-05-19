"""Unit tests for the state hard-limit gate (check_hard_limits).

These tests cover only the deterministic layer — no LLM, no DB, no Docker.
SessionRow objects are built inline with the minimal fields needed.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from unittest.mock import MagicMock

import pytest

from backend.state.tools.hard_limits import check_hard_limits
from backend.state.types import StateAction


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _turn(step_type: str | None = "show") -> MagicMock:
    """Return a minimal TurnRow-like object."""
    t = MagicMock()
    t.step_type = step_type
    return t


def _full(turns: list, max_turns: int = 15) -> MagicMock:
    """Return a minimal SessionRow-like object."""
    f = MagicMock()
    f.session_id = uuid.uuid4()
    f.turns = turns
    f.max_turns = max_turns
    return f


def _cfg(max_turns: int = 15, max_recommendations: int = 5) -> MagicMock:
    """Return a minimal Settings-like object."""
    cfg = MagicMock()
    cfg.session.max_turns = max_turns
    cfg.session.max_recommendations = max_recommendations
    return cfg


class TestHardLimitsUnderBudget:
    """When both limits are under threshold, the gate proceeds."""

    def test_first_turn_proceeds(self) -> None:
        full = _full(turns=[])
        result = check_hard_limits(turn_number=1, full=full, cfg=_cfg())
        assert result.action is StateAction.proceed

    def test_mid_session_proceeds(self) -> None:
        turns = [_turn("show"), _turn("ask"), _turn("show")]
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=4, full=full, cfg=_cfg(max_turns=15, max_recommendations=5))
        assert result.action is StateAction.proceed

    def test_ask_turns_do_not_count_toward_recommendations(self) -> None:
        turns = [_turn("ask")] * 4
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=5, full=full, cfg=_cfg(max_recommendations=1))
        assert result.action is StateAction.proceed


class TestMaxTurnsLimit:
    """turn_number > max_turns trips the terminate gate."""

    def test_exactly_at_limit_proceeds(self) -> None:
        full = _full(turns=[_turn("ask")] * 2)
        result = check_hard_limits(turn_number=15, full=full, cfg=_cfg(max_turns=15))
        assert result.action is StateAction.proceed

    def test_one_over_limit_terminates(self) -> None:
        full = _full(turns=[_turn("ask")] * 15)
        result = check_hard_limits(turn_number=16, full=full, cfg=_cfg(max_turns=15))
        assert result.action is StateAction.terminate
        assert result.reply is not None
        assert "15" in result.reply
        assert result.reason

    def test_far_over_limit_terminates(self) -> None:
        full = _full(turns=[_turn("show")] * 20)
        result = check_hard_limits(turn_number=30, full=full, cfg=_cfg(max_turns=15))
        assert result.action is StateAction.terminate


class TestMaxRecommendationsLimit:
    """show_count >= max_recommendations trips the terminate gate."""

    def test_exactly_at_cap_terminates(self) -> None:
        turns = [_turn("show")] * 5
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=6, full=full, cfg=_cfg(max_recommendations=5))
        assert result.action is StateAction.terminate
        assert result.reply is not None
        assert "5" in result.reply

    def test_one_under_cap_proceeds(self) -> None:
        turns = [_turn("show")] * 4
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=5, full=full, cfg=_cfg(max_recommendations=5))
        assert result.action is StateAction.proceed

    def test_mixed_turn_types_only_show_counted(self) -> None:
        turns = [_turn("show"), _turn("ask"), _turn("show"), _turn("ask"), _turn("show")]
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=6, full=full, cfg=_cfg(max_recommendations=3))
        assert result.action is StateAction.terminate

    def test_stop_type_not_counted(self) -> None:
        turns = [_turn("stop"), _turn("stop"), _turn("stop")]
        full = _full(turns=turns)
        result = check_hard_limits(turn_number=4, full=full, cfg=_cfg(max_recommendations=3))
        assert result.action is StateAction.proceed


class TestTerminateDecisionShape:
    """Terminated decisions carry a non-empty reply and a reason string."""

    def test_terminate_has_reply(self) -> None:
        full = _full(turns=[_turn("show")] * 5)
        result = check_hard_limits(turn_number=6, full=full, cfg=_cfg(max_recommendations=5))
        assert result.action is StateAction.terminate
        assert isinstance(result.reply, str)
        assert len(result.reply) > 0

    def test_terminate_has_reason(self) -> None:
        full = _full(turns=[])
        result = check_hard_limits(turn_number=20, full=full, cfg=_cfg(max_turns=15))
        assert result.action is StateAction.terminate
        assert "max_turns" in result.reason or "turn_number" in result.reason
