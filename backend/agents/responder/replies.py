SMALL_TALK = (
    "I'm here to help you explore the movie catalogue through clustering. "
    "You can ask me to split a cluster, merge groups, or explain a placement."
)

RESET_REPLY = (
    "Session reset — you're back to an unclustered state. "
    "Tell me how you'd like to start, or ask me to go back to the default clustering."
)

NO_CLUSTER_TO_SPLIT = "Please specify which cluster to split."

FEWER_THAN_TWO_TO_MERGE = "There are fewer than two clusters to merge."

MERGE_REPLY = "Merged the selected clusters into one."

UNSUPPORTED_OPERATION = (
    "I understood your request but couldn't perform that operation on the current "
    "cluster snapshot. Try asking to split, merge, or explain a cluster."
)

NO_BASE_SNAPSHOT = "No base cluster snapshot found yet. Ingest the catalogue first."

EXPLAIN_TARGET_UNCLEAR = (
    "I couldn't identify which movie or cluster to explain. Please be more specific."
)

NO_UNDO = "Nothing to undo — there is no previous clustering snapshot to return to."


def format_partition_clarification(attribute: str, labels: list[str | None]) -> str:
    """Format a clarification question when no target cluster was specified for partition_by.

    Args:
        attribute: The partition attribute (e.g. ``"runtime"``).
        labels:    Labels of the current clusters (may contain None for unlabeled).

    Returns:
        A question asking the user which cluster to partition, naming the attribute so
        the intent agent can preserve it on the follow-up turn.
    """
    attr_label = attribute.replace("_", " ")
    names = ", ".join(f"'{l}'" for l in labels if l) or "the available clusters"
    return f"Which cluster would you like to partition by {attr_label}? Current clusters: {names}."


def format_drill_down_clarification(labels: list[str | None]) -> str:
    """Format a clarification question when no target cluster was specified for drill-down.

    Args:
        labels: Labels of the current clusters (may contain None for unlabeled).

    Returns:
        A question asking the user to specify which cluster to drill into.
    """
    names = ", ".join(f"'{l}'" for l in labels if l) or "the available clusters"
    return f"Which cluster would you like to drill into? Current clusters: {names}."


def format_drill_down_reply(labels: list[str | None], n_new: int, n_movies: int) -> str:
    """Format the reply for a completed CLUSTER (semantic branch) operation.

    Args:
        labels:   Label strings of the new sub-clusters (may contain None).
        n_new:    Total number of new sub-clusters produced.
        n_movies: Total number of movies across all sub-clusters.

    Returns:
        A human-readable summary of the split result.
    """
    display = [lbl for lbl in labels[:5]]
    ellipsis = "…" if n_new > 5 else ""
    return f"Split into {n_new} sub-clusters ({n_movies} movies): {', '.join(str(l) for l in display)}{ellipsis}."


def format_recut_reply(n_new: int) -> str:
    """Format the reply for a completed RECUT operation.

    Args:
        n_new: Total number of new clusters produced.

    Returns:
        A human-readable summary of the re-clustering result.
    """
    return f"Re-clustered the catalogue into {n_new} new clusters."


def format_reset_reply(n: int) -> str:
    """Format the reply for a completed RESET operation.

    Args:
        n: Number of clusters in the root snapshot.

    Returns:
        A human-readable summary of the reset result.
    """
    return f"Reset to the base clustering with {n} clusters."


def format_focus_reply(label: str | None, n_members: int) -> str:
    """Format the reply for a completed FOCUS operation.

    Args:
        label:     Label of the focused cluster.
        n_members: Number of movies retained.

    Returns:
        A human-readable summary of the focus result.
    """
    name = label or "the selected cluster"
    return f"Focused on '{name}' — {n_members} movies retained, all others discarded."


def format_cross_filter_reply(n_movies: int) -> str:
    """Format the reply for a completed CROSS_FILTER operation.

    Args:
        n_movies: Total number of movies that survived the filter.

    Returns:
        A human-readable summary of the cross-filter result.
    """
    return f"Applied metadata filter — {n_movies} movies matched. Use cluster to sub-group them."


def format_partition_reply(attribute: str, n_new: int, n_movies: int) -> str:
    """Format the reply for a completed CLUSTER (deterministic branch) operation.

    Args:
        attribute: The metadata attribute used to partition (e.g. ``"genre"``).
        n_new:     Total number of clusters produced.
        n_movies:  Total number of movies across all clusters.

    Returns:
        A human-readable summary of the partition result.
    """
    return f"Partitioned {n_movies} movies by {attribute} into {n_new} groups."


def format_exclude_reply(label: str | None, n_remaining: int) -> str:
    """Format the reply for a completed EXCLUDE operation.

    Args:
        label:       Label of the excluded cluster.
        n_remaining: Number of clusters remaining after the exclusion.

    Returns:
        A human-readable summary of the exclude result.
    """
    name = label or "the selected cluster"
    return f"Excluded '{name}' — {n_remaining} cluster{'s' if n_remaining != 1 else ''} remaining."


def format_undo_reply(operation: str, n_clusters: int) -> str:
    """Format the reply for a completed UNDO operation.

    Args:
        operation:  The operation name that was undone (e.g. ``"drill_down"``).
        n_clusters: Number of clusters in the restored snapshot.

    Returns:
        A human-readable summary of the undo result.
    """
    op_label = operation.replace("_", " ")
    return f"Stepped back — undid '{op_label}'. Now showing {n_clusters} cluster{'s' if n_clusters != 1 else ''}."


def format_axis_proposal(concept_name: str, n_movies: int) -> str:
    """Format the concept-axis beeswarm proposal message shown before clustering.

    Tells the user the scoring is done and invites them to inspect the distribution
    before deciding on a cluster count.  No cluster state has changed at this point.

    Args:
        concept_name: Human-readable name of the scored concept (e.g. ``"open-ended ending"``).
        n_movies:     Number of films scored along the axis.

    Returns:
        A conversational message directing the user to open the axis distribution view.
    """
    return (
        f"I've scored {n_movies:,} film{'s' if n_movies != 1 else ''} along the "
        f"\"{concept_name}\" axis. Open **View axis distribution** to see how they spread, "
        f"then tell me how many groups you'd like."
    )


def format_bin_proposal(
    attribute: str,
    bins: list,
    bin_counts: dict[str, int],
    unspecified: int,
) -> str:
    """Format a proactive bin proposal before executing a numeric partition.

    Shown to the user for confirmation; no cluster state has changed yet.

    Args:
        attribute:   The partition attribute name (e.g. ``"runtime"``).
        bins:        Proposed ``PartitionBin`` objects from the partition advisor.
        bin_counts:  Number of movies per bin label.
        unspecified: Number of movies that fall outside all bins or have no value.

    Returns:
        A conversational proposal message with per-bin movie counts.
    """
    attr_label = attribute.replace("_", " ")
    lines = [f"I'll split by {attr_label} into:"]
    for b in bins:
        count = bin_counts.get(b.label, 0)
        lines.append(f"  • {b.label} — {count:,} film{'s' if count != 1 else ''}")
    if unspecified:
        lines.append(
            f"  • (no value / out of range) — {unspecified:,} film{'s' if unspecified != 1 else ''}"
        )
    lines.append("Does that work, or would you prefer different thresholds?")
    return "\n".join(lines)
