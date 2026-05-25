import json

from mcp.server.fastmcp import FastMCP

from mcp_server.client import CinePalClient


def register_resources(mcp: FastMCP, client: CinePalClient) -> None:
    """Register all CinePal MCP resources on the given FastMCP instance.

    Resources are read-only, URI-addressable data sources. Each resource maps
    to a GET endpoint on the CinePal FastAPI backend.

    Args:
        mcp:    The FastMCP server instance to register resources on.
        client: The CinePal HTTP client used by each resource handler.
    """

    @mcp.resource("conversation://{conversation_id}")
    async def get_conversation(conversation_id: str) -> str:
        """Fetch a CinePal conversation with its recent message history.

        Returns up to 20 of the most recent messages and the current active
        cluster snapshot ID.

        Args:
            conversation_id: UUID of the conversation to fetch.

        Returns:
            JSON object with id, current_cluster_snapshot_id, messages, and created_at.
        """
        result = await client.get_conversation(conversation_id)
        return json.dumps(result, indent=2)

    @mcp.resource("snapshot://{snapshot_id}")
    async def get_snapshot(snapshot_id: str) -> str:
        """Fetch a cluster snapshot with its full cluster list.

        Each cluster includes its label, one-sentence summary, top exemplar
        movie IDs, parent cluster ID (for drill-downs), and member count.

        Args:
            snapshot_id: UUID of the cluster snapshot to fetch.

        Returns:
            JSON object with id, operation, params, config_hash, clusters, and created_at.
        """
        result = await client.get_snapshot(snapshot_id)
        return json.dumps(result, indent=2)

    @mcp.resource("snapshot-graph://{conversation_id}")
    async def get_snapshot_graph(conversation_id: str) -> str:
        """Fetch the full cluster snapshot DAG for a conversation.

        Returns all snapshots the conversation has touched, each with its id,
        parent_id, operation type, and creation timestamp. Use this to discover
        past snapshot IDs for the navigate_to_snapshot tool.

        Args:
            conversation_id: UUID of the conversation whose snapshot graph to fetch.

        Returns:
            JSON object with cluster_snapshots list (id, parent_id, operation, created_at).
        """
        result = await client.get_snapshot_graph(conversation_id)
        return json.dumps(result, indent=2)

    @mcp.resource("cluster-members://{snapshot_id}/{cluster_id}")
    async def get_cluster_members(snapshot_id: str, cluster_id: str) -> str:
        """Fetch all movie memberships for a cluster with soft probabilities.

        Returns every movie assigned to the cluster with its soft membership
        probability, ordered by probability descending. Use the snapshot resource
        to discover cluster IDs within a snapshot.

        Args:
            snapshot_id: UUID of the cluster snapshot that owns the cluster.
            cluster_id:  UUID of the cluster to fetch members for.

        Returns:
            JSON array of objects with movie_id (int) and probability (float).
        """
        result = await client.get_cluster_members(snapshot_id, cluster_id)
        return json.dumps(result, indent=2)
