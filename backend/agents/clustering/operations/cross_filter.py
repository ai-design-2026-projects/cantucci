import logging
import uuid

from backend.agents.clustering.operations.drill_down import concept_drill_down, free_drill_down
from backend.agents.clustering.types import ClusterSnapshotDraft, MetadataFilter, Modality
from backend.agents.concept.types import ConceptRep
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
from backend.data_access.movies.queries import filter_movie_ids_by_metadata
from backend.settings import get_settings

log = logging.getLogger(__name__)


async def cross_filter(
    parent_cluster_snapshot_id: uuid.UUID,
    metadata_filter: MetadataFilter,
) -> ClusterSnapshotDraft:
    """
    Filter the current snapshot's movies by metadata.

    Collects all movie IDs across every cluster in the parent snapshot, applies the
    metadata predicate via SQL (genres / year range / director), and returns a snapshot
    containing the surviving movies as a single flat cluster. No clustering is performed;
    use a follow-up ``drill_down`` to cluster the filtered set.

    Args:
        parent_cluster_snapshot_id: Snapshot whose member movies form the input universe.
        metadata_filter:            Predicate to apply (all non-null fields combined with AND).
    Returns:
        ``ClusterSnapshotDraft`` with operation ``"cross_filter"`` containing a single cluster.
    Raises:
        ValueError: If the parent snapshot is not found or no movies survive the filter.
    """
    cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
    if cswc is None:
        raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")

    # Aggregate all movie IDs across every cluster in the parent snapshot, deduplicating as we go
    seen: set[int] = set()
    all_movie_ids: list[int] = []
    for cluster in cswc.clusters:
        for m in get_memberships(cluster.id):
            if m.movie_id not in seen:
                seen.add(m.movie_id)
                all_movie_ids.append(m.movie_id)

    # Apply the metadata filter via SQL to get the surviving movie IDs
    filtered_ids = filter_movie_ids_by_metadata(
        movie_ids=all_movie_ids,
        genres=metadata_filter.genres,
        release_year_min=metadata_filter.release_year_min,
        release_year_max=metadata_filter.release_year_max,
        director=metadata_filter.director,
    )

    if not filtered_ids:
        raise ValueError("No movies matched the metadata filter")

    log.info(
        "cross_filter_subset",
        extra={
            "parent_snapshot_id": str(parent_cluster_snapshot_id),
            "input_movies": len(all_movie_ids),
            "filtered_movies": len(filtered_ids),
        },
    )

    cfg = get_settings()
    cluster = ClusterDraft(
        label=None,
        summary=None,
        exemplar_movie_ids=exemplars(filtered_ids, [1.0] * len(filtered_ids), cfg.labeling.top_exemplars),
        parent_cluster_id=None,
        memberships=[(mid, 1.0) for mid in filtered_ids],
    )

    params: dict = {
        "genres": metadata_filter.genres,
        "release_year_min": metadata_filter.release_year_min,
        "release_year_max": metadata_filter.release_year_max,
        "director": metadata_filter.director,
    }

    if concept is not None:
        base_draft = await concept_drill_down(
            source_cluster_id=None,
            movie_ids=filtered_ids,
            concept=concept,
            parent_cluster_snapshot_id=parent_cluster_snapshot_id,
            embedding_spaces=embedding_spaces,
        )
    else:
        base_draft = await free_drill_down(
            source_cluster_id=None,
            movie_ids=filtered_ids,
            parent_cluster_snapshot_id=parent_cluster_snapshot_id,
            embedding_spaces=embedding_spaces,
        )
    return base_draft.with_operation("cross_filter", extra_params)
