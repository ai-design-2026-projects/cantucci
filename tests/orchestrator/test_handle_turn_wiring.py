"""Integration-style tests for Orchestrator.handle_turn wiring.

All external dependencies (api, agents) are monkeypatched. No DB, no LLM,
no Docker. Tests verify:
  - Scenario A (fresh) vs Scenario B (refinement after ask) cluster dispatch
  - Profile agent is called after the main pipeline and its result persisted
  - Render is deterministic (no LLM, no orchestrator_render step_type)
  - First-turn prior_profile=None flows correctly
  - Convergence short-circuit paths (terminate, natural_end, clarify_drift)
  - Decision agent receives prior_questions and emits the question on continue
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from backend.cluster.domain import ClusterAssignment
from backend.orchestrator.domain import SessionStatus, StepType
from backend.repository.sessions import ClusterRow, SessionRow, TurnRow
from backend.retrieval.types import RetrievalResult
from backend.state.types import StateAction, StateDecision
from backend.decision.types import DecisionAction, DecisionResult
from backend.profile.types import UserProfile
from backend.orchestrator.orchestrator import Orchestrator
from backend.orchestrator.turn.progress import ProgressEvent, ProgressStep


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

def _session_id() -> uuid.UUID:
    return uuid.uuid4()


def _cluster(name: str = "Drama", n_assignments: int = 3) -> ClusterRow:
    c = MagicMock(spec=ClusterRow)
    c.id = uuid.uuid4()
    c.name = name
    c.description = "Great dramas"
    c.level = 0
    c.parent_cluster_id = None
    c.assignments = [
        MagicMock(spec=ClusterAssignment, title=f"Film {i}", movie_id=i + 1, score=1.0, excluded=False)
        for i in range(n_assignments)
    ]
    return c


def _turn(step_type: str = "ask", assistant_message: str = "What genre?", clusters=None) -> MagicMock:
    t = MagicMock()
    t.id = uuid.uuid4()
    t.step_type = step_type
    t.assistant_message = assistant_message
    t.user_message = "hi"
    t.clusters = clusters or []
    return t


def _full(
    turns: list | None = None,
    preference_profile: dict[str, Any] | None = None,
) -> MagicMock:
    f = MagicMock(spec=SessionRow)
    f.session_id = uuid.uuid4()
    f.run_id = uuid.uuid4()
    f.turns = turns or []
    f.preference_profile = preference_profile
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


def _proceed() -> StateDecision:
    return StateDecision(action=StateAction.proceed, reason="ok")


def _decision_continue(question_text: str = "What mood are you in?") -> DecisionResult:
    return DecisionResult(
        action=DecisionAction.continue_,
        best_cluster_id=None,
        rationale="still uncertain",
        entropy_score=0.8,
        question_text=question_text,
        cluster_refs=[],
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
        conv_decision: StateDecision | None = None,
        clusters: list[ClusterRow] | None = None,
        decision: DecisionResult | None = None,
        profile: UserProfile | None = None,
        cfg: MagicMock | None = None,
    ):
        cluster_list = clusters or [_cluster()]
        self._conv = conv_decision or _proceed()
        self._clusters = cluster_list
        self._decision = decision or _decision_continue()
        self._profile = profile or _profile()
        self._full = full
        self._cfg = cfg or _cfg()
        self._patchers: list = []

    def __enter__(self):
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
            "backend.repository.sessions.get_session_full",
            return_value=self._full,
        )
        self.get_settings = _patch(
            "backend.orchestrator.turn.context.get_settings",
            return_value=self._cfg,
        )
        self.get_config_hash = _patch(
            "backend.orchestrator.orchestrator.get_config_hash",
            return_value="deadbeef",
        )
        self.conv_check = _patch(
            "backend.state.state_agent.check_session_state",
            return_value=self._conv,
        )
        mock_rr = MagicMock(spec=RetrievalResult)
        mock_rr.reformulated_query = "mock reformulated query"
        mock_rr.candidates = []
        self.retrieval_retrieve_from_message = _patch(
            "backend.retrieval.agent.retrieve_from_message",
            return_value=mock_rr,
        )
        self.retrieval_retrieve_from_profile = _patch(
            "backend.retrieval.agent.retrieve_from_profile",
            return_value=mock_rr,
        )
        self.fetch_stubs = _patch(
            "backend.repository.movies.fetch_stubs",
            side_effect=lambda ids: [
                {
                    "id": mid,
                    "title": f"Film {mid}",
                    "poster_url": None,
                    "release_year": 2000 + mid,
                    "vote_average": 7.0,
                }
                for mid in ids
            ],
        )
        self.fetch_movies_dto = _patch(
            "backend.repository.movies.fetch_movies_dto",
            side_effect=lambda ids: [
                {
                    "id": mid,
                    "title": f"Film {mid}",
                    "release_year": 2000 + mid,
                    "runtime": 100.0,
                    "vote_average": 7.0,
                    "vote_count": 100,
                    "bayesian_rating": 7.0,
                    "overview": None,
                    "poster_url": None,
                    "genres": [],
                    "director": None,
                    "top_cast": [],
                    "original_language": "en",
                }
                for mid in ids
            ],
        )
        mock_sr = MagicMock()
        self.cluster_soft = _patch(
            "backend.cluster.cluster_agent.soft_cluster",
            return_value=mock_sr,
        )
        self.cluster_describe = _patch(
            "backend.cluster.cluster_agent.describe_clusters",
            return_value=self._clusters,
        )
        self.cluster_refine = _patch(
            "backend.cluster.cluster_agent.refine",
            return_value=self._clusters,
        )
        self.decision_decide = _patch(
            "backend.decision.decision_agent.decide",
            return_value=self._decision,
        )
        self.profile_extract = _patch(
            "backend.profile.profile_agent.extract",
            return_value=self._profile,
        )
        self.append_turn = _patch(
            "backend.repository.sessions.append_turn",
        )
        self.update_turn = _patch(
            "backend.repository.sessions.update_turn",
        )
        self.snapshot_clusters = _patch(
            "backend.repository.sessions.snapshot_clusters",
        )
        self.write_feedback = _patch(
            "backend.repository.sessions.write_feedback",
        )
        self.update_profile = _patch(
            "backend.repository.sessions.update_preference_profile",
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
            asyncio.run(orch.run_turn(full.session_id, "I want something contemplative"))
        assert p.cluster_soft.called
        assert not p.cluster_refine.called

    def test_cluster_called_with_user_query(self) -> None:
        full = _full(turns=[_turn("show", "Here is a pick")])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "more like that"))
        call_kwargs = p.cluster_describe.call_args.kwargs
        assert "user_query" in call_kwargs


class TestScenarioBRefinementAfterAsk:
    """When the prior turn already carried clusters, Scenario B is used."""

    def test_cluster_called_with_prior_clusters(self) -> None:
        prior_clusters = [_cluster("Drama")]
        prior = _turn("ask", "What genre?", clusters=prior_clusters)
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Drama please"))
        assert p.cluster_refine.called
        call_kwargs = p.cluster_refine.call_args.kwargs
        assert call_kwargs.get("prior_clusters") is not None
        assert len(call_kwargs["prior_clusters"]) == 1

    def test_scenario_b_passes_asked_question(self) -> None:
        prior = _turn("ask", "What do you feel like?", clusters=[_cluster()])
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Action"))
        call_kwargs = p.cluster_refine.call_args.kwargs
        assert call_kwargs.get("system_message") == "What do you feel like?"

    def test_scenario_b_when_prior_turn_is_show(self) -> None:
        prior = _turn("show", "Here are some dramas", clusters=[_cluster()])
        full = _full(turns=[prior])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "something different"))
        assert p.cluster_refine.called
        call_kwargs = p.cluster_refine.call_args.kwargs
        assert call_kwargs.get("prior_clusters") is not None
        assert len(call_kwargs["prior_clusters"]) == 1


class TestProfileAgentFlow:
    """Profile agent is called after main pipeline; result is persisted."""

    def test_profile_extract_called(self) -> None:
        full = _full(turns=[])
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "fun movie tonight"))
        assert p.profile_extract.called

    def test_profile_result_persisted(self) -> None:
        profile = _profile()
        full = _full(turns=[])
        with _Patches(full=full, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "fun movie tonight"))
        p.update_profile.assert_called_once()
        call_args = p.update_profile.call_args
        persisted = call_args.args[1] if call_args.args else call_args.kwargs.get("preference_profile") or call_args.kwargs.get("profile_jsonb")
        assert persisted == profile.model_dump()

    def test_profile_extract_receives_prior_profile(self) -> None:
        prior = {"constraints": ["no horror"], "preferences": [], "attitudes": [], "summary": ""}
        full = _full(turns=[], preference_profile=prior)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "something calm"))
        call_kwargs = p.profile_extract.call_args.kwargs
        assert call_kwargs["prior_profile"] == prior

    def test_first_turn_prior_profile_is_none(self) -> None:
        full = _full(turns=[], preference_profile=None)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "anything good tonight"))
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
            result = asyncio.run(orch.run_turn(full.session_id, "surprise me"))
        assert result.step_type == StepType.show

    def test_render_reply_contains_cluster_name(self) -> None:
        cluster = _cluster("Epic Adventures")
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            result = asyncio.run(orch.run_turn(full.session_id, "surprise me"))
        assert "Epic Adventures" in result.assistant_message

    def test_render_reply_contains_rationale(self) -> None:
        cluster = _cluster()
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision):
            orch = Orchestrator()
            result = asyncio.run(orch.run_turn(full.session_id, "surprise me"))
        assert "Great dramas" in result.assistant_message


class TestStateShortCircuits:
    """Terminate, natural_end, and clarify_drift bypass the main pipeline."""

    def test_terminate_returns_stop_step_type(self) -> None:
        full = _full(turns=[])
        terminate = StateDecision(
            action=StateAction.terminate,
            reason="max_turns exceeded",
            reply="Session over.",
        )
        with _Patches(full=full) as p:
            with patch("backend.state.state_agent.check_hard_limits", return_value=terminate), \
                 patch("backend.repository.sessions.mark_abandoned"), \
                 patch("backend.repository.sessions.append_turn"):
                orch = Orchestrator()
                result = asyncio.run(orch.run_turn(full.session_id, "hi"))
        assert result.step_type == StepType.stop
        assert not p.update_profile.called

    def test_natural_end_does_not_persist_profile(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.natural_end,
            reason="oracle said bye",
            reply="Goodbye!",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            with patch("backend.repository.sessions.mark_converged"), \
                 patch("backend.repository.sessions.append_turn"):
                orch = Orchestrator()
                result = asyncio.run(orch.run_turn(full.session_id, "bye"))
        # Profile result must NOT be persisted on natural_end (speculative run is discarded)
        assert not p.update_profile.called

    def test_clarify_drift_does_not_snapshot_clusters(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.clarify_drift,
            reason="contradiction",
            reply="Did your preference change?",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror please",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            with patch("backend.orchestrator.turn.terminal_paths.emit_drift_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                asyncio.run(orch.run_turn(full.session_id, "horror please"))
        # Cluster result must NOT be persisted on clarify_drift (speculative run is discarded)
        assert not p.snapshot_clusters.called


class TestDecisionAgentReceivesProfile:
    """Decision agent is called with the N-1 preference profile."""

    def test_decision_receives_prior_profile(self) -> None:
        prior = {"constraints": ["no horror"], "preferences": [], "attitudes": [], "summary": ""}
        full = _full(turns=[], preference_profile=prior)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "drama"))
        call_kwargs = p.decision_decide.call_args.kwargs
        assert call_kwargs["preference_profile"] == prior

    def test_decision_receives_none_on_first_turn(self) -> None:
        full = _full(turns=[], preference_profile=None)
        with _Patches(full=full) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "drama"))
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
            asyncio.run(orch.run_turn(full.session_id, "surprise me", progress_cb=rec))
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
            asyncio.run(orch.run_turn(full.session_id, "tell me more", progress_cb=rec))
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("choose", "start"),
            ("choose", "end"),
            ("finalize", "start"),
            ("finalize", "end"),
        ]

    def test_terminate_emits_wrap_up(self) -> None:
        """Hard-limit terminate fires before tasks spawn, so only wrap_up events."""
        full = _full(turns=[])
        terminate = StateDecision(
            action=StateAction.terminate,
            reason="max_turns exceeded",
            reply="Session over.",
        )
        rec = _Recorder()
        with _Patches(full=full):
            with patch("backend.state.state_agent.check_hard_limits", return_value=terminate), \
                 patch("backend.repository.sessions.mark_abandoned"), \
                 patch("backend.repository.sessions.append_turn"):
                orch = Orchestrator()
                asyncio.run(orch.run_turn(full.session_id, "hi", progress_cb=rec))
        assert rec.events == [
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_natural_end_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.natural_end,
            reason="oracle said bye",
            reply="Goodbye!",
        )
        rec = _Recorder()
        with _Patches(full=full, conv_decision=conv):
            with patch("backend.repository.sessions.mark_converged"), \
                 patch("backend.repository.sessions.append_turn"), \
                 patch("backend.repository.sessions.write_feedback"):
                orch = Orchestrator()
                asyncio.run(orch.run_turn(full.session_id, "bye", progress_cb=rec))
        assert rec.events == [
            ("understand", "start"),
            ("understand", "end"),
            ("wrap_up", "start"),
            ("wrap_up", "end"),
        ]

    def test_clarify_drift_emits_wrap_up(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.clarify_drift,
            reason="contradiction",
            reply="Did your preference change?",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror please",
        )
        rec = _Recorder()
        with _Patches(full=full, conv_decision=conv):
            with patch("backend.orchestrator.turn.terminal_paths.emit_drift_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                asyncio.run(orch.run_turn(full.session_id, "horror please", progress_cb=rec))
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
            p.cluster_soft.return_value = None
            with patch("backend.orchestrator.turn.terminal_paths.emit_early_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                asyncio.run(orch.run_turn(full.session_id, "thing", progress_cb=rec))
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
            result = asyncio.run(orch.run_turn(full.session_id, "go", progress_cb=boom))
        assert result.step_type == StepType.show


class TestDriftConfirmAndDismiss:
    """drift_confirmed re-retrieves via retrieve_from_profile; drift_dismissed uses speculative clusters."""

    def _drift_full(self) -> MagicMock:
        """Session whose last turn is a drift-clarification turn."""
        drift_turn = _turn("ask", "Did your preference change?")
        drift_turn.user_message = "Actually show me horror"
        full = _full(turns=[drift_turn])
        return full

    def test_drift_confirmed_calls_retrieve_from_profile(self) -> None:
        full = self._drift_full()
        conv = StateDecision(
            action=StateAction.drift_confirmed,
            reason="oracle confirmed genre change",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Yes I changed my mind"))
        assert p.retrieval_retrieve_from_profile.called

    def test_drift_confirmed_uses_profile_summary_as_summary_arg(self) -> None:
        full = self._drift_full()
        conv = StateDecision(
            action=StateAction.drift_confirmed,
            reason="oracle confirmed genre change",
        )
        profile = UserProfile(
            constraints=["no horror"],
            preferences=["slow burn"],
            attitudes=[],
            summary="Enjoys slow drama",
        )
        with _Patches(full=full, conv_decision=conv, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Yes I changed my mind"))
        call_kwargs = p.retrieval_retrieve_from_profile.call_args.kwargs
        assert call_kwargs.get("summary") == "Enjoys slow drama"

    def test_drift_confirmed_falls_back_to_user_message_when_no_profile_summary(self) -> None:
        full = self._drift_full()
        full.preference_profile = None
        conv = StateDecision(
            action=StateAction.drift_confirmed,
            reason="oracle confirmed genre change",
        )
        profile = UserProfile(constraints=[], preferences=[], attitudes=[], summary="")
        with _Patches(full=full, conv_decision=conv, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Yes I changed my mind"))
        call_kwargs = p.retrieval_retrieve_from_profile.call_args.kwargs
        assert call_kwargs.get("summary") == "Yes I changed my mind"

    def test_drift_confirmed_passes_seen_films_as_excluded_films(self) -> None:
        full = self._drift_full()
        full.preference_profile = {
            "constraints": [], "preferences": [], "attitudes": [], "summary": "Likes drama",
            "seen_films": ["Film X", "Film Y"], "anchor_films": [],
        }
        conv = StateDecision(
            action=StateAction.drift_confirmed,
            reason="oracle confirmed genre change",
        )
        profile = UserProfile(
            constraints=[], preferences=[], attitudes=[], summary="Likes drama",
            seen_films=["Film X", "Film Y"],
        )
        with _Patches(full=full, conv_decision=conv, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Yes I changed my mind"))
        call_kwargs = p.retrieval_retrieve_from_profile.call_args.kwargs
        assert "Film X" in call_kwargs.get("excluded_films", [])
        assert "Film Y" in call_kwargs.get("excluded_films", [])

    def test_drift_dismissed_does_not_call_retrieve_from_profile(self) -> None:
        full = self._drift_full()
        conv = StateDecision(
            action=StateAction.drift_dismissed,
            reason="oracle explained misunderstanding",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "No I meant supernatural drama"))
        assert not p.retrieval_retrieve_from_profile.called

    def test_drift_dismissed_proceeds_to_decision_agent(self) -> None:
        full = self._drift_full()
        conv = StateDecision(
            action=StateAction.drift_dismissed,
            reason="oracle explained misunderstanding",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "No I meant supernatural drama"))
        assert p.decision_decide.called

    def test_drift_confirmed_proceeds_to_decision_agent(self) -> None:
        full = self._drift_full()
        conv = StateDecision(
            action=StateAction.drift_confirmed,
            reason="oracle confirmed genre change",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "Yes I changed my mind"))
        assert p.decision_decide.called


class TestTerminalStateTolerance:
    """When state is terminal, a cluster-agent crash must NOT kill the turn."""

    def test_natural_end_survives_cluster_crash(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.natural_end,
            reason="oracle said bye",
            reply="Goodbye!",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            p.cluster_soft.side_effect = RuntimeError("retrieval reformulation failed")
            with patch("backend.repository.sessions.mark_converged"), \
                 patch("backend.repository.sessions.append_turn"):
                orch = Orchestrator()
                result = asyncio.run(orch.run_turn(full.session_id, "that's all, thanks"))
        assert result.step_type == StepType.stop

    def test_terminate_completes_without_prior_recommendation(self) -> None:
        """Hard-limit terminate with no prior show turn still returns a stop turn."""
        full = _full(turns=[])
        terminate = StateDecision(
            action=StateAction.terminate,
            reason="max turns",
            reply="Session over.",
        )
        with _Patches(full=full):
            with patch("backend.state.state_agent.check_hard_limits", return_value=terminate), \
                 patch("backend.repository.sessions.mark_abandoned"), \
                 patch("backend.repository.sessions.append_turn"):
                orch = Orchestrator()
                result = asyncio.run(orch.run_turn(full.session_id, "done"))
        assert result.step_type == StepType.stop

    def test_clarify_drift_survives_profile_crash(self) -> None:
        full = _full(turns=[])
        conv = StateDecision(
            action=StateAction.clarify_drift,
            reason="contradiction",
            reply="Did your preference change?",
            drift_topic="horror",
            prior_statement="no horror",
            current_statement="horror please",
        )
        with _Patches(full=full, conv_decision=conv) as p:
            p.profile_extract.side_effect = RuntimeError("profile agent crashed")
            with patch("backend.orchestrator.turn.terminal_paths.emit_drift_clarification") as mock_emit:
                mock_emit.return_value = MagicMock(step_type=StepType.ask)
                orch = Orchestrator()
                result = asyncio.run(orch.run_turn(full.session_id, "horror please"))
        assert result.step_type == StepType.ask


class TestReRetrieve:
    """re_retrieve runs a fresh chain via retrieve_from_profile with seen_films as excluded_films."""

    def test_re_retrieve_calls_retrieve_from_profile(self) -> None:
        prior_show = _turn("show", "Here are some films", clusters=[_cluster()])
        full = _full(turns=[prior_show])
        conv = StateDecision(action=StateAction.re_retrieve, reason="oracle already seen all films")
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "I've already seen all of those"))
        assert p.retrieval_retrieve_from_profile.called

    def test_re_retrieve_proceeds_to_decision_agent(self) -> None:
        prior_show = _turn("show", "Here are some films", clusters=[_cluster()])
        full = _full(turns=[prior_show])
        conv = StateDecision(action=StateAction.re_retrieve, reason="oracle already seen all films")
        with _Patches(full=full, conv_decision=conv) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "I've already seen all of those"))
        assert p.decision_decide.called

    def test_re_retrieve_passes_seen_films_as_excluded_films(self) -> None:
        prior_show = _turn("show", "Here are some films", clusters=[_cluster()])
        full = _full(turns=[prior_show], preference_profile={
            "constraints": [],
            "preferences": [],
            "attitudes": [],
            "summary": "Likes slow drama",
            "seen_films": ["Film A", "Film B"],
            "anchor_films": [],
        })
        conv = StateDecision(action=StateAction.re_retrieve, reason="all seen")
        profile = UserProfile(
            constraints=[],
            preferences=[],
            attitudes=[],
            summary="Likes slow drama",
            seen_films=["Film A", "Film B"],
        )
        with _Patches(full=full, conv_decision=conv, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "I've seen them all"))
        call_kwargs = p.retrieval_retrieve_from_profile.call_args.kwargs
        assert "Film A" in call_kwargs.get("excluded_films", [])
        assert "Film B" in call_kwargs.get("excluded_films", [])


class TestSeenFilmsAccumulation:
    """seen_films is accumulated deterministically across turns."""

    def test_recommendations_added_to_seen_films(self) -> None:
        cluster = _cluster("Drama", n_assignments=3)
        full = _full(turns=[])
        decision = _decision_recommend(cluster.id)
        with _Patches(full=full, clusters=[cluster], decision=decision) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "surprise me"))
        p.update_profile.assert_called_once()
        call_args = p.update_profile.call_args
        persisted = call_args.args[1] if call_args.args else call_args.kwargs.get("preference_profile") or call_args.kwargs.get("profile_jsonb")
        assert "seen_films" in persisted
        assert len(persisted["seen_films"]) > 0

    def test_anchor_films_merged_into_seen(self) -> None:
        full = _full(turns=[], preference_profile=None)
        profile = UserProfile(
            constraints=[],
            preferences=[],
            attitudes=[],
            summary="Test",
            anchor_films=["Interstellar"],
        )
        with _Patches(full=full, profile=profile) as p:
            orch = Orchestrator()
            asyncio.run(orch.run_turn(full.session_id, "something like Interstellar"))
        p.update_profile.assert_called_once()
        call_args = p.update_profile.call_args
        persisted = call_args.args[1] if call_args.args else call_args.kwargs.get("preference_profile") or call_args.kwargs.get("profile_jsonb")
        assert "Interstellar" in persisted.get("seen_films", [])
