# Backend

FastAPI application that drives the CinePal conversational clustering loop. Each user message triggers a full pipeline: intent classification, optional clarification, command dispatch (clustering, merge, focus, explain, …), LLM labeling, and an SSE-streamed response — all within a single HTTP request. Session state is persisted to Postgres after every turn; no in-process state survives restarts.

---

## Prerequisites

- Postgres running and `DATABASE_URL` set — see [`db/README.md`](../db/README.md) for the Docker one-liner and migration commands.
- API key for your configured LLM provider (`OPENAI_API_KEY` or `OPENROUTER_API_KEY`).
- A catalogue ingested into Postgres — `python -m db.ingest` (default: mini set).
- `.venv` activated:
  ```bash
  source .venv/bin/activate
  ```

---

## Running

```bash
uvicorn backend.app:app --reload
```

Swagger UI: <http://127.0.0.1:8000/docs>

On startup, `lifespan()` in `app.py`:
1. Configures logging (`logging_setup.configure_logging()`).
2. Preloads the text encoder (`core.text_encoder`) and CLIP model (`core.image_encoder`) into process memory — this avoids first-request latency.
3. If `CINEPAL_DEMO_MODE=replay`, loads the recording into memory — see [`demo/README.md`](../demo/README.md).

---

## Directory layout

```
backend/
├── app.py               FastAPI entry: lifespan wiring, CORS, DomainError handler, router mount
├── settings.py          YAML config loader → typed Pydantic models; get_env() for secrets only
├── logging_setup.py     configure_logging() + log_llm_call() helper
├── exceptions.py        DomainError base + 6 families: NotFoundError / ParseError / AuthError / ForbiddenError / ConflictError / OperationalError
├── CLAUDE.md            Type-layering and exception conventions — read before adding new types
├── auth/
│   ├── tokens.py        JWT encode/decode (HS256, expiry from config)
│   ├── passwords.py     bcrypt password hashing
│   └── types.py         User Pydantic model used as FastAPI dependency injection type
├── baseline/            Single-call ablation agent (see Baseline section below)
│   ├── agent.py         baseline_turn() — one LLM call produces clusters + reply
│   ├── runner.py        BaselineHandler used by eval/runtime/handlers.py
│   └── types.py         BaselineResponse Pydantic wire schema
├── data_access/         The ONLY layer that opens a DB cursor
│   ├── connection.py    Connection pool + transaction() context manager (dict_row default)
│   ├── movies/          fetch_metadata, fetch_stubs, fetch_movie_details, fetch_modality_embeddings, fetch_cluster_profile, filter_movie_ids_by_metadata, …
│   ├── conversations/   CRUD: conversations, messages
│   ├── cluster_snapshots/ CRUD: snapshots, clusters, memberships; find_cached_snapshot()
│   ├── concepts/        CRUD: concepts, concept_scores
│   ├── users/           CRUD: users joined with roles
│   └── eval/            CRUD: eval runs, sessions, metrics, judge scores, personas, ground truths
├── agents/              LLM-backed agents; each subclasses LLMAgent from base.py
│   ├── base.py          LLMAgent abstract base: render_kwargs → harness call → build_result → log
│   ├── intent/          Classify user message → NavigationMode + target cluster + confidence
│   ├── labeling/        Batch-label unlabeled clusters
│   ├── concept/         Derive a linear-axis or prototype concept from text
│   ├── explanation/     Explain a movie's cluster placement → ExplanationResult
│   ├── clarifier/       Generate clarifying questions when intent confidence is low
│   └── responder/       Suggest next exploration moves to the oracle
├── coordinator/         Orchestrator + command layer (not an agent)
│   ├── agent.py         Coordinator.handle_message() — top-level turn entry point
│   ├── types.py         TurnTrace, CoordinatorResult, ClusterDraft, ClusterSnapshotDraft
│   ├── commands/
│   │   ├── base.py      ActionResult, ExecutionContext dataclasses + Command Protocol (execute() interface)
│   │   ├── factory.py   build_command() — IntentAction → typed command
│   │   ├── impl/        9 command implementations (ClusterCommand has its own subdirectory)
│   │   └── helpers/     Shared pure helpers: bins.py, clustering.py, drafts.py, movies.py, targets.py
│   ├── pipeline/        6 turn phases: preparation, clarification, dispatch, finalize, pending, trace
│   └── tools/           Shared helpers: labeling, clarification_state, persist, progress (SSE)
├── llm/
│   ├── llm_harness.py   Single call() entry point: cost guard, retries, dry_run, provider routing
│   ├── types.py         LLMResponse dataclass (content, parsed, cost_usd, token counts)
│   ├── exceptions.py    CostLimitExceeded, LLMParseError, ReplayDriftError
│   └── utils/           client.py, retry.py, dry_run.py, pricing.py, prompts.py, schema_validation.py
└── routers/             HTTP layer — the only place that calls agents and data_access together
    ├── auth.py          /auth/* routes
    ├── conversations.py /conversations/* routes + SSE turn endpoint
    ├── cluster_snapshots.py /cluster-snapshots/* routes
    ├── concepts.py      /concepts/* routes
    ├── movies.py        /movies/* routes
    ├── eval.py          /eval/* routes (admin only)
    ├── auth_deps.py     FastAPI JWT bearer dependency
    └── dto/             Pydantic request/response wire models
```

