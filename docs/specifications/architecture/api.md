# Public API and Internal Interfaces

Named contracts between modules: inputs, outputs, error cases. These are the
handoffs that multi-person work depends on. The HTTP API is served by FastAPI
(`backend/app.py`); an optional MCP server (`mcp_server/`) wraps it for LLM hosts.

---

## HTTP API

Base URL: `http://localhost:8000` (dev). Interactive docs at `/docs`.

Routers registered in `backend/app.py`: `auth`, `movies`, `conversations`,
`cluster-snapshots`, `concepts`, `eval`.

**Access levels**

| Level | Description |
|---|---|
| `public` | No authentication required. |
| `user` | Valid JWT required — via `Authorization: Bearer <token>` header or `auth_token` HttpOnly cookie. Resolved by `get_current_user` in `backend/routers/auth_deps.py`. |
| `admin` | Admin-scoped JWT required. Resolved by `require_admin` in `backend/routers/auth_deps.py`. Used exclusively by `/eval/*` routes. |

Domain errors are raised as `DomainError` subclasses and translated to JSON `{"detail": ...}` by
the global handler in `backend/app.py`, using each exception's `http_status`.

---

### Auth — `/auth`

| Method | Path | Level | Description |
|---|---|---|---|
| `POST` | `/auth/login` | public | Verify credentials. Returns a signed JWT and sets an HttpOnly cookie. Returns 401 on bad credentials. |
| `POST` | `/auth/register` | public | Create a new account with the `user` role. Returns 201 with a signed JWT and sets an HttpOnly cookie. Returns 409 if the email is already registered. |
| `POST` | `/auth/logout` | public | Clears the `auth_token` cookie (204). No server-side token revocation. |
| `GET` | `/auth/me` | user | Return the currently authenticated user (`id`, `email`, `role`). Returns 401 if anonymous. |

**Request body** (`LoginRequest`, used by `/auth/login` and `/auth/register`):
```json
{ "email": "user@example.com", "password": "at-least-8-chars" }
```

**Response** (`LoginResponse`):
```json
{ "token": "<jwt>", "user": { "id": "<uuid>", "email": "...", "role": "user" } }
```

---

### Conversations — `/conversations`

A conversation is one clustering session. It points at a `current_cluster_snapshot_id` (NULL = the
unclustered state) and tracks accumulated LLM cost.

| Method | Path | Level | Description |
|---|---|---|---|
| `POST` | `/conversations` | public or user | Create a new conversation (201). Anonymous is allowed; if authenticated, it is owned by the caller. Returns a `ConversationDto` with an empty `messages` list. |
| `GET` | `/conversations` | user | List all conversations owned by the authenticated user, newest first. Each item includes all messages. Returns 401 if anonymous. |
| `GET` | `/conversations/{conversation_id}` | public | Fetch a conversation with up to 20 most recent messages. Returns 404 if not found. |
| `PATCH` | `/conversations/{conversation_id}` | user | Set the active cluster snapshot (undo / branch navigation); records a `conversation_snapshot_refs` entry. Returns 401 if anonymous, 404 if the conversation is missing, 404 (`ClusterSnapshotNotFound`) if the snapshot is missing. |
| `POST` | `/conversations/{conversation_id}/messages` | public or user | Submit a user message; runs the Coordinator pipeline and returns the assistant reply plus the new snapshot id. Returns 404 if the conversation is missing. |
| `DELETE` | `/conversations/{conversation_id}` | user | Delete a conversation and its child data (204). Returns 401 if anonymous, 403 (`NotConversationOwner`) if not owned, 404 if not found. |
| `GET` | `/conversations/{conversation_id}/events` | public | Open a Server-Sent Events stream of real-time turn progress. One stream per conversation; the client opens it once and receives step events for subsequent turns. |
| `GET` | `/conversations/{conversation_id}/snapshot-graph` | public | Return all snapshot nodes touched by a conversation as a DAG (id, parent_id, operation, created_at) — for force-graph visualisation. |

**Send-message request body** (`SendMessageRequest`):
```json
{ "content": "split the noir cluster by tone" }
```

