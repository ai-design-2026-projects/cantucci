import logging
import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands._helpers import _NUMERIC_ATTRIBUTES, _persist_draft
from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.coordinator.tools.clarification_state import mark_awaiting
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft
from backend.agents.intent.types import PartitionAttribute, PartitionSpec
from backend.agents.responder import replies
from backend.data_access.movies.queries import fetch_numeric_stats, fetch_partition_values
from backend.settings import get_settings

_CATEGORICAL = {PartitionAttribute.GENRE, PartitionAttribute.DIRECTOR, PartitionAttribute.ORIGINAL_LANGUAGE}

log = logging.getLogger(__name__)

_UNSPECIFIED_LABEL = "Unspecified"


@dataclass(frozen=True, slots=True)
class PartitionByCommand:
    """Group movies into deterministic buckets by a metadata attribute.

    Attributes:
        target_cluster_id: Cluster to partition; None = full set or unclustered state.
        partition_spec:    Attribute and optional bins for the partition.
        confidence:        LLM confidence [0, 1].
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    partition_spec: PartitionSpec | None
    confidence: float

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Partition movies by attribute into deterministic buckets.

        When the attribute is numeric and no bins are supplied, proposes default bins
        and waits for user confirmation before executing.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        from backend.coordinator.commands._clustering import propose_bins

        if self.partition_spec is None:
            return ActionResult(
                reply_fragment=replies.UNSUPPORTED_OPERATION,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        spec = self.partition_spec

        if self.target_cluster_id is None and ctx.clusters:
            mark_awaiting(
                ctx.conversation_id,
                pending_spec=PartitionSpec(attribute=spec.attribute, bins=None),
            )
            return ActionResult(
                reply_fragment=replies.format_partition_clarification(
                    spec.attribute.value, [c.label for c in ctx.clusters]
                ),
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        if spec.attribute in _NUMERIC_ATTRIBUTES and not spec.bins:
            return self._propose_numeric_bins(ctx, spec, propose_bins)

        ctx.reporter.step("clustering")
        draft = await partition_by(
            spec=spec,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            source_cluster_id=self.target_cluster_id,
        )
        new_snapshot_id, step_cost, n_movies, _ = await _persist_draft(ctx, draft)
        n_new = len(draft.clusters)
        reply = replies.format_partition_reply(spec.attribute.value, n_new, n_movies)
        if draft.warning:
            reply = f"{reply}\n\n⚠ {draft.warning}"
        return ActionResult(
            reply_fragment=reply,
            cluster_snapshot_id=new_snapshot_id,
            step_cost=step_cost,
        )

    def _propose_numeric_bins(self, ctx: ExecutionContext, spec: PartitionSpec, propose_bins_fn) -> ActionResult:
        """Propose default bins to the user when a numeric partition_by has no bins specified.

        Args:
            ctx:              Execution context.
            spec:             Partition spec with numeric attribute and no bins.
            propose_bins_fn:  The propose_bins function (injected to avoid circular import).

        Returns:
            ActionResult with proposal text and unchanged snapshot id.
        """
        from backend.coordinator.commands._clustering import resolve_movie_ids

        ctx.reporter.step("clustering")

        resolved_ids = resolve_movie_ids(
            source_cluster_id=self.target_cluster_id,
            movie_ids=None,
            parent_cluster_snapshot_id=ctx.current_cluster_snapshot_id,
        )
        if not resolved_ids:
            return ActionResult(
                reply_fragment=replies.UNSUPPORTED_OPERATION,
                cluster_snapshot_id=ctx.current_cluster_snapshot_id,
                step_cost=0.0,
            )

        stats = fetch_numeric_stats(resolved_ids, spec.attribute.value)
        bins = propose_bins_fn(attribute=spec.attribute.value, stats=stats)

        raw_values = fetch_partition_values(resolved_ids, spec.attribute.value)
        bin_counts: dict[str, int] = {b.label: 0 for b in bins}
        unspecified = 0
        for mid in resolved_ids:
            value = raw_values.get(mid)
            if value is None:
                unspecified += 1
                continue
            matched = False
            for b in bins:
                lo_ok = b.min is None or float(value) >= b.min  # type: ignore[arg-type]
                hi_ok = b.max is None or float(value) < b.max  # type: ignore[arg-type]
                if lo_ok and hi_ok:
                    bin_counts[b.label] += 1
                    matched = True
                    break
            if not matched:
                unspecified += 1

        proposal_text = replies.format_bin_proposal(spec.attribute.value, bins, bin_counts, unspecified)
        confirmed_spec = PartitionSpec(attribute=spec.attribute, bins=bins)
        mark_awaiting(ctx.conversation_id, pending_spec=confirmed_spec)
        return ActionResult(
            reply_fragment=proposal_text,
            cluster_snapshot_id=ctx.current_cluster_snapshot_id,
            step_cost=0.0,
        )


async def partition_by(
    spec: PartitionSpec,
    parent_cluster_snapshot_id: uuid.UUID | None,
    source_cluster_id: uuid.UUID | None = None,
    movie_ids: list[int] | None = None,
) -> ClusterSnapshotDraft:
    """
    Deterministically group a movie set into clusters by a metadata attribute.

    No embeddings or HDBSCAN — memberships are determined directly from attribute
    values with probability 1.0.  Labels and summaries are generated by the LLM
    labeler via ``persist_and_label``; the ``"Unspecified"`` catch-all bucket keeps
    its deterministic text since the LLM cannot meaningfully theme a null-value set.

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
                                    ``None`` falls through to *movie_ids*, then to the
                                    parent snapshot's union of movies, then to the full
                                    catalogue.
        movie_ids:                  Explicit movie ID list; only used when
                                    ``source_cluster_id`` is ``None``.

    Returns:
        ``ClusterSnapshotDraft`` with operation ``"partition_by"``.

    Raises:
        ValueError: If the resolved movie set is empty or produces no clusters.
    """
    from backend.coordinator.commands._clustering import exemplars, resolve_movie_ids

    cfg = get_settings()
    top_n = cfg.labeling.top_exemplars

    resolved_ids = resolve_movie_ids(source_cluster_id, movie_ids, parent_cluster_snapshot_id)

    if not resolved_ids:
        raise ValueError("No movies found for partition_by")

    attribute = spec.attribute.value
    raw = fetch_partition_values(resolved_ids, attribute)

    warning: str | None = None

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

        top_n_cat = cfg.clustering.partition_by.categorical_top_n
        sorted_items = sorted(buckets.items(), key=lambda x: len(x[1]), reverse=True)
        truncated = len(sorted_items) > top_n_cat
        if truncated:
            attr_label_for_warning = attribute.replace("_", " ")
            warning = (
                f"Only the top {top_n_cat} of {len(sorted_items)} {attr_label_for_warning} "
                f"groups are shown; the rest are combined into 'Other {attr_label_for_warning}'."
            )
            other_mids = list(dict.fromkeys(mid for _, mids in sorted_items[top_n_cat:] for mid in mids))
            top_items = sorted(sorted_items[:top_n_cat], key=lambda x: x[0])
        else:
            other_mids = []
            top_items = sorted(sorted_items, key=lambda x: x[0])

        clusters: list[ClusterDraft] = []
        for key, mids in top_items:
            clusters.append(ClusterDraft(
                label=key,
                summary=None,
                exemplar_movie_ids=exemplars(mids, [1.0] * len(mids), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in mids],
            ))
        if other_mids:
            attr_label = attribute.replace("_", " ")
            clusters.append(ClusterDraft(
                label=f"Other {attr_label}",
                summary=f"Movies not in the top {top_n_cat} {attr_label} groups.",
                exemplar_movie_ids=exemplars(other_mids, [1.0] * len(other_mids), top_n),
                parent_cluster_id=source_cluster_id,
                memberships=[(mid, 1.0) for mid in other_mids],
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
                summary=None,
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
        "concept": attribute,
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
    return ClusterSnapshotDraft(operation="partition_by", params=params, clusters=clusters, warning=warning)
