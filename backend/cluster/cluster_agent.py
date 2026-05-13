"""Cluster Agent — groups retrieved candidates into named, soft-assigned clusters.

Pipeline per turn:
  1. Reformulate the oracle's query via LLM (``query_reformulator``).
  2. Retrieve top-K candidates via the Retrieval System.
  3. Fetch candidate embeddings from the catalogue.
  4. Run HDBSCAN soft clustering (``soft_cluster_engine``).
  5. Name and describe each cluster via a single batched LLM call (``cluster_describer``).
  6. Return ``list[ClusterSnapshot]`` — no DB writes (architecture rule).

If HDBSCAN classifies all points as noise AND the candidate count meets
``clustering.min_singleton_floor``, one fallback cluster is created covering
all candidates rather than returning an empty list to the Decision Agent.
"""

import logging
from uuid import UUID, uuid4

import numpy as np

import backend.retrieval.agent as retrieval_agent
from backend.cluster.tools import (
    cluster_describer,
    embedding_fetcher,
    query_reformulator,
    soft_cluster_engine,
)
from backend.llm.configs import load_config
from backend.models.clusters import ClusterAssignment, ClusterSnapshot

log = logging.getLogger(__name__)


def cluster(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_query: str,
    config_hash: str,
    model_version: str,
    dry_run: bool = False,
) -> list[ClusterSnapshot]:
    """Retrieve candidates and produce soft-assigned, named clusters.

    Args:
        session_id:    UUID of the current session.
        run_id:        UUID of the parent run.
        turn_id:       UUID of the current turn.
        turn_number:   1-based turn index within the session.
        user_query:    Oracle's raw utterance for this turn.
        config_hash:   SHA-256 prefix of the session's YAML config snapshot.
        model_version: LLM model string stored on the session row.
        dry_run:       If ``True``, skip all LLM calls (harness short-circuits);
                       HDBSCAN still runs deterministically on real embeddings.

    Returns:
        List of ``ClusterSnapshot`` objects.  Empty list if the Retrieval
        System returns no candidates.

    Raises:
        LLMParseError:     If the reformulator or describer returns malformed JSON.
        CostLimitExceeded: If the session budget is exhausted before either LLM call.
        ValueError:        If embedding fetching fails (no rows returned).
    """
    cfg, _ = load_config("default")
    cluster_cfg: dict = cfg["clustering"]
    k: int = cfg["retrieval"]["top_k"]

    reformulated = query_reformulator.reformulate(
        user_query=user_query,
        turn_number=turn_number,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_version=model_version,
        cfg=cfg,
        dry_run=dry_run,
    )

    retrieval_result = retrieval_agent.retrieve(query=reformulated, k=k)
    candidates = retrieval_result.candidates

    if not candidates:
        log.warning(
            "cluster agent: retrieval returned no candidates",
            extra={"session_id": str(session_id), "turn_number": turn_number},
        )
        return []

    movie_ids = [c.movie_id for c in candidates]
    kept_ids, embeddings = embedding_fetcher.fetch(movie_ids)

    result = soft_cluster_engine.cluster(
        embeddings,
        min_cluster_size=cluster_cfg["min_cluster_size"],
        min_samples=cluster_cfg["min_samples"],
        cluster_selection_method=cluster_cfg["cluster_selection_method"],
    )

    meta_by_id = {c.movie_id: c for c in candidates}

    if result.n_clusters == 0:
        if len(kept_ids) >= cluster_cfg.get("min_singleton_floor", 3):
            log.warning(
                "cluster agent: all-noise fallback — single cluster over all candidates",
                extra={
                    "session_id": str(session_id),
                    "n_candidates": len(kept_ids),
                },
            )
            return _build_fallback_cluster(
                kept_ids=kept_ids,
                embeddings=embeddings,
                meta_by_id=meta_by_id,
                reformulated_query=reformulated,
            )
        log.warning(
            "cluster agent: all-noise, candidate count below floor — returning empty",
            extra={"session_id": str(session_id), "n_candidates": len(kept_ids)},
        )
        return []

    membership: np.ndarray = result.membership  # type: ignore[assignment]
    top_n: int = cluster_cfg.get("top_titles_per_cluster", 8)
    threshold: float = cluster_cfg.get("assignment_threshold", 0.05)

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

    labels = cluster_describer.describe(
        clusters_payload=clusters_payload,
        user_query=user_query,
        reformulated_query=reformulated,
        session_id=session_id,
        run_id=run_id,
        turn_id=turn_id,
        config_hash=config_hash,
        model_version=model_version,
        cfg=cfg,
        dry_run=dry_run,
    )

    snapshots: list[ClusterSnapshot] = []
    for ci, (name, description) in enumerate(labels):
        scores = membership[:, ci]
        assignments = [
            ClusterAssignment(movie_id=kept_ids[i], score=float(scores[i]), excluded=False)
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
        "cluster agent complete",
        extra={
            "session_id": str(session_id),
            "turn_number": turn_number,
            "n_clusters": len(snapshots),
            "n_candidates": len(kept_ids),
        },
    )
    return snapshots


def _build_fallback_cluster(
    *,
    kept_ids: list[int],
    embeddings: np.ndarray,
    meta_by_id: dict,
    reformulated_query: str,
) -> list[ClusterSnapshot]:
    """Return a single cluster spanning all candidates (all-noise fallback)."""
    assignments = [
        ClusterAssignment(movie_id=mid, score=1.0 / len(kept_ids), excluded=False)
        for mid in kept_ids
    ]
    name = reformulated_query[:50] if len(reformulated_query) > 50 else reformulated_query
    return [
        ClusterSnapshot(
            id=uuid4(),
            name=name,
            description="Fallback: all retrieved candidates grouped into one cluster.",
            level=0,
            parent_cluster_id=None,
            assignments=assignments,
        )
    ]
