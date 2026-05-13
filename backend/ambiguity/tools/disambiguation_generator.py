"""Stub for the disambiguation generator tool used by the Ambiguity Agent.

The actual question generation happens inside the LLM prompt (ambiguity_v1.j2).
This tool exists as a deterministic fallback entry point for future template-
based question generation without an LLM call.
"""

import logging

from backend.models.clusters import ClusterSnapshot

log = logging.getLogger(__name__)


def propose(cluster_a: ClusterSnapshot, cluster_b: ClusterSnapshot) -> str:
    """Return a template-based disambiguating question (not yet implemented).

    Args:
        cluster_a: First candidate cluster.
        cluster_b: Second candidate cluster.

    Returns:
        Empty string until a deterministic implementation is added.
    """
    log.warning("disambiguation_generator not yet implemented")
    return ""
