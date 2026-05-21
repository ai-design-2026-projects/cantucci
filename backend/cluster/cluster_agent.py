"""Cluster Agent — groups retrieved candidates into named, soft-assigned clusters.

Two paths, both driven explicitly by the Orchestrator:

Fresh path (Scenario A):
  1. ``soft_cluster``:      fetch embeddings + HDBSCAN → ``SoftClusterResult`` (no LLM).
  2. ``describe_clusters``: LLM-name each cluster → ``list[ClusterRow]``.

Refinement path (Scenario B):
  ``refine``: thin wrapper over ``cluster_refiner.refine``.

The Orchestrator calls retrieval itself and passes the result to ``soft_cluster``.
Retrieval and clustering are fully decoupled.
"""

import logging
from dataclasses import dataclass
from uuid import UUID, uuid4

import numpy as np

from backend.cluster.tools import (
    cluster_describer,
    cluster_refiner,
    embedding_fetcher,
    soft_cluster_engine,
)
from backend.cluster.domain import ClusterAssignment, ClusterPayload
from backend.repository.sessions import ClusterRow
from backend.retrieval.types import RetrievalResult
from backend.repository.movies.types import MovieRow
from backend.settings import get_settings

log = logging.getLogger(__name__)


@dataclass
class SoftClusterResult:
    """Intermediate result from HDBSCAN clustering, before LLM naming.

    Attributes:
        kept_ids:        Movie IDs that survived the embedding fetch (subset
                         of retrieval candidates — some may be missing from DB).
        membership:      HDBSCAN soft-membership matrix, shape (n_kept, n_clusters).
        meta_by_id:      Metadata keyed by movie_id, for title look-up in snapshots.
        clusters_payload: Pre-built per-cluster dicts (top_titles, genres, overviews)
                         passed verbatim to the describer LLM call.
    """

    kept_ids: list[int]
    membership: np.ndarray
    meta_by_id: dict[int, MovieRow]
    clusters_payload: list[ClusterPayload]


def soft_cluster(
    *,
    retrieval_result: RetrievalResult,
    session_id: UUID,
    turn_id: UUID,
    turn_number: int,
) -> SoftClusterResult | None:
    """Fetch embeddings and run HDBSCAN soft clustering on a retrieval result.

    No LLM calls. Returns None when retrieval is empty or HDBSCAN classifies
    all points as noise. The caller (Orchestrator) treats None as an empty
    cluster list and issues a canned clarifying question.

    Args:
        retrieval_result: Output of ``retrieval_agent.retrieve``.
        session_id:       UUID of the current session.
        turn_id:          UUID of the current turn.
        turn_number:      1-based turn index within the session.

    Returns:
        ``SoftClusterResult`` ready for ``describe_clusters``, or ``None``.
    """
    cfg = get_settings()
    metas = retrieval_result.candidates

    if not metas:
        log.warning(
            "soft_cluster: no candidates, returning None",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        return None

    movie_ids = [c.movie_id for c in metas]
    kept_ids, embeddings = embedding_fetcher.fetch(movie_ids)

    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=cfg.clustering.min_cluster_size,
        min_samples=cfg.clustering.min_samples,
        cluster_selection_method=cfg.clustering.cluster_selection_method,
        umap_cfg=cfg.clustering.umap,
        seed=cfg.models.strong.seed,
    )

    log.debug(
        "soft cluster engine output",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_kept": len(kept_ids),
            "n_clusters": result.n_clusters,
            "embedding_dim": int(embeddings.shape[1]) if embeddings.ndim == 2 else None,
        },
    )

    if result.n_clusters == 0:
        log.warning(
            "soft_cluster: HDBSCAN all-noise, returning None",
            extra={"session_id": str(session_id), "n_candidates": len(kept_ids)},
        )
        return None

    meta_by_id = {c.movie_id: c for c in metas}
    membership: np.ndarray = result.membership
    top_n: int = cfg.clustering.top_titles_per_cluster

    clusters_payload: list[ClusterPayload] = []
    for ci in range(result.n_clusters):
        scores = membership[:, ci]
        order = np.argsort(scores)[::-1][:top_n]
        top_metas = [meta_by_id[kept_ids[i]] for i in order if kept_ids[i] in meta_by_id]
        genres: list[str] = []
        for m in top_metas:
            for g in m.genres:
                if g not in genres:
                    genres.append(g)
        overviews = [m.overview for m in top_metas if m.overview]
        clusters_payload.append(
            ClusterPayload(
                cluster_index=ci,
                top_titles=[m.title for m in top_metas],
                top_genres=genres[:6],
                sample_overviews=overviews[:2],
            )
        )

    return SoftClusterResult(
        kept_ids=kept_ids,
        membership=membership,
        meta_by_id=meta_by_id,
        clusters_payload=clusters_payload,
    )


