"""Integration-style tests for Orchestrator.handle_turn wiring.

All external dependencies (api, agents) are monkeypatched. No DB, no LLM,
no Docker. Tests verify:
  - Scenario A (fresh) vs Scenario B (refinement after ask) cluster dispatch
  - Profile agent is called after the main pipeline and its result persisted
  - Render is deterministic (no LLM, no orchestrator_render step_type)
  - First-turn prior_profile=None flows correctly
  - Convergence short-circuit paths (terminate, natural_end, clarify_drift)
"""

from __future__ import annotations

import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.api.types import (
    ClusterAssignment,
    ClusterSnapshot,
    SessionFull,
    SessionStatus,
    StepType,
    TurnDetail,
)
from backend.convergence.types import ConvergenceAction, ConvergenceDecision
from backend.decision.types import DecisionAction, DecisionResult
from backend.profile.types import UserProfile
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.progress import ProgressEvent, ProgressStep


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _session_id() -> uuid.UUID:
    return uuid.uuid4()


def _cluster(name: str = "Drama", n_assignments: int = 3) -> ClusterSnapshot:
    c = MagicMock(spec=ClusterSnapshot)
    c.id = uuid.uuid4()
    c.name = name
    c.description = "Great dramas"
    c.level = 0
    c.parent_cluster_id = None
    c.assignments = [
        MagicMock(spec=ClusterAssignment, title=f"Film {i}", movie_id=uuid.uuid4(), score=1.0, excluded=False)
        for i in range(n_assignments)
    ]
    return c


def _turn(step_type: str = "ask", assistant_message: str = "What genre?", clusters=None) -> MagicMock:
    t = MagicMock(spec=TurnDetail)
    t.step_type = step_type
    t.assistant_message = assistant_message
    t.user_message = "hi"
    t.clusters = clusters or []
    return t


def _full(
    turns: list | None = None,
    preference_profile: dict[str, Any] | None = None,
) -> MagicMock:
    f = MagicMock(spec=SessionFull)
    f.session_id = uuid.uuid4()
    f.run_id = uuid.uuid4()
    f.turns = turns or []
    f.preference_profile = preference_profile
    return f


def _cfg() -> MagicMock:
    cfg = MagicMock()
    cfg.model.name = "gpt-4o-mini"
    cfg.model.provider = "openai"
    cfg.model.seed = 42
    cfg.model.max_tokens = 256
    cfg.session.max_turns = 15
    cfg.session.max_recommendations = 5
    cfg.session.cost_limit_usd = 5.0
    cfg.session.recommendation_top_k = 3
    return cfg


def _proceed() -> ConvergenceDecision:
    return ConvergenceDecision(action=ConvergenceAction.proceed, reason="ok")


def _decision_continue() -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.continue_,
        best_cluster_id=None,
        rationale="still uncertain",
        entropy_score=0.8,
    )


def _decision_recommend(cluster_id: uuid.UUID) -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.recommend,
        best_cluster_id=cluster_id,
        rationale="best match for oracle",
        entropy_score=0.1,
    )


def _profile() -> UserProfile:
    return UserProfile(
        constraints=["no horror"],
        preferences=["slow burn"],
        attitudes=["exploratory"],
        summary="Likes slow drama",
    )


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

