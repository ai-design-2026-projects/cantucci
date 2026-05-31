"""Single-call baseline agent: one LLM call per turn producing clusters, operation, and reply."""
import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.baseline.types import BaselineResponse
from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_snapshot_members,
)
from backend.data_access.conversations.queries import get_messages
from backend.data_access.movies.queries import fetch_metadata, list_movie_ids
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_SYSTEM = (
    "You are a movie-catalogue clustering assistant. "
    "Follow the instructions in the user message exactly and output valid JSON only."
)


async def baseline_turn(
    conversation_id: uuid.UUID,
    current_cluster_snapshot_id: uuid.UUID | None,
    accumulated_cost: float,
    message_id: uuid.UUID,
) -> tuple[BaselineResponse, float]:
    """Make one LLM call that produces clusters, the declared operation, and the oracle reply.

    Loads the full film list from the current snapshot (falling back to the full catalogue
    if no snapshot exists), the current cluster state for context, and the conversation
    transcript.  Renders ``baseline_v1.j2`` and calls the LLM once.

    Args:
        conversation_id:             UUID of the active conversation.
        current_cluster_snapshot_id: Active cluster snapshot, or None if unclustered.
        accumulated_cost:            Running LLM cost for limit enforcement.
        message_id:                  Per-turn UUID used in LLM log records.

    Returns:
        Tuple of (BaselineResponse, cost_usd).

    Raises:
        CostLimitExceeded: When accumulated cost exceeds the configured limit.
        LLMParseError:     When the LLM returns an unparseable response.
    """
    cfg = get_settings()
    model = cfg.models.strong

    if current_cluster_snapshot_id is not None:
        members = get_snapshot_members(current_cluster_snapshot_id)
        movie_ids = [m.movie_id for m in members]
    else:
        movie_ids = list_movie_ids()

    films = fetch_metadata(movie_ids)

    clusters_info: list[dict] = []
    if current_cluster_snapshot_id is not None:
        snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
        if snapshot is not None:
            for c in snapshot.clusters:
                clusters_info.append({
                    "label": c.label or "(unlabelled)",
                    "summary": c.summary or "",
                })

    messages = get_messages(conversation_id, limit=1000)
    transcript = [{"role": m.role, "content": m.content} for m in messages]

    # Use 1-based sequential indices in the prompt so the LLM copies small integers,
    # not arbitrary TMDB IDs.  We map back to real IDs after parsing.
    idx_to_movie_id: dict[int, int] = {}
    films_for_prompt = []
    for idx, f in enumerate(films, start=1):
        idx_to_movie_id[idx] = f.movie_id
        films_for_prompt.append({
            "idx": idx,
            "title": f.title,
            "year": f.release_year,
            "genres": ", ".join(f.genres) if f.genres else "Unknown",
            "overview": f.overview,
        })

    log.info(
        "baseline_turn_start",
        extra={
            "conversation_id": str(conversation_id),
            "n_films": len(films_for_prompt),
            "n_current_clusters": len(clusters_info),
            "n_transcript_msgs": len(transcript),
        },
    )

    template = _ENV.get_template("baseline_v1.j2")
    user_prompt = template.render(
        films=films_for_prompt,
        clusters=clusters_info,
        transcript=transcript,
    )

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="baseline",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=BaselineResponse,
    )

    parsed: BaselineResponse = resp.parsed  # type: ignore[assignment]

    # Remap sequential indices → real TMDB movie IDs before returning.
    remapped_clusters = []
    for cluster in parsed.clusters:
        real_ids = [idx_to_movie_id[idx] for idx in cluster.film_ids if idx in idx_to_movie_id]
        remapped_clusters.append(cluster.model_copy(update={"film_ids": real_ids}))
    remapped = parsed.model_copy(update={"clusters": remapped_clusters})

    log.info(
        "baseline_llm_done",
        extra={
            "conversation_id": str(conversation_id),
            "operation": remapped.operation,
            "concept": remapped.concept,
            "n_clusters": len(remapped.clusters),
            "n_films_assigned": sum(len(c.film_ids) for c in remapped.clusters),
            "n_films_total": len(films_for_prompt),
        },
    )
    return remapped, resp.cost_usd
