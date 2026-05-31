from typing import Literal

from pydantic import BaseModel


class MonolithicDecideResponse(BaseModel):
    """Call 1 output: operation selection and parameters.

    No reply text — the reply is produced after the operation runs.

    When operation is "cluster" and the oracle named a concept, the concept axis
    fields replace the concept agent's LLM call: the decide call produces the axis
    descriptions directly and ``build_linear_axis`` turns them into a scoring vector.

    Attributes:
        operation:                   Chosen operation.
        concept:                     Human-readable concept name (cluster only).
        concept_space:               Embedding space — "semantic" (text) or "visual" (trailer).
        concept_positive_descriptions: 3 full sentences describing films at the high end of the axis.
        concept_negative_descriptions: 3 full sentences describing films at the low end.
        concept_positive_label:      Short label for the high end (e.g. "nature-dominant").
        concept_negative_label:      Short label for the low end (e.g. "human-dominant").
        target_cluster_label:        Cluster to split / focus / exclude.
        cluster_a_label:             First cluster to merge.
        cluster_b_label:             Second cluster to merge.
        merged_label:                Label for the merged result.
        genres:                      Genre filter (cross_filter; OR semantics).
        release_year_min:            Earliest year, inclusive (cross_filter).
        release_year_max:            Latest year, inclusive (cross_filter).
        director:                    Director name substring (cross_filter).
        filtered_cluster_label:      Label for the single filtered cluster (cross_filter).
    """
    operation: Literal["cluster", "merge", "focus", "exclude", "cross_filter", "reply"]
    concept: str | None = None
    concept_space: Literal["semantic", "visual"] | None = None
    concept_positive_descriptions: list[str] | None = None
    concept_negative_descriptions: list[str] | None = None
    concept_positive_label: str | None = None
    concept_negative_label: str | None = None
    target_cluster_label: str | None = None
    cluster_a_label: str | None = None
    cluster_b_label: str | None = None
    merged_label: str | None = None
    genres: list[str] | None = None
    release_year_min: int | None = None
    release_year_max: int | None = None
    director: str | None = None
    filtered_cluster_label: str | None = None


class MonolithicLabelledCluster(BaseModel):
    """Label and summary for one cluster.

    Attributes:
        label:   Short descriptive name.
        summary: One-sentence description of the cluster's members.
    """
    label: str
    summary: str


class MonolithicReplyResponse(BaseModel):
    """Call 2 output: reply text and optional cluster labels.

    Attributes:
        reply:          Natural reply to send back to the oracle.
        cluster_labels: One label+summary per new cluster in order.
                        Populated only when operation == "cluster".
    """
    reply: str
    cluster_labels: list[MonolithicLabelledCluster] | None = None
