import dataclasses
import logging
import uuid

from backend.agents.clarifier.agent import agent as clarifier_agent
from backend.coordinator.commands.factory import build_command
from backend.coordinator.commands.base import ExecutionContext
from backend.coordinator.tools.clarification_state import mark_awaiting, take_awaiting
from backend.agents.concept.types import PendingConcept
from backend.coordinator.tools.labeling import label_unlabeled_clusters
from backend.coordinator.tools.progress import ProgressReporter
from backend.agents.responder.suggestions import maybe_suggest
from backend.coordinator.types import CoordinatorResult, TurnTrace, sentinel_cluster_snapshot_id
from backend.agents.intent.agent import agent as intent_agent
from backend.agents.intent.types import NavigationMode
from backend.agents.intent.types import DialogueMode, IntentAction, IntentResult, PartitionSpec
from backend.agents.responder.types import SuggestionResult
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.queries import get_messages
from backend.data_access.conversations.types import ConversationRow
from backend.settings import get_settings

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
        snapshot_id, accumulated_cost, turn_start_cost, clusters, message_id = await self._prepare_turn(
            conversation_id, conversation_row, reporter
        )

        # Check if we're awaiting clarification on a previous message
        was_awaiting, clarification_question, pending_spec, pending_concept = self._resolve_clarification_context(conversation_id)

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
            actions = self._apply_pending_spec_override(actions, pending_spec)

        # If we were awaiting a concept-axis confirmation, patch the CLUSTER action to reuse
        # the persisted concept scores instead of invoking the concept agent again
        if was_awaiting and pending_concept is not None:
            actions = self._apply_pending_concept_override(actions, pending_concept)

        trace_modes, trace_concepts, trace_targets, trace_confidence, trace_raw = self._extract_trace_fields(intent)

        early_return = await self._clarify_if_low_confidence(
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
                turn_trace=self._build_trace(
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
        snapshot_id, accumulated_cost, reply_fragments, axis_concept_id = await self._dispatch_actions(
            actions=actions,
            conversation_id=conversation_id,
            conversation_row=conversation_row,
            current_cluster_snapshot_id=snapshot_id,
            accumulated_cost=accumulated_cost,
            message_id=message_id,
            reporter=reporter,
        )

        # Join replies and run the suggester on the final snapshot
        final_snapshot_id = snapshot_id or sentinel_cluster_snapshot_id()
        combined_reply, suggestion = await self._finalize(
            reply_fragments=reply_fragments,
            final_snapshot_id=final_snapshot_id,
            conversation_id=conversation_id,
            message_id=message_id,
            accumulated_cost=accumulated_cost,
            reporter=reporter,
        )

        reporter.done()
        return CoordinatorResult(
            reply_text=combined_reply,
            cluster_snapshot_id=final_snapshot_id,
            turn_cost_usd=accumulated_cost - turn_start_cost,
            suggestion=suggestion.text if suggestion else None,
            axis_concept_id=axis_concept_id,
            turn_trace=self._build_trace(
                trace_modes, trace_concepts, trace_targets, trace_confidence, trace_raw,
                clarifier_fired=False, suggestion=suggestion, reply_fragments=reply_fragments,
                intent_actions=actions,
            ),
        )

    async def _prepare_turn(
        self,
        conversation_id: uuid.UUID,
        conversation_row: ConversationRow,
        reporter: ProgressReporter,
    ) -> tuple[uuid.UUID | None, float, float, list[ClusterRow], uuid.UUID]:
        """Load conversation state and label any unlabeled clusters.

        Args:
            conversation_id:  Conversation UUID.
            conversation_row: Pre-loaded conversation row.
            reporter:         SSE progress reporter for this turn.

        Returns:
            Tuple of (current_cluster_snapshot_id, accumulated_cost,
            turn_start_cost, clusters, message_id).
        """
        # Load current conversation state
        current_cluster_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = conversation_row.accumulated_cost_usd
        turn_start_cost = accumulated_cost
        current_snapshot = (
            get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
            if current_cluster_snapshot_id else None
        )
        current_clusters = current_snapshot.clusters if current_snapshot else []
        message_id = uuid.uuid4()

        # Lazy labelling all the unlabeled clusters
        clusters = current_clusters
        if any(cluster.label is None for cluster in current_clusters):
            reporter.step("labeling")
            clusters, label_cost = await label_unlabeled_clusters(
                current_clusters, conversation_id, message_id, accumulated_cost
            )
            accumulated_cost += label_cost

        return current_cluster_snapshot_id, accumulated_cost, turn_start_cost, clusters, message_id

    def _resolve_clarification_context(
        self,
        conversation_id: uuid.UUID,
    ) -> tuple[bool, str | None, PartitionSpec | None, PendingConcept | None]:
        """Check for a pending clarification and fetch the prior question text if set.

        Consumes the in-memory awaiting flag via ``take_awaiting``; subsequent
        calls on the same turn will see ``was_awaiting=False``.

        Args:
            conversation_id: Conversation UUID to check.

        Returns:
            Tuple of (was_awaiting, clarification_question, pending_spec, pending_concept).
            ``clarification_question`` is the prior assistant message text when
            ``was_awaiting`` is True, else ``None``.
        """
        # Check if we're awaiting clarification on a previous message
        was_awaiting, pending_spec, pending_concept = take_awaiting(conversation_id)
        clarification_question: str | None = None
        # If so, find the most recent assistant message to use as the clarification question for intent classification.
        if was_awaiting:
            recent = get_messages(conversation_id, limit=2)
            prior_assistant = next((m for m in reversed(recent) if m.role == "assistant"), None)
            if prior_assistant is not None:
                clarification_question = prior_assistant.content
        return was_awaiting, clarification_question, pending_spec, pending_concept

    def _apply_pending_spec_override(
        self,
        actions: list[IntentAction],
        pending_spec: PartitionSpec,
    ) -> list[IntentAction]:
        """Patch any CLUSTER action with the spec stored from the clarification turn.

        On a "yes" or short-answer reply the intent agent may re-extract bins or
        attributes incorrectly.  The stored spec is authoritative for two cases:

        - Bin-proposal confirmation: ``pending_spec.bins is not None`` and the
          returned action has no bins → restore the stored spec wholesale.
        - Target-clarification confirmation: the stored spec has no bins but the
          returned attribute differs → restore just the attribute.

        Args:
            actions:      Classified actions from the intent agent (may be mutated copy).
            pending_spec: Stored partition spec from the prior clarification turn.

        Returns:
            New list of actions with CLUSTER entries patched where needed.
        """
        result = list(actions)
        for i, a in enumerate(result):
            if a.mode == NavigationMode.CLUSTER and a.partition_spec is not None:
                if pending_spec.bins is not None and a.partition_spec.bins is None:
                    # Bin-proposal confirmation: stored spec is authoritative regardless of
                    # which attribute the intent agent returned on the short "yes" reply.
                    result[i] = dataclasses.replace(a, partition_spec=pending_spec)
                elif pending_spec.bins is None and a.partition_spec.attribute != pending_spec.attribute:
                    # Target-clarification confirmation: intent returned the wrong attribute;
                    # restore the one from the stored spec.
                    result[i] = dataclasses.replace(
                        a,
                        partition_spec=dataclasses.replace(
                            a.partition_spec, attribute=pending_spec.attribute
                        ),
                    )
        return result

    def _apply_pending_concept_override(
        self,
        actions: list[IntentAction],
        pending_concept: PendingConcept,
    ) -> list[IntentAction]:
        """Patch the CLUSTER action to reuse the persisted concept scores from the proposal turn.

        When the user is confirming a concept-axis beeswarm proposal (by stating the
        desired cluster count), the intent agent may re-extract the concept name but
        we want to reuse the already-computed and persisted scores rather than calling
        the concept agent again.  If the user redirected to a *different* concept (i.e.
        the returned action has a concept string and it differs from the pending name),
        we skip the override and let the new concept flow through normally.

        Args:
            actions:         Classified actions from the intent agent.
            pending_concept: Stored concept context from the prior proposal turn.

        Returns:
            New list of actions with the CLUSTER entry patched to carry ``reuse_concept_id``
            and the original ``target_cluster_id``.
        """
        result = list(actions)
        for i, a in enumerate(result):
            if a.mode == NavigationMode.CLUSTER:
                if a.concept is not None and a.concept != pending_concept.concept_name:
                    break
                result[i] = dataclasses.replace(
                    a,
                    reuse_concept_id=pending_concept.concept_id,
                    target_cluster_id=pending_concept.target_cluster_id,
                )
                break
        return result

    def _extract_trace_fields(
        self, intent: IntentResult
    ) -> tuple[list[str], list[str | None], list[uuid.UUID | None], float, str]:
        """Extract per-turn trace metadata from the intent result.

        Args:
            intent: Classified intent with one or more actions.

        Returns:
            Tuple of (modes, concepts, target_cluster_ids, min_confidence, raw_intent).
        """
        return (
            [a.mode.value for a in intent.actions],
            [a.concept for a in intent.actions],
            [a.target_cluster_id for a in intent.actions],
            min((a.confidence for a in intent.actions), default=1.0),
            intent.raw_intent,
        )

    async def _dispatch_actions(
        self,
        actions: list[IntentAction],
        conversation_id: uuid.UUID,
        conversation_row: ConversationRow,
        current_cluster_snapshot_id: uuid.UUID | None,
        accumulated_cost: float,
        message_id: uuid.UUID,
        reporter: ProgressReporter,
    ) -> tuple[uuid.UUID | None, float, list[str], uuid.UUID | None]:
        """Execute each action in sequence, threading the cluster snapshot forward.

        Clusters are re-read from the DB at the start of each action so later
        steps see the actual post-operation state from prior steps.

        Args:
            actions:                      Classified actions to dispatch.
            conversation_id:              Conversation UUID.
            conversation_row:             Pre-loaded conversation row.
            current_cluster_snapshot_id:  Active snapshot before this batch.
            accumulated_cost:             Running LLM cost before dispatch.
            message_id:                   Current message UUID for logging.
            reporter:                     SSE progress reporter.

        Returns:
            Tuple of (final_cluster_snapshot_id, accumulated_cost, reply_fragments,
            axis_concept_id).  ``axis_concept_id`` is the last non-None value produced
            by any action in this batch; None when no action proposed a concept axis.
        """
        reply_fragments: list[str] = []
        axis_concept_id: uuid.UUID | None = None
        for action in actions:
            step_snapshot = (
                get_cluster_snapshot_with_clusters(current_cluster_snapshot_id)
                if current_cluster_snapshot_id else None
            )
            step_clusters = step_snapshot.clusters if step_snapshot else []

            command = build_command(action)
            ctx = ExecutionContext(
                current_cluster_snapshot_id=current_cluster_snapshot_id,
                clusters=step_clusters,
                conversation_id=conversation_id,
                conversation_row=conversation_row,
                message_id=message_id,
                accumulated_cost=accumulated_cost,
                reporter=reporter,
            )
            result = await command.execute(ctx)
            current_cluster_snapshot_id = result.cluster_snapshot_id
            accumulated_cost += result.step_cost
            reply_fragments.append(result.reply_fragment)
            if result.axis_concept_id is not None:
                axis_concept_id = result.axis_concept_id
        return current_cluster_snapshot_id, accumulated_cost, reply_fragments, axis_concept_id

    async def _finalize(
        self,
        reply_fragments: list[str],
        final_snapshot_id: uuid.UUID,
        conversation_id: uuid.UUID,
        message_id: uuid.UUID,
        accumulated_cost: float,
        reporter: ProgressReporter,
    ) -> tuple[str, SuggestionResult | None]:
        """Join reply fragments and run the suggester on the final snapshot.

        Args:
            reply_fragments:  One fragment per dispatched action.
            final_snapshot_id: UUID of the last produced snapshot.
            conversation_id:  Conversation UUID.
            message_id:       Current message UUID for logging.
            accumulated_cost: Running LLM cost after all actions.
            reporter:         SSE progress reporter.

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

    def _build_trace(
        self,
        trace_modes: list[str],
        trace_concepts: list[str | None],
        trace_targets: list[uuid.UUID | None],
        trace_confidence: float,
        trace_raw: str,
        clarifier_fired: bool,
        suggestion: SuggestionResult | None,
        reply_fragments: list[str],
        intent_actions: list[IntentAction],
    ) -> TurnTrace:
        """Construct a ``TurnTrace`` for the completed turn.

        Handles both the early-return (clarifier fired) and normal dispatch paths.
        When ``clarifier_fired`` is True, explanation is always ``None`` and
        suggestion is always ``None``.

        Args:
            trace_modes:      Mode value strings from intent actions.
            trace_concepts:   Concept strings (parallel to modes).
            trace_targets:    Target cluster UUIDs (parallel to modes).
            trace_confidence: Minimum confidence across all actions.
            trace_raw:        Raw intent JSON string.
            clarifier_fired:  True when the clarifier gate fired this turn.
            suggestion:       Suggester result (``None`` on the clarifier path).
            reply_fragments:  Per-action reply texts (empty on the clarifier path).
            intent_actions:   Classified actions (used to extract the explain text).

        Returns:
            ``TurnTrace`` for persistence by eval/baseline runners.
        """
        explanation_text: str | None = None
        if not clarifier_fired:
            for i, action in enumerate(intent_actions):
                if action.mode == DialogueMode.EXPLAIN and i < len(reply_fragments):
                    explanation_text = reply_fragments[i]
                    break
        return TurnTrace(
            modes=trace_modes,
            concepts=trace_concepts,
            target_cluster_ids=trace_targets,
            confidence=trace_confidence,
            clarifier_fired=clarifier_fired,
            raw_intent=trace_raw,
            suggestion=suggestion.text if suggestion else None,
            explanation=explanation_text,
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
                if build_command(a).CREATES_SNAPSHOT
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
        clarification = await clarifier_agent.run(
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
