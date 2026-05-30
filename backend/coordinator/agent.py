import logging
import uuid

from backend.coordinator.pipeline.clarification import clarify_if_low_confidence
from backend.coordinator.pipeline.dispatch import dispatch_actions
from backend.coordinator.pipeline.finalize import finalize
from backend.coordinator.pipeline.pending import (
    apply_pending_concept_override,
    apply_pending_spec_override,
    resolve_clarification_context,
)
from backend.coordinator.pipeline.preparation import prepare_turn
from backend.coordinator.pipeline.trace import build_trace, extract_trace_fields
from backend.coordinator.tools.clarification_state import is_awaiting
from backend.coordinator.tools.progress import ProgressReporter
from backend.coordinator.types import CoordinatorResult, sentinel_cluster_snapshot_id
from backend.agents.intent.agent import agent as intent_agent
from backend.data_access.conversations.types import ConversationRow

log = logging.getLogger(__name__)


class Coordinator:
    """
    Orchestrates one user message through the agent pipeline.
    Does not hold session state — all state is read from and written to the DB.
    Each call to handle_message is stateless and re-reads current conversation state.
    """

    async def handle_message(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> CoordinatorResult:
        """
        Process one user message and return the assistant reply with updated cluster snapshot.
        Pipeline:
          1. Load current cluster snapshot + recent messages.
          2. Label any unlabeled clusters (single batched LLM call).
          3. Classify intent (Intent agent) — may return multiple sequential actions.
          4. Up-front confidence gate: if any state-changing action is below threshold,
             call the Clarifier and return a disambiguation question without modifying state.
          5. Execute actions in order, threading each resulting snapshot into the next.
             Clusters are re-read from the DB at the start of each action so later steps
             operate on the actual post-operation state.
          6. After all actions, run the Suggester once on the final snapshot.
          7. Return aggregated reply, final snapshot id, optional suggestion, and turn trace.
        Args:
            conversation_id:  Conversation UUID.
            user_message:     Raw user message text.
            conversation_row: Pre-loaded conversation row (avoids double DB hit).
        Returns:
            ``CoordinatorResult`` with reply text, active cluster snapshot ID,
            optional follow-up suggestion, and a ``TurnTrace`` for eval runners.
        """
        # Create a progress reporter to send step events to the SSE stream
        reporter = ProgressReporter(str(conversation_id))

        # Load current conversation state and label any unlabeled clusters
        snapshot_id, accumulated_cost, turn_start_cost, clusters, message_id = await prepare_turn(
            conversation_id, conversation_row, reporter
        )

        # Check if we're awaiting clarification on a previous message
        was_awaiting, clarification_question, pending_spec, pending_target_id, pending_concept = resolve_clarification_context(conversation_id)

        # Classify oracle intent and retrieve proposed actions
        reporter.step("intent")
        intent = await intent_agent.run(
            user_message=user_message,
            clusters=clusters,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            clarification_question=clarification_question,
        )
        accumulated_cost += intent.cost
        actions = list(intent.actions)

        # If we were awaiting clarification and the intent agent returned a partitioning action,
        # override the returned partition spec with the one we stored from the clarification turn
        if was_awaiting and pending_spec is not None:
            actions = apply_pending_spec_override(actions, pending_spec, pending_target_id)

        # If we were awaiting a concept-axis confirmation, patch the CLUSTER action to reuse
        # the persisted concept scores instead of invoking the concept agent again
        if was_awaiting and pending_concept is not None:
            actions = apply_pending_concept_override(actions, pending_concept)

        trace_modes, trace_concepts, trace_targets, trace_confidence, trace_raw = extract_trace_fields(intent)

        early_return = await clarify_if_low_confidence(
            intent=intent,
            clusters=clusters,
            user_message=user_message,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            current_cluster_snapshot_id=snapshot_id,
            reporter=reporter,
        )
        if early_return is not None:
            reporter.done()
            return CoordinatorResult(
                reply_text=early_return.reply_text,
                cluster_snapshot_id=early_return.cluster_snapshot_id,
                turn_cost_usd=accumulated_cost - turn_start_cost,
                suggestion=early_return.suggestion,
                turn_trace=build_trace(
                    trace_modes, trace_concepts, trace_targets, trace_confidence, trace_raw,
                    clarifier_fired=True, suggestion=None, reply_fragments=[], intent_actions=actions,
                ),
            )

        log.info(
            "coordinator_dispatch",
            extra={
                "conversation_id": str(conversation_id),
                "n_actions": len(intent.actions),
                "intent_modes": trace_modes,
                "n_clusters": len(clusters),
            },
        )

        # Execute actions in sequence, threading the snapshot id forward
        snapshot_id, accumulated_cost, reply_fragments, axis_concept_id = await dispatch_actions(
            actions=actions,
            conversation_id=conversation_id,
            conversation_row=conversation_row,
            current_cluster_snapshot_id=snapshot_id,
            accumulated_cost=accumulated_cost,
            message_id=message_id,
            reporter=reporter,
        )

        # Join replies and run the suggester on the final snapshot, but skip it
        # when dispatch ended with a clarification question — there is nothing to suggest
        # until the oracle answers and the operation actually executes.
        final_snapshot_id = snapshot_id or sentinel_cluster_snapshot_id()
        awaiting_after_dispatch = is_awaiting(conversation_id)
        combined_reply, suggestion = await finalize(
            reply_fragments=reply_fragments,
            final_snapshot_id=final_snapshot_id,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            reporter=reporter,
            skip_suggester=awaiting_after_dispatch,
        )

        reporter.done()
        return CoordinatorResult(
            reply_text=combined_reply,
            cluster_snapshot_id=final_snapshot_id,
            turn_cost_usd=accumulated_cost - turn_start_cost,
            suggestion=suggestion.text if suggestion else None,
            axis_concept_id=axis_concept_id,
            turn_trace=build_trace(
                trace_modes, trace_concepts, trace_targets, trace_confidence, trace_raw,
                clarifier_fired=False, suggestion=suggestion, reply_fragments=reply_fragments,
                intent_actions=actions,
            ),
        )
