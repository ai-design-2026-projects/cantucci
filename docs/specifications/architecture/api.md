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

**`LoginRequest`** (body for `/auth/login` and `/auth/register`):

| Field | Type | Notes |
|---|---|---|
| `email` | `string` | Valid email address |
| `password` | `string` | Minimum 8 characters |

**`LoginResponse`**:

| Field | Type | Notes |
|---|---|---|
| `token` | `string` | Signed JWT; include as `Authorization: Bearer <token>` |
| `user` | `User` | |

**`User`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `email` | `string` | |
| `role` | `string` | `"user"` or `"admin"` |

**Admin accounts** — `POST /auth/register` always assigns the `user` role; there is no
API endpoint that can create an `admin` account. Admin users must be bootstrapped via the
CLI script:

```bash
python -m db.create_user --role admin
```

This is intentional: keeping privileged account creation off the HTTP surface eliminates
the attack vector of an unauthenticated caller escalating to admin.

---

### Conversations — `/conversations`

A conversation is one clustering session. It points at a `current_cluster_snapshot_id` (NULL = the
unclustered state) and tracks accumulated LLM cost.

| Method | Path | Level | Description |
|---|---|---|---|
| `POST` | `/conversations` | public or user | Create a new conversation (201). Anonymous is allowed; if authenticated, it is owned by the caller. Returns a `ConversationDto` with an empty `messages` list. |
| `GET` | `/conversations` | user | List all conversations owned by the authenticated user, newest first. Each item includes all messages. Returns 401 if anonymous. |
| `GET` | `/conversations/{conversation_id}` | public | Fetch a conversation with all its messages. Returns 404 if not found. |
| `PATCH` | `/conversations/{conversation_id}` | public | Set the active cluster snapshot (undo / branch navigation); records a `conversation_snapshot_refs` entry. Pass `null` to detach. Returns 404 if the conversation is missing, 404 (`ClusterSnapshotNotFound`) if the snapshot is missing. |
| `POST` | `/conversations/{conversation_id}/messages` | public or user | Submit a user message; runs the Coordinator pipeline and returns the assistant reply plus the new snapshot id. Returns 404 if the conversation is missing. |
| `DELETE` | `/conversations/{conversation_id}` | user | Delete a conversation and its child data (204). Returns 401 if anonymous, 403 (`NotConversationOwner`) if not owned, 404 if not found. |
| `GET` | `/conversations/{conversation_id}/events` | public | Open a Server-Sent Events stream of real-time turn progress. One stream per conversation; the client opens it once and receives step events for subsequent turns. |
| `GET` | `/conversations/{conversation_id}/snapshot-graph` | public | Return all snapshot nodes touched by a conversation as a `ClusterSnapshotGraphDto` — for evolution-graph visualisation. |

**`ConversationDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `current_cluster_snapshot_id` | `uuid \| null` | `null` = unclustered state |
| `messages` | `list[MessageDto]` | All messages, oldest first |
| `created_at` | `datetime` | UTC ISO-8601 |

**`UpdateConversationRequest`** (body for `PATCH /conversations/{id}`):

| Field | Type | Notes |
|---|---|---|
| `current_cluster_snapshot_id` | `uuid \| null` | Pass `null` to detach from any snapshot |

**`SendMessageRequest`** (body for `POST /conversations/{id}/messages`): `{ "content": "..." }`

**`MessageDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `role` | `string` | `"user"` or `"assistant"` |
| `content` | `string` | |
| `created_at` | `datetime` | UTC ISO-8601 |
| `suggestion` | `string \| null` | Follow-up suggestion; non-null only on assistant replies after a state-changing operation |
| `axis_concept_id` | `uuid \| null` | Concept backing a beeswarm axis proposal; non-null only on concept-clustering turns |

**`SendMessageResponse`**:

| Field | Type | Notes |
|---|---|---|
| `message` | `MessageDto` | The assistant reply |
| `cluster_snapshot_id` | `uuid \| null` | New snapshot if one was created this turn; `null` otherwise |

