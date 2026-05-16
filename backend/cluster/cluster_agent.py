"""Cluster Agent — groups retrieved candidates into named, soft-assigned clusters.

Pipeline per turn:
  1. Reformulate the oracle's query via the Retrieval System's reformulator.
  2. Retrieve top-K candidates via the Retrieval System.
  3. Fetch candidate embeddings from the catalogue.
  4. Run HDBSCAN soft clustering (``soft_cluster_engine``).
  5. Name and describe each cluster via a single batched LLM call (``cluster_describer``).
  6. Return ``list[ClusterSnapshot]`` — no DB writes (architecture rule).

Returns an empty list when retrieval yields no candidates or when HDBSCAN
classifies all points as noise.  The Orchestrator handles the empty case by
issuing a canned clarifying question.
"""

import logging
from uuid import UUID, uuid4

import numpy as np

import backend.retrieval.agent as retrieval_agent
from backend.cluster.tools import (
    cluster_describer,
    cluster_updater,
    embedding_fetcher,
    soft_cluster_engine,
)
from backend.api.types import ClusterAssignment, ClusterSnapshot
from backend.settings import get_settings
from backend.retrieval.tools import metadata_fetcher

log = logging.getLogger(__name__)


def cluster(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    accumulated_cost_usd: float = 0.0,
    prior_candidates: list[int] | None = None,
    accepted_cluster: dict | None = None,
    dry_run: bool = False,
) -> list[ClusterSnapshot]:
    """Retrieve candidates and produce soft-assigned, named clusters.

    When *prior_candidates* is None (default), drives the Retrieval System
    internally: reformulates the query, fetches top-K candidates via vector
    search, clusters their embeddings, and returns named snapshots.

    When *prior_candidates* is provided, skips vector search and reuses the
    supplied movie IDs as the candidate pool, re-running HDBSCAN and the
    cluster describer on the fixed pool with the newly reformulated query.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        turn_number:          1-based turn index within the session.
        user_query:           Oracle's raw (or pre-refined) utterance.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        prior_candidates:     Optional list of TMDB movie IDs from a prior turn's
                              cluster pool; when provided, vector search is skipped.
        accepted_cluster:     Optional dict ``{name, description, feedback_type}``
                              describing the cluster the oracle accepted or rejected
                              in the prior turn.  Passed to the cluster updater to
                              re-score soft assignments via LLM.  Ignored when
                              ``prior_candidates`` is ``None``.
        dry_run:              If ``True``, skip all LLM calls; HDBSCAN still runs
                              deterministically on real embeddings.

    Returns:
        List of ``ClusterSnapshot`` objects, or an empty list when retrieval
        returns no candidates or HDBSCAN classifies all points as noise.

    Raises:
        LLMParseError:     If the reformulator or describer returns malformed JSON.
        CostLimitExceeded: If the session budget is exhausted before either LLM call.
        ValueError:        If embedding fetching fails (no rows returned).
    """
    cfg = get_settings()
    k: int = cfg.retrieval.top_k

    log.debug(
        "cluster agent entry",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "turn_number": turn_number,
            "user_query_len": len(user_query),
            "prior_candidates": 0 if prior_candidates is None else len(prior_candidates),
            "top_k": k,
            "dry_run": dry_run,
        },
    )

    # If prior candidates are provided, skip reformulation and retrieval
    if prior_candidates is not None:
        movie_ids = prior_candidates
        metas = metadata_fetcher.fetch(movie_ids)
        meta_by_id = {m.movie_id: m for m in metas}

        kept_ids, result = cluster_updater.update(
            movie_ids,
            metas=metas,
            accepted_cluster=accepted_cluster,
            user_query=user_query,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            accumulated_cost_usd=accumulated_cost_usd,
            dry_run=dry_run,
        )

        if result.n_clusters == 0:
            log.warning(
                "Cluster agent: HDBSCAN classified all prior candidates as noise — returning empty",
                extra={"session_id": str(session_id), "n_candidates": len(kept_ids)},
            )
            return []

    # Otherwise, run the full retrieval pipeline to get candidates
    else:
        retrieval_result = retrieval_agent.retrieve(
            user_query=user_query,
            k=k,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            accumulated_cost_usd=accumulated_cost_usd,
            dry_run=dry_run,
        )
        metas = retrieval_result.candidates

        # If no candidates are retrieved, return an empty list
        if not metas:
            log.warning(
                "Cluster agent: no candidates retrieved, returning empty",
                extra={"session_id": str(session_id), "turn_number": turn_number},
            )
            return []
        
        # Fetch embeddings for the candidate pool and cluster them with HDBSCAN
        movie_ids = [c.movie_id for c in metas]
        kept_ids, embeddings = embedding_fetcher.fetch(movie_ids)

        # Cluster with HDBSCAN; the describer and downstream decision agent will see only the
        result = soft_cluster_engine.cluster(
            embeddings,
            min_cluster_size=cfg.clustering.min_cluster_size,
            min_samples=cfg.clustering.min_samples,
            cluster_selection_method=cfg.clustering.cluster_selection_method,
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

        meta_by_id = {c.movie_id: c for c in metas}

        if result.n_clusters == 0:
            log.warning(
                "Cluster agent: HDBSCAN classified all points as noise — returning empty",
                extra={"session_id": str(session_id), "n_candidates": len(kept_ids)},
            )
            return []

    # At this point we have a cluster result (either from the full pipeline or just the update) 
    membership: np.ndarray = result.membership  # type: ignore[assignment]
    top_n: int = cfg.clustering.top_titles_per_cluster
    threshold: float = cfg.clustering.assignment_threshold

    # Describe each cluster with the describer, then construct snapshots with soft assignments
    clusters_payload: list[dict] = []
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
            {
                "cluster_index": ci,
                "top_titles": [m.title for m in top_metas],
                "top_genres": genres[:6],
                "sample_overviews": overviews[:2],
            }
        )

    log.debug(
        "cluster describer pre-call",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_clusters_to_describe": len(clusters_payload),
            "top_titles_per_cluster": top_n,
        },
    )

    # The describer returns a list of (name, description) pairs in the same order as the input clusters
    labels = cluster_describer.describe(
        clusters_payload=clusters_payload,
        user_query=user_query,
        reformulated_query=user_query if prior_candidates is not None else retrieval_result.reformulated_query,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        accumulated_cost_usd=accumulated_cost_usd,
        dry_run=dry_run,
    )

    # Finally, construct the list of ClusterSnapshots with soft assignments based on the describer's output
    snapshots: list[ClusterSnapshot] = []
    for ci, (name, description) in enumerate(labels):
        scores = membership[:, ci]
        assignments = [
            ClusterAssignment(
                movie_id=kept_ids[i],
                score=float(scores[i]),
                excluded=False,
                title=meta_by_id[kept_ids[i]].title if kept_ids[i] in meta_by_id else None,
            )
            for i in range(len(kept_ids))
            if scores[i] >= threshold
        ]
        snapshots.append(
            ClusterSnapshot(
                id=uuid4(),
                name=name,
                description=description,
                level=0,
                parent_cluster_id=None,
                assignments=assignments,
            )
        )

    log.info(
        "Cluster agent complete",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "n_clusters": len(snapshots),
            "n_candidates": len(kept_ids),
        },
    )
    log.debug(
        "final ClusterSnapshot list",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "cluster_names": [s.name for s in snapshots],
            "cluster_sizes": [len(s.assignments) for s in snapshots],
        },
    )
    return snapshots
