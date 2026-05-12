# Cantucci Backend

HTTP API for the Cantucci conversational clustering system. The backend exposes
a session / turn interface consumed by the frontend: the user opens a session,
sends messages, and the system responds with recommendations and follow-up
questions. Session logic is owned by the orchestrator, which will eventually
call LLM-backed agents and a PostgreSQL database — both are stubbed for now.

---

## Layout

```
backend/
├── app.py               FastAPI application, lifespan wiring, router mount.
├── config.py            Environment variable loader (DATABASE_URL, LOG_LEVEL).
├── logging.py           Logging setup: ANSI-coloured key=value lines + log_llm_call().
├── api/                 Data-access layer — the ONLY place SQL is allowed.
│   ├── db.py            Connection pool and tx() context manager.
│   ├── sessions.py      CRUD: sessions, turns, clusters, oracle_feedback.
│   ├── runs.py          CRUD: runs table, config hashing.
│   ├── eval.py          Write: session_metrics, judge_scores.
│   └── retrieval.py     Read: get_run_results(), get_session_full().
├── models/
│   ├── schemas.py       Pydantic HTTP models + enums (SessionState, TurnResult, TurnRequest).
│   ├── orchestrator.py  Orchestrator Protocol (interface the router calls).
│   ├── exceptions.py    Domain exceptions (SessionNotFound).
│   ├── runs.py          Run — in-memory representation of the runs table row.
│   ├── clusters.py      ClusterSpec, ClusterAssignment, ClusterSnapshot.
│   ├── eval.py          SessionMetrics, JudgeScore.
│   └── retrieval.py     Query result types: SessionFull, RunResults, TurnDetail, etc.
├── orchestrator/
│   ├── orchestrator.py  EchoOrchestrator stub (real impl will live here).
│   ├── agent.py         LLM reasoning agent (not yet implemented).
│   └── tools.py         Agent tool definitions (not yet implemented).
└── routers/
    └── sessions.py      HTTP endpoints: POST /sessions, POST /sessions/{id}/turns,
                         GET /sessions/{id}.
```

---

## Architectural invariants

- **`backend/api/` is the only place SQL runs.** Routers, the orchestrator,
  agents, notebooks, and scripts all go through that layer.
- **All LLM calls go through `backend/llm_harness.py`** (not yet written).
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

---

## Environment variables

| Variable       | Default       | Description                                             |
|----------------|---------------|---------------------------------------------------------|
| `DATABASE_URL` | (required)    | Postgres connection string.                             |
| `LOG_LEVEL`    | `INFO`        | Root logging level (`DEBUG`, `INFO`, `WARNING`, …).    |

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
through `backend/logging.py`, including uvicorn's own access and error logs.

For LLM calls, use the helper to ensure the full CLAUDE.md-required field set
is always emitted:

```python
from backend.logging import log_llm_call

log_llm_call(
    log,
    run_id=..., session_id=..., turn_id=..., seed=...,
    config_hash=..., model_and_version=..., prompt_hash=...,
    step_type=..., input_tokens=..., output_tokens=..., latency_ms=...,
)
```
