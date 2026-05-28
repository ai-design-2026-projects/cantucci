from backend.agents.intent.types import DialogueMode, IntentAction, NavigationMode
from backend.coordinator.commands.cross_filter import CrossFilterCommand
from backend.coordinator.commands.drill_down import DrillDownCommand
from backend.coordinator.commands.exclude import ExcludeCommand
from backend.coordinator.commands.explain import ExplainCommand
from backend.coordinator.commands.focus import FocusCommand
from backend.coordinator.commands.go_to_base import GoToBaseCommand
from backend.coordinator.commands.merge import MergeCommand
from backend.coordinator.commands.partition_by import PartitionByCommand
from backend.coordinator.commands.reset import ResetCommand
from backend.coordinator.commands.small_talk import SmallTalkCommand
from backend.coordinator.commands.undo import UndoCommand

AnyCommand = (
    DrillDownCommand
    | MergeCommand
    | FocusCommand
    | ExcludeCommand
    | CrossFilterCommand
    | PartitionByCommand
    | ResetCommand
    | GoToBaseCommand
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

    if mode == NavigationMode.DRILL_DOWN:
        return DrillDownCommand(
            target_cluster_id=action.target_cluster_id,
            concept=action.concept,
            embedding_spaces=action.embedding_spaces,
            confidence=action.confidence,
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
    if mode == NavigationMode.PARTITION_BY:
        return PartitionByCommand(
            target_cluster_id=action.target_cluster_id,
            partition_spec=action.partition_spec,
            confidence=action.confidence,
        )
    if mode == DialogueMode.RESET:
        return ResetCommand(confidence=action.confidence)
    if mode == DialogueMode.GO_TO_BASE:
        return GoToBaseCommand(confidence=action.confidence)
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
