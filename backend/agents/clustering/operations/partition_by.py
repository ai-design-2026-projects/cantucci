import logging
import uuid

from backend.agents.clustering.operations._helpers import exemplars
from backend.agents.clustering.types import ClusterDraft, ClusterSnapshotDraft, PartitionAttribute, PartitionSpec

_CATEGORICAL = {PartitionAttribute.GENRE, PartitionAttribute.DIRECTOR, PartitionAttribute.ORIGINAL_LANGUAGE}
from backend.data_access.cluster_snapshots.queries import get_memberships
from backend.data_access.movies.queries import fetch_partition_values, list_movie_ids
from backend.settings import get_settings

log = logging.getLogger(__name__)

_UNSPECIFIED_LABEL = "Unspecified"


async def partition_by(
    spec: PartitionSpec,
    parent_cluster_snapshot_id: uuid.UUID | None,
    source_cluster_id: uuid.UUID | None = None,
    movie_ids: list[int] | None = None,
) -> ClusterSnapshotDraft:
    """
    Deterministically group a movie set into clusters by a metadata attribute.

    No embeddings, HDBSCAN, or LLM labeling — cluster labels and summaries are
    derived directly from attribute values.  Memberships use probability 1.0.

    We can distinguish between categorical and numeric attributes:
    - For categorical attributes (``GENRE``, ``DIRECTOR``) each distinct value
    becomes its own cluster; a movie may appear in multiple clusters when it has
    multiple values.  
    - For numeric attributes (``RUNTIME``, ``RELEASE_YEAR``) the
    LLM-supplied bins are applied and each movie lands in exactly one bin.
    
    Movies with no attribute value (null runtime, no genre, etc.) are collected
    into an explicit ``"Unspecified"`` cluster rather than being silently dropped.

    Args:
        spec:                       Attribute and optional bins for the partition.
        parent_cluster_snapshot_id: Snapshot that owns the source cluster (may be
                                    ``None`` when operating from the unclustered
                                    state).
        source_cluster_id:          Cluster whose members form the input universe;
                                    ``None`` to use the full catalogue or *movie_ids*.
        movie_ids:                  Explicit movie ID list; only used when
                                    ``source_cluster_id`` is ``None``.

    Returns:
        ``ClusterSnapshotDraft`` with operation ``"partition_by"``.

    Raises:
        ValueError: If the resolved movie set is empty or produces no clusters.
    """
    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    if source_cluster_id is not None:
        memberships = get_memberships(source_cluster_id)
        if not memberships:
            raise ValueError(f"Cluster {source_cluster_id} has no members")
        resolved_ids = [m.movie_id for m in memberships]
    else:
        resolved_ids = movie_ids if movie_ids is not None else list_movie_ids()
        if not resolved_ids:
            raise ValueError("No movies found for partition_by")

    attribute = spec.attribute.value
    raw = fetch_partition_values(resolved_ids, attribute)

    if spec.attribute in _CATEGORICAL:
        buckets: dict[str, list[int]] = {}
        unspecified: list[int] = []

        for mid in resolved_ids:
            values = raw.get(mid, [])
            if not values:
                unspecified.append(mid)
            else:
                for v in values:  # type: ignore[union-attr]
                    buckets.setdefault(v, []).append(mid)

        sorted_keys = sorted(buckets.keys())
        clusters: list[ClusterDraft] = []
        for key in sorted_keys:
            mids = buckets[key]
            clusters.append(ClusterDraft(
                label=key,
                summary=f"Movies grouped by {attribute}: {key}.",
                exemplar_movie_ids=exemplars(mids, [1.0] * len(mids), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in mids],
            ))
        if unspecified:
            clusters.append(ClusterDraft(
                label=_UNSPECIFIED_LABEL,
                summary=f"Movies with no {attribute} listed.",
                exemplar_movie_ids=exemplars(unspecified, [1.0] * len(unspecified), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in unspecified],
            ))

    else:
        if not spec.bins:
            raise ValueError(f"partition_by requires bins for numeric attribute {attribute!r}")

        bin_buckets: dict[str, list[int]] = {b.label: [] for b in spec.bins}
        num_unspecified: list[int] = []

        for mid in resolved_ids:
            value = raw.get(mid)
            if value is None:
                num_unspecified.append(mid)
                continue
            matched = False
            for b in spec.bins:
                lo_ok = b.min is None or float(value) >= b.min  # type: ignore[arg-type]
                hi_ok = b.max is None or float(value) < b.max  # type: ignore[arg-type]
                if lo_ok and hi_ok:
                    bin_buckets[b.label].append(mid)
                    matched = True
                    break
            if not matched:
                num_unspecified.append(mid)

        clusters = []
        for b in spec.bins:
            mids = bin_buckets[b.label]
            if not mids:
                continue
            clusters.append(ClusterDraft(
                label=b.label,
                summary=f"Movies grouped by {attribute}: {b.label}.",
                exemplar_movie_ids=exemplars(mids, [1.0] * len(mids), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in mids],
            ))
        if num_unspecified:
            clusters.append(ClusterDraft(
                label=_UNSPECIFIED_LABEL,
                summary=f"Movies with no {attribute} value or outside all specified bins.",
                exemplar_movie_ids=exemplars(num_unspecified, [1.0] * len(num_unspecified), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in num_unspecified],
            ))

    if not clusters:
        raise ValueError(f"partition_by produced no clusters for attribute {attribute!r}")

    params: dict = {
        "operation": "partition_by",
        "attribute": attribute,
        "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
        "parent_cluster_snapshot_id": str(parent_cluster_snapshot_id) if parent_cluster_snapshot_id else None,
        "bins": [
            {"label": b.label, "min": b.min, "max": b.max}
            for b in (spec.bins or [])
        ],
    }

    log.info(
        "partition_by_complete",
        extra={
            "attribute": attribute,
            "source_cluster_id": str(source_cluster_id) if source_cluster_id else None,
            "n_clusters": len(clusters),
        },
    )
    return ClusterSnapshotDraft(operation="partition_by", params=params, clusters=clusters)