class _Patches:
    """Context manager that patches all external dependencies."""

    def __init__(
        self,
        *,
        full: MagicMock,
        conv_decision: ConvergenceDecision | None = None,
        clusters: list[ClusterSnapshot] | None = None,
        decision: DecisionResult | None = None,
        ambiguity_question: str = "What mood are you in?",
        profile: UserProfile | None = None,
        cfg: MagicMock | None = None,
    ):
        cluster_list = clusters or [_cluster()]
        self._conv = conv_decision or _proceed()
        self._clusters = cluster_list
        self._decision = decision or _decision_continue()
        self._question = ambiguity_question
        self._profile = profile or _profile()
        self._full = full
        self._cfg = cfg or _cfg()
        self._patchers: list = []

    def __enter__(self):
        base = "backend.orchestrator.orchestrator"

        def _patch(target, return_value=None, side_effect=None):
            kw = {}
            if return_value is not None:
                kw["return_value"] = return_value
            if side_effect is not None:
                kw["side_effect"] = side_effect
            p = patch(target, **kw)
            self._patchers.append(p)
            return p.start()

        self.get_session_full = _patch(
            "backend.orchestrator.orchestrator.api_retrieval.get_session_full",
            return_value=self._full,
        )
        self.get_settings = _patch(
            "backend.orchestrator.orchestrator.get_settings",
            return_value=self._cfg,
        )
        self.get_config_hash = _patch(
            "backend.orchestrator.orchestrator.get_config_hash",
            return_value="deadbeef",
        )
        self.conv_check = _patch(
            "backend.orchestrator.orchestrator.convergence_agent.check",
            return_value=self._conv,
        )
        self.cluster_cluster = _patch(
            "backend.orchestrator.orchestrator.cluster_agent.cluster",
            return_value=self._clusters,
        )
        self.decision_decide = _patch(
            "backend.orchestrator.orchestrator.decision_agent.decide",
            return_value=self._decision,
        )
        self.ambiguity_gen = _patch(
            "backend.orchestrator.orchestrator.ambiguity_agent.generate_question",
            return_value=MagicMock(question_text=self._question),
        )
        self.profile_extract = _patch(
            "backend.orchestrator.orchestrator.profile_agent.extract",
            return_value=self._profile,
        )
        self.append_turn = _patch(
            "backend.orchestrator.orchestrator.api_sessions.append_turn",
        )
        self.update_turn = _patch(
            "backend.orchestrator.orchestrator.api_sessions.update_turn",
        )
        self.snapshot_clusters = _patch(
            "backend.orchestrator.orchestrator.api_sessions.snapshot_clusters",
        )
        self.write_feedback = _patch(
            "backend.orchestrator.orchestrator.api_sessions.write_feedback",
        )
        self.update_profile = _patch(
            "backend.orchestrator.orchestrator.api_sessions.update_preference_profile",
        )
        self.should_retrieve = _patch(
            "backend.orchestrator.orchestrator.should_retrieve",
            return_value=MagicMock(retrieve=False, query=None),
        )
        return self

    def __exit__(self, *args):
        for p in reversed(self._patchers):
            p.stop()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestScenarioAFreshClustering:
    """When no prior ask turn, Scenario A (fresh) is used — no prior_clusters."""

    def test_cluster_called_without_prior_clusters(self) -> None:
        full = _full(turns=[])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "I want something contemplative")
        call_kwargs = p.cluster_cluster.call_args.kwargs
        assert "prior_clusters" not in call_kwargs or call_kwargs.get("prior_clusters") is None

    def test_cluster_called_with_user_query(self) -> None:
        full = _full(turns=[_turn("show", "Here is a pick")])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "more like that")
        call_kwargs = p.cluster_cluster.call_args.kwargs
        assert "user_query" in call_kwargs


class TestScenarioBRefinementAfterAsk:
    """When prior turn is an ask with clusters, Scenario B is used."""

    def test_cluster_called_with_prior_clusters(self) -> None:
        prior_clusters = [_cluster("Drama")]
        prior = _turn("ask", "What genre?", clusters=prior_clusters)
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "Drama please")
        call_kwargs = p.cluster_cluster.call_args.kwargs
        assert call_kwargs.get("prior_clusters") is not None
        assert len(call_kwargs["prior_clusters"]) == 1

    def test_scenario_b_passes_asked_question(self) -> None:
        prior = _turn("ask", "What do you feel like?", clusters=[_cluster()])
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "Action")
        call_kwargs = p.cluster_cluster.call_args.kwargs
        assert call_kwargs.get("asked_question") == "What do you feel like?"

    def test_scenario_a_when_prior_turn_is_show(self) -> None:
        prior = _turn("show", "Here are some dramas", clusters=[_cluster()])
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "something different")
        call_kwargs = p.cluster_cluster.call_args.kwargs
        assert not call_kwargs.get("prior_clusters")


