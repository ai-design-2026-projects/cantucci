"""Orchestrator — DB-backed, policy-driven coordinator for conversational sessions.

No in-memory session state: all persistence flows through ``backend.api``.

Each turn is structured as an explicit ``asyncio`` task graph:

* A sync hard-limit gate short-circuits the turn before any LLM call.
* State gate, profile extraction, and a speculative branch (refinement or
  retrieval-from-message → cluster_describe) are scheduled in parallel.
* Once the state gate returns, the branch is either consumed, cancelled,
  or replaced — cancellation propagates as ``asyncio.CancelledError`` and
  reaches the in-flight ``httpx`` connection inside the async LLM harness,
  so abandoned LLM calls are aborted rather than silently completed.

The Orchestrator is the sole writer to the DB. All sub-agents are read-only.
Private decision logic lives in ``backend/orchestrator/tools/``.
"""

import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID, uuid4

import backend.api.movies as api_movies
import backend.api.retrieval as api_retrieval
import backend.api.runs as api_runs
import backend.api.sessions as api_sessions
import backend.retrieval.agent as retrieval_agent
from backend.cluster import cluster_agent
from backend.state import state_agent
from backend.decision import decision_agent
from backend.profile import profile_agent
from backend.api.types import ClusterSnapshot, SessionStatus, StepType, TurnDetail
from backend.state.types import StateAction, StateDecision
from backend.decision.types import DecisionAction
from backend.exceptions import SessionNotFound
from backend.retrieval.types import RetrievalResult
from backend.routers.dtos import (
    ClusterPublic,
    MoviePublic,
    RecommendationPublic,
    SessionState,
    SoftScore,
    TurnResult,
)
from backend.orchestrator.progress import (
    ClusterFilmStub,
    ClusterSnapshotEvent,
    ClusterSnapshotPayload,
    NullProgressCallback,
    ProgressCallback,
    ProgressPhase,
    ProgressStep,
    make_progress_event,
)
from backend.orchestrator.task_graph import SpeculativeBranch, cancel_and_drain
from backend.orchestrator.tools.feedback import classify_feedback
from backend.orchestrator.tools.policy import (
    cluster_snapshot_to_spec,
    prior_questions,
)
from backend.orchestrator.tools.render import render_recommendation
from backend.orchestrator.tools.turns import emit_drift_clarification, emit_early_clarification
from backend.settings import get_config_hash, get_config_snapshot, get_settings

log = logging.getLogger(__name__)


def _pick_best_cluster(clusters: list[ClusterSnapshot]) -> ClusterSnapshot:
    """Return the cluster with the highest mean non-excluded assignment score.

    Used to reconstruct which cluster was recommended on a show turn when the
    best_cluster_id is not stored separately.

    Args:
        clusters: Non-empty list of ClusterSnapshot objects.

    Returns:
        The cluster whose mean active score is highest.
    """
    def mean_score(c: ClusterSnapshot) -> float:
        active = [a.score for a in c.assignments if not a.excluded]
        return sum(active) / len(active) if active else 0.0

    return max(clusters, key=mean_score)


def _make_recommendation_public(
    cluster: ClusterSnapshot,
    top_ids: list[int],
    movie_data: dict[int, dict],
) -> RecommendationPublic:
    """Assemble a RecommendationPublic from pre-fetched movie data.

    Args:
        cluster:    The cluster to include in the payload.
        top_ids:    Ordered list of movie_ids (descending score) to include.
        movie_data: Dict mapping movie_id → MoviePublic-shaped dict.

    Returns:
        A ``RecommendationPublic`` DTO.
    """
    films = [MoviePublic(**movie_data[mid]) for mid in top_ids if mid in movie_data]
    cluster_pub = ClusterPublic(
        id=cluster.id,
        name=cluster.name,
        description=cluster.description,
        level=cluster.level,
        parent_cluster_id=cluster.parent_cluster_id,
        soft_scores=[
            SoftScore(movie_id=a.movie_id, score=a.score, excluded=a.excluded)
            for a in cluster.assignments
        ],
        top_titles=top_ids,
    )
    return RecommendationPublic(cluster=cluster_pub, films=films)


