import json

from mcp.server.fastmcp import FastMCP

from mcp_server.clients.cluster_snapshots import ClusterSnapshotsClient


def register(mcp: FastMCP, client: ClusterSnapshotsClient) -> None:
    """Register all cluster snapshot tools on the given FastMCP instance.

    Args:
        mcp:    The FastMCP server instance to register tools on.
        client: The cluster snapshots HTTP client used by each tool handler.
    """

    @mcp.tool()
    async def get_root_snapshot() -> str:
        """Fetch the most recent corpus-level cluster snapshot.

        This is the starting point for any new conversation — it represents
        the full movie catalogue clustered without any oracle guidance.

        The per-movie UMAP member assignments are omitted from this response
        (frontend-only data). Use get_cluster_members to retrieve movie
        memberships for a specific cluster.

        Returns:
            JSON object with id, operation, params, config_hash, clusters list,
            and created_at. Each cluster has id, label, summary,
            exemplar_movie_ids, parent_cluster_id, and color_slot.
        """
        result = await client.get_root_snapshot()
        result.pop("members", None)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def get_snapshot(snapshot_id: str) -> str:
        """Fetch a cluster snapshot with its full cluster list.

        Each cluster includes its label, one-sentence summary, top exemplar
        movie IDs, parent cluster ID (for drill-downs), and color slot.

        The per-movie UMAP member assignments are omitted from this response
        (frontend-only data). Use get_cluster_members to retrieve movie
        memberships for a specific cluster.

        Args:
            snapshot_id: UUID of the cluster snapshot to fetch.

        Returns:
            JSON object with id, operation, params, config_hash, clusters,
            and created_at. Each cluster has id, label, summary,
            exemplar_movie_ids, parent_cluster_id, and color_slot.
        """
        result = await client.get_snapshot(snapshot_id)
        result.pop("members", None)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def get_cluster_members(snapshot_id: str, cluster_id: str) -> str:
        """Fetch all movie memberships for a cluster with soft probabilities.

        Returns every movie assigned to the cluster with its soft membership
        probability, ordered by probability descending. Use the get_snapshot
        tool to discover cluster IDs within a snapshot.

        Args:
            snapshot_id: UUID of the cluster snapshot that owns the cluster.
            cluster_id:  UUID of the cluster to fetch members for.

        Returns:
            JSON array of objects with movie_id (int) and probability (float).
        """
        result = await client.get_cluster_members(snapshot_id, cluster_id)
        return json.dumps(result, indent=2)