**`ClusterSnapshotGraphDto`** — wraps `cluster_snapshots: list[ClusterSnapshotGraphNodeDto]`.

**`ClusterSnapshotGraphNodeDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `parent_id` | `uuid \| null` | `null` for the root |
| `operation` | `string` | |
| `created_at` | `datetime` | UTC ISO-8601 |
| `params` | `object` | Replayability parameters (operation inputs) |
| `resolved_cluster_labels` | `object` | Labels keyed by cluster UUID string; used to build display names in the Evolution Map |

**Progress stream** (`GET /conversations/{id}/events`, `text/event-stream`) — one SSE
event per pipeline step:
```
event: step
data: {"step": "intent"}

event: step
data: {"step": "clustering"}

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

**`UmapPointDto`** (returned by `GET /movies/umap-points`):

| Field | Type |
|---|---|
| `movie_id` | `int` |
| `title` | `string` |
| `umap_x` | `float` |
| `umap_y` | `float` |

**`MovieBatchRequest`** (body for `POST /movies/batch`): `{ "ids": [603, 604, ...] }` (max 200).

**`MovieDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `int` | TMDB movie ID |
| `title` | `string` | |
| `release_year` | `int \| null` | |
| `runtime` | `float \| null` | Minutes |
| `vote_average` | `float \| null` | TMDB mean rating 0–10 |
| `vote_count` | `int \| null` | |
| `bayesian_rating` | `float \| null` | Smoothed rating; preferred ranking signal |
| `overview` | `string \| null` | Plot synopsis |
| `poster_url` | `string \| null` | Full TMDB URL (`https://image.tmdb.org/t/p/w500{path}`) |
| `genres` | `list[string]` | Genre names |
| `director` | `string \| null` | |
| `top_cast` | `list[string]` | Up to 3 top-billed cast names |
| `original_language` | `string \| null` | ISO 639-1 code |
| `trailer_youtube_key` | `string \| null` | YouTube video key |
| `umap_x` | `float \| null` | UMAP 2D x-coordinate |
| `umap_y` | `float \| null` | UMAP 2D y-coordinate |

---

### Cluster snapshots — `/cluster-snapshots`

The cluster-snapshot tree. All reads and deletes are public (no authentication required). Snapshot DTOs carry
the operation, replay params, config hash, the cluster list, and (for the full snapshot) argmax
member assignments.

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/cluster-snapshots/{cluster_snapshot_id}` | public | Return a snapshot with its full cluster list and argmax members. Returns 404 if not found. |
| `DELETE` | `/cluster-snapshots/{cluster_snapshot_id}` | public | Delete a **leaf** snapshot. Conversations pointing at it are reparented to its parent (or NULL for root). Returns 404 if missing, 409 (`SnapshotHasChildren`) if it still has children. |
| `GET` | `/cluster-snapshots/{cluster_snapshot_id}/clusters/{cluster_id}/members` | public | Return all movie memberships in a cluster, ordered by descending probability. Validates the cluster belongs to the snapshot (404 otherwise). |

**`ClusterSnapshotDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `parent_id` | `uuid \| null` | `null` for the root snapshot |
| `operation` | `string` | Operation that produced this snapshot |
| `params` | `object` | Replayability parameters |
| `config_hash` | `string` | SHA-256 prefix of the YAML config |
| `clusters` | `list[ClusterDto]` | |
| `members` | `list[SnapshotMemberDto]` | Argmax per-movie cluster assignments |
| `created_at` | `datetime` | UTC ISO-8601 |

**`ClusterDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `label` | `string \| null` | Human-readable label |
| `summary` | `string \| null` | One-sentence description |
| `exemplar_movie_ids` | `list[int]` | Top movie IDs by probability |
| `parent_cluster_id` | `uuid \| null` | Source cluster UUID for drill-downs |
| `color_slot` | `int` | Stable integer for golden-angle colour assignment |

**`SnapshotMemberDto`**:

| Field | Type | Notes |
|---|---|---|
| `movie_id` | `int` | TMDB movie ID |
| `title` | `string` | |
| `umap_x` | `float` | |
| `umap_y` | `float` | |
| `cluster_id` | `uuid` | Highest-probability cluster for this movie |
| `probability` | `float` | Argmax membership probability |

**`ClusterMembershipDto`**:

| Field | Type |
|---|---|
| `movie_id` | `int` |
| `probability` | `float` |

---

### Concepts — `/concepts`

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/concepts/{concept_id}/axis` | public | Return the distribution of movies along a concept's linear axis. Scores are normalised to [-1, 1]. Returns 404 if the concept does not exist. |

