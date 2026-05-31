"""Monolithic baseline agent: two LLM calls per turn, no specialised sub-agents."""
import logging
import uuid
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from backend.data_access.cluster_snapshots.queries import (
    get_cluster_snapshot_with_clusters,
    get_snapshot_members,
)
from backend.data_access.conversations.queries import get_messages
from backend.data_access.movies.queries import fetch_stubs
from backend.llm import llm_harness
from backend.settings import get_config_hash, get_settings
from backend.baseline.monolithic.types import MonolithicDecideResponse, MonolithicReplyResponse

log = logging.getLogger(__name__)

_PROMPTS_DIR = Path(__file__).parent / "prompts"
_ENV = Environment(loader=FileSystemLoader(str(_PROMPTS_DIR)), autoescape=False)

_SYSTEM = (
    "You are a movie-catalogue clustering assistant. "
    "Follow the instructions in the user message exactly and output valid JSON only."
)


async def monolithic_decide(
    conversation_id: uuid.UUID,
    current_cluster_snapshot_id: uuid.UUID | None,
    accumulated_cost: float,
    message_id: uuid.UUID,
) -> tuple[MonolithicDecideResponse, float]:
    """Call 1: select the operation and extract its parameters.

    Reads the full message history and current cluster state, then asks the
    monolithic LLM to choose one operation and fill in its parameters.
    No reply text is produced at this stage.

    Args:
        conversation_id:             UUID of the active conversation.
        current_cluster_snapshot_id: Active cluster snapshot, or None if unclustered.
        accumulated_cost:            Running LLM cost for limit enforcement.
        message_id:                  Per-turn UUID used in LLM log records.

    Returns:
        Tuple of (MonolithicDecideResponse, cost_usd).

    Raises:
        CostLimitExceeded: When accumulated cost exceeds the configured limit.
        LLMParseError:     When the LLM returns an unparseable response.
    """
    cfg = get_settings()
    model = cfg.models.strong

    messages = get_messages(conversation_id, limit=1000)
    transcript = [{"role": m.role, "content": m.content} for m in messages]

    clusters_info: list[dict] = []
    if current_cluster_snapshot_id is not None:
        snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
        if snapshot is not None:
            all_members = get_snapshot_members(current_cluster_snapshot_id)
            counts: dict[uuid.UUID, int] = {}
            for m in all_members:
                counts[m.cluster_id] = counts.get(m.cluster_id, 0) + 1
            for cluster in snapshot.clusters:
                clusters_info.append({
                    "label": cluster.label,
                    "summary": cluster.summary,
                    "member_count": counts.get(cluster.id, 0),
                })

    template = _ENV.get_template("monolithic_v2_decide.j2")
    user_prompt = template.render(clusters=clusters_info, transcript=transcript)

    resp = await llm_harness.call(
        run_id="eval",
        conversation_id=str(conversation_id),
        message_id=str(message_id),
        config_hash=get_config_hash(),
        model_and_version=model.name,
        provider=model.provider,
        seed=model.seed,
        max_tokens=model.max_tokens,
        step_type="monolithic_decide",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=MonolithicDecideResponse,
    )

    parsed: MonolithicDecideResponse = resp.parsed  # type: ignore[assignment]
    log.debug(
        "monolithic_decide_done",
        extra={"conversation_id": str(conversation_id), "operation": parsed.operation},
    )
    return parsed, resp.cost_usd


async def monolithic_reply(
    oracle_message: str,
    operation: str,
    new_cluster_exemplars: list[list[int]],
    conversation_id: uuid.UUID,
    accumulated_cost: float,
    message_id: uuid.UUID,
    concept: str | None = None,
    concept_positive_label: str | None = None,
    concept_negative_label: str | None = None,
) -> tuple[MonolithicReplyResponse, float]:
    """Call 2: formulate the oracle reply and label any new clusters.

    Called after the operation has been executed. Receives exemplar movie IDs for
    newly produced clusters (empty for operations that do not create new clusters)
    and asks the monolithic LLM to label them and write the reply — replacing both
    the labelling agent and the responder agent used by the full coordinator.

    Args:
        oracle_message:          The oracle's latest message (context for the reply).
        operation:               Operation that was executed (shown in the prompt).
        new_cluster_exemplars:   Exemplar movie-ID lists for new clusters, in order.
                                 Empty list for focus/exclude/merge/cross_filter/reply.
        conversation_id:         UUID of the active conversation.
        accumulated_cost:        Running LLM cost for limit enforcement.
        message_id:              Per-turn UUID used in LLM log records.
        concept:                 Concept name from the decide call (cluster only).
        concept_positive_label:  Short label for the high end of the concept axis.
                                 When set, clusters are labelled relative to the axis
                                 rather than by generic film content.
        concept_negative_label:  Short label for the low end of the concept axis.

    Returns:
        Tuple of (MonolithicReplyResponse, cost_usd).

    Raises:
        CostLimitExceeded: When accumulated cost exceeds the configured limit.
        LLMParseError:     When the LLM returns an unparseable response.
    """
    cfg = get_settings()
    model = cfg.models.strong

    new_clusters = []
    for exemplar_ids in new_cluster_exemplars:
        stubs = fetch_stubs(exemplar_ids[:8]) if exemplar_ids else []
        exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
        new_clusters.append({"exemplar_titles": exemplar_titles})

    template = _ENV.get_template("monolithic_v2_reply.j2")
    user_prompt = template.render(
        oracle_message=oracle_message,
        operation=operation,
        new_clusters=new_clusters,
        concept=concept,
        concept_positive_label=concept_positive_label,
        concept_negative_label=concept_negative_label,
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
        step_type="monolithic_reply",
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": user_prompt},
        ],
        cost_limit_usd=cfg.conversation.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost,
        dry_run=model.dry_run,
        response_schema=MonolithicReplyResponse,
    )

    parsed: MonolithicReplyResponse = resp.parsed  # type: ignore[assignment]
    log.debug(
        "monolithic_reply_done",
        extra={"conversation_id": str(conversation_id), "operation": operation},
    )
    return parsed, resp.cost_usd
