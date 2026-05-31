"""Monolithic baseline system handler.

Two LLM calls per turn, both using the same generalist model (no specialised
sub-agents):
  1. Decide  — select the operation and extract parameters.
  2. Reply   — after the operation runs, label new clusters and write the reply.

All structural mutations (HDBSCAN, focus, merge, exclude, cross_filter) use the
same implementation as the full coordinator pipeline.
"""
import logging
import uuid

from backend.agents.concept.axe_builder import build_linear_axis
from backend.agents.concept.types import ConceptLLMResponse
from backend.agents.intent.types import MetadataFilter, Modality
from backend.baseline.monolithic.agent import monolithic_decide, monolithic_reply
from backend.baseline.monolithic.types import MonolithicDecideResponse
from backend.baseline.shared.types import SystemTurnResult
from backend.coordinator.commands.helpers.drafts import merge_in_siblings
from backend.coordinator.commands.impl.cluster.building import concept_cluster, free_cluster
from backend.coordinator.commands.impl.cross_filter import cross_filter
from backend.coordinator.commands.impl.exclude import exclude_cluster
from backend.coordinator.commands.impl.focus import focus
from backend.coordinator.commands.impl.merge import merge_clusters
from backend.coordinator.tools.persist import persist_and_label
from backend.coordinator.types import ClusterDraft, ClusterSnapshotDraft, TurnTrace, sentinel_cluster_snapshot_id
from backend.data_access.cluster_snapshots.queries import get_cluster_snapshot_with_clusters
from backend.data_access.cluster_snapshots.types import ClusterRow
from backend.data_access.conversations.types import ConversationRow

log = logging.getLogger(__name__)


def _resolve_cluster(
    label: str | None,
    clusters: list[ClusterRow],
    fallback_first: bool = True,
) -> uuid.UUID | None:
    """Resolve a label string to a cluster UUID via case-insensitive substring match.

    Args:
        label:          Label to match, or None.
        clusters:       Available clusters.
        fallback_first: Return the first cluster's ID when label is absent or unmatched.

    Returns:
        Matched UUID, first-cluster fallback, or None.
    """
    if clusters and label is not None:
        label_lower = label.strip().lower()
        for c in clusters:
            if c.label and label_lower in c.label.lower():
                return c.id
    return clusters[0].id if (fallback_first and clusters) else None


