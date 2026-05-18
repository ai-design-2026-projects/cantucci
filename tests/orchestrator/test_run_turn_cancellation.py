"""Cancellation and concurrency tests for ``Orchestrator.run_turn``.

These tests verify the *async task graph* contract — properties that did not
exist in the old wave-based orchestrator and that the wiring tests do not
exercise:

* Speculative branches run concurrently with the state gate (turn 1 race).
* State verdicts that invalidate the speculative branch CANCEL the in-flight
  task, instead of awaiting and discarding it.
* Outer cancellation (FastAPI request task / client disconnect) cascades
  into every spawned child task.
* The sync hard-limit gate trips before any LLM agent is invoked.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.api.types import (
    ClusterAssignment,
    ClusterSnapshot,
    SessionFull,
    StepType,
    TurnDetail,
)
from backend.retrieval.types import RetrievalResult
from backend.state.types import StateAction, StateDecision
from backend.decision.types import DecisionAction, DecisionResult
from backend.profile.types import UserProfile
from backend.orchestrator.orchestrator import Orchestrator


# ---------------------------------------------------------------------------
# Builders (mirror tests/orchestrator/test_handle_turn_wiring.py)
# ---------------------------------------------------------------------------

_NEXT_MOVIE_ID: list[int] = [10_000]


def _cluster(name: str = "Drama", n: int = 3) -> ClusterSnapshot:
    c = MagicMock(spec=ClusterSnapshot)
    c.id = uuid.uuid4()
    c.name = name
    c.description = "x"
    c.level = 0
    c.parent_cluster_id = None
    assignments = []
    for i in range(n):
        mid = _NEXT_MOVIE_ID[0]
        _NEXT_MOVIE_ID[0] += 1
        assignments.append(
            MagicMock(spec=ClusterAssignment, title=f"Film {i}", movie_id=mid, score=1.0, excluded=False)
        )
    c.assignments = assignments
    return c


def _turn(step_type: str = "ask", assistant: str = "?", clusters=None) -> MagicMock:
    t = MagicMock(spec=TurnDetail)
    t.step_type = step_type
    t.assistant_message = assistant
    t.user_message = "x"
    t.clusters = clusters or []
    return t


def _full(turns: list | None = None, prior_profile: dict[str, Any] | None = None) -> MagicMock:
    f = MagicMock(spec=SessionFull)
    f.session_id = uuid.uuid4()
    f.run_id = uuid.uuid4()
    f.turns = turns or []
    f.preference_profile = prior_profile
    return f


def _cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.models.strong.name = "gpt-4o-mini"
    cfg.models.strong.provider = "openai"
    cfg.models.strong.seed = 42
    cfg.models.strong.max_tokens = 256
    cfg.session.max_turns = 15
    cfg.session.max_recommendations = 5
    cfg.session.cost_limit_usd = 5.0
    cfg.session.recommendation_top_k = 3
    return cfg


def _profile_dto() -> UserProfile:
    return UserProfile(constraints=[], preferences=[], attitudes=[], summary="")


def _proceed() -> StateDecision:
    return StateDecision(action=StateAction.proceed, reason="ok")


def _decision_continue() -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.continue_,
        best_cluster_id=None,
        rationale="r",
        entropy_score=0.5,
        question_text="why?",
        cluster_refs=[],
    )


def _mock_rr() -> MagicMock:
    rr = MagicMock(spec=RetrievalResult)
    rr.reformulated_query = "rq"
    rr.candidates = []
    return rr


# ---------------------------------------------------------------------------
# Patch helper
# ---------------------------------------------------------------------------

class _GraphPatches:
    """Patch all agent + DB seams for run_turn. Override mocks per-test."""

    def __init__(self, full: MagicMock, *, cfg: MagicMock | None = None) -> None:
        self._full = full
        self._cfg = cfg or _cfg()
        self._patchers: list = []
        self.gate_event: asyncio.Event | None = None

    def __enter__(self):
        def _p(target, return_value=None, side_effect=None, *, is_async=False):
            kw: dict = {}
            if return_value is not None:
                kw["return_value"] = return_value
            if side_effect is not None:
                kw["side_effect"] = side_effect
            if is_async:
                kw["new_callable"] = AsyncMock
            patcher = patch(target, **kw)
            self._patchers.append(patcher)
            return patcher.start()

        # Make the orchestrator DB-free.
        self.get_session_full = _p(
            "backend.orchestrator.orchestrator.api_retrieval.get_session_full",
            return_value=self._full,
        )
        self.get_settings = _p(
            "backend.orchestrator.orchestrator.get_settings",
            return_value=self._cfg,
        )
        self.get_config_hash = _p(
            "backend.orchestrator.orchestrator.get_config_hash",
            return_value="deadbeef",
        )
        self.hard_limits = _p(
            "backend.orchestrator.orchestrator.state_agent.check_hard_limits",
            return_value=StateDecision(action=StateAction.proceed, reason="ok"),
        )
        self.check_gate = _p(
            "backend.orchestrator.orchestrator.state_agent.check_gate",
            return_value=_proceed(),
            is_async=True,
        )
        self.retrieve_from_message = _p(
            "backend.orchestrator.orchestrator.retrieval_agent.retrieve_from_message",
            return_value=_mock_rr(),
            is_async=True,
        )
        self.retrieve_from_profile = _p(
            "backend.orchestrator.orchestrator.retrieval_agent.retrieve_from_profile",
            return_value=_mock_rr(),
            is_async=True,
        )
        self.soft_cluster = _p(
            "backend.orchestrator.orchestrator.cluster_agent.soft_cluster",
            return_value=MagicMock(),
        )
        self.describe_clusters = _p(
            "backend.orchestrator.orchestrator.cluster_agent.describe_clusters",
            return_value=[_cluster()],
            is_async=True,
        )
        self.refine = _p(
            "backend.orchestrator.orchestrator.cluster_agent.refine",
            return_value=[_cluster()],
            is_async=True,
        )
        self.decide = _p(
            "backend.orchestrator.orchestrator.decision_agent.decide",
            return_value=_decision_continue(),
            is_async=True,
        )
        self.profile_extract = _p(
            "backend.orchestrator.orchestrator.profile_agent.extract",
            return_value=_profile_dto(),
            is_async=True,
        )
        self.append_turn = _p("backend.orchestrator.orchestrator.api_sessions.append_turn")
        self.update_turn = _p("backend.orchestrator.orchestrator.api_sessions.update_turn")
        self.snapshot_clusters = _p(
            "backend.orchestrator.orchestrator.api_sessions.snapshot_clusters"
        )
        self.write_feedback = _p("backend.orchestrator.orchestrator.api_sessions.write_feedback")
        self.update_profile = _p(
            "backend.orchestrator.orchestrator.api_sessions.update_preference_profile"
        )
        self.mark_abandoned = _p(
            "backend.orchestrator.orchestrator.api_sessions.mark_abandoned"
        )
        self.mark_converged = _p(
            "backend.orchestrator.orchestrator.api_sessions.mark_converged"
        )
        self.fetch_stubs = _p(
            "backend.orchestrator.orchestrator.api_movies.fetch_stubs",
            return_value=[],
        )
        self.fetch_movies_public = _p(
            "backend.orchestrator.orchestrator.api_movies.fetch_movies_public",
            return_value=[],
        )
        return self

    def __exit__(self, *exc):
        for p in reversed(self._patchers):
            p.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_turn_one_speculative_retrieval_runs_concurrently_with_state_gate() -> None:
    """On turn 1, retrieval_from_message must be in-flight before check_gate resolves."""
    full = _full(turns=[])

    with _GraphPatches(full) as p:
        retrieval_started = asyncio.Event()
        retrieval_release = asyncio.Event()

        async def _retrieve(*args, **kwargs):
            retrieval_started.set()
            await retrieval_release.wait()
            return _mock_rr()

        async def _gate(*args, **kwargs):
            # State gate only completes after observing the speculative branch
            # already entered retrieval. If retrieval had been gated on the
            # state result we'd deadlock here.
            await retrieval_started.wait()
            retrieval_release.set()
            return _proceed()

        p.retrieve_from_message.side_effect = _retrieve
        p.check_gate.side_effect = _gate

        orch = Orchestrator()
        await asyncio.wait_for(
            orch.run_turn(full.session_id, "hi"),
            timeout=2.0,
        )

        assert p.retrieve_from_message.called
        assert p.check_gate.called


async def test_drift_confirmed_cancels_speculative_retrieval() -> None:
    """drift_confirmed must cancel the in-flight speculative retrieval task."""
    prior_show = _turn("show", "here", clusters=[_cluster()])
    full = _full(turns=[prior_show])

    with _GraphPatches(full) as p:
        # Speculative retrieve_from_message blocks indefinitely so cancellation
        # is the only path that lets the turn finish.
        cancel_seen = asyncio.Event()

        async def _slow_retrieve(*args, **kwargs):
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                cancel_seen.set()
                raise
            return _mock_rr()

        p.retrieve_from_message.side_effect = _slow_retrieve
        p.check_gate.return_value = StateDecision(
            action=StateAction.drift_confirmed, reason="changed"
        )

        orch = Orchestrator()
        await asyncio.wait_for(
            orch.run_turn(full.session_id, "yes I changed my mind"),
            timeout=2.0,
        )

        assert cancel_seen.is_set(), "speculative retrieve_from_message was not cancelled"
        assert p.retrieve_from_profile.called, "drift_confirmed must call retrieve_from_profile"


async def test_refine_path_does_not_call_retrieve_from_message() -> None:
    """On a refinement turn, the speculative branch is refine — not retrieve."""
    prior_ask = _turn("ask", "what mood?", clusters=[_cluster()])
    full = _full(turns=[prior_ask])

    with _GraphPatches(full) as p:
        orch = Orchestrator()
        await asyncio.wait_for(
            orch.run_turn(full.session_id, "calm"),
            timeout=2.0,
        )
        assert p.refine.called
        assert not p.retrieve_from_message.called


async def test_outer_cancellation_propagates_into_state_gate() -> None:
    """Cancelling the run_turn task aborts the in-flight LLM gate."""
    full = _full(turns=[])

    with _GraphPatches(full) as p:
        gate_cancelled = asyncio.Event()
        gate_entered = asyncio.Event()

        async def _slow_gate(*args, **kwargs):
            gate_entered.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                gate_cancelled.set()
                raise
            return _proceed()

        p.check_gate.side_effect = _slow_gate

        orch = Orchestrator()
        task = asyncio.create_task(orch.run_turn(full.session_id, "hi"))
        await gate_entered.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert gate_cancelled.is_set(), "state gate did not observe CancelledError"
        # update_turn writes only on the success path; cancellation must NOT
        # persist a half-run turn.
        assert not p.update_turn.called


async def test_outer_cancellation_propagates_into_speculative_branch() -> None:
    """Cancelling the run_turn task also aborts the speculative branch."""
    full = _full(turns=[])

    with _GraphPatches(full) as p:
        spec_cancelled = asyncio.Event()
        spec_entered = asyncio.Event()
        gate_entered = asyncio.Event()

        async def _slow_retrieve(*args, **kwargs):
            spec_entered.set()
            try:
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                spec_cancelled.set()
                raise
            return _mock_rr()

        async def _slow_gate(*args, **kwargs):
            gate_entered.set()
            await asyncio.sleep(60)
            return _proceed()

        p.retrieve_from_message.side_effect = _slow_retrieve
        p.check_gate.side_effect = _slow_gate

        orch = Orchestrator()
        task = asyncio.create_task(orch.run_turn(full.session_id, "hi"))
        # Both tasks must be in-flight before we cancel, otherwise we'd just be
        # asserting that an unstarted coroutine "cancels".
        await spec_entered.wait()
        await gate_entered.wait()
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        assert spec_cancelled.is_set(), "speculative branch did not observe CancelledError"


async def test_hard_limit_terminate_makes_no_llm_call() -> None:
    """When hard_limits trips, the LLM gate / profile / retrieval are never called."""
    full = _full(turns=[])

    with _GraphPatches(full) as p:
        p.hard_limits.return_value = StateDecision(
            action=StateAction.terminate,
            reason="max_turns",
            reply="bye",
        )
        orch = Orchestrator()
        result = await asyncio.wait_for(
            orch.run_turn(full.session_id, "hi"),
            timeout=2.0,
        )

        assert result.step_type == StepType.stop
        # The terminal path may not even await the LLM mocks; assert they were
        # never called.
        assert not p.check_gate.called
        assert not p.profile_extract.called
        assert not p.retrieve_from_message.called
        assert not p.refine.called
        assert p.mark_abandoned.called
