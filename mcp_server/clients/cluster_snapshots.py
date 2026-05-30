from mcp_server.clients.http import BaseClient


class ClusterSnapshotsClient(BaseClient):
    """HTTP client for the /cluster-snapshots domain.

    All methods map 1-to-1 to backend routes under the ``/cluster-snapshots``
    prefix. Non-2xx responses are raised as ``BackendError``.
    """

    async def get_root_snapshot(self) -> dict:
        """GET /cluster-snapshots/get_root — most recent corpus-level snapshot.

        Returns:
            ``ClusterSnapshotDto`` dict with the root snapshot and its clusters.
        """
        resp = await self._http.get("/cluster-snapshots/get_root")
        self._check(resp)
        return resp.json()

    async def get_snapshot(self, snapshot_id: str) -> dict:
        """GET /cluster-snapshots/get/{id} — fetch a snapshot with its full cluster list.

        Each cluster includes its label, one-sentence summary, top exemplar
        movie IDs, parent cluster ID (for drill-downs), and member count.

        Args:
            snapshot_id: Cluster snapshot UUID string.

        Returns:
            ``ClusterSnapshotDto`` dict with id, operation, params, clusters, and created_at.
        """
        resp = await self._http.get(f"/cluster-snapshots/get/{snapshot_id}")
        self._check(resp)
        return resp.json()

    async def get_cluster_members(self, snapshot_id: str, cluster_id: str) -> list:
        """GET /cluster-snapshots/cluster_members/{sid}/{cid} — all movie memberships.

        Args:
            snapshot_id: Cluster snapshot UUID string.
            cluster_id:  Cluster UUID string within that snapshot.

        Returns:
            List of ``ClusterMembershipDto`` dicts with movie_id and probability,
            ordered by probability descending.
        """
        resp = await self._http.get(
            f"/cluster-snapshots/cluster_members/{snapshot_id}/{cluster_id}"
        )
        self._check(resp)
        return resp.json()