class TestProfileAgentFlow:
    """Profile agent is called after main pipeline; result is persisted."""

    def test_profile_extract_called(self) -> None:
        full = _full(turns=[])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "fun movie tonight")
        assert p.profile_extract.called

    def test_profile_result_persisted(self) -> None:
        profile = _profile()
        full = _full(turns=[])
        with _Patches(full=full, profile=profile) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "fun movie tonight")
        p.update_profile.assert_called_once()
        call_args = p.update_profile.call_args
        persisted = call_args.args[1] if call_args.args else call_args.kwargs.get("preference_profile") or call_args.kwargs.get("profile_jsonb")
        assert persisted == profile.model_dump()

    def test_profile_extract_receives_prior_profile(self) -> None:
        prior = {"constraints": ["no horror"], "preferences": [], "attitudes": [], "summary": ""}
        full = _full(turns=[], preference_profile=prior)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "something calm")
        call_kwargs = p.profile_extract.call_args.kwargs
        assert call_kwargs["prior_profile"] == prior

    def test_first_turn_prior_profile_is_none(self) -> None:
        full = _full(turns=[], preference_profile=None)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "anything good tonight")
        call_kwargs = p.profile_extract.call_args.kwargs
        assert call_kwargs["prior_profile"] is None


class TestRenderIsDeterministic:
    """Render path uses no LLM — only cluster + decision data."""

    def test_recommend_step_type_is_show(self) -> None:
        cluster = _cluster()
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision) as p:
            orch = Orchestrator()
            result = orch.handle_turn(full.session_id, "surprise me")
        assert result.step_type == StepType.show

    def test_render_reply_contains_cluster_name(self) -> None:
        cluster = _cluster("Epic Adventures")
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            result = orch.handle_turn(full.session_id, "surprise me")
        assert "Epic Adventures" in result.assistant_message

    def test_render_reply_contains_rationale(self) -> None:
        cluster = _cluster()
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            result = orch.handle_turn(full.session_id, "surprise me")
        assert "best match for oracle" in result.assistant_message


