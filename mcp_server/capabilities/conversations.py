import json

from mcp.server.fastmcp import FastMCP

from mcp_server.clients.conversations import ConversationsClient


def register(mcp: FastMCP, client: ConversationsClient) -> None:
    """Register all conversation tools on the given FastMCP instance.

    Args:
        mcp:    The FastMCP server instance to register tools on.
        client: The conversations HTTP client used by each tool handler.
    """

    @mcp.tool()
    async def create_conversation() -> str:
        """Create a new anonymous CinePal conversation.

        Starts a fresh clustering session seeded with the base corpus snapshot.
        The returned conversation ID must be supplied to subsequent tool calls.

        Returns:
            JSON object with id, current_cluster_snapshot_id, messages, and created_at.
        """
        result = await client.create_conversation()
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def send_message(conversation_id: str, content: str) -> str:
        """Send an oracle message to a CinePal conversation and receive the AI reply.

        The backend processes the message through the full intent → cluster →
        suggester pipeline and returns the assistant reply together with the
        updated cluster snapshot ID.

        Args:
            conversation_id: UUID of the conversation to send the message to.
            content:         The oracle's natural-language message.

        Returns:
            JSON object with message (role, content, suggestion) and cluster_snapshot_id.
        """
        result = await client.send_message(conversation_id, content)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def navigate_to_snapshot(conversation_id: str, snapshot_id: str) -> str:
        """Set the active cluster snapshot for a conversation (undo / branch navigation).

        Use the get_snapshot_graph tool to find past snapshot IDs, then call
        this tool to rewind or branch the conversation to that point.

        Args:
            conversation_id: UUID of the conversation to update.
            snapshot_id:     UUID of the cluster snapshot to make active.

        Returns:
            JSON object with the updated conversation (id, current_cluster_snapshot_id, messages).
        """
        result = await client.navigate_to_snapshot(conversation_id, snapshot_id)
        return json.dumps(result, indent=2)

    @mcp.tool()
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

    @mcp.tool()
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
