import uuid

from backend.agents.responder.suggestions import maybe_suggest
from backend.agents.responder.types import SuggestionResult
from backend.coordinator.tools.progress import ProgressReporter
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters


async def finalize(
    reply_fragments: list[str],
    final_snapshot_id: uuid.UUID,
    conversation_id: uuid.UUID,
    message_id: uuid.UUID,
    accumulated_cost: float,
    reporter: ProgressReporter,
    skip_suggester: bool = False,
) -> tuple[str, SuggestionResult | None]:
    """Join reply fragments and run the suggester on the final snapshot.

    Args:
        reply_fragments:  One fragment per dispatched action.
        final_snapshot_id: UUID of the last produced snapshot.
        conversation_id:  Conversation UUID.
        message_id:       Current message UUID for logging.
        accumulated_cost: Running LLM cost after all actions.
        reporter:         SSE progress reporter.
        skip_suggester:   When ``True``, the suggester is skipped entirely and
                          ``None`` is returned for the suggestion. Set when the
                          turn ended with a clarification question so that no
                          suggestion is shown before the oracle has answered.

    Returns:
        Tuple of (combined_reply_text, suggestion_or_none).
    """
    final_cswc = get_cluster_snapshot_with_clusters(final_snapshot_id)
    final_clusters = final_cswc.clusters if final_cswc else []

    combined_reply = (
        "\n".join(f"{i + 1}) {frag}" for i, frag in enumerate(reply_fragments))
        if len(reply_fragments) > 1
        else (reply_fragments[0] if reply_fragments else "")
    )

    if skip_suggester:
        return combined_reply, None

    reporter.step("suggester")
    suggestion = await maybe_suggest(
        new_cluster_snapshot_id=final_snapshot_id,
        new_clusters=final_clusters,
        last_operation=combined_reply,
        conversation_id=conversation_id,
        message_id=message_id,
        accumulated_cost=accumulated_cost,
    )
    return combined_reply, suggestion