**`AxisDistributionDto`**:

| Field | Type | Notes |
|---|---|---|
| `concept_id` | `uuid` | |
| `concept_name` | `string` | e.g. `"open-ended ending"` |
| `positive_label` | `string` | Label for the high (+1) end |
| `negative_label` | `string` | Label for the low (−1) end |
| `points` | `list[AxisPointDto]` | Ordered by ascending score |

**`AxisPointDto`**:

| Field | Type | Notes |
|---|---|---|
| `movie_id` | `int` | |
| `title` | `string` | |
| `score` | `float` | Normalised to [−1, 1] |
| `vote_count` | `int` | TMDB vote count |

---

### Eval — `/eval`

All eval routes require an admin-scoped JWT, used in the admin dashboard frontend.

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/eval/runs` | admin | Paginated list of eval runs, newest first. Query params: `limit` (default 50), `offset` (default 0). |
| `GET` | `/eval/runs/{run_id}` | admin | Return a single eval run by ID. Returns 404 if not found. |
| `GET` | `/eval/runs/{run_id}/aggregate` | admin | Return a run with per-session metrics, latest judge scores per dimension, and summary KPIs. Returns 404 if not found. |
| `GET` | `/eval/runs/{run_id}/sessions` | admin | Return all eval sessions for a run. |
| `GET` | `/eval/sessions/{session_id}` | admin | Return full detail for a single eval session: metrics, judge scores, and per-turn intent records. Returns 404 if not found. |
| `GET` | `/eval/ground-truths` | admin | Return all ground truth trajectories. |
| `GET` | `/eval/personas` | admin | Return all evaluation personas. |

**`RunDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `name` | `string \| null` | Optional human-readable label |
| `condition` | `string` | Experimental condition (`conversational`, `baseline`, `human`) |
| `model_version` | `string \| null` | Model tier string from config |
| `config_hash` | `string` | SHA-256 8-char prefix of the YAML config |
| `seed` | `int` | Top-level RNG seed |
| `status` | `string` | Run lifecycle status |
| `notes` | `string \| null` | Optional free-text notes |
| `started_at` | `datetime` | UTC ISO-8601 |
| `ended_at` | `datetime \| null` | `null` while active |

**`PersonaDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `slug` | `string` | Unique slug |
| `verbosity` | `string` | `"terse"`, `"medium"`, or `"verbose"` |
| `patience` | `float` | Patience level in [0, 1] |
| `created_at` | `datetime` | UTC ISO-8601 |

**`GroundTruthDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `slug` | `string` | Unique slug |
| `version` | `int` | Schema version number |
| `intent_description` | `string` | Natural-language paraphrase of the trajectory intent |
| `operations` | `list[object]` | Ordered list of `{op, concept}` dicts |
| `prompt_hash` | `string` | SHA-256 of the GT builder prompts |
| `created_at` | `datetime` | UTC ISO-8601 |