---

## Configuration

Configuration is split into two layers:

- **YAML config** (`configs/dev.yaml` by default; `CONFIG_PATH` overrides) — all behavioural knobs: model names, seeds, cost limits, clustering params, HDBSCAN settings, fusion weights. Loaded by `backend.settings.get_settings()` into typed Pydantic models.
- **Env vars** (`backend.settings.get_env()`) — secrets only: API keys, `DATABASE_URL`.

**Switching experimental condition = set `CONFIG_PATH`, never edit code.** See `configs/dev.yaml` for the full key reference with inline comments.

| Env var | Required | Description |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `AUTH_SECRET` | yes | Secret key for JWT signing (no default — app fails without it) |
| `OPENAI_API_KEY` | provider | Required when `models.*.provider == openai` |
| `OPENROUTER_API_KEY` | provider | Required when `models.*.provider == openrouter` |
| `CONFIG_PATH` | no | Active YAML config; defaults to `configs/dev.yaml` |
| `LOG_LEVEL` | no | `DEBUG \| INFO \| WARNING \| ERROR \| CRITICAL` (default `INFO`) |
| `HF_TOKEN` | ingestion | Only when the HF artifacts repo is private |

---

## Per-turn pipeline

Every `POST /conversations/{id}/messages` call enters `Coordinator.handle_message()` which runs 6 sequential phases:

| Phase | Module | What it does |
|---|---|---|
| **preparation** | `pipeline/preparation.py` | Load conversation state; label any unlabeled clusters via the labeling agent |
| **clarification** | `pipeline/clarification.py` | If the clarifier agent was triggered last turn, extract the oracle's answer |
| **dispatch** | `pipeline/dispatch.py` | Run intent agent → build command → execute command (clustering / merge / …) |
| **finalize** | `pipeline/finalize.py` | Persist the new snapshot, write the assistant message, update conversation state |
| **pending** | `pipeline/pending.py` | Decide whether to trigger the clarifier agent next turn |
| **trace** | `pipeline/trace.py` | Write the turn trace for replay and debugging |

The coordinator is the **sole DB writer** during a turn. All agents are read-only.

---

## Command layer

The intent agent classifies each message into a `NavigationMode` or `DialogueMode`. The factory (`coordinator/commands/factory.py`) converts that into one of 9 typed command objects:

