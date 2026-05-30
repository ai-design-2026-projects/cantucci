from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import ClassVar

from backend.coordinator.commands.base import ActionResult, ExecutionContext
from backend.agents.intent.types import Modality, PartitionSpec


@dataclass(frozen=True, slots=True)
class ClusterCommand:
    """Split a cluster (or the full catalogue) into sub-groups.

    Dispatches to one of two branches based on whether a ``partition_spec`` is
    provided:

    * **Deterministic branch** (``partition_spec`` is not ``None``): groups movies by
      an exact metadata attribute (genre, runtime, release_year, director,
      vote_average, original_language) with probability 1.0.  No embeddings or
      HDBSCAN are used.

    * **Semantic branch** (``partition_spec`` is ``None``): runs HDBSCAN soft
      clustering on the movie embeddings, optionally guided by a concept string.

    In both cases, if ``target_cluster_id`` resolves to a concrete cluster,
    sibling clusters from the parent snapshot are carried forward unchanged
    alongside the new sub-clusters (no FOCUS-like narrowing).

    Attributes:
        target_cluster_id: Cluster to split; ``None`` = full set or unclustered state.
        concept:           Semantic concept to guide clustering (semantic branch only).
        partition_spec:    Attribute and optional bins (deterministic branch only).
        embedding_spaces:  Modalities to fuse for embedding loading (semantic branch).
        confidence:        LLM confidence [0, 1].
        target_n_clusters: Exact cluster count requested by the oracle (semantic branch).
                           ``None`` preserves the emergent HDBSCAN count.
        reuse_concept_id:  UUID of a persisted concept whose normalized scores should be
                           reused for clustering.  Set by the coordinator when the user is
                           confirming a concept-axis beeswarm proposal; never extracted from
                           LLM output.  When non-None the concept agent call is skipped.
    """

    REQUIRES_SNAPSHOT: ClassVar[bool] = False
    CREATES_SNAPSHOT: ClassVar[bool] = True
    READS_CLUSTERS: ClassVar[bool] = True

    target_cluster_id: uuid.UUID | None
    concept: str | None
    partition_spec: PartitionSpec | None
    embedding_spaces: list[Modality]
    confidence: float
    target_n_clusters: int | None
    reuse_concept_id: uuid.UUID | None = None

    async def execute(self, ctx: ExecutionContext) -> ActionResult:
        """Split the target cluster (or full catalogue) into sub-groups.

        Routes to the deterministic branch when ``partition_spec`` is set,
        otherwise to the semantic (HDBSCAN) branch.

        Args:
            ctx: Execution context with session state.

        Returns:
            ActionResult with reply, new snapshot id, and cost.
        """
        from backend.coordinator.commands.impl.cluster.deterministic import execute_deterministic
        from backend.coordinator.commands.impl.cluster.semantic import execute_semantic

        if self.partition_spec is not None:
            return await execute_deterministic(self, ctx)
        return await execute_semantic(self, ctx)