def _build_recommendation(
    cluster: ClusterSnapshot,
    top_k: int,
) -> RecommendationPublic:
    """Build a RecommendationPublic from a live ClusterSnapshot via a DB fetch.

    Args:
        cluster: The cluster to recommend.
        top_k:   Maximum number of top-scoring films to include.

    Returns:
        A ``RecommendationPublic`` DTO with fully enriched movie data.
    """
    top_assignments = sorted(
        [a for a in cluster.assignments if not a.excluded],
        key=lambda a: a.score,
        reverse=True,
    )[:top_k]
    top_ids = [a.movie_id for a in top_assignments]
    movie_dicts = api_movies.fetch_movies_public(top_ids)
    movie_data = {m["id"]: m for m in movie_dicts}
    return _make_recommendation_public(cluster, top_ids, movie_data)


def _prior_clusters_from_turn(turn: TurnDetail) -> list[ClusterSnapshot]:
    """Return the ClusterSnapshots stored on a prior turn."""
    return list(turn.clusters)


def _last_clustered_turn(turns: list[TurnDetail]) -> TurnDetail | None:
    """Most recent turn that persisted a non-empty cluster set, or None.

    Walks the history in reverse so a clarify_drift turn (which carries no
    clusters) does not block refinement from reaching the show turn that
    came before it. Returns None only on the truly-first clustered turn of
    a session — that is the single point at which retrieval is allowed to
    rebuild the cluster set from scratch.
    """
    for t in reversed(turns):
        if t.clusters:
            return t
    return None


def _last_show_recommendation(
    full,
    top_k: int,
) -> RecommendationPublic | None:
    """Return the last show-turn's recommendation, if any.

    Used by terminal paths (terminate, natural_end) to surface the most
    recent recommendation alongside the stop turn.
    """
    for prior_t in reversed(full.turns):
        if prior_t.step_type == StepType.show.value and prior_t.clusters:
            return _build_recommendation(_pick_best_cluster(prior_t.clusters), top_k)
    return None


_TOP_K_FILMS = 6


def _emit_cluster_snapshot(
    clusters: list[ClusterSnapshot],
    progress_cb: ProgressCallback,
) -> None:
    """Enrich clusters with poster/rating stubs and emit a ClusterSnapshotEvent.

    Gathers the top-K non-excluded movie ids from each cluster, fetches
    lightweight stubs from the DB in one batch, then fires the event via
    *progress_cb* so the router can stream it to the frontend.

    Args:
        clusters:    List of ClusterSnapshot objects produced by clustering.
        progress_cb: The turn's streaming callback.
    """
    all_ids: list[int] = []
    cluster_tops: list[list[int]] = []
    for c in clusters:
        top = sorted(
            [a for a in c.assignments if not a.excluded],
            key=lambda a: a.score,
            reverse=True,
        )[:_TOP_K_FILMS]
        ids = [a.movie_id for a in top]
        cluster_tops.append(ids)
        all_ids.extend(ids)

    unique_ids = list(dict.fromkeys(all_ids))
    stubs_by_id: dict[int, dict] = {
        s["id"]: s for s in api_movies.fetch_stubs(unique_ids)
    }

    payloads: list[ClusterSnapshotPayload] = []
    for c, ids in zip(clusters, cluster_tops):
        top_films = [
            ClusterFilmStub(
                id=mid,
                title=stubs_by_id[mid]["title"],
                poster_url=stubs_by_id[mid]["poster_url"],
                release_year=stubs_by_id[mid]["release_year"],
                vote_average=stubs_by_id[mid]["vote_average"],
            )
            for mid in ids
            if mid in stubs_by_id
        ]
        payloads.append(
            ClusterSnapshotPayload(
                id=str(c.id),
                name=c.name,
                description=c.description,
                level=c.level,
                top_films=top_films,
            )
        )

    try:
        progress_cb(ClusterSnapshotEvent(clusters=payloads))
    except Exception:
        log.warning("cluster snapshot event dropped", exc_info=True)