**`EvalSessionDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `run_id` | `uuid` | Parent run |
| `conversation_id` | `uuid` | Linked conversation |
| `seed` | `int` | Per-session RNG seed |
| `condition` | `string` | Experimental condition |
| `status` | `string` | Session lifecycle status |
| `oracle_rating` | `int \| null` | 1–5 oracle self-rating; `null` for human sessions |
| `termination_rationale` | `string \| null` | Free-text oracle rationale |
| `created_at` | `datetime` | UTC ISO-8601 |

**`EvalSessionDetailDto`** — extends `EvalSessionDto` with:

| Field | Type | Notes |
|---|---|---|
| `metrics` | `ConversationMetricsDto \| null` | `null` if not yet computed |
| `judge_scores` | `list[JudgeScoreDto]` | All judge dimension scores for this session |
| `turn_intents` | `list[TurnIntentDto]` | Ordered per-turn intent records |
| `persona` | `PersonaDto \| null` | `null` for sessions created before this field was added |
| `ground_truth` | `GroundTruthDto \| null` | `null` for human sessions or old sessions |

**`TurnIntentDto`**:

| Field | Type | Notes |
|---|---|---|
| `id` | `uuid` | |
| `turn_number` | `int` | 1-based turn ordinal |
| `mode` | `string` | `NavigationMode` or `DialogueMode` value |
| `concept` | `string \| null` | Semantic concept, if any |
| `confidence` | `float` | Classified confidence score |
| `clarifier_fired` | `bool` | `true` if the clarifier gate fired this turn |
| `created_at` | `datetime` | UTC ISO-8601 |

**`ConversationMetricsDto`**:

| Field | Type | Notes |
|---|---|---|
| `final_num_clusters` | `int` | Number of clusters at session end |
| `clarifier_trigger_rate` | `float \| null` | Rate of turns that triggered the clarifier |
| `num_turns` | `int` | Total oracle turns |
| `num_operations` | `int` | Total `NavigationMode` operations recorded |
| `total_cost_usd` | `float` | Total LLM cost in USD |
| `computed_at` | `datetime` | UTC ISO-8601 |

**`JudgeScoreDto`**:

| Field | Type | Notes |
|---|---|---|
| `dimension` | `string` | Judge dimension name |
| `score` | `int` | Score in [1, 5] |
| `judge_model` | `string` | Model identifier used for scoring |
| `judge_prompt_hash` | `string` | SHA-256 of the rendered judge prompt |
| `rationale` | `string \| null` | One-sentence rationale from the judge |
| `created_at` | `datetime` | UTC ISO-8601 |

**`RunAggregateDto`** (returned by `GET /eval/runs/{id}/aggregate`):

| Field | Type | Notes |
|---|---|---|
| `run` | `RunDto` | Parent run metadata |
| `config_snapshot` | `object` | Full YAML config dict stored for replay |
| `sessions` | `list[SessionAggregateRowDto]` | One entry per eval session |
| `summary` | `RunAggregateSummaryDto` | Convenience KPI aggregate |

**`SessionAggregateRowDto`**:

| Field | Type | Notes |
|---|---|---|
| `eval_session_id` | `uuid` | |
| `conversation_id` | `uuid` | |
| `persona_id` | `uuid \| null` | `null` for human sessions |
| `ground_truth_id` | `uuid \| null` | `null` for human sessions |
| `status` | `string` | Session lifecycle status |
| `oracle_rating` | `int \| null` | 1–5 self-rating; `null` for human sessions |
| `termination_rationale` | `string \| null` | |
| `created_at` | `datetime` | UTC ISO-8601 |
| `metrics` | `SessionMetricsDto \| null` | `null` if not yet computed |
| `judge_scores` | `list[JudgeScoreDto]` | Latest score per dimension |
| `persona_slug` | `string \| null` | |
| `persona_verbosity` | `string \| null` | |
| `persona_patience` | `float \| null` | |
| `mean_confidence` | `float \| null` | Mean turn-intent confidence for this session |
| `ground_truth_slug` | `string \| null` | |

**`SessionMetricsDto`**:

| Field | Type | Notes |
|---|---|---|
| `final_num_clusters` | `int \| null` | |
| `clarifier_trigger_rate` | `float \| null` | |
| `num_turns` | `int` | |
| `num_operations` | `int` | |
| `total_cost_usd` | `float` | |
| `computed_at` | `datetime` | UTC ISO-8601 |

**`RunAggregateSummaryDto`**:

| Field | Type | Notes |
|---|---|---|
| `n_sessions` | `int` | Total sessions in the run |
| `n_completed` | `int` | Sessions with a terminal completed status |

---

### Status codes & error cases

| Code | Raised by | Examples |
|---|---|---|
| `200` | success | GET/PATCH, `POST /conversations/{id}/messages` |
| `201` | success | `POST /auth/register`, `POST /conversations` |
| `204` | success | `POST /auth/logout`, `DELETE /conversations/{id}`, `DELETE /cluster-snapshots/{id}` |
| `401` | `AuthError` (`InvalidToken`, `TokenExpired`) / `HTTPException(401)` | bad credentials at login, anonymous caller on `/auth/me` or list/delete conversations |
| `403` | `ForbiddenError` (`NotConversationOwner`) | deleting a conversation you don't own |
| `404` | `NotFoundError` family | `ConversationNotFound`, `ClusterSnapshotNotFound`, `MovieNotFound`, `ConceptNotFound`, `RunNotFound`, `EvalSessionNotFound`, cluster-not-in-snapshot |
| `409` | `ConflictError` (`SnapshotHasChildren`) / `HTTPException(409)` | `SnapshotHasChildren` on snapshot delete; duplicate email on register |
| `422` | `ParseError` (`ConceptParseError`) | coordinator cannot parse a concept |
| `500` | `OperationalError` family | `CostLimitExceeded`, `LLMParseError`, `ReplayDriftError` |

---

## MCP server

`mcp_server/` is a FastMCP server (entry point `mcp_server/server.py`) that runs over **stdio** and
wraps the HTTP API one-to-one. It holds no state of its own. Four domain clients —
`ConversationsClient`, `ClusterSnapshotsClient`, `MoviesClient`, `ConceptsClient` — each
subclass `BaseClient` (`mcp_server/clients/http.py`) and share one injected `httpx.AsyncClient`
pool wired in `server.py`. The backend URL is configured with `CINEPAL_MCP_BACKEND_URL`
(default `http://localhost:8000`).