**Send-message response** (`SendMessageResponse`) — synchronous JSON, not a stream:
```json
{
  "message": {
    "id": "<uuid>", "role": "assistant", "content": "...",
    "created_at": "...", "suggestion": "... or null",
    "axis_concept_id": "<uuid> or null"
  },
  "cluster_snapshot_id": "<uuid> or null"
}
```
`suggestion` is present only on assistant replies produced after a state-changing operation; it is
`null` for clarifications, small-talk, and explanations. `axis_concept_id` is set when the reply
attaches a linear-axis concept for the drill-down view.

**Progress stream** (`GET /conversations/{id}/events`, `text/event-stream`) — one SSE
event per pipeline step:
```
event: step
data: {"step": "intent", ...}

event: step
data: {"step": "clustering", ...}

event: turn_done
data: {}
```
Step names: `labeling`, `intent`, `clarifier`, `concept`, `clustering`, `explain`, `suggester`,
then the terminal `turn_done`. A `: heartbeat` comment line is sent every 15s of inactivity.

---

### Movies — `/movies`

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/movies/{movie_id}` | public | Return full metadata for a single TMDB film. Returns 404 if the ID is not in the catalogue. |
| `GET` | `/movies/umap-points` | public | Return UMAP 2D coordinates for all catalogued movies. |
| `POST` | `/movies/batch` | public | Return metadata for up to 200 movies in one request. Preserves input order; unknown IDs are silently dropped. |

**Batch request body** (`MovieBatchRequest`): `{ "ids": [603, 604, ...] }` (max 200).

**`MovieDto`** fields: `id`, `title`, `release_year`, `runtime`, `vote_average`, `vote_count`,
`bayesian_rating`, `overview`, `poster_url` (full TMDB URL), `genres` (names), `director`,
`top_cast` (≤3), `original_language`, `trailer_youtube_key`, `umap_x`, `umap_y`.

---

### Cluster snapshots — `/cluster-snapshots`

The cluster-snapshot tree. Mostly public reads; deletion requires authentication. Snapshot DTOs carry
the operation, replay params, config hash, the cluster list, and (for the full snapshot) argmax
member assignments.

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/cluster-snapshots/{cluster_snapshot_id}` | public | Return a snapshot with its full cluster list and argmax members. Returns 404 if not found. |
| `DELETE` | `/cluster-snapshots/{cluster_snapshot_id}` | user | Delete a **leaf** snapshot. Conversations pointing at it are reparented to its parent (or NULL for root). Returns 401 if anonymous, 404 if missing, 409 (`SnapshotHasChildren`) if it still has children. |
| `GET` | `/cluster-snapshots/{cluster_snapshot_id}/clusters/{cluster_id}/members` | public | Return all movie memberships in a cluster, ordered by descending probability. Validates the cluster belongs to the snapshot (404 otherwise). |

**DTOs**: `ClusterSnapshotDto` (`id`, `parent_id`, `operation`, `params`, `config_hash`,
`clusters`, `members`, `created_at`), `ClusterDto` (`id`, `label`, `summary`,
`exemplar_movie_ids`, `parent_cluster_id`, `color_slot`), `SnapshotMemberDto` (`movie_id`, `title`,
`umap_x`, `umap_y`, `cluster_id`, `probability`), `ClusterMembershipDto` (`movie_id`,
`probability`), `ClusterSnapshotGraphDto` (`cluster_snapshots`: list of node dicts).

---

### Concepts — `/concepts`

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/concepts/{concept_id}/axis` | public | Return the distribution of movies along a concept's linear axis. Scores are normalised to [-1, 1]. Returns 404 if the concept does not exist. |

**`AxisDistributionDto`** fields: `concept_id`, `concept_name`, `positive_label`,
`negative_label`, `points` (list of `AxisPointDto`: `movie_id`, `title`, `score`,
`vote_count`), ordered by ascending score.

---

### Eval — `/eval`

All eval routes require an admin-scoped JWT and are not intended for frontend consumption.

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/eval/runs` | admin | Paginated list of eval runs, newest first. Query params: `limit` (default 50), `offset` (default 0). |
| `GET` | `/eval/runs/{run_id}` | admin | Return a single eval run by ID. Returns 404 if not found. |
| `GET` | `/eval/runs/{run_id}/aggregate` | admin | Return a run with per-session metrics, latest judge scores per dimension, and summary KPIs. Returns 404 if not found. |
| `GET` | `/eval/runs/{run_id}/sessions` | admin | Return all eval sessions for a run. |
| `GET` | `/eval/sessions/{eval_session_id}` | admin | Return full detail for a single eval session: metrics, judge scores, and per-turn intent records. Returns 404 if not found. |
| `GET` | `/eval/ground-truths` | admin | Return all ground truth trajectories. |
| `GET` | `/eval/personas` | admin | Return all evaluation personas. |

