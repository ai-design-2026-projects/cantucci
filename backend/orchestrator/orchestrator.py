"""Real Orchestrator — DB-backed, policy-driven coordinator.

Implements the ``backend.models.orchestrator.Orchestrator`` Protocol.
No in-memory session state: all persistence flows through ``backend.api``.

Turn flow (per architecture.md):
  Oracle → Orchestrator → Cluster Agent (→ Retrieval internally) →
  Decision Agent → (Ambiguity Resolver if continue) → Orchestrator → DB/UI.

The Orchestrator is the sole writer to the DB.  All sub-agents are read-only.
"""

import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import backend.api.movies as api_movies
import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
from backend.ambiguity import ambiguity_agent
from backend.cluster import cluster_agent
from backend.decision import decision_agent
from backend.models.clusters import ClusterSnapshot, ClusterSpec
from backend.models.decision import DecisionAction, DecisionResult
from backend.models.exceptions import MovieNotFound, SessionNotConverged, SessionNotFound
from backend.models.public import (
    ClusterPublic,
    ConvergedClusterPublic,
    MoviePublic,
    SoftScore,
)
from backend.models.retrieval import TurnDetail
from backend.models.sessions import SessionState, SessionStatus, StepType, TurnResult
from backend.orchestrator import agent
from backend.settings import get_config_hash, get_config_snapshot, get_settings

log = logging.getLogger(__name__)

# Words that signal oracle rejection; used by the heuristic feedback classifier.
_NEGATIVE_LEXICON = frozenset({
    "no", "not", "wrong", "don't", "doesn't", "didn't", "never", "nothing",
    "hate", "dislike", "avoid", "terrible", "awful", "bad", "nope", "neither",
})


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


def _snapshot_to_spec(snapshot: ClusterSnapshot) -> ClusterSpec:
    """Convert a ClusterSnapshot (in-memory) to a ClusterSpec (DB input).

    Args:
        snapshot: In-memory cluster produced by the Cluster Agent.

    Returns:
        ClusterSpec suitable for ``api_sessions.snapshot_clusters``.
    """
    return ClusterSpec(
        name=snapshot.name,
        description=snapshot.description,
        level=snapshot.level,
        centroid=None,
        parent_cluster_id=snapshot.parent_cluster_id,
        assignments=[(a.movie_id, a.score, a.excluded) for a in snapshot.assignments],
    )


def _build_refined_query(turns: list[TurnDetail], user_message: str) -> str:
    """Combine the original oracle query with the latest message for retrieval.

    For the first turn, returns *user_message* unchanged.  For subsequent turns,
    prepends the original session query so retrieval retains the user's core
    intent even as messages become shorter feedback phrases.

    Args:
        turns:        Prior turns in ascending turn_number order.
        user_message: Oracle's message for the current turn.

    Returns:
        Enriched query string for the Cluster Agent's retrieval step.
    """
    if not turns:
        return user_message
    original = turns[0].user_message
    if original == user_message:
        return user_message
    return f"{original}. {user_message}"


def _convergence_policy(turns: list[TurnDetail], convergence_turns: int) -> bool:
    """Return True when the last *convergence_turns* steps were all show-type.

    Simple policy: the oracle has seen the recommendation without issuing a
    corrective step for *convergence_turns* consecutive turns.  LLM-driven
    preference-stability detection is a future iteration.

    Args:
        turns:            Prior turns in ascending turn_number order.
        convergence_turns: Number of consecutive show turns required.

    Returns:
        True if convergence criterion is met.
    """
    recent_show = [t for t in turns if t.step_type == StepType.show.value]
    return len(recent_show) >= convergence_turns


