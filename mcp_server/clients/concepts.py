from mcp_server.clients.http import BaseClient


class ConceptsClient(BaseClient):
    """HTTP client for the /concepts domain.

    All methods map 1-to-1 to backend routes under the ``/concepts`` prefix.
    Non-2xx responses are raised as ``BackendError``.
    """

    async def get_concept_axis(self, concept_id: str) -> dict:
        """GET /concepts/{id}/axis — distribution of movies along a concept axis.

        Returns the movie distribution along the concept's linear axis in [-1, 1],
        where -1 is the negative pole and +1 is the positive pole.

        Args:
            concept_id: Concept UUID string.

        Returns:
            ``AxisDistributionDto`` dict with concept_id, concept_name, positive_label,
            negative_label, and a points list ordered by ascending score.
        """
        resp = await self._http.get(f"/concepts/{concept_id}/axis")
        self._check(resp)
        return resp.json()
