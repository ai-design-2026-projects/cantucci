# CinePal MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that exposes CinePal's conversational clustering system to AI agents and Claude Desktop users.

The server wraps the CinePal FastAPI backend over HTTP — all requests flow through the existing REST API, keeping layer boundaries intact.

---

## Tools

State-changing operations callable by the MCP host.

| Tool | Description |
|---|---|
| `create_conversation` | Start a new anonymous clustering session. Returns the conversation ID needed for all subsequent calls. |
| `send_message` | Submit an oracle message and receive the AI reply + updated cluster snapshot ID. |
| `delete_conversation` | Delete a conversation. **Requires auth** — returns 401 in anonymous mode. |
| `navigate_to_snapshot` | Set the active cluster snapshot (undo / branch). **Requires auth** — returns 401 in anonymous mode. |

## Resources

Read-only, URI-addressable data sources.

| URI | Description |
|---|---|
| `conversation://{conversation_id}` | Conversation with up to 20 recent messages and current snapshot ID. |
| `snapshot://{snapshot_id}` | Cluster snapshot with full cluster list (labels, summaries, exemplar movie IDs, member count). |
| `snapshot-graph://{conversation_id}` | Full DAG of all snapshots touched by a conversation — use to find past snapshot IDs for `navigate_to_snapshot`. |
| `cluster-members://{snapshot_id}/{cluster_id}` | All movies in a cluster with their soft membership probabilities, ordered descending. |

---

## Configuration

| Environment variable | Default | Description |
|---|---|---|
| `CINEPAL_MCP_BACKEND_URL` | `http://localhost:8000` | Base URL of the CinePal FastAPI backend. |
| `CINEPAL_MCP_TIMEOUT` | `30.0` | HTTP request timeout in seconds. |

---

## Running

Make sure the CinePal backend is running first:

```bash
uv run uvicorn backend.app:app --reload
```

Then run the MCP server:

```bash
uv run cinepal-mcp
```

The server communicates over stdio (standard for MCP hosts).

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cinepal": {
      "command": "uv",
      "args": ["run", "cinepal-mcp"],
      "cwd": "/absolute/path/to/cantucci"
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Anonymous mode limitations

The server operates anonymously by default (no JWT). Two tools require auth on the backend:

- `delete_conversation` — calls `DELETE /conversations/{id}`, which requires a logged-in user.
- `navigate_to_snapshot` — calls `PATCH /conversations/{id}`, which requires a logged-in user.

Both will return a descriptive error if called without auth. The remaining two tools and all four resources work fully in anonymous mode.
