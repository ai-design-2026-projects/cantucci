import json

from mcp.server.fastmcp import FastMCP

from mcp_server.client import CinePalClient


def register_tools(mcp: FastMCP, client: CinePalClient) -> None:
    """Register all CinePal MCP tools on the given FastMCP instance.

    Tools are state-changing operations: they create, modify, or delete
    resources in the CinePal backend.

    Args:
        mcp:    The FastMCP server instance to register tools on.
        client: The CinePal HTTP client used by each tool handler.
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
    async def delete_conversation(conversation_id: str) -> str:
        """Delete a CinePal conversation.

        Note: this operation requires the backend to be running with authentication.
        Anonymous callers will receive a 401 error from the backend.

        Args:
            conversation_id: UUID of the conversation to delete.

        Returns:
            Confirmation message string.
        """
        await client.delete_conversation(conversation_id)
        return f"Conversation {conversation_id} deleted."

    @mcp.tool()
    async def navigate_to_snapshot(conversation_id: str, snapshot_id: str) -> str:
        """Set the active cluster snapshot for a conversation (undo / branch navigation).

        Use the snapshot-graph resource to find past snapshot IDs, then call
        this tool to rewind or branch the conversation to that point.

        Note: this operation requires the backend to be running with authentication.
        Anonymous callers will receive a 401 error from the backend.

        Args:
            conversation_id: UUID of the conversation to update.
            snapshot_id:     UUID of the cluster snapshot to make active.

        Returns:
            JSON object with the updated conversation (id, current_cluster_snapshot_id, messages).
        """
        result = await client.navigate_to_snapshot(conversation_id, snapshot_id)
        return json.dumps(result, indent=2)