async def describe_clusters(
    *,
    soft_result: SoftClusterResult,
    user_query: str,
    reformulated_query: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> list[ClusterRow]:
    """LLM-name each cluster and build ClusterSnapshots with soft assignments.

    Args:
        soft_result:          Output of ``soft_cluster``.
        user_query:           Oracle's raw query (for the describer prompt).
        reformulated_query:   Reformulated query from retrieval (for the describer prompt).
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running cost for the current turn.
        dry_run:              If ``True``, skip live LLM calls.

    Returns:
        List of named ``ClusterRow`` objects with soft assignments.

    Raises:
        LLMParseError:     If the describer LLM call returns malformed JSON.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()
    threshold: float = cfg.clustering.assignment_threshold

    log.debug(
        "cluster describer pre-call",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_clusters_to_describe": len(soft_result.clusters_payload),
        },
    )

    labels = await cluster_describer.describe(
        clusters_payload=soft_result.clusters_payload,
        user_query=user_query,
        reformulated_query=reformulated_query,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
    )

    snapshots: list[ClusterRow] = []
    for ci, (name, description) in enumerate(labels):
        scores = soft_result.membership[:, ci]
        assignments = [
            ClusterAssignment(
                movie_id=soft_result.kept_ids[i],
                score=float(scores[i]),
                excluded=False,
                title=soft_result.meta_by_id[soft_result.kept_ids[i]].title
                if soft_result.kept_ids[i] in soft_result.meta_by_id else None,
            )
            for i in range(len(soft_result.kept_ids))
            if scores[i] >= threshold
        ]
        snapshots.append(
            ClusterRow(
                id=uuid4(),
                name=name,
                description=description,
                level=0,
                parent_cluster_id=None,
                assignments=assignments,
            )
        )

    log.info(
        "describe_clusters complete",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_clusters": len(snapshots),
        },
    )
    log.debug(
        "final ClusterRow list",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "cluster_names": [s.name for s in snapshots],
            "cluster_sizes": [len(s.assignments) for s in snapshots],
        },
    )
    return snapshots


async def refine(
    *,
    prior_clusters: list[ClusterRow],
    user_query: str,
    system_message: str,
    oracle_reply: str,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> list[ClusterRow]:
    """Refine prior clusters in light of the oracle's latest reply.

    Wrapper over ``cluster_refiner.refine``. The orchestrator fires this on
    every turn that already has a clustered prior turn — whether the prior
    assistant message was a clarifying ``ask`` or a ``show`` recommendation.

    Args:
        prior_clusters:       The most recent clustered turn's snapshots.
        user_query:           The oracle's original session-level query.
        system_message:       The system's last assistant message (question
                              or rendered recommendation).
        oracle_reply:         The oracle's reply to *system_message*.
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        accumulated_cost_usd: Running cost for the current turn.
        dry_run:              If ``True``, skip live LLM calls.

    Returns:
        Refined ``list[ClusterRow]`` with new UUIDs.

    Raises:
        LLMParseError:     If the harness exhausts its retry budget.
        CostLimitExceeded: If the session budget is exhausted.
    """
    return await cluster_refiner.refine(
        prior_clusters=prior_clusters,
        user_query=user_query,
        system_message=system_message,
        oracle_reply=oracle_reply,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
    )