class TestConvergenceShortCircuits:
    """Terminate, natural_end, and clarify_drift bypass the main pipeline."""

    def test_terminate_returns_stop_step_type(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.terminate,
            reason="max_turns exceeded",
            reply="Session over.",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            # Terminate path calls append_turn + mark_abandoned — mock those
            mark_abandoned = patch(
                "backend.orchestrator.orchestrator.api_sessions.mark_abandoned"
            ).start()
            try:
                orch = Orchestrator()
                result = orch.handle_turn(full.session_id, "hi")
            finally:
                mark_abandoned.stop()
        assert result.step_type == StepType.stop
        # Profile result must NOT be persisted on termination (speculative run is discarded)
        assert not p.update_profile.called

    def test_natural_end_does_not_persist_profile(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.natural_end,
            reason="oracle said bye",
            reply="Goodbye!",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            with patch("backend.orchestrator.orchestrator.api_sessions.mark_converged"), \
                 patch("backend.orchestrator.orchestrator.api_sessions.append_turn"):
                orch = Orchestrator()
                result = orch.handle_turn(full.session_id, "bye")
        # Profile result must NOT be persisted on natural_end (speculative run is discarded)
        assert not p.update_profile.called

    def test_clarify_drift_does_not_snapshot_clusters(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.clarify_drift,
            reason="contradiction",
            reply="Did your preference change?",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror please",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            with patch("backend.orchestrator.orchestrator.emit_drift_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                orch.handle_turn(full.session_id, "horror please")
        # Cluster result must NOT be persisted on clarify_drift (speculative run is discarded)
        assert not p.snapshot_clusters.called


class TestDecisionAgentReceivesProfile:
    """Decision agent is called with the N-1 preference profile."""

    def test_decision_receives_prior_profile(self) -> None:
        prior = {"constraints": ["no horror"], "preferences": [], "attitudes": [], "summary": ""}
        full = _full(turns=[], preference_profile=prior)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "drama")
        call_kwargs = p.decision_decide.call_args.kwargs
        assert call_kwargs["preference_profile"] == prior

    def test_decision_receives_none_on_first_turn(self) -> None:
        full = _full(turns=[], preference_profile=None)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "drama")
        call_kwargs = p.decision_decide.call_args.kwargs
        assert call_kwargs["preference_profile"] is None


class _Recorder:
    """ProgressCallback that records (step, phase) pairs in order."""

    def __init__(self) -> None:
        self.events: list[tuple[str, str]] = []

    def __call__(self, event: ProgressEvent) -> None:
        self.events.append((event.step.value, event.phase))


class TestProgressCallback:
    """Wave-level progress events fire in the expected order for every branch."""

    def test_recommend_emits_understand_choose_finalize(self) -> None:
        cluster = _cluster()
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        rec = _Recorder()
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "surprise me", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("choose", "start"),
            ("choose", "end"),
            ("finalize", "start"),
            ("finalize", "end"),
        ]

    def test_continue_emits_understand_choose_finalize(self) -> None:
        full = _full(turns=[])
        rec = _Recorder()
        with _Patches(full=full):
            orch = Orchestrator()
            orch.handle_turn(full.session_id, "tell me more", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("choose", "start"),
            ("choose", "end"),
            ("finalize", "start"),
            ("finalize", "end"),
        ]

    def test_terminate_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.terminate,
            reason="max_turns exceeded",
            reply="Session over.",
        )
        rec = _Recorder()
        with _Patches(full=full, conv_decision=conv):
            with patch("backend.orchestrator.orchestrator.api_sessions.mark_abandoned"), \
                 patch("backend.orchestrator.orchestrator.api_sessions.append_turn"):
                orch = Orchestrator()
                orch.handle_turn(full.session_id, "hi", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_natural_end_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.natural_end,
            reason="oracle said bye",
            reply="Goodbye!",
        )
        rec = _Recorder()
        with _Patches(full=full, conv_decision=conv):
            with patch("backend.orchestrator.orchestrator.api_sessions.mark_converged"), \
                 patch("backend.orchestrator.orchestrator.api_sessions.append_turn"), \
                 patch("backend.orchestrator.orchestrator.api_sessions.write_feedback"):
                orch = Orchestrator()
                orch.handle_turn(full.session_id, "bye", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_clarify_drift_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        conv = ConvergenceDecision(
            action=ConvergenceAction.clarify_drift,
            reason="contradiction",
            reply="Did your preference change?",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror please",
        )
        rec = _Recorder()
        with _Patches(full=full, conv_decision=conv):
            with patch("backend.orchestrator.orchestrator.emit_drift_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                orch.handle_turn(full.session_id, "horror please", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_empty_retrieval_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        rec = _Recorder()
        with _Patches(full=full) as p:
            # ``_Patches`` ignores empty cluster lists (``or`` default); override.
            p.cluster_cluster.return_value = []
            with patch("backend.orchestrator.orchestrator.emit_early_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                orch.handle_turn(full.session_id, "thing", progress_cb=rec)
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_callback_exception_does_not_abort_turn(self) -> None:
        """A misbehaving callback must not crash the orchestrator."""

        def boom(event: ProgressEvent) -> None:
            raise RuntimeError("callback exploded")

        cluster = _cluster()
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            result = orch.handle_turn(full.session_id, "go", progress_cb=boom)
        assert result.step_type == StepType.show