def _classify_feedback(
    prior_turns: list[TurnDetail],
    user_message: str,
    decision: DecisionResult,
) -> tuple[str, str, str | None]:
    """Return (feedback_level, feedback_type, target_id) for the current oracle message.

    MVP heuristic: first turn is a global constraint; responses to ask-type turns
    are classified as accept or reject based on lexical cues; all others are
    global constraints.  An LLM-based classifier (``f_next_state``) is a future
    iteration.

    Args:
        prior_turns:  All turns before the current one.
        user_message: Oracle's message for the current turn.
        decision:     Decision Agent output (for best_cluster_id).

    Returns:
        Three-tuple of (feedback_level, feedback_type, target_id).
    """
    if not prior_turns:
        return "global", "constraint", None
    last_turn = prior_turns[-1]
    if last_turn.step_type == StepType.ask.value:
        words = set(user_message.lower().split())
        target = str(decision.best_cluster_id) if decision.best_cluster_id else None
        if words & _NEGATIVE_LEXICON:
            return "cluster", "reject", target
        return "cluster", "accept", target
    return "global", "constraint", None


def _extract_preference_profile(
    turns: list[TurnDetail],
    user_message: str,
    clusters: list[ClusterSnapshot],
    decision: DecisionResult,
) -> dict:
    """Build a minimal preference profile from the conversation history.

    Collects oracle utterances from ask-type turns as constraints, and captures
    the final cluster name and description.  A richer extraction pass (structured
    by the LLM) is a future iteration.

    Args:
        turns:        All prior turns (not including the current one).
        user_message: Oracle's message for the current (converging) turn.
        clusters:     Current cluster snapshots.
        decision:     Decision Agent output for the current turn.

    Returns:
        Dict with keys ``oracle_constraints``, ``final_cluster_name``,
        ``final_cluster_description``.
    """
    constraints = [t.user_message for t in turns if t.step_type == StepType.ask.value]
    constraints.append(user_message)
    best: ClusterSnapshot | None = None
    if decision.best_cluster_id:
        best = next((c for c in clusters if c.id == decision.best_cluster_id), None)
    if best is None and clusters:
        best = clusters[0]
    return {
        "oracle_constraints": constraints,
        "final_cluster_name": best.name if best else "unknown",
        "final_cluster_description": best.description if best else None,
    }


def _is_duplicate_question(text: str, turns: list[TurnDetail]) -> bool:
    """Return True if *text* exactly matches a prior ask-type assistant message.

    The Orchestrator is the authoritative deduplication source per architecture.md.

    Args:
        text:  Proposed question text from the Ambiguity Resolver.
        turns: Prior turns in ascending turn_number order.

    Returns:
        True if the question has already been asked.
    """
    for t in turns:
        if t.step_type == StepType.ask.value and t.assistant_message == text:
            return True
    return False


def _prior_questions(turns: list[TurnDetail]) -> list[str]:
    """Collect all prior clarifying-question texts in turn order.

    Args:
        turns: Prior turns in ascending turn_number order.

    Returns:
        List of assistant messages from ask-type turns.
    """
    return [
        t.assistant_message
        for t in turns
        if t.step_type == StepType.ask.value and t.assistant_message
    ]


