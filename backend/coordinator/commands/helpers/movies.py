from __future__ import annotations

import uuid

import logging

log = logging.getLogger(__name__)


def resolve_movie_ids(
    source_cluster_id: uuid.UUID | None,
    movie_ids: list[int] | None,
    parent_cluster_snapshot_id: uuid.UUID | None,
) -> list[int]:
    """Resolve the input movie set for a clustering operation.

    Resolution order:
    1. ``source_cluster_id`` → members of that cluster.
    2. ``movie_ids`` → explicit list.
    3. ``parent_cluster_snapshot_id`` → union of all movies across that snapshot's clusters.
    4. No arguments → full catalogue.

    Args:
        source_cluster_id:          Cluster whose members form the input; takes priority.
        movie_ids:                  Explicit list; used when ``source_cluster_id`` is ``None``.
        parent_cluster_snapshot_id: Snapshot from which to union all movies; used when
                                    both ``source_cluster_id`` and ``movie_ids`` are ``None``.

    Returns:
        List of TMDB movie IDs in the resolved input set.

    Raises:
        ValueError: If ``source_cluster_id`` is set but has no members, or the referenced
                    snapshot is not found.
    """
    from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters, get_memberships
    from backend.data_access.movies.queries import list_movie_ids

    if source_cluster_id is not None:
        memberships = get_memberships(source_cluster_id)
        if not memberships:
            raise ValueError(f"Cluster {source_cluster_id} has no members")
        return [m.movie_id for m in memberships]
    if movie_ids is not None:
        return movie_ids
    if parent_cluster_snapshot_id is not None:
        cswc = get_cluster_snapshot_with_clusters(parent_cluster_snapshot_id)
        if cswc is None:
            raise ValueError(f"Cluster snapshot {parent_cluster_snapshot_id} not found")
        seen: set[int] = set()
        result: list[int] = []
        for cluster in cswc.clusters:
            for m in get_memberships(cluster.id):
                if m.movie_id not in seen:
                    seen.add(m.movie_id)
                    result.append(m.movie_id)
        return result
    return list_movie_ids()