| Command | Trigger | What it does |
|---|---|---|
| `ClusterCommand` | `CLUSTER` | Sub-cluster a subset using concept guidance or numeric partition |
| `MergeCommand` | `MERGE` | Merge selected clusters into one |
| `FocusCommand` | `FOCUS` | Zoom into a single cluster (drop the rest) |
| `ExcludeCommand` | `EXCLUDE` | Remove a cluster from the active view |
| `CrossFilterCommand` | `CROSS_FILTER` | Filter by a metadata attribute value |
| `ResetCommand` | `RESET` | Return to the root cluster snapshot |
| `UndoCommand` | `UNDO` | Step back to the previous snapshot |
| `SmallTalkCommand` | `SMALL_TALK` | Handle off-topic messages without touching clusters |
| `ExplainCommand` | `EXPLAIN` | Explain why movies appear in a given cluster |

---

## Baseline

`backend/baseline/` is an alternative turn handler used by the eval harness for ablation (`--condition baseline`). Instead of the full coordinator pipeline (intent → command → agents), it makes a single LLM call that returns clusters, an operation name, and a reply in one shot. It is never wired to an HTTP route — `eval/runtime/handlers.py` imports `BaselineHandler` directly based on the condition flag. This makes it easy to compare the multi-agent coordinator against a simpler single-call approach without touching the production code path.

---

## LLM harness

All LLM calls go through `backend/llm/llm_harness.py:call()`. Direct model-client imports anywhere else are a bug.

Key behaviours:
- **Cost guard**: checks `accumulated_cost_usd` against `cost_limit_usd` before every call; raises `CostLimitExceeded` immediately if exceeded — never a silent overrun.
- **Retries**: up to 3 attempts with exponential backoff on transient API errors (rate-limit, timeout). Raises on exhaustion.
- **Structured output**: when `response_schema` (a Pydantic model) is supplied, the call switches to JSON-object mode, parses and validates the response. Parse failures consume the same retry budget.
- **`dry_run=True`**: short-circuits to a fixture response — no API call, no cost. Used in all component tests.
- **Pricing**: `utils/pricing.py` estimates `cost_usd` from token counts; logged per call via `log_llm_call()`.

---

## Content-addressed snapshot cache

Clustering operations that are deterministic given `(parent_snapshot_id, operation, params, config_hash)` are computed once and reused across conversations:

- `data_access/cluster_snapshots/queries.py:find_cached_snapshot()` returns an existing snapshot when all four inputs match.
- `coordinator/tools/persist.py:persist_and_label()` does the cache lookup before computing; on a hit it skips both HDBSCAN and LLM labeling.
- The uniqueness constraint is a `NULLS NOT DISTINCT` index — see `db/migrations/` for the DDL.

---

## Type layering

Three layers, conversion flows one direction only:

```
data_access/<domain>/types.py  →  agents/<name>/types.py  →  routers/dto/<domain>/dtos.py
        XRow                         XResult / XDraft               XDto (Pydantic)
```

- **`XRow`** — `@dataclass(frozen=True, slots=True)`, carries a `from_row(cls, r: dict)` classmethod. No HTTP knowledge.
- **`XResult`** — `@dataclass(frozen=True, slots=True)`, carries a `from_llm_response(cls, parsed, cost, …)` classmethod. Must include a `cost: float` field.
- **`XDto`** — Pydantic wire model. Constructed from row types inline in router handlers.

Row → agent-internal → DTO only. Never reverse. Inbound request payloads are Pydantic request DTOs unpacked into primitives before calling `data_access/` or `agents/`. Full conventions in `backend/CLAUDE.md`.

---

## Exception taxonomy

All domain failures inherit from `DomainError` in `backend/exceptions.py`. The global handler in `app.py` translates them to HTTP responses automatically — routers raise the domain exception directly and never construct `HTTPException` for domain failures.

