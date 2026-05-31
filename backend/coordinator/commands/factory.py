from backend.agents.intent.types import DialogueMode, IntentAction, NavigationMode
from backend.coordinator.commands.impl.cluster.command import ClusterCommand
from backend.coordinator.commands.impl.cross_filter import CrossFilterCommand
from backend.coordinator.commands.impl.exclude import ExcludeCommand
from backend.coordinator.commands.impl.explain import ExplainCommand
from backend.coordinator.commands.impl.focus import FocusCommand
from backend.coordinator.commands.impl.merge import MergeCommand
from backend.coordinator.commands.impl.reset import ResetCommand
from backend.coordinator.commands.impl.small_talk import SmallTalkCommand
from backend.coordinator.commands.impl.undo import UndoCommand

AnyCommand = (
    ClusterCommand
    | MergeCommand
    | FocusCommand
    | ExcludeCommand
    | CrossFilterCommand
    | ResetCommand
    | UndoCommand
    | SmallTalkCommand
    | ExplainCommand
)


def build_command(action: IntentAction) -> AnyCommand:
    """Convert a normalised IntentAction into a typed command object.

    IntentAction already has UUID and enum fields parsed. This factory
    extracts only the fields relevant to each command class.

    Args:
        action: Normalised classified action from the intent agent.

    Returns:
        Typed command dataclass with an execute() method.

    Raises:
        ValueError: If the mode is unrecognised.
    """
    mode = action.mode

    if mode == NavigationMode.CLUSTER:
        return ClusterCommand(
            target_cluster_id=action.target_cluster_id,
            concept=action.concept,
            partition_spec=action.partition_spec,
            embedding_spaces=action.embedding_spaces,
            confidence=action.confidence,
            target_n_clusters=action.target_n_clusters,
            reuse_concept_id=action.reuse_concept_id,
        )
    if mode == NavigationMode.MERGE:
        return MergeCommand(
            merged_label=action.merged_label,
            confidence=action.confidence,
        )
    if mode == NavigationMode.FOCUS:
        return FocusCommand(
            target_cluster_id=action.target_cluster_id,
            confidence=action.confidence,
        )
    if mode == NavigationMode.EXCLUDE:
        return ExcludeCommand(
            target_cluster_id=action.target_cluster_id,
            confidence=action.confidence,
        )
    if mode == NavigationMode.CROSS_FILTER:
        if action.metadata_filter is None:
            raise ValueError("CROSS_FILTER action missing metadata_filter")
        return CrossFilterCommand(
            metadata_filter=action.metadata_filter,
            confidence=action.confidence,
        )
    if mode == DialogueMode.RESET:
        return ResetCommand(confidence=action.confidence)
    if mode == DialogueMode.UNDO:
        return UndoCommand(confidence=action.confidence)
    if mode == DialogueMode.SMALL_TALK:
        return SmallTalkCommand(confidence=action.confidence)
    if mode == DialogueMode.EXPLAIN:
        return ExplainCommand(
            target_cluster_id=action.target_cluster_id,
            confidence=action.confidence,
        )
    raise ValueError(f"Unrecognised action mode: {mode!r}")
