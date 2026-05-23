import logging
import uuid

import numpy as np

from backend.agents.clustering.operations._helpers import exemplars, reduce_for_clustering
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.concept.scoring import score_movies
from backend.agents.concept.types import ConceptRep
from backend.agents.clustering.operations.subcluster import subcluster
from backend.agents.intent.types import Modality
from backend.data_access.movies.queries import fetch_text_embeddings, fetch_modality_embeddings
from backend.settings import get_settings
from core.fusion import combined_distance_matrix

log = logging.getLogger(__name__)

_LABEL_PLACEHOLDER = "Cluster"


async def recut(
    movie_ids: list[int],
    parent_cluster_snapshot_id: uuid.UUID,
    concept: ConceptRep | None = None,
    embedding_spaces: list[Modality] | None = None,
) -> ClusterSnapshotDraft:
    """Re-cluster a set of movies from scratch using HDBSCAN.

    The default embedding space is ``[Modality.TEXT]`` (BGE text embedding). Pass
    multiple spaces (e.g. ``[Modality.TEXT, Modality.TRAILER]``) to cluster using
    a combined distance matrix. Only movies with a non-null embedding for every
    requested space are included.

    Args:
        movie_ids:                  TMDB IDs to recluster (typically the full catalogue or a filter).
        parent_cluster_snapshot_id: Cluster snapshot being replaced.
        concept:                    Optional concept to sort movies before clustering.
        embedding_spaces:           Embedding spaces to fuse. Defaults to ``[Modality.TEXT]``.

    Returns:
        ``ClusterSnapshotDraft`` with freshly computed clusters.
    """
    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars
    space_keys = [s.value for s in embedding_spaces]

    if len(embedding_spaces) == 1 and embedding_spaces[0] == Modality.TEXT:
        emb_map = fetch_text_embeddings(movie_ids)
        available_ids = [mid for mid in movie_ids if mid in emb_map]
        multi_modal = False
        modal_data: dict = {}
    else:
        modal_data = fetch_modality_embeddings(movie_ids, space_keys)
        available_ids = [
            mid for mid in movie_ids
            if all(mid in modal_data[m] for m in space_keys)
        ]
        multi_modal = True
        emb_map = {mid: modal_data["text"][mid].tolist() for mid in available_ids if "text" in modal_data}

    if not available_ids:
        raise ValueError("No embeddings available for recut")

    if concept is not None:
        concept_scores = score_movies(concept, available_ids, emb_map)
        available_ids = sorted(available_ids, key=lambda m: concept_scores.get(m, 0), reverse=True)

    if multi_modal:
        embs_by_modality = {
            key: np.array([modal_data[key][mid] for mid in available_ids], dtype=np.float32)
            for key in space_keys
        }
        runtime_weights = cfg.fusion.runtime_weights
        dist_mat = combined_distance_matrix(embs_by_modality, runtime_weights)
        result = subcluster(
            None,
            cfg.clustering.online.recut_min_cluster_size,
            cfg.clustering.base.min_samples,
            distance_matrix=dist_mat,
        )
    else:
        vecs = np.array([emb_map[mid] for mid in available_ids], dtype=np.float32)
        vecs = reduce_for_clustering(vecs, cfg.umap, cfg.split.seed)
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
            exemplar_movie_ids=exemplars(mids, prbs, top_n),
            parent_cluster_id=None,
            memberships=members,
        ))

    params: dict = {
        "operation": "recut",
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
        "n_movies": len(available_ids),
        "n_clusters": len(clusters),
        "concept": concept.concept_name if concept else None,
        "embedding_spaces": space_keys,
    }
    log.info("recut_complete", extra={"n_movies": len(available_ids), "n_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="recut", params=params, clusters=clusters)