| Family | HTTP status | Subclasses |
|---|---|---|
| `NotFoundError` | 404 | `ConversationNotFound`, `ClusterSnapshotNotFound`, `MovieNotFound`, `ConceptNotFound`, `RunNotFound`, `EvalSessionNotFound` |
| `ParseError` | 422 | `ConceptParseError`, `LLMParseError` |
| `AuthError` | 401 | `InvalidToken`, `TokenExpired` |
| `ForbiddenError` | 403 | `NotConversationOwner` |
| `ConflictError` | 409 | `SnapshotHasChildren` |
| `OperationalError` | 500 | `CostLimitExceeded`, `ReplayDriftError` |

`CostLimitExceeded`, `LLMParseError`, and `ReplayDriftError` live in `backend/llm/exceptions.py` and inherit from the families above: `CostLimitExceeded → OperationalError`, `LLMParseError → ParseError`, `ReplayDriftError → OperationalError`.

---

## Logging

Every module: `log = logging.getLogger(__name__)`. All records route through `backend/logging_setup.configure_logging()` — one ANSI-coloured `key=value` line per record in dev. Level via `LOG_LEVEL`.

Every LLM call must use `log_llm_call()` to emit the required field set:

```python
from backend.logging_setup import log_llm_call

log_llm_call(
    log,
    run_id=..., conversation_id=..., message_id=..., seed=...,
    config_hash=..., model_and_version=..., prompt_hash=...,
    step_type=..., input_tokens=..., output_tokens=..., latency_ms=...,
)
```

---

## Endpoints

Auth levels: `public` — no token checked; `optional` — anonymous or authenticated both accepted; `user` — valid JWT required; `admin` — admin role required.

| Method | Path | Auth | Description |
|---|---|---|---|
| POST | `/auth/login` | public | Obtain a JWT token (sets HttpOnly cookie) |
| POST | `/auth/register` | public | Create a `user`-role account |
| POST | `/auth/logout` | public | Clear the auth cookie |
| GET | `/auth/me` | user | Return the authenticated user (401 if anonymous) |
| GET | `/conversations` | user | List conversations for the authenticated user |
| POST | `/conversations` | optional | Create a new conversation (anonymous or authenticated) |
| GET | `/conversations/{id}` | public | Retrieve conversation state + all messages |
| PATCH | `/conversations/{id}` | public | Set active cluster snapshot (undo / branch navigation) |
| POST | `/conversations/{id}/messages` | optional | Submit a user message; anonymous or authenticated |
| DELETE | `/conversations/{id}` | user | Delete a conversation (must be owner) |
| GET | `/conversations/{id}/events` | public | SSE stream of real-time turn progress events |
| GET | `/conversations/{id}/snapshot-graph` | public | Full DAG of snapshots touched by a conversation |
| GET | `/cluster-snapshots/{id}` | public | Retrieve a snapshot with its clusters |
| DELETE | `/cluster-snapshots/{id}` | public | Delete a leaf snapshot |
| GET | `/cluster-snapshots/{id}/clusters/{cluster_id}/members` | public | All movie memberships in a cluster |
| GET | `/movies/umap-points` | public | UMAP 2D coordinates for all catalogued movies |
| GET | `/movies/{id}` | public | Full movie metadata |
| POST | `/movies/batch` | public | Metadata for up to 200 movies |
| GET | `/concepts/{id}/axis` | public | Movie score distribution along a concept axis |
| GET | `/eval/runs` | admin | Paginated list of eval runs |
| GET | `/eval/runs/{run_id}` | admin | Single eval run |
| GET | `/eval/runs/{run_id}/aggregate` | admin | Run with per-session metrics and KPIs |
| GET | `/eval/runs/{run_id}/sessions` | admin | All eval sessions for a run |
| GET | `/eval/sessions/{session_id}` | admin | Full detail for a single eval session |
| GET | `/eval/ground-truths` | admin | All ground truth trajectories |
| GET | `/eval/personas` | admin | All evaluation personas |

All responses are JSON. Unknown resource → 404. Invalid request body → 422. Eval endpoints require admin role — see [`db/README.md`](../db/README.md) for account creation.
