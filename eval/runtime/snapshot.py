"""Shared cluster-info builder used by both the session runner and the judge."""
import logging
import uuid

from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.movies.queries import fetch_stubs

log = logging.getLogger(__name__)


def build_cluster_info(snapshot_id: uuid.UUID, exemplar_k: int) -> list[dict]:
    """Build the cluster description list for oracle and judge prompts.

    Fetches the snapshot's clusters and resolves the top-``exemplar_k`` exemplar
    movie stubs (title + release year) for each cluster.

    Args:
        snapshot_id: UUID of the cluster snapshot to describe.
        exemplar_k:  Maximum number of exemplar titles to include per cluster.

    Returns:
        List of dicts with keys ``label``, ``summary``, and ``exemplar_titles``
        (a list of ``"Title (year)"`` strings). Empty list when the snapshot is not found.
    """
    snapshot = get_cluster_snapshot_with_clusters(snapshot_id)
    if snapshot is None:
        return []
    result = []
    for cluster in snapshot.clusters:
        stubs = fetch_stubs(cluster.exemplar_movie_ids[:exemplar_k]) if cluster.exemplar_movie_ids else []
        exemplar_titles = [f"{s.title} ({s.release_year or '?'})" for s in stubs]
        result.append({
            "label": cluster.label,
            "summary": cluster.summary,
            "exemplar_titles": exemplar_titles,
        })
    log.debug(
        "cluster_info_built",
        extra={"snapshot_id": str(snapshot_id), "n_clusters": len(result)},
    )
    return result