---

### Status codes & error cases

| Code | Raised by | Examples |
|---|---|---|
| `200` | success | GET/PATCH, `POST /conversations/{id}/messages` |
| `201` | success | `POST /auth/register`, `POST /conversations` |
| `204` | success | `POST /auth/logout`, `DELETE /conversations/{id}`, `DELETE /cluster-snapshots/{id}` |
| `401` | `AuthError` / anonymous | `/auth/me`, list/patch/delete conversations, delete snapshot |
| `403` | `NotConversationOwner` | deleting a conversation you don't own |
| `404` | `NotFoundError` family | `ConversationNotFound`, `ClusterSnapshotNotFound`, `MovieNotFound`, `ConceptNotFound`, cluster-not-in-snapshot |
| `409` | `ConflictError` family | `register` email taken, `SnapshotHasChildren` |
| `422` | `ParseError` family | coordinator cannot process a message |
| `500` | `OperationalError` family | `CostLimitExceeded`, `LLMParseError`, `ReplayDriftError` |

---

## MCP server

`mcp_server/` is a FastMCP server (entry point `mcp_server/server.py`) that runs over **stdio** and
wraps the HTTP API one-to-one via an async `CinePalClient`. It holds no state of its own. The
backend URL is configured with `CINEPAL_MCP_BACKEND_URL` (default `http://localhost:8000`).

All capabilities are exposed as **tools** (no MCP Resources). All tools work in anonymous mode.

### Conversation tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `create_conversation()` | — | `POST /conversations` | Start an anonymous conversation. Returns the conversation ID needed for all subsequent calls. |
| `send_message(conversation_id, content)` | 2 | `POST /conversations/{id}/messages` | Submit an oracle message; returns the assistant reply + updated snapshot id. |
| `get_conversation(conversation_id)` | 1 | `GET /conversations/{id}` | Fetch a conversation with up to 20 recent messages and the current active snapshot ID. |
| `navigate_to_snapshot(conversation_id, snapshot_id)` | 2 | `PATCH /conversations/{id}` | Undo / branch to a past snapshot. |
| `get_snapshot_graph(conversation_id)` | 1 | `GET /conversations/{id}/snapshot-graph` | Fetch the full DAG of all snapshots touched by a conversation. |

### Cluster snapshot tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `get_root_snapshot()` | — | `GET /cluster-snapshots/root` | The corpus-level starting snapshot. `members` (per-movie UMAP data) is stripped before returning — too large for the protocol and only needed by the frontend. |
| `get_snapshot(snapshot_id)` | 1 | `GET /cluster-snapshots/{id}` | A snapshot with its cluster list. `members` is stripped for the same reason. |
| `get_cluster_members(snapshot_id, cluster_id)` | 2 | `GET /cluster-snapshots/{sid}/clusters/{cid}/members` | All movies in a cluster with soft membership probabilities, ordered descending. |

### Movie tools

| Tool | Args | Backend call |
|---|---|---|
| `get_movie(movie_id)` | 1 | `GET /movies/{id}` |
| `get_movies_batch(movie_ids)` | 1 | `POST /movies/batch` |

### Concept tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `get_concept_axis(concept_id)` | 1 | `GET /concepts/{id}/axis` | Returns `concept_id`, `concept_name`, `positive_label`, `negative_label`, and `points` (list of `{movie_id, title, score, vote_count}` ordered by ascending score). |

### Excluded endpoints

Hard deletes (`DELETE /conversations/{id}`, `DELETE /cluster-snapshots/{id}`), the SSE progress
stream (`GET /conversations/{id}/events`), auth endpoints, per-user history, and all
`/eval/*` routes are intentionally not exposed.
