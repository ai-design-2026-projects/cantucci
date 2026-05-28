import dataclasses
import logging
import uuid

from backend.agents.clarifier.agent import clarify
from backend.agents.coordinator.tools.actions import ActionContext, execute_action
from backend.agents.coordinator.tools.clarification_state import mark_awaiting, take_awaiting
from backend.agents.coordinator.tools.labeling import label_unlabeled_clusters
from backend.agents.coordinator.tools.progress import ProgressReporter
from backend.agents.responder.suggestions import maybe_suggest
from backend.agents.coordinator.types import CoordinatorResult, TurnTrace, sentinel_cluster_snapshot_id
from backend.agents.intent.agent import classify as classify_intent
from backend.agents.clustering.types import NavigationMode
from backend.agents.intent.types import DialogueMode, IntentAction, IntentResult
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.queries import get_messages
from backend.data_access.conversations.types import ConversationRow
from backend.settings import get_settings

log = logging.getLogger(__name__)

_STATE_CHANGING = {
    NavigationMode.DRILL_DOWN,
    NavigationMode.MERGE,
    NavigationMode.FOCUS,
    NavigationMode.EXCLUDE,
    NavigationMode.CROSS_FILTER,
    NavigationMode.PARTITION_BY,
    DialogueMode.RESET,
    DialogueMode.GO_TO_BASE,
}


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
        current_cluster_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = conversation_row.accumulated_cost_usd
        turn_start_cost = accumulated_cost

        # Load current clusters from the DB
        current_snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id) if current_cluster_snapshot_id else None
        current_clusters = current_snapshot.clusters if current_snapshot else []

        message_id = uuid.uuid4()

        clusters = current_clusters
        if any(cluster.label is None for cluster in current_clusters):
            reporter.step("labeling")
            clusters, label_cost = await label_unlabeled_clusters(
                current_clusters, conversation_id, message_id, accumulated_cost
            )
            accumulated_cost += label_cost

        # Check for a recent assistant message awaiting clarification — if the
        # user is responding to a clarifier question, pass that question to the intent agent
        # for better parsing of short/pronoun-heavy replies.
        clarification_question: str | None = None
        was_awaiting, pending_spec = take_awaiting(conversation_id)
        if was_awaiting:
            recent = get_messages(conversation_id, limit=2)
            prior_assistant = next((m for m in reversed(recent) if m.role == "assistant"), None)
            if prior_assistant is not None:
                clarification_question = prior_assistant.content

        # Intent classification and dispatch
        reporter.step("intent")
        intent = await classify_intent(
            user_message=user_message,
            clusters=clusters,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            clarification_question=clarification_question,
        )
        accumulated_cost += intent.cost

        # When the user responded to a clarification, substitute the stored PartitionSpec
        # to correct for intent-agent drift on short replies like "yes" or cluster names.
        actions_to_dispatch = list(intent.actions)
        if was_awaiting and pending_spec is not None:
            for i, a in enumerate(actions_to_dispatch):
                if a.mode == NavigationMode.PARTITION_BY and a.partition_spec is not None:
                    if pending_spec.bins is not None and a.partition_spec.bins is None:
                        # Bin-proposal confirmation: stored spec is authoritative regardless of
                        # which attribute the intent agent returned on the short "yes" reply.
                        actions_to_dispatch[i] = dataclasses.replace(a, partition_spec=pending_spec)
                    elif pending_spec.bins is None and a.partition_spec.attribute != pending_spec.attribute:
                        # Target-clarification confirmation: intent returned the wrong attribute;
                        # restore the one from the stored spec.
                        actions_to_dispatch[i] = dataclasses.replace(
                            a,
                            partition_spec=dataclasses.replace(
                                a.partition_spec, attribute=pending_spec.attribute
                            ),
                        )

        trace_modes = [a.mode.value for a in intent.actions]
        trace_concepts = [a.concept for a in intent.actions]
        trace_targets = [a.target_cluster_id for a in intent.actions]
        trace_confidence = min((a.confidence for a in intent.actions), default=1.0)
        trace_raw = intent.raw_intent

        early_return = await self._clarify_if_low_confidence(
            intent=intent,
            clusters=clusters,
            user_message=user_message,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            current_cluster_snapshot_id=current_cluster_snapshot_id,
            reporter=reporter,
        )
        if early_return is not None:
            reporter.done()
            turn_trace = TurnTrace(
                modes=trace_modes,
                concepts=trace_concepts,
                target_cluster_ids=trace_targets,
                confidence=trace_confidence,
                clarifier_fired=True,
                raw_intent=trace_raw,
                suggestion=None,
                explanation=None,
            )
            return CoordinatorResult(
                reply_text=early_return.reply_text,
                cluster_snapshot_id=early_return.cluster_snapshot_id,
                turn_cost_usd=accumulated_cost - turn_start_cost,
                suggestion=early_return.suggestion,
                turn_trace=turn_trace,
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

        reply_fragments: list[str] = []

        for action in actions_to_dispatch:
            step_snapshot = get_cluster_snapshot_with_clusters(current_cluster_snapshot_id) if current_cluster_snapshot_id else None
            step_clusters = step_snapshot.clusters if step_snapshot else []

            ctx = ActionContext(
                action=action,
                current_cluster_snapshot_id=current_cluster_snapshot_id,
                clusters=step_clusters,
                conversation_id=conversation_id,
                conversation_row=conversation_row,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
                reporter=reporter,
            )
            fragment, current_cluster_snapshot_id, step_cost = await execute_action(ctx)
            accumulated_cost += step_cost
            reply_fragments.append(fragment)

        final_snapshot_id = current_cluster_snapshot_id or sentinel_cluster_snapshot_id()
        final_cswc = get_cluster_snapshot_with_clusters(final_snapshot_id)
        final_clusters = final_cswc.clusters if final_cswc else []

        combined_reply = "\n".join(
            f"{i + 1}) {frag}" for i, frag in enumerate(reply_fragments)
        ) if len(reply_fragments) > 1 else (reply_fragments[0] if reply_fragments else "")

        reporter.step("suggester")
        suggestion = await maybe_suggest(
            new_cluster_snapshot_id=final_snapshot_id,
            new_clusters=final_clusters,
            last_operation=combined_reply,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
        )

        explanation_text: str | None = None
        for i, action in enumerate(intent.actions):
            if action.mode == DialogueMode.EXPLAIN and i < len(reply_fragments):
                explanation_text = reply_fragments[i]
                break

        turn_trace = TurnTrace(
            modes=trace_modes,
            concepts=trace_concepts,
            target_cluster_ids=trace_targets,
            confidence=trace_confidence,
            clarifier_fired=False,
            raw_intent=trace_raw,
            suggestion=suggestion.text if suggestion else None,
            explanation=explanation_text,
        )

        reporter.done()
        return CoordinatorResult(
            reply_text=combined_reply,
            cluster_snapshot_id=final_snapshot_id,
            turn_cost_usd=accumulated_cost - turn_start_cost,
            suggestion=suggestion.text if suggestion else None,
            turn_trace=turn_trace,
        )

    async def _clarify_if_low_confidence(
        self,
        intent: IntentResult,
        clusters: list[ClusterRow],
        user_message: str,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        accumulated_cost: float,
        current_cluster_snapshot_id: uuid.UUID | None,
        reporter: ProgressReporter,
    ) -> CoordinatorResult | None:
        """Gate state-changing actions behind a confidence threshold.

        If any state-changing action falls below the configured confidence threshold,
        calls the Clarifier and returns a disambiguation question without modifying
        cluster state.  Returns None to signal that dispatch should proceed normally.

        Args:
            intent:                      Classified intent with one or more actions.
            clusters:                    Current cluster list for the clarifier prompt.
            user_message:                Raw user message.
            conversation_id:             Conversation UUID.
            message_id:                  Current message UUID for LLM logging.
            accumulated_cost:            Running LLM cost before this check.
            current_cluster_snapshot_id: Active cluster snapshot (snapshot is not modified).
            reporter:                    SSE progress reporter for this turn.

        Returns:
            ``CoordinatorResult`` with clarification text, or None to continue dispatch.
        """
        cfg = get_settings()
        low_confidence_action: IntentAction | None = next(
            (
                a for a in intent.actions
                if a.mode in _STATE_CHANGING
                and a.confidence < cfg.intent.confidence_threshold
            ),
            None,
        )
        if low_confidence_action is None:
            return None

        log.info(
            "coordinator_low_confidence_gate",
            extra={
                "conversation_id": str(conversation_id),
                "navigation_mode": low_confidence_action.mode.value,
                "confidence": low_confidence_action.confidence,
                "threshold": cfg.intent.confidence_threshold,
                "concept": low_confidence_action.concept,
            },
        )
        reporter.step("clarifier")
        clarification = await clarify(
            user_message=user_message,
            clusters=clusters,
            action=low_confidence_action,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
        )
        mark_awaiting(conversation_id)
        return CoordinatorResult(
            reply_text=clarification.text,
            cluster_snapshot_id=current_cluster_snapshot_id or sentinel_cluster_snapshot_id(),
        )
