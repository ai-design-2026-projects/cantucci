import json

from mcp.server.fastmcp import FastMCP

from mcp_server.clients.movies import MoviesClient


def register(mcp: FastMCP, client: MoviesClient) -> None:
    """Register all movie tools on the given FastMCP instance.

    Args:
        mcp:    The FastMCP server instance to register tools on.
        client: The movies HTTP client used by each tool handler.
    """

    @mcp.tool()
    async def get_movie(movie_id: int) -> str:
        """Fetch full metadata for a single movie by TMDB ID.

        Use this to understand the content of a specific movie after discovering
        its ID in a cluster members list.

        Args:
            movie_id: Integer TMDB movie ID.

        Returns:
            JSON object with title, overview, genres, release_year, vote_average, and more.
        """
        result = await client.get_movie(movie_id)
        return json.dumps(result, indent=2)

    @mcp.tool()
    async def get_movies_batch(movie_ids: list[int]) -> str:
        """Fetch full metadata for up to 200 movies in a single call.

        More efficient than calling get_movie repeatedly when you need details
        for multiple movies — for example, to understand the contents of a cluster.

        Args:
            movie_ids: List of up to 200 integer TMDB movie IDs.

        Returns:
            JSON array of MovieDto objects, each with title, overview, genres,
            release_year, vote_average, and more.
        """
        result = await client.get_movies_batch(movie_ids)
        return json.dumps(result, indent=2)
