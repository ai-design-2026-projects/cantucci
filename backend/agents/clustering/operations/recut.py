import logging
import uuid

import numpy as np

from backend.agents.clustering.operations._helpers import _LABEL_PLACEHOLDER, exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.concept.agent import score_movies
from backend.agents.concept.types import ConceptRep
from backend.agents.clustering.operations.subcluster import subcluster
from backend.data_access.movies.queries import fetch_fused_embeddings
from backend.settings import get_settings

log = logging.getLogger(__name__)


async def recut(
    movie_ids: list[int],
    parent_cluster_snapshot_id: uuid.UUID,
    concept: ConceptRep | None = None,
) -> ClusterSnapshotDraft:
    """Re-cluster a set of movies from scratch using HDBSCAN.

    Args:
        movie_ids:                  TMDB IDs to recluster (typically the full catalogue or a filter).
        parent_cluster_snapshot_id: Cluster snapshot being replaced.
        concept:                    Optional concept to sort movies before clustering.

    Returns:
        ``ClusterSnapshotDraft`` with freshly computed clusters.
    """
    cfg = get_settings()
    emb_map = fetch_fused_embeddings(movie_ids)
    available_ids = [mid for mid in movie_ids if mid in emb_map]
    if not available_ids:
        raise ValueError("No embeddings available for recut")

    if concept is not None:
        concept_scores = score_movies(concept, available_ids, emb_map)
        available_ids = sorted(available_ids, key=lambda m: concept_scores.get(m, 0), reverse=True)

    vecs = np.array([emb_map[mid] for mid in available_ids], dtype=np.float32)
    result = subcluster(vecs, cfg.clustering.online.recut_min_cluster_size, cfg.clustering.base.min_samples)

    clusters: list[ClusterDraft] = []
    for ci in range(result.n_clusters):
        col = result.probabilities[:, ci]
        members = [(available_ids[i], float(col[i])) for i in range(len(available_ids)) if col[i] > 0]
        mids = [m[0] for m in members]
        prbs = [m[1] for m in members]
        clusters.append(ClusterDraft(
            label=f"{_LABEL_PLACEHOLDER} {ci + 1}",
            summary=None,
            exemplar_movie_ids=exemplars(mids, prbs),
            parent_cluster_id=None,
            memberships=members,
        ))

    params: dict = {
        "operation": "recut",
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
        "n_movies": len(available_ids),
        "n_clusters": len(clusters),
        "concept": concept.concept_name if concept else None,
    }
    log.info("recut_complete", extra={"n_movies": len(available_ids), "n_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="recut", params=params, clusters=clusters)