All capabilities are exposed as **tools** (no MCP Resources). All tools work in anonymous mode.

### Conversation tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `create_conversation()` | — | `POST /conversations` | Start an anonymous conversation. Returns the conversation ID needed for all subsequent calls. |
| `send_message(conversation_id, content)` | 2 | `POST /conversations/{id}/messages` | Submit an oracle message; returns the assistant reply + updated snapshot id. |
| `get_conversation(conversation_id)` | 1 | `GET /conversations/{id}` | Fetch a conversation with all its messages and the current active snapshot ID. |
| `navigate_to_snapshot(conversation_id, snapshot_id)` | 2 | `PATCH /conversations/{id}` | Undo / branch to a past snapshot. |
| `get_snapshot_graph(conversation_id)` | 1 | `GET /conversations/{id}/snapshot-graph` | Fetch the full DAG of all snapshots touched by a conversation. |

### Cluster snapshot tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `get_snapshot(snapshot_id)` | 1 | `GET /cluster-snapshots/{id}` | A snapshot with its cluster list. `members` (per-movie UMAP data) is stripped before returning — too large for the protocol. |
| `get_cluster_members(snapshot_id, cluster_id)` | 2 | `GET /cluster-snapshots/{sid}/clusters/{cid}/members` | All movies in a cluster with soft membership probabilities, ordered descending. |

### Movie tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `get_movie(movie_id)` | 1 | `GET /movies/{id}` | Full metadata for a single movie by TMDB ID. |
| `get_movies_batch(movie_ids)` | 1 | `POST /movies/batch` | Full metadata for up to 200 movies in one call — efficient when inspecting cluster contents. |

### Concept tools

| Tool | Args | Backend call | Notes |
|---|---|---|---|
| `get_concept_axis(concept_id)` | 1 | `GET /concepts/{id}/axis` | Returns `concept_id`, `concept_name`, `positive_label`, `negative_label`, and `points` (list of `{movie_id, title, score, vote_count}` ordered by ascending score). |

### Excluded endpoints

Hard deletes (`DELETE /conversations/{id}`, `DELETE /cluster-snapshots/{id}`), the SSE progress
stream (`GET /conversations/{id}/events`), UMAP points (`GET /movies/umap-points`), auth
endpoints, per-user history, and all `/eval/*` routes are intentionally not exposed.
