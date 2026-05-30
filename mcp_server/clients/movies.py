from mcp_server.clients.http import BaseClient


class MoviesClient(BaseClient):
    """HTTP client for the /movies domain.

    All methods map 1-to-1 to backend routes under the ``/movies`` prefix.
    Non-2xx responses are raised as ``BackendError``.
    """

    async def get_movie(self, movie_id: int) -> dict:
        """GET /movies/get/{id} — full metadata for one movie by TMDB ID.

        Args:
            movie_id: Integer TMDB movie ID.

        Returns:
            ``MovieDto`` dict with title, overview, genres, release_year, and more.
        """
        resp = await self._http.get(f"/movies/get/{movie_id}")
        self._check(resp)
        return resp.json()

    async def get_movies_batch(self, movie_ids: list[int]) -> list:
        """POST /movies/get_batch — full metadata for up to 200 movies in one call.

        Args:
            movie_ids: List of up to 200 integer TMDB movie IDs.

        Returns:
            List of ``MovieDto`` dicts.
        """
        resp = await self._http.post("/movies/get_batch", json={"ids": movie_ids})
        self._check(resp)
        return resp.json()
