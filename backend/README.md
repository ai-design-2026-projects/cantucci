# CinePal Backend

HTTP API for the CinePal conversational clustering system. The backend exposes
a session / turn interface consumed by the frontend: the user opens a session,
sends messages, and the system responds with recommendations and follow-up
questions. Session logic is owned by the orchestrator, which coordinates
LLM-backed agents and the PostgreSQL-backed data-access layer.

---

## Layout

```
backend/
├── app.py               FastAPI application, lifespan wiring, DomainError handler, router mount.
├── settings.py          Typed config loader (Pydantic) + env-var helpers.
├── logging_setup.py     Logging setup: ANSI-coloured key=value lines + log_llm_call().
├── exceptions.py        DomainError base + NotFoundError / ParseError / AuthError / OperationalError families.
├── CLAUDE.md            Type-layering and exception conventions — read this before adding new types.
├── auth/                JWT token encode/decode; password hashing.
├── data_access/         Data-access layer — the ONLY place SQL is allowed.
│   ├── connection.py    Connection pool, transaction() context manager, dict_row default.
│   ├── movies/          vector_search, fetch_metadata, fetch_stubs, fetch_movie_details.
│   ├── conversations/   CRUD: conversations, messages.
│   ├── cluster_snapshots/ CRUD: cluster_snapshots, clusters, cluster_memberships.
│   ├── concepts/        CRUD: concepts, concept_scores.
│   └── users/           CRUD: users (joined with roles).
├── agents/              LLM-backed agents; each owns a prompts/ subdir of Jinja2 templates.
│   ├── intent/          Classify user message → NavigationMode + target cluster.
│   ├── coordinator/     Orchestrate per-turn agent pipeline.
│   ├── clustering/      Drill-down / merge / recut operations → ClusterSnapshotDraft.
│   ├── labeling/        Batch-label unlabeled clusters via LLM.
│   ├── explanation/     Explain a movie's cluster placement → ExplanationResult.
│   ├── concept/         Derive a linear-axis or prototype concept from text.
│   ├── clarifier/       Generate clarifying questions when intent is ambiguous.
│   └── suggester/       Suggest next exploration moves.
├── llm/                 LLM harness, structured response parsing, record/replay utilities.
│   ├── llm_harness.py   Single call() entry point: cost guard, retries, dry_run.
│   ├── types.py         LLMResponse dataclass.
│   └── exceptions.py    CostLimitExceeded, LLMParseError, ReplayDriftError.
├── routers/             HTTP layer — the ONLY place that calls agents and data_access together.
│   ├── auth.py          POST /auth/login, POST /auth/logout, GET /auth/me.
│   ├── auth_deps.py     FastAPI dependency for JWT bearer token extraction.
│   ├── conversations.py POST /conversations, POST /conversations/{id}/messages, GET /conversations/{id}.
│   ├── cluster_snapshots.py GET /cluster-snapshots/{id}.
│   ├── movies.py        GET /movies/{id}.
│   └── dto/             Pydantic request/response wire models.
```

---

## Architectural invariants

- **`backend/data_access/` is the only place SQL runs.** Routers, agents, notebooks,
  and scripts all go through that layer. SQL outside `data_access/` is a bug.
- **All LLM calls go through `backend/llm/llm_harness.py`.**
  Never import a model client directly elsewhere.
- **No module-level state.** Nothing at module scope accumulates cross-request data.
- **UTC, ISO-8601, server-set timestamps.** The HTTP layer never trusts client-sent times.
- **Fail loudly.** No `except: pass`, no silent fallbacks. Unknown resource →
  domain `NotFoundError` subclass → global handler → HTTP 404. Startup failure →
  process exit.
- **Type conventions.** Row types (`XRow`) live in `data_access/<domain>/types.py`; agent-internal types in `agents/<name>/types.py`; wire DTOs in `routers/dto/`. See `backend/CLAUDE.md` for the full layering and exception taxonomy.

---

## Running locally

```bash
uv sync --extra test
uvicorn backend.app:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

### Running via Docker

The published image applies migrations automatically on startup, then launches uvicorn.

```bash
# Pull and run against an existing Postgres instance
docker run --env-file .env \
  -e DATABASE_URL=postgresql://cinepal:cinepal@<pg-host>:5432/cinepal \
  -p 8000:8000 \
  ghcr.io/ai-design-2026-projects/cinepal-backend:latest
```

For the full stack (backend + frontend + Postgres together) use `docker compose up` from the repo root — see the root `README.md`.

### Tests

```bash
pytest tests/
```

Tests spin up a throwaway pgvector container automatically via `testcontainers` — no manual Postgres setup required. The `db_url` fixture is registered globally by `tests/db/test_config.py`.

---

## Environment variables

| Variable          | Default    | Description                                                                                      |
|-------------------|------------|--------------------------------------------------------------------------------------------------|
| `DATABASE_URL`    | (required) | Postgres connection string.                                                                      |
| `LOG_LEVEL`       | `INFO`     | Root logging level (`DEBUG`, `INFO`, `WARNING`, …).                                              |
| `OPENAI_API_KEY`  | empty      | OpenAI API key (required when `models.*.provider == openai`).                                    |
| `OPENROUTER_API_KEY` | empty   | OpenRouter API key (required when `models.*.provider == openrouter`).                            |
| `HF_TOKEN`        | empty      | HuggingFace token; only needed when the artifacts repo pinned in YAML is private.                |
| `TMDB_API_KEY`    | empty      | TMDB v3 API key; **only** used by the Colab snapshot script, never by the running backend.       |

---

## Endpoints

| Method | Path                                        | Description                                        |
|--------|---------------------------------------------|----------------------------------------------------|
| POST   | `/auth/login`                               | Obtain a JWT token.                                |
| POST   | `/auth/logout`                              | Invalidate the current token.                      |
| GET    | `/auth/me`                                  | Return the authenticated user.                     |
| GET    | `/conversations`                            | List conversations for the authenticated user.     |
| POST   | `/conversations`                            | Create a new conversation (returns 201).           |
| GET    | `/conversations/{conversation_id}`          | Retrieve conversation state + message history.     |
| PATCH  | `/conversations/{conversation_id}`          | Update conversation metadata.                      |
| DELETE | `/conversations/{conversation_id}`          | Delete a conversation (returns 204).               |
| POST   | `/conversations/{conversation_id}/messages` | Submit a user message, get a response.             |
| GET    | `/cluster-snapshots/{snapshot_id}`          | Retrieve a cluster snapshot with its clusters.     |
| GET    | `/movies/{movie_id}`                        | Retrieve movie details.                            |

All responses are JSON. Unknown resource → 404. Invalid request body → 422.

---

## Logging

Every module uses `log = logging.getLogger(__name__)`. All records route
through `backend/logging_setup.py`, including uvicorn's own access and error logs.

For LLM calls, use the helper to ensure the full CLAUDE.md-required field set
is always emitted:

```python
from backend.logging_setup import log_llm_call

log_llm_call(
    log,
    run_id=..., session_id=..., turn_id=..., seed=...,
    config_hash=..., model_and_version=..., prompt_hash=...,
    step_type=..., input_tokens=..., output_tokens=..., latency_ms=...,
)
```
