from mcp_server.clients.http import BaseClient


class ConversationsClient(BaseClient):
    """HTTP client for the /conversations domain.

    All methods map 1-to-1 to backend routes under the ``/conversations``
    prefix. Non-2xx responses are raised as ``BackendError``.
    """

    async def create_conversation(self) -> dict:
        """POST /conversations — create a new anonymous conversation.

        Returns:
            ``ConversationDto`` dict with id, current_cluster_snapshot_id,
            messages, and created_at.
        """
        resp = await self._http.post("/conversations")
        self._check(resp)
        return resp.json()

    async def get_conversation(self, conversation_id: str) -> dict:
        """GET /conversations/{id} — fetch a conversation with its recent messages.

        Returns up to 20 of the most recent messages and the current active
        cluster snapshot ID.

        Args:
            conversation_id: Conversation UUID string.

        Returns:
            ``ConversationDto`` dict.
        """
        resp = await self._http.get(f"/conversations/{conversation_id}")
        self._check(resp)
        return resp.json()

    async def send_message(self, conversation_id: str, content: str) -> dict:
        """POST /conversations/{id}/messages — submit an oracle message.

        Runs the full intent → cluster → suggester pipeline and returns the
        assistant reply together with the updated cluster snapshot ID.

        Args:
            conversation_id: Conversation UUID string.
            content:         The oracle's message text.

        Returns:
            ``SendMessageResponse`` dict with message and cluster_snapshot_id.
        """
        resp = await self._http.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": content},
        )
        self._check(resp)
        return resp.json()

    async def navigate_to_snapshot(self, conversation_id: str, snapshot_id: str) -> dict:
        """PATCH /conversations/{id} — set the active cluster snapshot.

        Args:
            conversation_id: Conversation UUID string.
            snapshot_id:     Cluster snapshot UUID string to make active.

        Returns:
            Updated ``ConversationDto`` dict.
        """
        resp = await self._http.patch(
            f"/conversations/{conversation_id}",
            json={"current_cluster_snapshot_id": snapshot_id},
        )
        self._check(resp)
        return resp.json()

    async def get_snapshot_graph(self, conversation_id: str) -> dict:
        """GET /conversations/{id}/snapshot-graph — fetch the snapshot DAG.

        Args:
            conversation_id: Conversation UUID string.

        Returns:
            ``ClusterSnapshotGraphDto`` dict with cluster_snapshots list.
        """
        resp = await self._http.get(
            f"/conversations/{conversation_id}/snapshot-graph"
        )
        self._check(resp)
        return resp.json()