async def _drain_speculative(task: asyncio.Task | None, name: str) -> None:
    """Cancel *task* and swallow any exception with a discard warning.

    Used on terminal state paths (terminate, natural_end, clarify_drift)
    where a speculative branch's result is no longer needed and its failure
    must not propagate. ``CancelledError`` is swallowed silently; other
    exceptions are logged once as ``WARNING`` and then suppressed.
    """
    if task is None:
        return
    if not task.done():
        task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass
    except Exception as exc:  # noqa: BLE001 — discarded result; logged.
        log.warning(
            "speculative agent failed (discarded — state terminal)",
            extra={"agent": name, "error": str(exc)},
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
        cfg = get_settings()
        config_hash = get_config_hash()
        config_snapshot = get_config_snapshot()

        run_id = api_runs.create_run(
            name="interactive",
            condition="baseline",
            config_snapshot=config_snapshot,
            config_hash=config_hash,
            seed=cfg.models.strong.seed,
            model_version=cfg.models.strong.name,
        )

        now = datetime.now(timezone.utc)
        session_id = api_sessions.create_session(
            run_id=run_id,
            seed=cfg.models.strong.seed,
            config_hash=config_hash,
            model_version=cfg.models.strong.name,
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
            max_turns=cfg.session.max_turns,
            created_at=now,
            updated_at=now,
            turns=[],
        )

    async def run_turn(
        self,
        session_id: UUID,
        user_message: str,
        *,
        progress_cb: ProgressCallback = NullProgressCallback(),
    ) -> TurnResult:
        """Orchestrate one conversational turn as an async task graph.

        Flow:
          1. Hard-limit gate (sync) — short-circuits before any LLM work.
          2. Spawn ``state_gate``, ``profile_extract``, and one speculative
             branch (refinement OR retrieval-from-message → cluster_describe)
             as concurrent ``asyncio.Task``s.
          3. Resolve the state-gate verdict and cancel / replace the
             speculative branch as needed. Cancellation cascades into the
             in-flight LLM call via the async harness.
          4. Run the decision agent on the resolved clusters + N profile.
          5. Persist turn, clusters, feedback, and updated profile.

        Args:
            session_id:   UUID of the target session.
            user_message: The oracle's message for this turn.
            progress_cb:  Invoked at the start and end of each progress step
                          so the router can stream events to the frontend.
                          Called on the event loop thread; must not block or raise.

        Returns:
            A ``TurnResult`` describing the outcome of this turn.

        Raises:
            SessionNotFound:   If *session_id* does not exist in the DB.
            CostLimitExceeded: If the session budget is exhausted.
            LLMParseError:     If any agent LLM call returns malformed JSON.
        """
        turn_id = uuid4()

        def _emit(step: ProgressStep, phase: ProgressPhase) -> None:
            try:
                progress_cb(make_progress_event(step, phase))
            except Exception:
                log.warning(
                    "progress callback failed",
                    exc_info=True,
                    extra={
                        "session_id": str(session_id),
                        "turn_id": str(turn_id),
                        "step": step.value,
                        "phase": phase,
                    },
                )

        full = await asyncio.to_thread(api_retrieval.get_session_full, session_id)

        turn_number = len(full.turns) + 1
        cfg = get_settings()

        # N-1 profile (may be None on the first turn)
        prior_profile = full.preference_profile

        # Short history: last 2 completed turns
        recent_turns: list[TurnDetail] = full.turns[-2:]

        log.debug(
            "turn entry",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "turn_number": turn_number,
                "user_message_len": len(user_message),
                "prior_turns": len(full.turns),
            },
        )

        # Refinement fires whenever the session already has a cluster set we
        # can evolve, regardless of whether the prior assistant message was an
        # ``ask`` (clarifying question) or a ``show`` (recommendation). The
        # only fresh-retrieval path is the very first clustered turn of the
        # session; state-driven re-retrieval (drift_confirmed / re_retrieve)
        # is handled later in _resolve_clusters.
        prior_clustered = _last_clustered_turn(full.turns)
        if prior_clustered is not None:
            log.info(
                "refining prior clusters",
                extra={
                    "session_id": str(session_id),
                    "turn_number": turn_number,
                    "prior_clustered_turn_id": str(prior_clustered.id),
                },
            )

        prior_seen: list[str] = list(prior_profile.get("seen_films", [])) if prior_profile else []
        recommended_last_turn: list[str] = []
        if full.turns:
            last = full.turns[-1]
            if last.step_type == StepType.show.value:
                for c in last.clusters:
                    for a in c.assignments:
                        if not a.excluded and a.title:
                            recommended_last_turn.append(a.title)

        # 1. Hard-limit gate. Synchronous; trips before any LLM work.
        hard = state_agent.check_hard_limits(turn_number=turn_number, full=full, cfg=cfg)
        if hard.action is StateAction.terminate:
            _emit(ProgressStep.understand, "start")
            _emit(ProgressStep.understand, "end")
            last_show_rec = await asyncio.to_thread(
                _last_show_recommendation, full, cfg.session.recommendation_top_k,
            )
            _emit(ProgressStep.wrap_up, "start")
            try:
                return await asyncio.to_thread(
                    self._terminate_turn,
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=hard,
                    recommendation=last_show_rec,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        # 2. Spawn the task graph for the turn. The LLM state gate runs in
        # parallel with profile extraction and one speculative branch so that
        # the speculative work is already in-flight by the time the gate
        # resolves. On turn 1, retrieval is already racing with the state
        # gate — no wasted wait.
        _emit(ProgressStep.understand, "start")

        state_t = asyncio.create_task(
            state_agent.check_gate(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                full=full,
                preference_profile=prior_profile,
                cfg=cfg,
                recommended_last_turn=recommended_last_turn,
                seen_films=prior_seen,
            ),
            name="state_gate",
        )
        profile_t = asyncio.create_task(
            profile_agent.extract(
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
                user_message=user_message,
                prior_profile=prior_profile,
                recent_turns=recent_turns,
            ),
            name="profile_extract",
        )

        spec_kind, spec_t = self._spawn_speculative(
            prior_clustered=prior_clustered,
            user_message=user_message,
            cfg=cfg,
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
        )

        try:
            state = await state_t
        except BaseException:
            # State gate failed (including cancellation). Drop everything we
            # spawned so the LLM calls behind those tasks are aborted before
            # we re-raise to the caller.
            await cancel_and_drain(profile_t)
            await cancel_and_drain(spec_t)
            raise

        # 3. Branch on the state verdict. LLM-detected terminal verdicts
        # discard the speculative branch and the profile result (the
        # docstring for clarify_drift in the LLM gate says no profile
        # update is persisted on these turns).
        if state.action is StateAction.natural_end:
            await _drain_speculative(spec_t, spec_kind.value)
            await _drain_speculative(profile_t, "profile")
            _emit(ProgressStep.understand, "end")
            last_show_rec = await asyncio.to_thread(
                _last_show_recommendation, full, cfg.session.recommendation_top_k,
            )
            _emit(ProgressStep.wrap_up, "start")
            try:
                return await asyncio.to_thread(
                    self._natural_end_turn,
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=state,
                    preference_profile=prior_profile or {},
                    recommendation=last_show_rec,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        if state.action is StateAction.clarify_drift:
            await _drain_speculative(spec_t, spec_kind.value)
            await _drain_speculative(profile_t, "profile")
            _emit(ProgressStep.understand, "end")
            _emit(ProgressStep.wrap_up, "start")
            try:
                return await asyncio.to_thread(
                    emit_drift_clarification,
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                    decision=state,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        # 4. Non-terminal path. Profile is needed for cluster re-retrieval
        # (drift_confirmed / re_retrieve) and for persistence.
        try:
            new_profile = await profile_t
        except BaseException:
            await cancel_and_drain(spec_t)
            raise

        clusters = await self._resolve_clusters(
            state=state,
            spec_kind=spec_kind,
            spec_t=spec_t,
            new_profile=new_profile,
            prior_seen=prior_seen,
            user_message=user_message,
            cfg=cfg,
            session_id=session_id,
            full=full,
            turn_id=turn_id,
            turn_number=turn_number,
        )

        _emit(ProgressStep.understand, "end")

        if clusters:
            _emit_cluster_snapshot(clusters, progress_cb)

        if not clusters:
            _emit(ProgressStep.wrap_up, "start")
            try:
                return await asyncio.to_thread(
                    emit_early_clarification,
                    session_id=session_id,
                    turn_id=turn_id,
                    turn_number=turn_number,
                    user_message=user_message,
                )
            finally:
                _emit(ProgressStep.wrap_up, "end")

        await asyncio.to_thread(
            api_sessions.append_turn,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=None,
            step_type=None,
            converged=False,
            turn_id=turn_id,
        )

        await asyncio.to_thread(
            api_sessions.snapshot_clusters,
            session_id,
            turn_id,
            [cluster_snapshot_to_spec(c) for c in clusters],
        )

        log.debug(
            "cluster snapshot persisted",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "n_clusters": len(clusters),
            },
        )

        _emit(ProgressStep.choose, "start")
        decision = await decision_agent.decide(
            session_id=session_id,
            run_id=full.run_id,
            turn_id=turn_id,
            turn_number=turn_number,
            user_query=user_message,
            clusters=clusters,
            preference_profile=prior_profile,
            prior_questions=prior_questions(full.turns),
        )

        log.debug(
            "decision action chosen",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "action": decision.action.value,
                "entropy_score": decision.entropy_score,
            },
        )

        reply: str
        step_type: StepType
        converged: bool
        recommendation: RecommendationPublic | None = None

        if decision.action == DecisionAction.continue_:
            reply = decision.question_text or ""
            step_type = StepType.ask
            converged = False
        else:
            best_cluster = next(
                (c for c in clusters if c.id == decision.best_cluster_id),
                clusters[0],
            )
            reply = render_recommendation(
                best_cluster=best_cluster,
                top_k=cfg.session.recommendation_top_k,
            )
            rendered_titles = [
                a.title
                for a in sorted(
                    [a for a in best_cluster.assignments if not a.excluded],
                    key=lambda a: a.score,
                    reverse=True,
                )[: cfg.session.recommendation_top_k]
                if a.title
            ]
            new_profile.seen_films = list(
                dict.fromkeys(new_profile.seen_films + rendered_titles)
            )
            converged = False
            step_type = StepType.show
            recommendation = await asyncio.to_thread(
                _build_recommendation, best_cluster, cfg.session.recommendation_top_k,
            )

        log.debug(
            "state verdict",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "converged": converged,
                "step_type": step_type.value,
            },
        )
        _emit(ProgressStep.choose, "end")

        _emit(ProgressStep.finalize, "start")
        await asyncio.to_thread(
            api_sessions.update_turn,
            turn_id=turn_id,
            assistant_message=reply,
            step_type=step_type.value,
            converged=converged,
        )

        fb_level, fb_type, fb_target_id = classify_feedback(full.turns, user_message, decision)
        await asyncio.to_thread(
            api_sessions.write_feedback,
            session_id=session_id,
            turn_id=turn_id,
            feedback_level=fb_level,
            feedback_type=fb_type,
            content=user_message,
            target_id=fb_target_id,
        )

        new_profile.seen_films = list(
            dict.fromkeys(prior_seen + new_profile.anchor_films + new_profile.seen_films)
        )
        await asyncio.to_thread(
            api_sessions.update_preference_profile, session_id, new_profile.model_dump(),
        )
        _emit(ProgressStep.finalize, "end")

        log.debug(
            "profile updated",
            extra={
                "session_id": str(session_id),
                "turn_id": str(turn_id),
                "n_constraints": len(new_profile.constraints),
            },
        )

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
            recommendation=recommendation,
        )

    def _spawn_speculative(
        self,
        *,
        prior_clustered: TurnDetail | None,
        user_message: str,
        cfg,
        session_id: UUID,
        run_id: UUID,
        turn_id: UUID,
        turn_number: int,
    ) -> tuple[SpeculativeBranch, asyncio.Task | None]:
        """Spawn the one speculative branch appropriate for the upcoming turn.

        Whenever the session already has clusters from a prior turn we
        speculatively refine them in light of the oracle's reply. Only the
        truly-first clustered turn of a session (and any session whose
        earlier retrievals returned nothing) takes the fresh-retrieval path
        via ``retrieve_from_message → soft_cluster → describe_clusters``.
        State-invalidated speculative work is cancelled once the gate
        resolves; the still-running branch is consumed otherwise.
        """
        if prior_clustered is not None:
            spec_t = asyncio.create_task(
                cluster_agent.refine(
                    prior_clusters=_prior_clusters_from_turn(prior_clustered),
                    user_query=user_message,
                    system_message=prior_clustered.assistant_message or "",
                    oracle_reply=user_message,
                    session_id=session_id,
                    run_id=run_id,
                    turn_id=turn_id,
                ),
                name="refine_speculative",
            )
            return SpeculativeBranch.REFINE, spec_t

        spec_t = asyncio.create_task(
            self._retrieve_msg_then_cluster(
                user_query=user_message,
                cfg=cfg,
                session_id=session_id,
                run_id=run_id,
                turn_id=turn_id,
                turn_number=turn_number,
            ),
            name="retrieve_msg_speculative",
        )
        return SpeculativeBranch.RETRIEVE_MSG, spec_t

    async def _retrieve_msg_then_cluster(
        self,
        *,
        user_query: str,
        cfg,
        session_id: UUID,
        run_id: UUID,
        turn_id: UUID,
        turn_number: int,
    ) -> list[ClusterSnapshot]:
        """Speculative chain: retrieve_from_message → soft_cluster → describe.

        Wrapped as a single task so the orchestrator can cancel the whole
        chain in one call when state invalidates the speculative branch.
        Cancellation between retrieval and clustering, or mid-LLM-describe,
        all propagate via ``CancelledError``.
        """
        rr = await retrieval_agent.retrieve_from_message(
            user_query=user_query,
            k=cfg.retrieval.top_k,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
        )
        return await self._cluster_from_retrieval(
            rr,
            user_query=user_query,
            cfg=cfg,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            turn_number=turn_number,
        )

    async def _cluster_from_retrieval(
        self,
        rr: RetrievalResult,
        *,
        user_query: str,
        cfg,
        session_id: UUID,
        run_id: UUID,
        turn_id: UUID,
        turn_number: int,
    ) -> list[ClusterSnapshot]:
        """Run HDBSCAN → LLM describe over an already-fetched ``RetrievalResult``.

        ``soft_cluster`` is sync and CPU-bound (HDBSCAN + embedding fetch);
        we hop into a thread so the event loop stays free for in-flight LLM
        calls on other turns.

        Args:
            rr:          ``RetrievalResult`` produced by retrieve_from_*.
            user_query:  Query string used for the describer LLM call.
            cfg:         Loaded settings for the current turn.
            session_id:  UUID of the current session.
            run_id:      UUID of the parent run.
            turn_id:     UUID of the current turn.
            turn_number: 1-based turn index within the session.

        Returns:
            List of named ``ClusterSnapshot`` objects, or an empty list when
            retrieval yields no candidates or HDBSCAN classifies all as noise.
        """
        sr = await asyncio.to_thread(
            cluster_agent.soft_cluster,
            retrieval_result=rr,
            session_id=session_id,
            turn_id=turn_id,
            turn_number=turn_number,
        )
        if sr is None:
            return []
        return await cluster_agent.describe_clusters(
            soft_result=sr,
            user_query=user_query,
            reformulated_query=rr.reformulated_query,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
        )

    async def _resolve_clusters(
        self,
        *,
        state: StateDecision,
        spec_kind: SpeculativeBranch,
        spec_t: asyncio.Task | None,
        new_profile,
        prior_seen: list[str],
        user_message: str,
        cfg,
        session_id: UUID,
        full,
        turn_id: UUID,
        turn_number: int,
    ) -> list[ClusterSnapshot]:
        """Convert the state verdict into the final cluster list for this turn.

        Either consumes the speculative branch (proceed / drift_dismissed) or
        cancels it and spawns a profile-driven re-retrieval (drift_confirmed,
        re_retrieve). All ``state.action`` dispatch lives here so the rest of
        ``run_turn`` stays a straight line.
        """
        if state.action in (StateAction.drift_confirmed, StateAction.re_retrieve):
            await cancel_and_drain(spec_t)
            summary = new_profile.summary or user_message
            excluded = list(dict.fromkeys(prior_seen + new_profile.anchor_films))
            log.info(
                "re-retrieving from profile summary",
                extra={
                    "session_id": str(session_id),
                    "turn_id": str(turn_id),
                    "state_action": state.action.value,
                    "using_profile_summary": bool(new_profile.summary),
                    "n_excluded_films": len(excluded),
                },
            )
            rr = await retrieval_agent.retrieve_from_profile(
                summary=summary,
                excluded_films=excluded,
                k=cfg.retrieval.top_k,
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
            )
            return await self._cluster_from_retrieval(
                rr,
                user_query=summary,
                cfg=cfg,
                session_id=session_id,
                run_id=full.run_id,
                turn_id=turn_id,
                turn_number=turn_number,
            )

        if state.action is StateAction.drift_dismissed:
            log.info(
                "drift dismissed — using speculative result",
                extra={"session_id": str(session_id), "turn_id": str(turn_id)},
            )

        # proceed / drift_dismissed: consume the speculative branch.
        if spec_t is None:
            return []
        return await spec_t

    def _terminate_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
        decision: StateDecision,
        recommendation: RecommendationPublic | None = None,
    ) -> TurnResult:
        """Persist and return a terminal turn when a hard limit is reached.

        Writes step_type=stop, converged=False and marks the session abandoned.
        No LLM call is made.

        Args:
            session_id:     UUID of the target session.
            turn_id:        Pre-allocated turn UUID.
            turn_number:    1-based index for this turn.
            user_message:   Oracle's message that triggered the limit check.
            decision:       StateDecision from check_hard_limits.
            recommendation: Last show turn's recommendation, if any.

        Returns:
            A TurnResult with step_type=stop, converged=False.
        """
        reply = decision.reply or "Session limit reached. Thank you for using CinePal!"
        step_type = StepType.stop
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=False,
            turn_id=turn_id,
        )
        api_sessions.mark_abandoned(session_id, decision.reason)
        log.warning(
            "turn terminated: hard limit",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "reason": decision.reason,
            },
        )
        now = datetime.now(timezone.utc)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": False,
            },
        )
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=False,
            created_at=now,
            recommendation=recommendation,
        )

    def _natural_end_turn(
        self,
        *,
        session_id: UUID,
        turn_id: UUID,
        turn_number: int,
        user_message: str,
        decision: StateDecision,
        preference_profile: dict,
        recommendation: RecommendationPublic | None = None,
    ) -> TurnResult:
        """Persist and return a natural-end turn detected by the LLM gate.

        Writes step_type=stop, converged=True, marks the session converged,
        and records an accept feedback row.

        Args:
            session_id:        UUID of the target session.
            turn_id:           Pre-allocated turn UUID.
            turn_number:       1-based index for this turn.
            user_message:      Oracle's message that the gate classified as natural end.
            decision:          StateDecision from the state agent.
            preference_profile: N-1 profile to persist with the converged session.
            recommendation:    Last show turn's recommendation, if any.

        Returns:
            A TurnResult with step_type=stop, converged=True.
        """
        reply = decision.reply or "Thank you — closing the session!"
        step_type = StepType.stop
        api_sessions.append_turn(
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type.value,
            converged=True,
            turn_id=turn_id,
        )
        api_sessions.write_feedback(
            session_id=session_id,
            turn_id=turn_id,
            feedback_level="global",
            feedback_type="accept",
            content=user_message,
            target_id=None,
        )
        api_sessions.mark_converged(session_id, preference_profile)
        log.info(
            "turn handled",
            extra={
                "session_id": str(session_id),
                "turn_number": turn_number,
                "step_type": step_type.value,
                "converged": True,
            },
        )
        now = datetime.now(timezone.utc)
        return TurnResult(
            turn_id=turn_id,
            session_id=session_id,
            turn_number=turn_number,
            user_message=user_message,
            assistant_message=reply,
            step_type=step_type,
            converged=True,
            created_at=now,
            recommendation=recommendation,
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

        cfg = get_settings()

        # Pre-compute the best cluster + top-movie-ids for every show turn so we
        # can batch all movie fetches into a single DB call.
        show_turn_info: dict[UUID, tuple[ClusterSnapshot, list[int]]] = {}
        for t in full.turns:
            if t.step_type == StepType.show.value and t.clusters:
                best = _pick_best_cluster(t.clusters)
                top_ids = [
                    a.movie_id
                    for a in sorted(
                        [a for a in best.assignments if not a.excluded],
                        key=lambda a: a.score,
                        reverse=True,
                    )[: cfg.session.recommendation_top_k]
                ]
                show_turn_info[t.id] = (best, top_ids)

        # Batch-fetch all movie metadata needed across all show turns
        all_ids = list(
            dict.fromkeys(mid for _, (_, ids) in show_turn_info.items() for mid in ids)
        )
        movie_data: dict[int, dict] = (
            {m["id"]: m for m in api_movies.fetch_movies_public(all_ids)}
            if all_ids
            else {}
        )

        # Build turns, hydrating recommendation for show and stop steps
        last_show_recommendation: RecommendationPublic | None = None
        turns: list[TurnResult] = []
        for t in full.turns:
            recommendation: RecommendationPublic | None = None
            step = StepType(t.step_type) if t.step_type else StepType.show
            if step == StepType.show and t.id in show_turn_info:
                best, top_ids = show_turn_info[t.id]
                recommendation = _make_recommendation_public(best, top_ids, movie_data)
                last_show_recommendation = recommendation
            elif step == StepType.stop:
                recommendation = last_show_recommendation

            turns.append(
                TurnResult(
                    turn_id=t.id,
                    session_id=session_id,
                    turn_number=t.turn_number,
                    user_message=t.user_message,
                    assistant_message=t.assistant_message or "",
                    step_type=step,
                    converged=t.converged,
                    created_at=t.created_at,
                    recommendation=recommendation,
                )
            )

        return SessionState(
            session_id=full.session_id,
            status=SessionStatus(full.status),
            max_turns=full.max_turns,
            created_at=full.created_at,
            updated_at=full.updated_at,
            turns=turns,
        )
