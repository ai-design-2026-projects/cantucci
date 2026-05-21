# Public API and Internal Interfaces

Named contracts between modules: inputs, outputs, error cases. These are the
handoffs that ablation and multi-person work depend on. Each section covers one
agent or layer.

---

## HTTP API

Base URL: `http://localhost:8000` (dev). Interactive docs at `/docs`.

**Access levels**

| Level | Description |
|---|---|
| `public` | No authentication required. |
| `user` | Valid JWT required — via `Authorization: Bearer <token>` header or `auth_token` HttpOnly cookie. |
| `admin` | JWT required with `role = admin`. Admin accounts are provisioned via `python -m db.create_user --role admin`. |

---

### Auth — `/auth`

| Method | Path | Level | Description |
|---|---|---|---|
| `POST` | `/auth/register` | public | Create a new account with the `user` role. Returns a signed JWT and sets an HttpOnly cookie. Returns 409 if the email is already registered. |
| `POST` | `/auth/login` | public | Verify credentials. Returns a signed JWT and sets an HttpOnly cookie. Returns 401 on bad credentials. |
| `POST` | `/auth/logout` | public | Clears the `auth_token` cookie. No server-side token revocation. |
| `GET` | `/auth/me` | user | Return the currently authenticated user (`id`, `email`, `role`). Returns 401 if anonymous. |

**Request body** (`/auth/login`, `/auth/register`):
```json
{ "email": "user@example.com", "password": "at-least-8-chars" }
```

**Response** (`LoginResponse`):
```json
{ "token": "<jwt>", "user": { "id": "<uuid>", "email": "...", "role": "user" } }
```

---

### Sessions — `/sessions`

| Method | Path | Level | Description |
|---|---|---|---|
| `POST` | `/sessions` | public | Create a new session. Returns a `SessionDto` with `status=active` and an empty turn list. The `session_id` is used in subsequent turn requests. |
| `GET` | `/sessions/list` | user | List all sessions owned by the authenticated user, newest first. Returns `turns=[]` on each item. Returns 401 if anonymous. |
| `GET` | `/sessions/{session_id}` | public | Fetch full session state including all turns in ascending `turn_number` order. Returns 404 if not found. |
| `POST` | `/sessions/{session_id}/turns` | public | Submit the oracle's message. Streams progress and the final result as NDJSON (`application/x-ndjson`). Returns 404 if session not found, 422 if `user_message` is empty. |
| `DELETE` | `/sessions/delete/{session_id}` | user | Delete a session and all its child data. Only the owning user may delete. Returns 204 on success, 401 if anonymous, 404 if not found or not owned by the caller. |

**Turn request body**:
```json
{ "user_message": "I want something slow and melancholic." }
```

**Turn stream format** (`application/x-ndjson`) — one JSON object per line:
```jsonc
{"type": "progress", "step": "retrieval", "phase": "start", "ts": "..."}
{"type": "cluster_snapshot", "clusters": [...]}
{"type": "result", "data": <TurnDto>}   // terminal on success
{"type": "error", "code": "...", "message": "..."}  // terminal on failure
```

---

### Movies — `/movies`

| Method | Path | Level | Description |
|---|---|---|---|
| `GET` | `/movies/get_movie/{movie_id}` | public | Return full metadata for a single TMDB film. Returns 404 if the ID is not in the catalogue. |

---

### Eval dashboard — `/eval` (admin only)

All routes require `role = admin`. Read-only — these endpoints never write to the DB.

| Method | Path | Description |
|---|---|---|
| `GET` | `/eval/runs` | List all eval runs with session counts, ordered by `started_at` descending. |
| `GET` | `/eval/runs/{run_id}` | Full run metadata plus overall aggregate metrics (95% CIs across all sessions). Returns 404 if not found. |
| `GET` | `/eval/runs/{run_id}/aggregate` | Overall `MetricBundle` for a run: Precision@K, Recall@K, NDCG@K, turns to convergence, cognitive load, cost, drift events, convergence rate, explicit acceptance rate, and three LLM-judge scores — each with 95% bootstrap CI. |
| `GET` | `/eval/runs/{run_id}/aggregate/by-persona` | Same metrics broken down per `persona_id`. Sessions with no persona are grouped under `"__none__"`. |
| `GET` | `/eval/runs/{run_id}/sessions` | Raw per-session rows (drill-down table): one entry per session with all `session_metrics` fields plus pivoted judge scores. |


