from dataclasses import dataclass
from pydantic import BaseModel

from backend.llm.exceptions import LLMParseError


class ClusterLabelItem(BaseModel):
    """A single cluster's label output within a batched LLM response."""
    cluster_index: int
    label: str
    summary: str


class BatchLabelLLMResponse(BaseModel):
    """Structured output expected from the batched labeling LLM call.

    The LLM returns one ``ClusterLabelItem`` per input cluster, keyed by the
    zero-based ``cluster_index`` used in the prompt.
    """
    clusters: list[ClusterLabelItem]


@dataclass(frozen=True, slots=True)
class LabelResult:
    """Label and summary for a single cluster.

    Attributes:
        label:   Short 2–4-word label for the cluster theme.
        summary: One-sentence description of the cluster's semantic theme.
        cost:    Proportional LLM cost share for this cluster (total / n_clusters).
    """
    label: str
    summary: str | None
    cost: float = 0.0


@dataclass(frozen=True, slots=True)
class BatchLabelResult:
    """Output of a single batched labeling LLM call covering N clusters.

    Attributes:
        results: One ``LabelResult`` per input cluster, in the same order as the
                 input ``exemplar_groups`` list.
        cost:    Total LLM cost in USD for the call.
    """
    results: list[LabelResult]
    cost: float

    @classmethod
    def from_llm_response(
        cls, parsed: BatchLabelLLMResponse, n_expected: int, total_cost: float
    ) -> "BatchLabelResult":
        """Construct from a structured LLM response.

        Validates that exactly ``n_expected`` cluster items were returned and that
        all cluster indices from 0 to n_expected-1 are present.

        Args:
            parsed:      Pydantic-validated batched LLM payload.
            n_expected:  Number of clusters that were sent in the prompt.
            total_cost:  LLM cost in USD for the full call.

        Raises:
            LLMParseError: If the number of returned items does not match ``n_expected``
                           or any index is out of range.
        """
        if len(parsed.clusters) != n_expected:
            raise LLMParseError(
                step_type="label_clusters",
                raw=f"expected {n_expected} clusters, got {len(parsed.clusters)}",
            )

        per_cluster_cost = total_cost / n_expected if n_expected > 0 else 0.0
        by_index: dict[int, ClusterLabelItem] = {item.cluster_index: item for item in parsed.clusters}

        results: list[LabelResult] = []
        for i in range(n_expected):
            if i not in by_index:
                raise LLMParseError(
                    step_type="label_clusters",
                    raw=f"missing cluster_index {i} in LLM response",
                )
            item = by_index[i]
            results.append(LabelResult(label=item.label, summary=item.summary, cost=per_cluster_cost))

        return cls(results=results, cost=total_cost)
