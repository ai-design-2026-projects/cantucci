"""Real Orchestrator — DB-backed, LLM-driven coordinator.

Implements the ``backend.models.orchestrator.Orchestrator`` Protocol.
No in-memory session state: all persistence flows through ``backend.api``.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import backend.api.movies as api_movies
import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
from backend.decision import decision_agent
from backend.llm.configs import load_config
from backend.models.clusters import ClusterSnapshot
from backend.models.decision import DecisionAction
from backend.models.exceptions import MovieNotFound, SessionNotConverged, SessionNotFound
from backend.models.public import (
    ClusterPublic,
    ConvergedClusterPublic,
    MoviePublic,
    SoftScore,
)
from backend.models.sessions import SessionState, SessionStatus, StepType, TurnResult
from backend.orchestrator import agent
from backend.orchestrator.tools import state as state_tools

log = logging.getLogger(__name__)


def _cluster_snapshot_to_public(c: ClusterSnapshot) -> ClusterPublic:
    """Convert an internal ClusterSnapshot to a ClusterPublic DTO.

    Args:
        c: Internal cluster snapshot.

    Returns:
        A ClusterPublic suitable for API responses.
    """
    scores = [
        SoftScore(movie_id=a.movie_id, score=a.score, excluded=a.excluded)
        for a in c.assignments
    ]
    top_titles = [
        a.movie_id
        for a in sorted(c.assignments, key=lambda x: x.score, reverse=True)
        if not a.excluded
    ][:5]
    return ClusterPublic(
        id=c.id,
        name=c.name,
        description=c.description,
        level=c.level,
        parent_cluster_id=c.parent_cluster_id,
        soft_scores=scores,
        top_titles=top_titles,
    )


class Orchestrator:
    """LLM-backed orchestrator. No in-memory session state; all persistence in DB.

    Each ``create_session`` call inserts one run + one session row. In the full
    system, runs are managed externally and ``create_session`` accepts a run_id.
    For the scaffold, a run is created implicitly per interactive session.
    """

    def create_session(self) -> SessionState:
        """Create a run + session row and return the initial SessionState.

        Loads the default config for model, seed, and session parameters.

        Returns:
            A ``SessionState`` with status=active and an empty turn list.
        """
        cfg, config_hash = load_config("default")

        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=cfg,
            seed=cfg["model"]["seed"],
            model_version=cfg["model"]["name"],
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg["model"]["seed"],
            config_hash=config_hash,
            model_version=cfg["model"]["name"],
            max_turns=cfg["session"]["max_turns"],
            cost_limit_usd=Decimal(str(cfg["session"]["cost_limit_usd"])),
        )

        log.info(
            "session created",
            extra={"session_id": str(session_id), "run_id": str(run_id)},
        )
        return SessionState(
            session_id=session_id,
            status=SessionStatus.active,
            max_turns=cfg["session"]["max_turns"],
            created_at=now,
            updated_at=now,
            turns=[],
        )

    def handle_turn(self, session_id: UUID, user_message: str) -> TurnResult:
        """Load history, call Decision Agent + Orchestrator agent, record turn.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message.

        Returns:
            A ``TurnResult`` with the LLM's reply, mapped step_type,
            convergence flag, and optional ambiguity_meta for ask turns.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted before the call.
            LLMParseError:     If the orchestrator LLM returns malformed JSON.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turn_id = uuid4()
        turn_number = len(full.turns) + 1

        clusters = cluster_agent.cluster(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        decision = decision_agent.decide(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            clusters=clusters,
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        reply: str
        converged: bool
        preference_profile: dict | None

        if decision.action == DecisionAction.continue_:
            prior_questions = [
                t.assistant_message
                for t in full.turns
                if t.step_type == StepType.ask.value and t.assistant_message
            ]
            question = ambiguity_agent.generate_question(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=user_message,
                clusters=clusters,
                entropy_score=decision.entropy_score,
                prior_questions=prior_questions,
                config_hash=full.config_hash,
                model_version=full.model_version,
            )
            reply, converged, preference_profile = question.question_text, False, None
            step_type = StepType.ask
        else:
            llm_out = agent.respond(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                history=full.turns,
                persona_id=full.persona_id,
                config_hash=full.config_hash,
                model_version=full.model_version,
                max_turns=full.max_turns,
                decision=decision,
            )
            reply, converged, preference_profile = (
                llm_out.reply,
                llm_out.converged,
                llm_out.preference_profile,
            )
            step_type = StepType.stop if converged else StepType.show

        state_tools.record_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
            turn_id=turn_id,
        )

        if converged:
            assert preference_profile is not None  # guaranteed by agent.respond
            state_tools.declare_convergence(session_id, preference_profile)

        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": converged,
            },
        )
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=converged,
            created_at=now,
        )

    def get_session(self, session_id: UUID) -> SessionState:
        """Return full session state including all turns from the DB.

        Args:
            session_id: UUID of the session to retrieve.

        Returns:
            A ``SessionState`` with turns in ascending turn_number order.

        Raises:
            SessionNotFound: If *session_id* does not exist in the DB.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turns = [
            TurnResult(
                turn_id=t.id,
                session_id=session_id,
                turn_number=t.turn_number,
                user_message=t.user_message,
                assistant_message=t.assistant_message or "",
                step_type=StepType(t.step_type) if t.step_type else StepType.show,
                converged=t.converged,
                created_at=t.created_at,
            )
            for t in full.turns
        ]

        return SessionState(
            session_id=full.session_id,
            status=SessionStatus(full.status),
            max_turns=full.max_turns,
            created_at=full.created_at,
            updated_at=full.updated_at,
            turns=turns,
        )

    def get_converged_cluster(self, session_id: UUID) -> ConvergedClusterPublic:
        """Return the fine cluster and its movies for a converged session.

        Reads the last turn's cluster snapshot, selects the finest (highest level)
        cluster, and enriches its top-20 non-excluded movies with full metadata.

        Args:
            session_id: UUID of the converged session.

        Returns:
            A ``ConvergedClusterPublic`` with cluster metadata, enriched movie
            list (top 20 by score), and the session's preference profile.

        Raises:
            SessionNotFound:     If *session_id* does not exist.
            SessionNotConverged: If the session status is not ``"converged"``.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        if full.status != "converged":
            raise SessionNotConverged(session_id, full.status)

        # Find clusters from the last turn that has clusters.
        clusters: list[ClusterSnapshot] = []
        for turn in reversed(full.turns):
            if turn.clusters:
                clusters = turn.clusters
                break

        # Pick the finest cluster (highest level); fall back to a synthetic empty one.
        if clusters:
            fine = max(clusters, key=lambda c: (c.level, len(c.assignments)))
        else:
            # Cluster Agent is still a placeholder — return an empty reveal shell.
            log.warning(
                "get_converged_cluster: no cluster snapshots for session %s", session_id
            )
            from uuid import uuid4 as _uuid4
            empty_cluster = ClusterPublic(
                id=_uuid4(),
                name="Your Taste",
                description="Cluster Agent not yet active — no movie groupings available.",
                level=1,
                parent_cluster_id=None,
                soft_scores=[],
                top_titles=[],
            )
            return ConvergedClusterPublic(
                cluster=empty_cluster,
                movies=[],
                preference_profile=full.preference_profile,
            )

        cluster_public = _cluster_snapshot_to_public(fine)

        # Top-20 non-excluded movies ordered by descending score.
        ranked_ids = [
            a.movie_id
            for a in sorted(fine.assignments, key=lambda x: x.score, reverse=True)
            if not a.excluded
        ][:20]

        movies = api_movies.fetch_movies_public(ranked_ids)

        return ConvergedClusterPublic(
            cluster=cluster_public,
            movies=movies,
            preference_profile=full.preference_profile,
        )

    def get_movie(self, movie_id: int) -> MoviePublic:
        """Return full public metadata for a single movie.

        Args:
            movie_id: TMDB integer movie id.

        Returns:
            A ``MoviePublic`` with all catalogue metadata.

        Raises:
            MovieNotFound: If *movie_id* is not in the catalogue.
        """
        results = api_movies.fetch_movies_public([movie_id])
        if not results:
            raise MovieNotFound(movie_id)
        return results[0]
