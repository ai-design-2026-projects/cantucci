import httpx
from mcp.server.fastmcp import FastMCP

import mcp_server.capabilities.cluster_snapshots as cap_cluster_snapshots
import mcp_server.capabilities.concepts as cap_concepts
import mcp_server.capabilities.conversations as cap_conversations
import mcp_server.capabilities.movies as cap_movies
from mcp_server.clients.cluster_snapshots import ClusterSnapshotsClient
from mcp_server.clients.concepts import ConceptsClient
from mcp_server.clients.conversations import ConversationsClient
from mcp_server.clients.movies import MoviesClient
from mcp_server.settings import get_settings

mcp = FastMCP("CinePal")

_settings = get_settings()
_http = httpx.AsyncClient(base_url=_settings.backend_url, timeout=_settings.timeout)

cap_conversations.register(mcp, ConversationsClient(_http))
cap_cluster_snapshots.register(mcp, ClusterSnapshotsClient(_http))
cap_movies.register(mcp, MoviesClient(_http))
cap_concepts.register(mcp, ConceptsClient(_http))


def main() -> None:
    """Entry point for the CinePal MCP server.

    Runs the server over stdio, which is the standard transport for
    Claude Desktop and other MCP hosts. Configure the backend URL via
    the ``CINEPAL_MCP_BACKEND_URL`` environment variable (default:
    ``http://localhost:8000``).
    """
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
