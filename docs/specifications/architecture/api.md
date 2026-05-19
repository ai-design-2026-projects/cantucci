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

---

## Retrieval System

Converts an oracle utterance or preference-profile summary into enriched film candidates via HyDE query expansion + pgvector cosine search. Entry points in `backend/retrieval/agent.py`; tools in `backend/retrieval/tools/`.

Two entry points share the same `RetrievalResult` output shape so downstream agents are unaffected by which path was used.

---

### `retrieve_from_message` — first-turn and proceed path

```python
await retrieve_from_message(
    *,
    user_query: str,
    k: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> RetrievalResult
```

LLM expands the raw oracle utterance into HyDE prose, extracts any film titles mentioned (positive or negative), fuzzy-matches them to catalogue IDs, and passes those IDs as a SQL exclusion filter before vector search. Used on the first turn and on `proceed` actions.

**Input**
| Parameter | Type | Description |
|---|---|---|
| `user_query` | `str` | Raw oracle utterance (non-empty). |
| `k` | `int` | Maximum candidates to return (must be > 0). |
| `session_id`, `run_id`, `turn_id` | `UUID` | Correlation IDs for logging. |
| `accumulated_cost_usd` | `float` | Running turn cost for the cost guard. |
| `dry_run` | `bool` | Uses canned fixture instead of a live LLM call. |

---

### `retrieve_from_profile` — drift and re-retrieve path

```python
await retrieve_from_profile(
    *,
    summary: str,
    excluded_films: list[str],
    k: int,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> RetrievalResult
```

LLM expands the preference-profile summary into HyDE prose (no title extraction — the LLM only writes the search string). The caller-supplied `excluded_films` list is resolved to catalogue IDs deterministically and pushed into the SQL filter, guaranteeing that already-seen films are always absent regardless of how the LLM reformulates the summary. Used on `drift_confirmed` and `re_retrieve` events.

**Input**
| Parameter | Type | Description |
|---|---|---|
| `summary` | `str` | Preference-profile summary from the Profile Agent (non-empty). |
| `excluded_films` | `list[str]` | Film titles to exclude; resolved via fuzzy title match. |
| `k` | `int` | Maximum candidates to return (must be > 0). |
| `session_id`, `run_id`, `turn_id` | `UUID` | Correlation IDs for logging. |

---

### `RetrievalResult` — shared output

| Field | Type | Description |
|---|---|---|
| `user_query` | `str` | Original oracle utterance or profile summary. |
| `reformulated_query` | `str` | HyDE prose string sent to the embedding model. |
| `k` | `int` | Echo of the requested candidate count. |
| `candidates` | `list[MovieRow]` | Films in descending cosine similarity order. |
| `scores` | `dict[int, float]` | `movie_id → cosine similarity` for every candidate. |
| `excluded_films` | `list[str]` | Raw title strings that were excluded. |
| `excluded_movie_ids` | `list[int]` | Resolved catalogue IDs pushed into the SQL filter. |

**Error cases**
| Condition | Exception |
|---|---|
| `user_query` / `summary` empty | `ValueError("... must be a non-empty string")` |
| `k ≤ 0` | `ValueError("k must be positive, got {k}")` |
| LLM returns malformed JSON on all retries | `LLMParseError` |
| Session budget exhausted | `CostLimitExceeded` |

---

### `vector_search.search` — tool

```python
vector_search.search(
    query: str,
    k: int,
    exclude_ids: list[int] | None = None,
) -> list[MovieHit]
```

Embeds `query` using `BAAI/bge-large-en-v1.5` (1024-dim, same model as ingest) and queries `movies.embedding` via pgvector cosine distance (`<=>`). Films in `exclude_ids` are filtered out in SQL before the `LIMIT k` is applied.

**Output** — `list[MovieHit]`
| Field | Type | Description |
|---|---|---|
| `movie_id` | `int` | TMDB integer ID. |
| `score` | `float` | Cosine similarity (`1 − cosine_distance`), descending. |

---

### `metadata_fetcher.fetch` — tool

```python
metadata_fetcher.fetch(movie_ids: list[int]) -> list[MovieRow]
```

Enriches a list of TMDB IDs with full metadata (title, overview, tagline, release year, genres, director). Joins `movies ← movie_genres → genres` and `crew_members (job='Director')`. Return order matches the input order; IDs absent from the catalogue are silently dropped.

| Field | Type | Description |
|---|---|---|
| `movie_id` | `int` | TMDB integer ID. |
| `title` | `str` | Film title. |
| `overview` | `str \| None` | Synopsis. |
| `tagline` | `str \| None` | Tagline. |
| `release_year` | `int \| None` | From `release_date`. |
| `genres` | `list[str]` | Genre names. |
| `director` | `str \| None` | First director found. |
| `poster_path` | `str \| None` | Relative poster path (prepend TMDB base URL). |
| `vote_average` | `float \| None` | TMDB rating. |
| `vote_count` | `int \| None` | TMDB vote count. |
