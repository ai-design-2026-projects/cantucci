from mcp.server.fastmcp import FastMCP

from mcp_server.client import CinePalClient
from mcp_server.resources import register_resources
from mcp_server.tools import register_tools

mcp = FastMCP("CinePal")

_client = CinePalClient()
register_tools(mcp, _client)
register_resources(mcp, _client)


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
