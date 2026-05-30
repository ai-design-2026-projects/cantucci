from pydantic import BaseModel

from backend.agents.intent.types import DialogueMode, Modality, NavigationMode


class MetadataFilterLLM(BaseModel):
    """Wire schema for the metadata predicate the LLM emits for CROSS_FILTER actions."""
    genres: list[str] | None = None
    release_year_min: int | None = None
    release_year_max: int | None = None
    director: str | None = None


class PartitionBinLLM(BaseModel):
    """A single labelled bucket emitted by the LLM for numeric cluster (deterministic branch) actions."""
    label: str
    min: float | None = None
    max: float | None = None


class PartitionSpecLLM(BaseModel):
    """Wire schema for the partition specification the LLM emits for cluster (deterministic branch) actions."""
    attribute: str
    bins: list[PartitionBinLLM] | None = None


class IntentActionLLM(BaseModel):
    """Structured output for a single action within the intent classification LLM call."""
    mode: NavigationMode | DialogueMode
    concept: str | None = None
    merged_label: str | None = None
    target_cluster_id: str | None = None
    confidence: float = 1.0
    embedding_spaces: list[Modality] = [Modality.TEXT]
    metadata_filter: MetadataFilterLLM | None = None
    partition_spec: PartitionSpecLLM | None = None
    target_n_clusters: int | None = None


class IntentLLMResponse(BaseModel):
    """Structured output expected from the intent classification LLM call.

    ``reasoning`` is a chain-of-thought scratchpad filled before ``actions``.
    It is generated first so the model can resolve ambiguities (pronoun
    references, partition_by vs drill_down, compound requests) before committing
    to a structured output.  It is used only for debugging and is not forwarded
    to the coordinator.

    ``actions`` wraps an ordered list of actions so the model can express
    compound requests (e.g. reset then drill-down) as a single turn.
    Single-action requests are represented as a one-element list.
    """
    reasoning: str = ""
    actions: list[IntentActionLLM]
