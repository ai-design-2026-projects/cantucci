import logging
import uuid

from backend.agents.clustering.operations.drill_down import drill_down
from backend.agents.clustering.types import ClusterSnapshotDraft, MetadataFilter, Modality
from backend.agents.concept.types import ConceptRep
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
from backend.data_access.movies.queries import filter_movie_ids_by_metadata

log = logging.getLogger(__name__)


async def cross_filter(
    parent_cluster_snapshot_id: uuid.UUID,
    metadata_filter: MetadataFilter,
    concept: ConceptRep | None = None,
    embedding_spaces: list[Modality] | None = None,
) -> ClusterSnapshotDraft:
    """
    Filter the current snapshot's movies by metadata then re-cluster the survivors.

    Collects all movie IDs across every cluster in the parent snapshot, applies the
    metadata predicate via SQL (genres / year range / director), and re-clusters the
    matching subset using HDBSCAN.
    Args:
        parent_cluster_snapshot_id: Snapshot whose member movies form the input universe.
        metadata_filter:            Predicate to apply (all non-null fields combined with AND).
        concept:                    Optional semantic concept to sort survivors before clustering.
        embedding_spaces:           Embedding modalities to fuse. Defaults to ``[Modality.TEXT]``.
    Returns:
        ``ClusterSnapshotDraft`` with operation ``"cross_filter"``.
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

    # Apply the metadata filter via SQL to get the subset of movie IDs to re-cluster
    filtered_ids = filter_movie_ids_by_metadata(
        movie_ids=all_movie_ids,
        genres=metadata_filter.genres,
        release_year_min=metadata_filter.release_year_min,
        release_year_max=metadata_filter.release_year_max,
        director=metadata_filter.director,
    )

    if not filtered_ids:
        raise ValueError("No movies matched the metadata filter; cannot re-cluster an empty set")

    log.info(
        "cross_filter_subset",
        extra={
            "parent_snapshot_id": str(parent_cluster_snapshot_id),
            "input_movies": len(all_movie_ids),
            "filtered_movies": len(filtered_ids),
        },
    )

    extra_params: dict = {
        "genres": metadata_filter.genres,
        "release_year_min": metadata_filter.release_year_min,
        "release_year_max": metadata_filter.release_year_max,
        "director": metadata_filter.director,
    }

    base_draft = await drill_down(
        source_cluster_id=None,
        movie_ids=filtered_ids,
        concept=concept,
        parent_cluster_snapshot_id=parent_cluster_snapshot_id,
        embedding_spaces=embedding_spaces,
    )
    return base_draft.with_operation("cross_filter", extra_params)
