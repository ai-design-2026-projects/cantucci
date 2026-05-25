import httpx

from mcp_server.settings import get_settings


class BackendError(Exception):
    """Raised when the CinePal backend returns a non-2xx response.

    Attributes:
        status_code: HTTP status code returned by the backend.
    """

    def __init__(self, status_code: int, detail: str) -> None:
        self.status_code = status_code
        super().__init__(f"Backend error {status_code}: {detail}")


class CinePalClient:
    """Async HTTP client wrapping the CinePal FastAPI backend.

    All methods map 1-to-1 to backend HTTP endpoints. Non-2xx responses are
    raised as ``BackendError`` with the status code and detail message from
    the backend JSON body.
    """

    def __init__(self) -> None:
        settings = get_settings()
        self._client = httpx.AsyncClient(
            base_url=settings.backend_url,
            timeout=settings.timeout,
        )

    def _check(self, response: httpx.Response) -> httpx.Response:
        """Raise ``BackendError`` for non-2xx responses.

        Args:
            response: The httpx response to check.

        Returns:
            The same response if it is 2xx.

        Raises:
            BackendError: If the response status code indicates an error.
        """
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except Exception:
                detail = response.text
            raise BackendError(response.status_code, str(detail))
        return response

    async def create_conversation(self) -> dict:
        """POST /conversations — create a new anonymous conversation.

        Returns:
            ``ConversationDto`` dict with id, current_cluster_snapshot_id, messages, created_at.
        """
        resp = await self._client.post("/conversations")
        self._check(resp)
        return resp.json()

    async def get_conversation(self, conversation_id: str) -> dict:
        """GET /conversations/{id} — fetch a conversation with its recent messages.

        Args:
            conversation_id: Conversation UUID string.

        Returns:
            ``ConversationDto`` dict.
        """
        resp = await self._client.get(f"/conversations/{conversation_id}")
        self._check(resp)
        return resp.json()

    async def send_message(self, conversation_id: str, content: str) -> dict:
        """POST /conversations/{id}/messages — submit an oracle message.

        Args:
            conversation_id: Conversation UUID string.
            content:         The oracle's message text.

        Returns:
            ``SendMessageResponse`` dict with message and cluster_snapshot_id.
        """
        resp = await self._client.post(
            f"/conversations/{conversation_id}/messages",
            json={"content": content},
        )
        self._check(resp)
        return resp.json()

    async def delete_conversation(self, conversation_id: str) -> None:
        """DELETE /conversations/{id} — delete a conversation.

        Note: The backend requires authentication for this operation. Calling
        this without a configured auth token will result in a BackendError(401).

        Args:
            conversation_id: Conversation UUID string.
        """
        resp = await self._client.delete(f"/conversations/{conversation_id}")
        self._check(resp)

    async def navigate_to_snapshot(self, conversation_id: str, snapshot_id: str) -> dict:
        """PATCH /conversations/{id} — set the active cluster snapshot.

        Note: The backend requires authentication for this operation. Calling
        this without a configured auth token will result in a BackendError(401).

        Args:
            conversation_id: Conversation UUID string.
            snapshot_id:     Cluster snapshot UUID string to make active.

        Returns:
            Updated ``ConversationDto`` dict.
        """
        resp = await self._client.patch(
            f"/conversations/{conversation_id}",
            json={"current_cluster_snapshot_id": snapshot_id},
        )
        self._check(resp)
        return resp.json()

    async def get_snapshot(self, snapshot_id: str) -> dict:
        """GET /cluster-snapshots/{id} — fetch a snapshot with its full cluster list.

        Args:
            snapshot_id: Cluster snapshot UUID string.

        Returns:
            ``ClusterSnapshotDto`` dict with clusters list.
        """
        resp = await self._client.get(f"/cluster-snapshots/{snapshot_id}")
        self._check(resp)
        return resp.json()

    async def get_snapshot_graph(self, conversation_id: str) -> dict:
        """GET /conversations/{id}/cluster-snapshots — fetch the snapshot DAG.

        Args:
            conversation_id: Conversation UUID string.

        Returns:
            ``ClusterSnapshotGraphDto`` dict with cluster_snapshots list.
        """
        resp = await self._client.get(f"/conversations/{conversation_id}/cluster-snapshots")
        self._check(resp)
        return resp.json()

    async def get_cluster_members(self, snapshot_id: str, cluster_id: str) -> list:
        """GET /cluster-snapshots/{snapshot_id}/clusters/{cluster_id}/members.

        Args:
            snapshot_id: Cluster snapshot UUID string.
            cluster_id:  Cluster UUID string within that snapshot.

        Returns:
            List of ``ClusterMembershipDto`` dicts with movie_id and probability.
        """
        resp = await self._client.get(
            f"/cluster-snapshots/{snapshot_id}/clusters/{cluster_id}/members"
        )
        self._check(resp)
        return resp.json()

    async def aclose(self) -> None:
        """Close the underlying httpx client and release connections."""
        await self._client.aclose()
