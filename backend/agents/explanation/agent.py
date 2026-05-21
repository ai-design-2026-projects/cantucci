import logging
import uuid

from jinja2 import Environment, FileSystemLoader

from backend.agents.explanation.types import ExplanationResult
from backend.data_access.movies.queries import fetch_metadata, fetch_stubs
from backend.data_access.cluster_snapshots.queries import get_memberships, get_cluster_snapshot_with_clusters
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings, prompts_dir

log = logging.getLogger(__name__)

_PROMPTS_DIR = prompts_dir("explanation")
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def explain_placement(
    movie_id: int,
    cluster_id: uuid.UUID,
    cluster_snapshot_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
) -> ExplanationResult:
    """Generate a natural-language explanation for a movie's cluster placement.

    Args:
        movie_id:            TMDB ID of the movie to explain.
        cluster_id:          UUID of the cluster the movie is in.
        cluster_snapshot_id: UUID of the cluster snapshot containing the cluster.
        conversation_id:     Conversation UUID for logging.
        message_id:          Message UUID for logging.
        accumulated_cost:    Running LLM cost this conversation.

    Returns:
        ``ExplanationResult`` with the explanation text.
    """
    cfg = get_settings()

    movie_rows = fetch_metadata([movie_id])
    if not movie_rows:
        return ExplanationResult(
            text=f"Movie {movie_id} not found in catalogue.",
            movie_title="Unknown",
            cluster_label="Unknown",
        )
    movie = movie_rows[0]

    cswc = get_cluster_snapshot_with_clusters(cluster_snapshot_id)
    target_cluster = next((c for c in (cswc.clusters if cswc else []) if c.id == cluster_id), None)
    cluster_label = target_cluster.label if target_cluster else "Unknown"
    cluster_summary = target_cluster.summary if target_cluster else None
    exemplar_ids = target_cluster.exemplar_movie_ids[:5] if target_cluster else []

    exemplar_stubs = fetch_stubs(exemplar_ids)
    exemplar_titles = [s.title for s in exemplar_stubs if s.id != movie_id][:4]

    template = _ENV.get_template("explain_v1.j2")
    prompt = template.render(
        movie_title=movie.title,
        release_year=movie.release_year,
        overview=movie.overview,
        genres=movie.genres,
        director=movie.director,
        cluster_label=cluster_label,
        cluster_summary=cluster_summary,
        exemplar_titles=exemplar_titles,
    )
    messages = [{"role": "user", "content": prompt}]

    resp = await llm_harness.call(
        run_id="online",
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        config_hash=get_config_hash(),
        model_and_version=cfg.models.strong.name,
        provider=cfg.models.strong.provider,
        seed=cfg.models.strong.seed,
        max_tokens=cfg.models.strong.max_tokens,
        step_type="explanation_agent",
        messages=messages,
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=cfg.models.strong.dry_run,
    )

    log.info("explanation_generated", extra={"movie_id": movie_id, "cluster_id": str(cluster_id)})
    return ExplanationResult.from_llm_response(resp.content, movie_title=movie.title, cluster_label=cluster_label)
