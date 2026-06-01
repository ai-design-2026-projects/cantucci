# CinePal MCP Server

An [MCP (Model Context Protocol)](https://modelcontextprotocol.io) server that exposes CinePal's conversational clustering system to AI agents and Claude Desktop users.

The server wraps the CinePal FastAPI backend over HTTP — all requests flow through the existing REST API, keeping layer boundaries intact.

All capabilities are exposed as **tools** (callable by the model autonomously), split by domain.

---

## Tools

### Conversations

| Tool | Description |
|---|---|
| `create_conversation` | Start a new anonymous clustering session. Returns the conversation ID needed for all subsequent calls. |
| `send_message` | Submit an oracle message and receive the AI reply + updated cluster snapshot ID. |
| `navigate_to_snapshot` | Set the active cluster snapshot (undo / branch navigation). Use `get_snapshot_graph` to discover past snapshot IDs. |
| `get_conversation` | Fetch a conversation with up to 20 recent messages and the current active snapshot ID. |
| `get_snapshot_graph` | Fetch the full DAG of all snapshots touched by a conversation — use to find past snapshot IDs for `navigate_to_snapshot`. |

### Cluster Snapshots

| Tool | Description |
|---|---|
| `get_snapshot` | Fetch a snapshot with its full cluster list (labels, summaries, exemplar movie IDs). Per-movie UMAP assignments are excluded; use `get_cluster_members` for memberships. |
| `get_cluster_members` | All movies in a cluster with their soft membership probabilities, ordered descending. |

### Movies

| Tool | Description |
|---|---|
| `get_movie` | Full metadata for a single movie by TMDB ID (title, overview, genres, release year, rating…). |
| `get_movies_batch` | Full metadata for up to 200 movies in one call — efficient when inspecting cluster contents. |

### Concepts

| Tool | Description |
|---|---|
| `get_concept_axis` | Distribution of movies along a concept's linear axis [-1, +1]. Returns `concept_id`, `concept_name`, `positive_label`, `negative_label`, and `points` (list of `{movie_id, title, score, vote_count}` ordered by ascending score). |

---

## What is not exposed

- **Hard deletes** — the MCP never destroys data; `DELETE /conversations/{id}` and `DELETE /cluster-snapshots/{id}` are excluded.
- **SSE progress stream** — `GET /conversations/{id}/events` doesn't fit the tool request/response model; `send_message` returns the final result directly.
- **Auth endpoints** — login, register, logout, me. The MCP runs anonymously or with a pre-configured token; auth lifecycle is not an LLM capability.
- **Per-user history** — `GET /conversations` requires user authentication, which is meaningless in anonymous mode.
- **Eval / research endpoints** — all `GET /eval/*` routes are admin-only experiment introspection, out of scope for the conversational oracle.

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
python -m uvicorn backend.app:app --reload
```

Then run the MCP server:

```bash
python -m mcp_server.server
```

Or via the console script:

```bash
cinepal-mcp
```

The server communicates over stdio (standard for MCP hosts).

### Claude Desktop

Add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or `%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "cinepal": {
      "command": "python",
      "args": ["-m", "mcp_server.server"],
      "cwd": "/absolute/path/to/cantucci"
    }
  }
}
```

Restart Claude Desktop after saving.

---

## Module layout

```
mcp_server/
  server.py                    # composition root — one shared httpx client wired into domain clients
  settings.py                  # McpSettings (CINEPAL_MCP_* env vars)
  clients/http.py              # BackendError + BaseClient (shared httpx.AsyncClient, _check())
  capabilities/                # MCP surface — @tool registrations, one module per domain
    conversations.py
    cluster_snapshots.py
    movies.py
    concepts.py
  clients/                     # HTTP transport — typed client classes, one per domain
    conversations.py
    cluster_snapshots.py
    movies.py
    concepts.py
```
