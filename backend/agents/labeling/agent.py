import logging
from typing import Any

from backend.agents.base import LLMAgent
from backend.agents.labeling.types import (
    BatchLabelLLMResponse,
    BatchLabelResult,
    ClusterLabelContext,
    LabelResult,
)
from backend.data_access.movies.queries import fetch_stubs
from backend.llm.types import LLMResponse
from backend.settings import get_settings

log = logging.getLogger(__name__)

_SENTINEL_MESSAGE_ID = "00000000-0000-0000-0000-000000000000"


class LabelingLLMAgent(LLMAgent[BatchLabelResult]):
    """Labels a batch of clusters in a single LLM call."""

    name = "labeling"
    step_type = "label_clusters"
    model_tier = "fast"
    template_name = "label_v7.j2"
    response_schema = BatchLabelLLMResponse

    async def render_kwargs(self, **inputs: Any) -> dict[str, Any]:
        return {"clusters": inputs["entries"], "concept": inputs.get("concept")}

    def build_result(self, resp: LLMResponse, **inputs: Any) -> BatchLabelResult:
        parsed: BatchLabelLLMResponse = resp.parsed  # type: ignore[assignment]
        return BatchLabelResult.from_llm_response(
            parsed, n_expected=inputs["n_expected"], total_cost=resp.cost_usd
        )

    async def call_batch(
        self,
        entries: list[dict],
        concept: str | None,
        conversation_id: str,
        message_id: str,
        accumulated_cost: float,
    ) -> BatchLabelResult:
        """Call the LLM for a single batch of clusters.

        Args:
            entries:          Rendered cluster entry dicts for the template.
            concept:          Optional split concept for context-aware labeling.
            conversation_id:  Conversation UUID string (or ``"offline"``).
            message_id:       Message UUID string for logging.
            accumulated_cost: Running LLM cost to check against limit.

        Returns:
            ``BatchLabelResult`` for the batch.
        """
        run_id = "offline" if conversation_id == "offline" else "online"
        return await self.run(
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            run_id=run_id,
            entries=entries,
            concept=concept,
            n_expected=len(entries),
        )


agent = LabelingLLMAgent()


def _build_entry(
    i: int,
    group: list[int],
    contexts: list[ClusterLabelContext] | None,
    top_n: int,
    concept_rank: int | None = None,
    concept_n: int | None = None,
) -> dict:
    """Build a single template entry dict for one cluster group.

    Args:
        i:            Index into ``contexts`` (if provided).
        group:        Ordered exemplar movie IDs for this cluster.
        contexts:     Optional per-cluster label contexts.
        top_n:        Maximum exemplar titles to include.
        concept_rank: 0-based rank of this cluster ordered low→high by mean concept score.
                      Only set when all clusters in the batch have a concept_score.
        concept_n:    Total number of clusters in the batch.

    Returns:
        Dict with keys ``exemplar_titles``, ``parent_label``, ``profile``,
        ``pre_set_label``, ``concept_score``, ``concept_rank``, ``concept_n``.
    """
    stubs = fetch_stubs(group[:top_n])
    titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
    ctx = contexts[i] if contexts is not None else None
    entry: dict = {
        "exemplar_titles": titles,
        "parent_label": None,
        "profile": None,
        "pre_set_label": None,
        "concept_score": None,
        "concept_rank": concept_rank,
        "concept_n": concept_n,
    }
    if ctx is not None:
        entry["parent_label"] = ctx.parent_label
        entry["pre_set_label"] = ctx.pre_set_label
        entry["concept_score"] = ctx.concept_score
        if ctx.profile is not None:
            p = ctx.profile
            entry["profile"] = {
                "mean_runtime": round(p.mean_runtime) if p.mean_runtime is not None else None,
                "year_range": f"{p.min_year}–{p.max_year}" if p.min_year is not None else None,
                "mean_rating": round(p.mean_rating, 1) if p.mean_rating is not None else None,
                "top_genres": p.top_genres,
            }
    return entry


async def label_clusters(
    exemplar_groups: list[list[int]],
    conversation_id: str,
    accumulated_cost: float,
    message_id: str | None = None,
    contexts: list[ClusterLabelContext] | None = None,
) -> BatchLabelResult:
    """Generate labels and summaries for multiple clusters in a single LLM call.

    Each entry in ``exemplar_groups`` is the ordered list of exemplar movie IDs
    for one cluster (highest-probability members first). The prompt renders all
    clusters together and the LLM returns one label+summary per cluster, reducing
    round-trips compared to calling the model once per cluster.

    When ``contexts`` is provided (one entry per cluster), the prompt is enriched
    with the split concept, parent-cluster breadcrumb, and per-cluster aggregate
    statistics so the LLM can name clusters by their position on the split
    dimension rather than by generic thematic identity.

    Args:
        exemplar_groups: List of exemplar-movie-ID lists, one per cluster to label.
                         IDs are truncated to ``cfg.labeling.top_exemplars`` per group.
        conversation_id: UUID string of the parent conversation (or ``"offline"``).
        accumulated_cost: Running LLM cost to check against limit.
        message_id:      Message UUID string for logging; a sentinel is used if omitted.
        contexts:        Optional per-cluster context (concept, parent label, stats).
                         When ``None`` the agent falls back to title-only labelling,
                         which is correct for root clusters.

    Returns:
        ``BatchLabelResult`` with one ``LabelResult`` per input cluster group and
        the total LLM cost.

    Raises:
        LLMParseError:  If the LLM response doesn't contain the expected number of
                        cluster labels.
        CostLimitExceeded: If the accumulated cost exceeds the conversation limit.
    """
    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars
    max_batch = cfg.labeling.max_batch_size
    mid = message_id or _SENTINEL_MESSAGE_ID

    concept_ranks: list[int | None] = [None] * len(exemplar_groups)
    concept_n: int | None = None
    if contexts and all(c.concept_score is not None for c in contexts):
        concept_n = len(contexts)
        sorted_indices = sorted(range(len(contexts)), key=lambda k: contexts[k].concept_score)  # type: ignore[index]
        concept_ranks = [0] * len(contexts)
        for rank, original_index in enumerate(sorted_indices):
            concept_ranks[original_index] = rank

    all_entries = [
        _build_entry(i, group, contexts, top_n, concept_ranks[i], concept_n)
        for i, group in enumerate(exemplar_groups)
    ]
    concept = contexts[0].concept if contexts else None

    if len(all_entries) <= max_batch:
        result = await agent.call_batch(all_entries, concept, conversation_id, mid, accumulated_cost)
    else:
        all_results: list[LabelResult] = []
        total_cost = 0.0
        for batch_start in range(0, len(all_entries), max_batch):
            batch = all_entries[batch_start : batch_start + max_batch]
            batch_result = await agent.call_batch(batch, concept, conversation_id, mid, accumulated_cost + total_cost)
            all_results.extend(batch_result.results)
            total_cost += batch_result.cost
        result = BatchLabelResult(results=all_results, cost=total_cost)

    log.debug(
        "label_clusters_done",
        extra={"n_clusters": len(exemplar_groups), "cost_usd": result.cost},
    )
    return result
