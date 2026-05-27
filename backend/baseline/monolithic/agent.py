"""Monolithic baseline agent: single LLM call per turn."""
import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.conversations.queries import get_messages
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings
from backend.baseline.monolithic.types import MonolithicLLMResponse

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)


async def monolithic_turn(
    conversation_id: uuid.UUID,
    current_cluster_snapshot_id: uuid.UUID | None,
    accumulated_cost: float,
) -> tuple[MonolithicLLMResponse, float]:
    """Run one monolithic LLM turn.

    Reads the full message history and current cluster state from the DB,
    renders the monolithic prompt, and returns the parsed LLM response.

    Args:
        conversation_id:             UUID of the conversation.
        current_cluster_snapshot_id: Current active cluster snapshot (may be None).
        accumulated_cost:            Running LLM cost for limit checking.

    Returns:
        Tuple of (MonolithicLLMResponse, cost_usd).

    Raises:
        CostLimitExceeded: If accumulated cost exceeds the limit.
        LLMParseError:     If the LLM returns an invalid response.
    """
    cfg = get_settings()
    model = cfg.models.strong

    messages = get_messages(conversation_id, limit=1000)
    transcript = [{"role": m.role, "content": m.content} for m in messages]

    clusters_info: list[dict] = []
    if current_cluster_snapshot_id is not None:
        snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
        if snapshot is not None:
            for cluster in snapshot.clusters:
                stubs = fetch_stubs(cluster.exemplar_movie_ids[:5]) if cluster.exemplar_movie_ids else []
                exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
                member_ids = [mid for mid, _ in cluster.memberships] if hasattr(cluster, "memberships") else []
                clusters_info.append({
                    "label": cluster.label,
                    "summary": cluster.summary,
                    "exemplar_titles": exemplar_titles,
                    "movie_ids": member_ids,
                })

    template = _ENV.get_template("monolithic_v1.j2")
    prompt = template.render(clusters=clusters_info, transcript=transcript)

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id=str(conversation_id),
        message_id="00000000-0000-0000-0000-000000000000",
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="monolithic_turn",
        messages=[{"role": "user", "content": prompt}],
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=MonolithicLLMResponse,
    )

    parsed: MonolithicLLMResponse = resp.parsed  # type: ignore[assignment]
    log.debug(
        "monolithic_turn_done",
        extra={
            "conversation_id": str(conversation_id),
            "n_clusters_proposed": len(parsed.clusters),
        },
    )
    return parsed, resp.cost_usd
