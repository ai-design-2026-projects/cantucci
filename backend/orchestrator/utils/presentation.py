"""
Recommendation rendering and DTO assembly for the orchestrator. All the 
enrichment and formatting logic lives here so the orchestrator and 
router can stay focused on their respective responsibilities of turn flow.
"""
import logging
import backend.api.movies as api_movies
from backend.api.types import ClusterRow, SessionRow, SessionStatus, StepType
from backend.orchestrator.utils.progress import (
    ClusterFilmStub,
    ClusterSnapshotEvent,
    ClusterSnapshotPayload,
    ProgressCallback,
)
from backend.routers.dtos import (
    ClusterDto,
    MovieDto,
    RecommendationDto,
    SessionDto,
    SoftScore,
    TurnDto,
)
from backend.settings import Settings

log = logging.getLogger(__name__)


def pick_best_cluster(clusters: list[ClusterRow]) -> ClusterRow:
    """
    Return the cluster with the highest mean non-excluded assignment score.
    Used to reconstruct which cluster was recommended on a show turn when the
    best_cluster_id is not stored separately.
    Args:
        clusters: Non-empty list of ClusterRow objects.
    Returns:
        The cluster whose mean active score is highest.
    """
    def mean_score(c: ClusterRow) -> float:
        active = [a.score for a in c.assignments if not a.excluded]
        return sum(active) / len(active) if active else 0.0

    return max(clusters, key=mean_score)


