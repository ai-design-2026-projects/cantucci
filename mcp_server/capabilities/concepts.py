import json

from mcp.server.fastmcp import FastMCP

from mcp_server.clients.concepts import ConceptsClient


def register(mcp: FastMCP, client: ConceptsClient) -> None:
    """Register all concept tools on the given FastMCP instance.

    Args:
        mcp:    The FastMCP server instance to register tools on.
        client: The concepts HTTP client used by each tool handler.
    """

    @mcp.tool()
    async def get_concept_axis(concept_id: str) -> str:
        """Fetch the distribution of movies along a concept's linear axis.

        Concepts are non-deterministic axes (e.g. "open-ended vs definitive
        endings") that the system computes for a cluster drill-down. The axis
        runs from -1 (negative pole) to +1 (positive pole), with each movie
        positioned by its axis score.

        Args:
            concept_id: UUID of the concept whose axis distribution to fetch.

        Returns:
            JSON object with concept_id, concept_name, positive_label, negative_label,
            and a points list of objects with movie_id, title, score, and vote_count,
            ordered by ascending score.
        """
        result = await client.get_concept_axis(concept_id)
        return json.dumps(result, indent=2)