class MonolithicHandler:
    """Implements the session-driver turn protocol for the monolithic baseline."""

    async def handle_turn(
        self,
        conversation_id: uuid.UUID,
        user_message: str,
        conversation_row: ConversationRow,
    ) -> SystemTurnResult:
        """Run one monolithic turn: decide → execute → reply.

        Call 1 (decide) selects the operation. The operation is executed in code
        using the same implementation as the coordinator. Call 2 (reply) receives
        the result — including exemplar titles for any new clusters — and produces
        the oracle reply and cluster labels in one shot.

        Args:
            conversation_id:  UUID of the active conversation.
            user_message:     Oracle message (already stored in DB before this call).
            conversation_row: Current conversation row with snapshot and cost state.

        Returns:
            ``SystemTurnResult`` with new snapshot ID, reply, cost, and TurnTrace.
        """
        current_snapshot_id = conversation_row.current_cluster_snapshot_id
        accumulated_cost = conversation_row.accumulated_cost_usd
        message_id = uuid.uuid4()

        clusters: list[ClusterRow] = []
        if current_snapshot_id is not None:
            snapshot = get_cluster_snapshot_with_clusters(current_snapshot_id)
            if snapshot is not None:
                clusters = snapshot.clusters

        # --- Call 1: decide ---
        decision, decide_cost = await monolithic_decide(
            conversation_id=conversation_id,
            current_cluster_snapshot_id=current_snapshot_id,
            accumulated_cost=accumulated_cost,
            message_id=message_id,
        )

        op = decision.operation
        new_snapshot_id = current_snapshot_id or sentinel_cluster_snapshot_id()
        new_cluster_exemplars: list[list[int]] = []
        op_cost = 0.0

        # --- Execute operation ---
        try:
            if op == "cluster":
                target_id = _resolve_cluster(
                    decision.target_cluster_label, clusters, fallback_first=False
                )

                if (
                    decision.concept
                    and decision.concept_positive_descriptions
                    and decision.concept_negative_descriptions
                ):
                    concept_llm_resp = ConceptLLMResponse(
                        space=decision.concept_space or "semantic",
                        positive_descriptions=decision.concept_positive_descriptions,
                        negative_descriptions=decision.concept_negative_descriptions,
                        positive_label=decision.concept_positive_label or "",
                        negative_label=decision.concept_negative_label or "",
                    )
                    concept_rep = build_linear_axis(concept_llm_resp, decision.concept, cost=0.0)
                    draft = await concept_cluster(
                        source_cluster_id=target_id,
                        concept=concept_rep,
                        parent_cluster_snapshot_id=current_snapshot_id,
                    )
                else:
                    draft = await free_cluster(
                        source_cluster_id=target_id,
                        parent_cluster_snapshot_id=current_snapshot_id,
                        embedding_spaces=[Modality.TEXT],
                    )

                if target_id is not None and current_snapshot_id is not None:
                    draft = ClusterSnapshotDraft(
                        operation=draft.operation,
                        params=draft.params,
                        clusters=merge_in_siblings(
                            current_snapshot_id, target_id, draft.clusters
                        ),
                    )
                new_cluster_exemplars = [cd.exemplar_movie_ids for cd in draft.clusters]

            elif op == "focus" and current_snapshot_id is not None:
                target_id = _resolve_cluster(decision.target_cluster_label, clusters)
                draft = await focus(target_id, current_snapshot_id)

            elif op == "exclude" and current_snapshot_id is not None:
                target_id = _resolve_cluster(decision.target_cluster_label, clusters)
                draft = await exclude_cluster(target_id, current_snapshot_id)

            elif op == "merge" and len(clusters) >= 2 and current_snapshot_id is not None:
                id_a = _resolve_cluster(decision.cluster_a_label, clusters, fallback_first=True)
                id_b = _resolve_cluster(decision.cluster_b_label, clusters, fallback_first=True)
                if id_a == id_b:
                    id_b = clusters[1].id
                draft = await merge_clusters(
                    cluster_ids=list(dict.fromkeys([id_a, id_b])),
                    parent_cluster_snapshot_id=current_snapshot_id,
                    merged_label=decision.merged_label or "Merged",
                )

            elif op == "cross_filter" and current_snapshot_id is not None:
                metadata_filter = MetadataFilter(
                    genres=decision.genres or None,
                    release_year_min=decision.release_year_min,
                    release_year_max=decision.release_year_max,
                    director=decision.director,
                )
                draft = await cross_filter(current_snapshot_id, metadata_filter)

        except (ValueError, RuntimeError) as exc:
            log.warning(
                "monolithic_operation_failed",
                extra={
                    "conversation_id": str(conversation_id),
                    "operation": op,
                    "error": str(exc),
                },
            )
            op = "reply"

        # --- Call 2: reply ---
        reply_resp, reply_cost = await monolithic_reply(
            oracle_message=user_message,
            operation=op,
            new_cluster_exemplars=new_cluster_exemplars,
            conversation_id=conversation_id,
            accumulated_cost=accumulated_cost + decide_cost + op_cost,
            message_id=message_id,
            concept=decision.concept,
            concept_positive_label=decision.concept_positive_label,
            concept_negative_label=decision.concept_negative_label,
        )

        # --- Persist (after reply so labels are available) ---
        if op == "cluster" and new_cluster_exemplars:
            labels = reply_resp.cluster_labels or []
            labeled: list[ClusterDraft] = []
            for i, cd in enumerate(draft.clusters):
                if i < len(labels):
                    label, summary = labels[i].label, labels[i].summary
                else:
                    label, summary = f"Cluster {i + 1}", "A group of related films."
                labeled.append(ClusterDraft(
                    label=label,
                    summary=summary,
                    exemplar_movie_ids=cd.exemplar_movie_ids,
                    parent_cluster_id=cd.parent_cluster_id,
                    memberships=cd.memberships,
                    concept_score=cd.concept_score,
                    color_slot=cd.color_slot,
                ))
            labeled_draft = ClusterSnapshotDraft(
                operation=draft.operation,
                params=draft.params,
                clusters=labeled,
            )
            new_snapshot_id, op_cost = await persist_and_label(
                draft=labeled_draft,
                conversation_id=conversation_id,
                parent_cluster_snapshot_id=current_snapshot_id,
                accumulated_cost=accumulated_cost + decide_cost + reply_cost,
            )

        elif op in ("focus", "exclude", "merge") and current_snapshot_id is not None:
            new_snapshot_id, op_cost = await persist_and_label(
                draft=draft,
                conversation_id=conversation_id,
                parent_cluster_snapshot_id=current_snapshot_id,
                accumulated_cost=accumulated_cost + decide_cost + reply_cost,
            )

        elif op == "cross_filter" and current_snapshot_id is not None:
            cluster_label = decision.filtered_cluster_label or "Filtered Set"
            cd = draft.clusters[0]
            labeled_cf = ClusterSnapshotDraft(
                operation=draft.operation,
                params=draft.params,
                clusters=[ClusterDraft(
                    label=cluster_label,
                    summary="Movies matching the requested metadata filter.",
                    exemplar_movie_ids=cd.exemplar_movie_ids,
                    parent_cluster_id=cd.parent_cluster_id,
                    memberships=cd.memberships,
                    concept_score=cd.concept_score,
                    color_slot=cd.color_slot,
                )],
            )
            new_snapshot_id, op_cost = await persist_and_label(
                draft=labeled_cf,
                conversation_id=conversation_id,
                parent_cluster_snapshot_id=current_snapshot_id,
                accumulated_cost=accumulated_cost + decide_cost + reply_cost,
            )

        turn_cost = decide_cost + reply_cost + op_cost
        trace = TurnTrace(
            modes=[op],
            concepts=[decision.concept],
            target_cluster_ids=[None],
            confidence=1.0,
            clarifier_fired=False,
            raw_intent="{}",
            suggestion=None,
            explanation=None,
        )

        log.info(
            "monolithic_turn_done",
            extra={
                "conversation_id": str(conversation_id),
                "operation": op,
                "turn_cost_usd": turn_cost,
            },
        )

        return SystemTurnResult(
            reply_text=reply_resp.reply,
            cluster_snapshot_id=new_snapshot_id,
            turn_cost_usd=turn_cost,
            suggestion=None,
            turn_trace=trace,
        )
