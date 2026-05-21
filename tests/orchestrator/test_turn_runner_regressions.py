"""Regression tests for the per-turn runner.

Each test pins behaviour that was either broken or latently broken before
the ``backend/orchestrator/turn/`` refactor:

* ``test_hard_limit_emits_wrap_up_only`` — the hard-limit branch must NOT
  fire any ``understand`` progress events. The pre-refactor code emitted
  a lowercase ``ProgressStep.understand`` pair here, which would have
  raised ``AttributeError`` had a real (non-mocked) ``_emit`` ever been
  driven through that path.

* ``test_natural_end_discard_all_does_not_raise`` — the discard path on
  ``natural_end`` (and ``clarify_drift``) used to reach for a field
  named ``speculative_kind`` while the attribute was actually
  ``speculative_branch_kind``. With the refactor the field has one
  canonical name on ``TurnTasks`` and ``discard_all`` is exercised end
  to end here against real tasks.
"""

from __future__ import annotations

import asyncio
import uuid
from unittest.mock import MagicMock

from backend.repository.sessions.types import SessionRow
from backend.orchestrator.turn.context import TurnContext
from backend.orchestrator.turn.runner import TurnRunner
from backend.orchestrator.turn.tasks import TurnTasks
from backend.orchestrator.turn.progress import ProgressEvent
from backend.orchestrator.turn.speculative import SpeculativeBranch
from backend.state.types import StateAction, StateDecision


class _Recorder:
    """Records (step, phase) tuples for every progress event it sees."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def __call__(self, event) -> None:
        if isinstance(event, ProgressEvent):
            self.events.append((event.step.value, event.phase))


def _cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.session.max_turns = 15
    cfg.session.cost_limit_usd = 5.0
    cfg.session.recommendation_top_k = 3
    return cfg


def _full() -> MagicMock:
    f = MagicMock(spec=SessionRow)
    f.session_id = uuid.uuid4()
    f.run_id = uuid.uuid4()
    f.turns = []
    f.preference_profile = None
    return f


def _ctx(progress_cb) -> TurnContext:
    return TurnContext(
        session_id=uuid.uuid4(),
        user_message="hi",
        turn_id=uuid.uuid4(),
        turn_number=1,
        cfg=_cfg(),
        full_session=_full(),
        prior_profile=None,
        recent_turns=[],
        prior_clustered=None,
        prior_seen=[],
        recommended_last_turn=[],
        progress_cb=progress_cb,
    )


async def test_hard_limit_emits_wrap_up_only(monkeypatch) -> None:
    """The hard-limit branch fires only ``wrap_up`` events — no ``understand``."""
    rec = _Recorder()
    ctx = _ctx(rec)

    captured: dict = {}

    def _fake_terminate_turn(**kwargs):
        captured.update(kwargs)
        return MagicMock()

    def _fake_last_show(full, top_k):
        return None

    monkeypatch.setattr(
        "backend.orchestrator.turn.runner.terminal_paths.terminate_turn",
        _fake_terminate_turn,
    )
    monkeypatch.setattr(
        "backend.orchestrator.turn.runner.presentation.last_show_recommendation",
        _fake_last_show,
    )

    runner = TurnRunner.__new__(TurnRunner)
    runner.ctx = ctx
    runner.tasks = TurnTasks(ctx)

    decision = StateDecision(
        action=StateAction.terminate, reason="max_turns", reply="bye"
    )
    await runner._hard_limit(decision)

    assert rec.events == [("wrap_up", "start"), ("wrap_up", "end")]
    assert captured["decision"] is decision


async def test_natural_end_discard_all_does_not_raise() -> None:
    """``discard_all`` survives a real speculative task without AttributeError.

    Pre-refactor this code path read ``self.speculative_kind.value`` while
    the attribute was named ``speculative_branch_kind`` — guaranteed to
    raise. The fix is in ``TurnTasks``: the field has one name and is
    referenced from the single ``discard_all`` method.
    """
    ctx = _ctx(progress_cb=_Recorder())
    tasks = TurnTasks(ctx)

    spec_started = asyncio.Event()
    spec_cancelled = asyncio.Event()
    profile_started = asyncio.Event()

    async def _slow_speculative() -> list:
        spec_started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            spec_cancelled.set()
            raise
        return []

    async def _slow_profile():
        profile_started.set()
        await asyncio.sleep(60)
        return MagicMock()

    tasks.speculative = asyncio.create_task(_slow_speculative())
    tasks.profile = asyncio.create_task(_slow_profile())
    tasks.speculative_kind = SpeculativeBranch.REFINE

    # Let both background tasks reach their `await asyncio.sleep` point so the
    # cancellation actually flows through their CancelledError handler.
    await spec_started.wait()
    await profile_started.wait()

    await asyncio.wait_for(tasks.discard_all(), timeout=1.0)

    assert spec_cancelled.is_set()
    assert tasks.speculative.cancelled()
    assert tasks.profile.cancelled()
