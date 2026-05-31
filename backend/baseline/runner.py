"""Baseline system handler: one LLM call per turn, no external clustering tools."""
import json
import logging
import uuid

from backend.baseline.agent import baseline_turn
from backend.baseline.types import SystemTurnResult
from backend.coordinator.types import TurnTrace
from backend.data_access.cluster_snapshots.queries import (
    canonicalize_params,
    create_cluster,
    create_cluster_snapshot,
    create_memberships,
    get_snapshot_members,
    record_conversation_snapshot_ref,
)
from backend.data_access.conversations.queries import set_current_cluster_snapshot
from backend.data_access.conversations.types import ConversationRow
from backend.data_access.movies.queries import list_movie_ids
from backend.llm.exceptions import LLMParseError
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)


class BaselineHandler:
    """Implements the session-driver turn protocol for the single-call baseline."""

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> SystemTurnResult:
        """Run one baseline turn: single LLM call → validate → persist.

        The LLM receives the full film list, the current cluster state, and the
        conversation transcript.  It emits the resulting cluster grouping, the declared
        navigation operation, and the oracle reply in one JSON response.  No external
        clustering tools (embeddings, HDBSCAN) are used at any point.

        Args:
            conversation_id:  UUID of the active conversation.
            user_message:     Oracle message (already stored in DB before this call).
            conversation_row: Current conversation row with snapshot and cost state.

        Returns:
            ``SystemTurnResult`` with new snapshot ID, reply, cost, and TurnTrace.

        Raises:
            LLMParseError:    When the LLM produces zero valid clusters after validation.
            CostLimitExceeded: When accumulated cost exceeds the configured limit.
        """
        current_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = conversation_row.accumulated_cost_usd
        message_id = uuid.uuid4()

        if current_snapshot_id is not None:
            members = get_snapshot_members(current_snapshot_id)
            valid_film_ids: set[int] = {m.movie_id for m in members}
        else:
            valid_film_ids = set(list_movie_ids())

        log.info(
            "baseline_handle_turn_start",
            extra={
                "conversation_id": str(conversation_id),
                "snapshot_id": str(current_snapshot_id) if current_snapshot_id else None,
                "n_films": len(valid_film_ids),
                "accumulated_cost_usd": accumulated_cost,
            },
        )

        response, call_cost = await baseline_turn(
            conversation_id=conversation_id,
            current_cluster_snapshot_id=current_snapshot_id,
            accumulated_cost=accumulated_cost,
            message_id=message_id,
        )

        validated: list[tuple[str, str, list[int]]] = []
        bad_ids: list[int] = []
        for cluster in response.clusters:
            kept = [fid for fid in cluster.film_ids if fid in valid_film_ids]
            bad_ids.extend(fid for fid in cluster.film_ids if fid not in valid_film_ids)
            if kept:
                validated.append((cluster.label, cluster.summary, kept))

        if bad_ids:
            log.warning(
                "baseline_invalid_film_ids_dropped",
                extra={
                    "conversation_id": str(conversation_id),
                    "n_dropped": len(bad_ids),
                    "sample": sorted(set(bad_ids))[:10],
                },
            )

        if not validated:
            raise LLMParseError(
                "baseline produced zero valid clusters after film_id validation"
            )

        cfg = get_settings()
        op = response.operation
        concept = response.concept

        params = canonicalize_params({
            "concept": concept or "",
            "operation": op,
            "turn_id": str(message_id),
        })
        snapshot_id = create_cluster_snapshot(
            operation=op,
            params=params,
            config_hash=get_config_hash(),
            parent_id=current_snapshot_id,
        )

        top_n = cfg.labeling.top_exemplars
        for i, (label, summary, film_ids) in enumerate(validated):
            cluster_id = create_cluster(
                cluster_snapshot_id=snapshot_id,
                label=label,
                summary=summary,
                exemplar_movie_ids=film_ids[:top_n],
                color_slot=i,
                parent_cluster_id=None,
            )
            create_memberships([(cluster_id, fid, 1.0) for fid in film_ids])

        record_conversation_snapshot_ref(conversation_id, snapshot_id)
        set_current_cluster_snapshot(conversation_id, snapshot_id)

        trace = TurnTrace(
            modes=[op],
            concepts=[concept],
            target_cluster_ids=[None],
            confidence=1.0,
            clarifier_fired=False,
            raw_intent=json.dumps({
                "operation": op,
                "concept": concept,
                "n_clusters": len(validated),
            }),
            suggestion=None,
            explanation=None,
        )

        log.info(
            "baseline_turn_done",
            extra={
                "conversation_id": str(conversation_id),
                "operation": op,
                "n_clusters": len(validated),
                "turn_cost_usd": call_cost,
            },
        )

        return SystemTurnResult(
            reply_text=response.reply,
            cluster_snapshot_id=snapshot_id,
            turn_cost_usd=call_cost,
            suggestion=None,
            turn_trace=trace,
        )
