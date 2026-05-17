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
├── app.py               FastAPI application, lifespan wiring, router mount.
├── settings.py          Typed config loader (Pydantic) + env-var helpers.
├── logging_setup.py     Logging setup: ANSI-coloured key=value lines + log_llm_call().
├── exceptions.py        Domain exceptions raised by orchestration/API boundaries.
├── api/                 Data-access layer — the ONLY place SQL is allowed.
│   ├── db.py            Connection pool and transaction() context manager.
│   ├── movies.py        Catalogue vector search, title resolution, metadata, embeddings.
│   ├── sessions.py      CRUD: sessions, turns, clusters, oracle_feedback.
│   ├── runs.py          CRUD: runs table, config hashing.
│   ├── eval.py          Write: session_metrics, judge_scores.
│   ├── retrieval.py     Read: get_run_results(), get_session_full().
│   └── types.py         DB-facing dataclasses/enums shared across backend layers.
├── llm/                 LLM harness, prompt loading, and LLM response types.
├── state/               Hard-limit and LLM state gate agent.
├── profile/             Preference-profile extraction agent and helpers.
├── retrieval/           Query reformulation, vector-search, metadata tools.
├── cluster/             Soft clustering, cluster description/refinement tools.
├── decision/            Decision agent and entropy/relevance helpers.
├── orchestrator/
│   ├── orchestrator.py  Orchestrator: sole DB writer, coordinates the turn pipeline.
│   └── tools/           feedback.py, policy.py, render.py, turns.py
└── routers/
    ├── dtos.py          Pydantic HTTP request/response models.
    └── sessions.py      HTTP endpoints: POST /sessions, POST /sessions/{id}/turns,
                         GET /sessions/{id}.
```

---

## Architectural invariants

- **`backend/api/` is the only place SQL runs.** Routers, the orchestrator,
  agents, notebooks, and scripts all go through that layer.
- **All LLM calls go through `backend/llm/llm_harness.py`.**
  Never import a model client directly elsewhere.
- **No module-level state.** The orchestrator instance lives on `app.state`;
  nothing at module scope accumulates cross-request data.
- **UTC, ISO-8601, server-set timestamps.** The orchestrator stamps turns;
  the HTTP layer never trusts client-sent times.
- **Fail loudly.** No `except: pass`, no silent fallbacks. Unknown session →
  `SessionNotFound` → HTTP 404. Bad input → pydantic 422. Startup failure →
  process exit.

---

## Running locally

```bash
pip install -r requirements.txt
uvicorn backend.app:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

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

| Method | Path                            | Description                              |
|--------|---------------------------------|------------------------------------------|
| POST   | `/sessions`                     | Create a new session (returns 201).      |
| POST   | `/sessions/{session_id}/turns`  | Submit a user message, get a response.   |
| GET    | `/sessions/{session_id}`        | Retrieve full session state + turn list. |

All responses are JSON. Unknown `session_id` → 404. Empty `user_message` → 422.

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
