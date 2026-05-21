"""Structured output schemas for the Cluster Agent's LLM calls.

Two response objects, one per scenario:

- ``ClusterDescribeResponse`` — for the fresh path (Scenario A). The describer
  receives HDBSCAN's clusters keyed by ``cluster_index`` and the model returns
  a ``(name, description)`` pair per cluster, addressed back by the same index
  so we can re-align if the model reorders the list.

- ``ClusterRefineResponse`` — for the refinement path (Scenario B). The refiner
  hands the model the prior clusters plus the clarifying Q&A and the model
  returns a new clustering: names, descriptions, and per-film soft assignments.
  Cluster identity is LLM-determined (clusters can be dropped, split, merged),
  so there is no input-keyed index — only a list.

The harness validates both schemas through ``response_schema=`` and retries on
parse/validation failures (see ``backend.llm.schema.validate_response``).

Pool-membership of ``movie_id`` values in the refine response is NOT enforced
here — the schema has no access to the allowed pool. The caller in
``backend.cluster.tools.cluster_refiner.refine`` does that semantic check
after the schema validates.
"""

from pydantic import BaseModel, Field, model_validator


class ClusterDescribeEntry(BaseModel):
    """One cluster's name and description, addressed by its HDBSCAN index.

    Attributes:
        cluster_index: Round-trips the input cluster ordinal so the caller can
                       re-align the response to the input list even if the
                       model emits clusters in a different order.
        name:          Short, evocative, contrastive name (≤ 6 words target;
                       80-char hard ceiling).
        description:   Tight description focused on what makes this cluster
                       distinct from the others (≤ 30 words target; 400-char
                       hard ceiling).
    """

    cluster_index: int = Field(ge=0)
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)


class ClusterDescribeResponse(BaseModel):
    """Wrapped response for the cluster-describe LLM call.

    The wrapper object is required because OpenAI's JSON-object mode rejects
    top-level arrays. ``clusters`` order is irrelevant — alignment to the
    input is by ``cluster_index``.

    The schema enforces uniqueness of ``cluster_index`` values; completeness
    (every input index covered exactly once) is checked caller-side in
    ``cluster_describer.describe`` because the schema has no access to the
    expected count.
    """

    clusters: list[ClusterDescribeEntry] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique_cluster_indices(self) -> "ClusterDescribeResponse":
        seen: set[int] = set()
        for entry in self.clusters:
            if entry.cluster_index in seen:
                raise ValueError(
                    f"duplicate cluster_index {entry.cluster_index} in describe response"
                )
            seen.add(entry.cluster_index)
        return self


class ClusterRefineAssignment(BaseModel):
    """A single film's soft assignment to a refined cluster.

    Attributes:
        movie_id: TMDB integer ID — must come from the allowed pool the refiner
                  passed into the prompt. Pool membership is verified by the
                  caller after schema validation.
        score:    Soft membership in [0, 1] reflecting strength of fit to the
                  cluster after refinement. Replaces the HDBSCAN-derived score
                  on this path.
    """

    movie_id: int
    score: float = Field(ge=0.0, le=1.0)


class ClusterRefineCluster(BaseModel):
    """One refined cluster: name, description, and its soft film assignments.

    Empty assignment lists are rejected: the LLM must drop a cluster by omitting
    it from the response, not by emitting it with no films.
    """

    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=400)
    assignments: list[ClusterRefineAssignment] = Field(min_length=1)


class ClusterRefineResponse(BaseModel):
    """Wrapped response for the cluster-refine LLM call.

    Attributes:
        reasoning: Chain-of-thought field the prompt forces the model to fill
                   before emitting the cluster list. Logged at DEBUG by the
                   refiner for postmortem; not consumed downstream.
        clusters:  Refined clusters after the LLM has applied drop / move /
                   rename / redescribe / remove / rescore / split / merge
                   operations.  An empty list is legal — it means the oracle's
                   answer disqualifies the whole pool and the orchestrator's
                   empty-cluster handling takes over.

    The schema enforces uniqueness of cluster names within the response.
    Pool-membership of movie_ids is checked caller-side.
    """

    reasoning: str = Field(min_length=1, max_length=4000)
    clusters: list[ClusterRefineCluster] = Field(min_length=0)

    @model_validator(mode="after")
    def _unique_cluster_names(self) -> "ClusterRefineResponse":
        seen: set[str] = set()
        for c in self.clusters:
            if c.name in seen:
                raise ValueError(
                    f"duplicate cluster name {c.name!r} in refine response"
                )
            seen.add(c.name)
        return self