class Orchestrator:
    """LLM-backed orchestrator. No in-memory session state; all persistence in DB.

    Each ``create_session`` call inserts one run + one session row.  In the full
    system, runs are managed externally and ``create_session`` accepts a run_id.
    For the scaffold, a run is created implicitly per interactive session.
    """

    def create_session(self) -> SessionState:
        """Create a run + session row and return the initial SessionState.

        Loads the default config for model, seed, and session parameters.

        Returns:
            A ``SessionState`` with status=active and an empty turn list.
        """
        cfg = get_settings()
        config_hash = get_config_hash()
        config_snapshot = get_config_snapshot()

        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=config_snapshot,
            seed=cfg.model.seed,
            model_version=cfg.model.name,
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg.model.seed,
            config_hash=config_hash,
            model_version=cfg.model.name,
            max_turns=cfg.session.max_turns,
            cost_limit_usd=Decimal(str(cfg.session.cost_limit_usd)),
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
        """Orchestrate one conversational turn and persist all resulting state.

        Full flow:
          1. Load session state from DB.
          2. Build a refined retrieval query from the conversation history.
          3. Cluster Agent retrieves candidates and clusters them.
          4. Persist the cluster snapshot (before downstream use).
          5. Decision Agent routes to recommend or continue.
          6. If continue: Ambiguity Resolver generates a clarifying question (deduped).
             If recommend: render a presentation reply; evaluate convergence policy.
          7. Persist the turn.
          8. Classify and persist oracle feedback.
          9. If converged: extract preference profile and mark session converged.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message for this turn.

        Returns:
            A ``TurnResult`` describing the outcome of this turn.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted.
            LLMParseError:     If any agent LLM call returns malformed JSON.
        """
        try:
            full = api_retrieval.get_session_full(session_id)
        except ValueError as exc:
            raise SessionNotFound(session_id) from exc

        turn_id = uuid4()
        turn_number = len(full.turns) + 1
        cfg = get_settings()

        refined_input = _build_refined_query(full.turns, user_message)

        clusters = cluster_agent.cluster(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=refined_input,
            config_hash=full.config_hash,
            model_version=full.model_version,
        )

        if not clusters:
            return self._early_clarification_turn(
                session_id=session_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
            )

        api_sessions.snapshot_clusters(
            session_id, turn_id, [_snapshot_to_spec(c) for c in clusters]
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
        step_type: StepType
        converged: bool

        if decision.action == DecisionAction.continue_:
            question = ambiguity_agent.generate_question(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_query=user_message,
                clusters=clusters,
                entropy_score=decision.entropy_score,
                prior_questions=_prior_questions(full.turns),
                config_hash=full.config_hash,
                model_version=full.model_version,
            )
            if _is_duplicate_question(question.question_text, full.turns):
                log.warning(
                    "ambiguity resolver produced duplicate question — forcing recommend path",
                    extra={"session_id": str(session_id), "turn_number": turn_number},
                )
                llm_out = agent.render_recommendation(
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
                    clusters=clusters,
                )
                reply = llm_out.reply
                converged = _convergence_policy(full.turns, cfg.session.convergence_turns)
                step_type = StepType.stop if converged else StepType.show
            else:
                reply = question.question_text
                step_type = StepType.ask
                converged = False
        else:
            llm_out = agent.render_recommendation(
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
                clusters=clusters,
            )
            reply = llm_out.reply
            converged = _convergence_policy(full.turns, cfg.session.convergence_turns)
            step_type = StepType.stop if converged else StepType.show

        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
            turn_id=turn_id,
        )

        fb_level, fb_type, fb_target_id = _classify_feedback(full.turns, user_message, decision)
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level=fb_level,
            feedback_type=fb_type,
            content=user_message,
            target_id=fb_target_id,
        )

        if converged:
            preference_profile = _extract_preference_profile(
                full.turns, user_message, clusters, decision
            )
            api_sessions.mark_converged(session_id, preference_profile)

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

    def _early_clarification_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
    ) -> TurnResult:
        """Persist and return a canned clarifying reply when retrieval yields no candidates.

        Args:
            session_id:   UUID of the target session.
            turn_id:      Pre-allocated turn UUID.
            turn_number:  1-based index for this turn.
            user_message: Oracle's message that produced empty retrieval.

        Returns:
            A TurnResult with step_type=ask and the canned reply.
        """
        reply = (
            "I couldn't find films matching that description. "
            "Could you tell me more about the kind of films you're looking for? "
            "For example, a mood, a director's style, a genre, or an era?"
        )
        step_type = StepType.ask
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=False,
            turn_id=turn_id,
        )
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="global",
            feedback_type="constraint",
            content=user_message,
            target_id=None,
        )
        log.warning(
            "no clusters returned — canned clarification turn",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        now = datetime.now(timezone.utc)
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=False,
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
        """Return the finest cluster and its movies for a converged session.

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

        clusters: list[ClusterSnapshot] = []
        for turn in reversed(full.turns):
            if turn.clusters:
                clusters = turn.clusters
                break

        if not clusters:
            raise SessionNotConverged(session_id, "converged but no cluster snapshots found")

        fine = max(clusters, key=lambda c: (c.level, len(c.assignments)))
        cluster_public = _cluster_snapshot_to_public(fine)

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
