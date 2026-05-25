import logging
import uuid
import numpy as np

from backend.agents.clustering.operations._helpers import exemplars, reduce_for_clustering, subcluster
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.concept.scoring import score_movies
from backend.agents.concept.types import ConceptRep
from backend.agents.clustering.types import Modality
from backend.data_access.cluster_snapshots.queries import get_memberships
from backend.data_access.movies.queries import fetch_text_embeddings, fetch_modality_embeddings
from backend.settings import get_settings
from core.fusion import combined_distance_matrix

log = logging.getLogger(__name__)

_LABEL_PLACEHOLDER = "Cluster"


async def drill_down(
    source_cluster_id: uuid.UUID,
    concept: ConceptRep | None,
    parent_cluster_snapshot_id: uuid.UUID,
    embedding_spaces: list[Modality] | None = None,
) -> ClusterSnapshotDraft:
    """
    Sub-cluster the movies in one cluster, optionally concept-sorted.

    If a concept is supplied, movies are first sorted by concept score
    and split at the median before re-clustering each half.
    Otherwise, HDBSCAN is run directly on the cluster's movies.

    Args:
        source_cluster_id:          Cluster to split.
        concept:                    Optional concept to guide the split.
        parent_cluster_snapshot_id: Cluster snapshot the source cluster belongs to.
        embedding_spaces:           Embedding spaces to fuse. Defaults to ``[Modality.TEXT]``.

    Returns:
        ``ClusterSnapshotDraft`` ready to be persisted.
    """
    # If no embedding spaces were specified, default to using the text embeddings
    if embedding_spaces is None:
        embedding_spaces = [Modality.TEXT]

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars
    memberships = get_memberships(source_cluster_id)
    if not memberships:
        raise ValueError(f"Cluster {source_cluster_id} has no members")

    movie_ids = [m.movie_id for m in memberships]

    # Determine the embedding map based on the specified embedding spaces
    if len(embedding_spaces) == 1 and embedding_spaces[0] == Modality.TEXT:
        emb_map = fetch_text_embeddings(movie_ids)
        available_ids = [movie_id for movie_id in movie_ids if movie_id in emb_map]
        multi_modal = False
    else:
        space_keys = [s.value for s in embedding_spaces]
        # Fetch embeddings for all specified modalities in one go
        modal_data = fetch_modality_embeddings(movie_ids, space_keys)
        
        # Only keep movies that have embeddings in all the specified modalities
        available_ids = [
            movie_id for movie_id in movie_ids
            if all(movie_id in modal_data[m] for m in space_keys)
        ]
        multi_modal = True
        emb_map = {movie_id: modal_data["text"][movie_id].tolist() for movie_id in available_ids if "text" in modal_data}

    if not available_ids:
        raise ValueError(f"No embeddings found for cluster {source_cluster_id}")

    params: dict = {
        "operation": "drill_down",
        "source_cluster_id": str(source_cluster_id),
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id),
        "concept": concept.concept_name if concept else None,
        "embedding_spaces": [s.value for s in embedding_spaces],
    }

    def _cluster_group(group_ids: list[int]) -> "SoftClusterResult":  # type: ignore[name-defined]
        """Cluster the given group of movie IDs, using either single-modality or multi-modal embeddings as appropriate."""
        if multi_modal:
            # Map each modality to its embedding matrix for the movies in this group
            embs_by_modality = {
                space.value: np.array([modal_data[space.value][movie_id] for movie_id in group_ids], dtype=np.float32)
                for space in embedding_spaces
            }
            # Compute a combined distance matrix across modalities and feed it to HDBSCAN for clustering
            runtime_weights = cfg.fusion.runtime_weights
            dist_mat = combined_distance_matrix(embs_by_modality, runtime_weights)
            # Run HDBSCAN directly on the precomputed distance matrix, since we don't have a single embedding space to reduce to
            return subcluster(None, cfg.clustering.online.drilldown_min_cluster_size, 1, distance_matrix=dist_mat)
        else:
            group_embs = np.array([emb_map[movie_id] for movie_id in group_ids], dtype=np.float32)
            group_embs = reduce_for_clustering(group_embs, cfg.umap, cfg.split.seed)
            return subcluster(group_embs, cfg.clustering.online.drilldown_min_cluster_size, 1)

    if concept is not None:
        concept_scores = score_movies(concept, available_ids, emb_map)
        median_score = float(np.median(list(concept_scores.values())))
        high_ids = [movie_id for movie_id in available_ids if concept_scores.get(movie_id, 0) >= median_score]
        low_ids = [movie_id for movie_id in available_ids if concept_scores.get(movie_id, 0) < median_score]

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
                    exemplar_movie_ids=exemplars(mids, prbs, top_n),
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
                exemplar_movie_ids=exemplars(mids, prbs, top_n),
                parent_cluster_id=source_cluster_id,
                memberships=members,
            ))

    params["n_clusters"] = len(clusters)
    log.info("drill_down_complete", extra={"source_cluster_id": str(source_cluster_id), "n_clusters": len(clusters)})
    return ClusterSnapshotDraft(operation="drill_down", params=params, clusters=clusters)