def make_recommendation_dto(
    cluster: ClusterRow,
    top_ids: list[int],
    movie_data: dict[int, dict],
) -> RecommendationDto:
    """
    Assemble a RecommendationDto from pre-fetched movie data.
    Args:
        cluster:    The cluster to include in the payload.
        top_ids:    Ordered list of movie_ids (descending score) to include.
        movie_data: Dict mapping movie_id → MovieDto-shaped dict.
    Returns:
        A ``RecommendationDto`` DTO.
    """
    films = [MovieDto(**movie_data[movie_id]) for movie_id in top_ids if movie_id in movie_data]
    cluster_pub = ClusterDto(
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
    return RecommendationDto(cluster=cluster_pub, films=films)


def build_recommendation(
    cluster: ClusterRow,
    top_k: int,
) -> RecommendationDto:
    """
    Build a RecommendationDto from a live ClusterRow via a DB fetch.
    Args:
        cluster: The cluster to recommend.
        top_k:   Maximum number of top-scoring films to include.

    Returns:
        A ``RecommendationDto`` DTO with fully enriched movie data.
    """
    top_assignments = sorted(
        [a for a in cluster.assignments if not a.excluded],
        key=lambda a: a.score,
        reverse=True,
    )[:top_k]
    top_ids = [a.movie_id for a in top_assignments]
    movie_dicts = api_movies.fetch_movies_dto(top_ids)
    movie_data = {m["id"]: m for m in movie_dicts}
    return make_recommendation_dto(cluster, top_ids, movie_data)


def last_show_recommendation(full, top_k: int) -> RecommendationDto | None:
    """
    Return the last show-turn's recommendation, if any.
    Used by terminal paths (terminate, natural_end) to surface the most
    recent recommendation alongside the stop turn.
    """
    from backend.api.types import StepType  # local: avoid pulling at module-import time
    for prior_t in reversed(full.turns):
        if prior_t.step_type == StepType.show.value and prior_t.clusters:
            return build_recommendation(pick_best_cluster(prior_t.clusters), top_k)
    return None


def render_recommendation(*, best_cluster: ClusterRow, top_k: int) -> str:
    """Format a recommendation reply from the best cluster.

    Args:
        best_cluster: The cluster the Decision Agent chose to recommend.
        top_k:        Maximum number of top-scoring films to list.

    Returns:
        A markdown-formatted reply string ready to show the oracle.
    """
    top_assignments = sorted(
        [a for a in best_cluster.assignments if not a.excluded],
        key=lambda a: a.score,
        reverse=True,
    )[:top_k]

    film_lines = "\n".join(
        f"- {a.title or str(a.movie_id)}" for a in top_assignments
    )

    reply = (
        f"**{best_cluster.name}**\n\n"
        f"{best_cluster.description or ''}\n\n"
        f"Top picks:\n{film_lines}"
    )

    log.debug(
        "deterministic render complete",
        extra={
            "cluster_name": best_cluster.name,
            "n_films": len(top_assignments),
        },
    )
    return reply


def emit_cluster_snapshot(
    clusters: list[ClusterRow],
    progress_cb: ProgressCallback,
) -> None:
    """Enrich clusters with poster/rating stubs and emit a ClusterSnapshotEvent.

    Gathers the top-K non-excluded movie ids from each cluster, fetches
    lightweight stubs from the DB in one batch, then fires the event via
    ``progress_cb`` so the router can stream it to the frontend.

    Args:
        clusters:    List of ClusterRow objects produced by clustering.
        progress_cb: The turn's streaming callback.
    """
    all_ids: list[int] = []
    cluster_tops: list[list[int]] = []
    for c in clusters:
        top = sorted(
            [a for a in c.assignments if not a.excluded],
            key=lambda a: a.score,
            reverse=True,
        )
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
        active_scores = [a.score for a in c.assignments if not a.excluded]
        confidence = sum(active_scores) / len(active_scores) if active_scores else 0.0
        payloads.append(
            ClusterSnapshotPayload(
                id=str(c.id),
                name=c.name,
                description=c.description,
                level=c.level,
                confidence=confidence,
                top_films=top_films,
            )
        )

    try:
        progress_cb(ClusterSnapshotEvent(clusters=payloads))
    except Exception:
        log.warning("cluster snapshot event dropped", exc_info=True)


def assemble_session_dto(full: SessionRow, cfg: Settings) -> SessionDto:
    """Project a ``SessionRow`` into the HTTP ``SessionDto`` DTO.

    Internal experimental fields (run_id, seed, config_hash, model_version,
    persona_id, preference_profile, feedback, metrics, judge_scores) are
    dropped. Every show turn is hydrated with a ``RecommendationDto``
    built from the turn's best cluster and the top-K non-excluded films;
    stop turns inherit the most recent show turn's recommendation; ask
    turns carry no recommendation.

    All movie-metadata fetches across the whole session are batched into a
    single DB call.

    Args:
        full: Full read-side snapshot loaded by ``api_retrieval.get_session_full``.
        cfg:  Active settings (used for ``cfg.session.recommendation_top_k``).

    Returns:
        A ``SessionDto`` ready to serialize to the HTTP client.
    """
    # Pre-compute the best cluster + top-movie-ids for every show turn so we
    # can batch all movie fetches into a single DB call.
    show_turn_info: dict = {}
    for t in full.turns:
        if t.step_type == StepType.show.value and t.clusters:
            best = pick_best_cluster(t.clusters)
            top_ids = [
                a.movie_id
                for a in sorted(
                    [a for a in best.assignments if not a.excluded],
                    key=lambda a: a.score,
                    reverse=True,
                )[: cfg.session.recommendation_top_k]
            ]
            show_turn_info[t.id] = (best, top_ids)

    all_ids = list(
        dict.fromkeys(mid for _, (_, ids) in show_turn_info.items() for mid in ids)
    )
    movie_data: dict[int, dict] = (
        {m["id"]: m for m in api_movies.fetch_movies_dto(all_ids)}
        if all_ids
        else {}
    )

    # Build turns, hydrating recommendation for show and stop steps
    last_show_recommendation: RecommendationDto | None = None
    turns: list[TurnDto] = []
    for t in full.turns:
        recommendation: RecommendationDto | None = None
        step = StepType(t.step_type) if t.step_type else StepType.show
        if step == StepType.show and t.id in show_turn_info:
            best, top_ids = show_turn_info[t.id]
            recommendation = make_recommendation_dto(best, top_ids, movie_data)
            last_show_recommendation = recommendation
        elif step == StepType.stop:
            recommendation = last_show_recommendation

        turns.append(
            TurnDto(
                turn_id=t.id,
                session_id=full.session_id,
                turn_number=t.turn_number,
                user_message=t.user_message,
                assistant_message=t.assistant_message or "",
                step_type=step,
                converged=t.converged,
                created_at=t.created_at,
                recommendation=recommendation,
            )
        )

    return SessionDto(
        session_id=full.session_id,
        status=SessionStatus(full.status),
        max_turns=full.max_turns,
        created_at=full.created_at,
        updated_at=full.updated_at,
        turns=turns,
    )


__all__ = [
    "assemble_session_dto",
    "build_recommendation",
    "emit_cluster_snapshot",
    "last_show_recommendation",
    "make_recommendation_dto",
    "pick_best_cluster",
    "render_recommendation",
]
