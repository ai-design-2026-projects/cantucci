"""Cluster Agent — groups retrieved candidates into named, soft-assigned clusters.

Two scenarios, one LLM call each:

Scenario A — fresh (``prior_clusters`` is ``None``):
  1. Reformulate the oracle's query via the Retrieval System's reformulator.
  2. Retrieve top-K candidates via the Retrieval System.
  3. Fetch candidate embeddings from the catalogue.
  4. Run HDBSCAN soft clustering (``soft_cluster_engine``).
  5. Name and describe each cluster via a single batched LLM call (``cluster_describer``).
  6. Return ``list[ClusterSnapshot]`` — no DB writes (architecture rule).

Scenario B — refinement (``prior_clusters`` is not ``None``, with ``asked_question`` + ``user_answer``):
  1. Fetch metadata for the films in the prior cluster pool.
  2. Render the refine prompt with prior clusters + clarifying Q&A.
  3. ``cluster_refiner`` makes one LLM call that drops, moves, renames,
     redescribes, and rescores in a single pass — no HDBSCAN re-run.
  4. Return ``list[ClusterSnapshot]`` with new UUIDs.

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
    cluster_refiner,
    embedding_fetcher,
    soft_cluster_engine,
)
from backend.api.types import ClusterAssignment, ClusterSnapshot
from backend.settings import get_settings

log = logging.getLogger(__name__)


def cluster(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    accumulated_cost_usd: float = 0.0,
    prior_clusters: list[ClusterSnapshot] | None = None,
    asked_question: str | None = None,
    user_answer: str | None = None,
    dry_run: bool = False,
) -> list[ClusterSnapshot]:
    """Retrieve candidates and produce soft-assigned, named clusters.

    When *prior_clusters* is None (default), drives the Retrieval System
    internally: reformulates the query, fetches top-K candidates via vector
    search, clusters their embeddings with HDBSCAN, names each cluster via the
    describer LLM call, and returns named snapshots.

    When *prior_clusters* is provided, skips retrieval/HDBSCAN and instead asks
    the refiner to semantically restructure the prior clusters in a single LLM
    call, using the system's clarifying *asked_question* and the oracle's
    *user_answer* to drive the refinement.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn.
        turn_number:          1-based turn index within the session.
        user_query:           Oracle's raw (or pre-refined) utterance.
        accumulated_cost_usd: Running USD cost for the current turn (for cost guard).
        prior_clusters:       Optional list of the previous turn's
                              ``ClusterSnapshot``s. When provided, dispatches to
                              the refinement path; *asked_question* and
                              *user_answer* are then required.
        asked_question:       The clarifying question the system asked on the
                              previous turn. Required when *prior_clusters* is
                              not None.
        user_answer:          The oracle's reply to *asked_question*. Required
                              when *prior_clusters* is not None.
        dry_run:              If ``True``, skip all live LLM calls.

    Returns:
        List of ``ClusterSnapshot`` objects, or an empty list when retrieval
        returns no candidates, when HDBSCAN classifies all points as noise, or
        when refinement drops every cluster.

    Raises:
        LLMParseError:     If any LLM call returns malformed JSON or fails
                           schema validation on every retry.
        CostLimitExceeded: If the session budget is exhausted before any LLM call.
        ValueError:        If the fresh path fails to fetch embeddings, or if
                           the refinement path is dispatched without
                           *asked_question* / *user_answer*.
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
            "has_prior_clusters": prior_clusters is not None,
            "n_prior_clusters": 0 if prior_clusters is None else len(prior_clusters),
            "top_k": k,
            "dry_run": dry_run,
        },
    )

    # Scenario B — refinement. The refiner owns its own LLM call and metadata
    # fetch; the agent's job here is just to validate the contract and dispatch.
    if prior_clusters is not None:
        if asked_question is None or user_answer is None:
            raise ValueError(
                "refinement path requires asked_question and user_answer; got None"
            )
        return cluster_refiner.refine(
            prior_clusters=prior_clusters,
            user_query=user_query,
            asked_question=asked_question,
            user_answer=user_answer,
            session_id=session_id,
            run_id=run_id,
            turn_id=turn_id,
            accumulated_cost_usd=accumulated_cost_usd,
            dry_run=dry_run,
        )

    # Scenario A — fresh retrieval + HDBSCAN + describer.
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

    # Cluster with UMAP+HDBSCAN; the describer and downstream decision agent will see only the
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

    meta_by_id = {c.movie_id: c for c in metas}

    if result.n_clusters == 0:
        log.warning(
            "Cluster agent: HDBSCAN classified all points as noise — returning empty",
            extra={"session_id": str(session_id), "n_candidates": len(kept_ids)},
        )
        return []

    # At this point we have a cluster result from the full pipeline
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
        reformulated_query=retrieval_result.reformulated_query,
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
