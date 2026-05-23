import logging
import uuid
import numpy as np

from backend.agents.clustering.operations._helpers import _LABEL_PLACEHOLDER, exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.concept.agent import score_movies
from backend.agents.concept.types import ConceptRep
from backend.agents.clustering.operations.subcluster import subcluster
from backend.data_access.cluster_snapshots.queries import get_memberships
from backend.data_access.movies.queries import fetch_text_embeddings, fetch_modality_embeddings
from backend.settings import get_settings
from core.fusion import combined_distance_matrix

log = logging.getLogger(__name__)


async def drill_down(
    source_cluster_id: uuid.UUID,
    concept: ConceptRep | None,
    parent_cluster_snapshot_id: uuid.UUID,
    modalities: list[str] | None = None,
) -> ClusterSnapshotDraft:
    """Sub-cluster the movies in one cluster, optionally concept-sorted.

    If a concept is supplied, movies are first sorted by concept score
    and split at the median before re-clustering each half.
    Otherwise, HDBSCAN is run directly on the cluster's movies.

    The default modality is ``["text"]`` (BGE text_embedding). Pass multiple
    modalities (e.g. ``["text", "trailer"]``) to cluster using a combined
    distance matrix across the specified embedding spaces.  Only movies that
    have a non-null embedding for every requested modality are included.

    Args:
        source_cluster_id:          Cluster to split.
        concept:                    Optional concept to guide the split.
        parent_cluster_snapshot_id: Cluster snapshot the source cluster belongs to.
        modalities:                 Embedding spaces to use. Defaults to ``["text"]``.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.
    """
    if modalities is None:
        modalities = ["text"]

    cfg = get_settings()
    memberships = get_memberships(source_cluster_id)
    if not memberships:
        raise ValueError(f"Cluster {source_cluster_id} has no members")

    movie_ids = [m.movie_id for m in memberships]

    if len(modalities) == 1 and modalities[0] == "text":
        emb_map = fetch_text_embeddings(movie_ids)
        available_ids = [mid for mid in movie_ids if mid in emb_map]
        multi_modal = False
    else:
        modal_data = fetch_modality_embeddings(movie_ids, modalities)
        available_ids = [
            mid for mid in movie_ids
            if all(mid in modal_data[m] for m in modalities)
        ]
        multi_modal = True
        emb_map = {mid: modal_data["text"][mid].tolist() for mid in available_ids if "text" in modal_data}

    if not available_ids:
        raise ValueError(f"No embeddings found for cluster {source_cluster_id}")

    params: dict = {
        "operation": "drill_down",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
        "concept": concept.concept_name if concept else None,
        "modalities": modalities,
    }

    def _cluster_group(group_ids: list[int]) -> "SoftClusterResult":  # type: ignore[name-defined]
        if multi_modal:
            embs_by_modality = {
                m: np.array([modal_data[m][mid] for mid in group_ids], dtype=np.float32)
                for m in modalities
            }
            runtime_weights = cfg.fusion.runtime_weights
            dist_mat = combined_distance_matrix(embs_by_modality, runtime_weights)
            return subcluster(None, cfg.clustering.online.drilldown_min_cluster_size, 1, distance_matrix=dist_mat)
        else:
            group_embs = np.array([emb_map[mid] for mid in group_ids], dtype=np.float32)
            return subcluster(group_embs, cfg.clustering.online.drilldown_min_cluster_size, 1)

    if concept is not None:
        concept_scores = score_movies(concept, available_ids, emb_map)
        median_score = float(np.median(list(concept_scores.values())))
        high_ids = [mid for mid in available_ids if concept_scores.get(mid, 0) >= median_score]
        low_ids = [mid for mid in available_ids if concept_scores.get(mid, 0) < median_score]

        clusters: list[ClusterDraft] = []
        for group_ids, label_suffix in [(high_ids, f"High {concept.concept_name}"), (low_ids, f"Low {concept.concept_name}")]:
            if len(group_ids) < 2:
                continue
            result = _cluster_group(group_ids)
            for ci in range(result.n_clusters):
                col = result.probabilities[:, ci]
                members = [(group_ids[i], float(col[i])) for i in range(len(group_ids)) if col[i] > 0]
                mids = [m[0] for m in members]
                prbs = [m[1] for m in members]
                clusters.append(ClusterDraft(
                    label=f"{label_suffix} {ci + 1}",
                    summary=None,
                    exemplar_movie_ids=exemplars(mids, prbs),
                    parent_cluster_id=source_cluster_id,
                    memberships=members,
                ))
    else:
        result = _cluster_group(available_ids)
        clusters = []
        for ci in range(result.n_clusters):
            col = result.probabilities[:, ci]
            members = [(available_ids[i], float(col[i])) for i in range(len(available_ids)) if col[i] > 0]
            mids = [m[0] for m in members]
            prbs = [m[1] for m in members]
            clusters.append(ClusterDraft(
                label=f"{_LABEL_PLACEHOLDER} {ci + 1}",
                summary=None,
                exemplar_movie_ids=exemplars(mids, prbs),
                parent_cluster_id=source_cluster_id,
                memberships=members,
            ))

    params["n_clusters"] = len(clusters)
    log.info("drill_down_complete", extra={"source_cluster_id": str(source_cluster_id), "n_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="drill_down", params=params, clusters=clusters)
