# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**CinePal — Conversational Clustering** — an AI system that clusters a movie catalogue by *conversing* with a human (the **oracle**) who is the sole judge of quality. There is no intrinsic ground truth; the oracle's acceptance *is* the objective function.

---

## Repository layout

```
backend/
  app.py               FastAPI entry (lifespan wires logging, orchestrator, embedder preload)
  settings.py          Pydantic Settings + EnvSettings; YAML config loader + config hash
  logging_setup.py     configure_logging() + log_llm_call() helper
  exceptions.py        SessionNotFound, SessionNotConverged, MovieNotFound
  api/                 ONLY layer that runs SQL (db, sessions, runs, eval, retrieval, movies)
  models/              Pydantic schemas + domain types (sessions, clusters, runs, eval, llm, …)
  llm/llm_harness.py   Single gateway for all LLM calls; cost guard; retries; dry_run mode
  orchestrator/        Orchestrator + convergence policy; tools/{feedback,policy,render,state}
  cluster/             Cluster agent; tools/{cluster_describer,soft_cluster_engine,…}
  decision/            Decision agent; tools/{entropy_calculator,relevance_scorer}
  ambiguity/           Ambiguity agent
  retrieval/           Retrieval agent; tools/{vector_search,query_reformulator,…}
  routers/sessions.py  HTTP endpoints: POST /sessions, POST /sessions/{id}/turns, GET /sessions/{id}
configs/default.yaml   Active experimental condition (model, session, retrieval, clustering, …)
db/
  migrations/00X_*.sql Numbered SQL; apply.py runs them; never edit applied files
  apply.py             Migration runner (idempotent)
  ingest.py            Single ingestion entry point
  ingestion/           download → clean → split → embed → load; fetch.py pulls HF artifacts
frontend/              React + Vite + TypeScript; zustand + react-query; vitest
tests/                 agents/, api/, cluster/, db/, retrieval/ — Postgres via testcontainers
notebooks/embed_in_colab.ipynb  GPU embedding path; uploads parquet artifacts to HF
```

---

## Commands

### Backend

```bash
pip install -r requirements.txt

python -m db.apply              # apply migrations (idempotent)
python -m db.ingest             # fetch pre-built HF artifacts → ingest mini (dev default)
python -m db.ingest --set main  # ingest full ~40k set
python -m db.ingest --source kaggle       # regenerate artifacts locally (slow)
python -m db.ingest --source kaggle --no-db  # build artifacts only, no DB writes

uvicorn backend.app:app --reload   # API server; Swagger at /docs

pytest tests/                              # full suite
pytest tests/api/test_sessions_api.py::test_name  # single test
pytest -k "fragment"                       # filter by name
```

### Frontend (run from `frontend/`)

```bash
npm install
npm run dev         # Vite dev server
npm run build       # tsc -b && vite build
npm run typecheck
npm test            # vitest (single run)
npm run test:watch
```

### Key env vars (full list in `.env.example`)

| Variable | Required | Purpose |
|---|---|---|
| `DATABASE_URL` | yes | Postgres connection string |
| `OPENAI_API_KEY` | yes (live) | LLM calls |
| `CONFIG_PATH` | no | Override active YAML config (default `configs/default.yaml`) |
| `LOG_LEVEL` | no | `DEBUG \| INFO \| WARNING \| ERROR \| CRITICAL` (default `INFO`) |
| `CINEPAL_ARTIFACTS_REPO` | ingestion | HF dataset repo id |
| `HF_TOKEN` | ingestion | Only for private HF repos |
| `KAGGLE_USERNAME` / `KAGGLE_KEY` | kaggle path | Local artifact regen only |

---

## Architecture — things that span files

**Per-turn flow** (orchestrator is the sole DB writer):
Oracle → `routers/sessions.py` → `Orchestrator.run_turn` → Retrieval Agent → Cluster Agent → Decision Agent → (Ambiguity Agent if *continue*) → Orchestrator writes turn / clusters / feedback → response to client. Sub-agents are read-only.

**Replayability contract**: every session row stores `seed` + full YAML `config_snapshot`. `runs.config_hash` is the SHA-256 prefix from `backend.settings.get_config_hash()`. Any non-deterministic change to the turn path breaks this and must be flagged.

**Config → code path**: `configs/<name>.yaml` is loaded by `backend.settings.get_settings()` into typed Pydantic models (`ModelConfig`, `SessionConfig`, `ClusteringConfig`, …). `get_env()` is separate — secrets only, via pydantic-settings. Switching experimental condition = set `CONFIG_PATH`, never edit code.

**Prompts**: each agent owns a `prompts/` subdir of versioned Jinja files (e.g. `backend/orchestrator/prompts/orchestrator_system_v1.j2`). `backend.settings.prompts_dir("orchestrator")` resolves the path. New prompt version = new file; old file stays for replay.

**LLM harness** (`backend/llm/llm_harness.py`): `call()` is the only entry point. Enforces `cost_limit_usd` before each call (raises `CostLimitExceeded`), retries 3× on transient OpenAI errors with exponential backoff, supports `dry_run=True` for tests, emits one `log_llm_call(...)` record per attempt.

**DB access boundary**: nothing outside `backend/api/` opens a cursor. `backend/api/db.py` exposes a connection pool + `transaction()` context manager; the other `api/*.py` files are typed CRUD helpers consumed by the orchestrator, routers, and tests.

**Tests boot real Postgres**: `tests/db/test_config.py` registers the `db_url` fixture via `testcontainers`. `pyproject.toml` injects it with `addopts = "-p tests.db.test_config"`. Each test gets a fresh schema. No SQLite fallback exists.

---

## Architectural rules

**These are absolute. If a proposed change would violate one, flag it rather than quietly going along.**

### Layer boundaries
- **`backend/api/` is the ONLY layer that touches SQL.** SQL outside `backend/api/` is a bug — fix it, do not work around it. HTTP routes, agents, evaluation scripts, and notebooks all go through the API layer.
- **All LLM calls go through `backend/llm/llm_harness.py`.** Never instantiate a model client (OpenAI, Anthropic, etc.) directly in any other module.
- **Auth/authorization lives on the HTTP layer.** The `api/` layer takes IDs and trusts them.

### Data and state
- **Every session is replayable** from its stored seed + YAML config snapshot + turn history alone, with no live LLM calls required.
- **Working memory is per-session and reset between sessions.** No module-level caches, no global state that bleeds across runs. Cross-session leakage is a silent bug that invalidates experimental conditions.
- **Persistent memory (personas, configs) has a versioned initial state.** Persona rows are write-once: created before the experiment run, never mutated. Changes create new rows with new IDs.
- **All timestamps are UTC, ISO-8601, server-set.** Never trust timestamps from the client or from LLM responses.

### Prompts
- **Prompts are versioned Jinja2 files in a `prompts/` subdir colocated with the agent module that owns them.** One file per named prompt, explicit Jinja2 variables, prompt-hash logged per run. Naming: `{function}_{version}.j2`.
- **Never embed prompts as f-strings or triple-quoted strings inside functions.** This is a scaffolding-check failure.
- When a prompt changes, create a new version file. Keep the old one.

### Configuration
- **Each experimental condition (A–D) is a YAML config file, not a forked script.** Ablating a condition means switching the config, never editing code.
- **Model, version, and seed come from config — never hard-coded in calling code.**
- **Cost hard-stop.** Every session has a `cost_limit_usd` from its config. The harness raises `CostLimitExceeded` when the limit is hit. Never a silent runover.

---

## Fail loudly — no silent errors

**The application must crash when it has to crash.**

- Never use bare `except: pass` or `except Exception: pass` around any meaningful operation.
- Never return a fallback value (`None`, empty list, stale state) that hides a failure without raising or re-raising with context.
- Any `try/except` block must either: (a) retry a transient error and eventually raise on exhaustion, or (b) catch a specific, well-understood exception and raise a richer one in its place.
- The one sanctioned exception is the LLM harness retry loop: transient API errors (rate-limit, timeout) are retried with exponential backoff, max 3 attempts. If all retries fail, **raise** — do not silently return the previous turn's data.
- Post-run integrity checks must `assert` or `raise` on missing data — do not log a warning and carry on.

---

## Logging

Stdlib `logging`, configured once in `backend/logging_setup.py`. One ANSI-coloured key=value line per record in dev. Level via `LOG_LEVEL` env var. Each module: `log = logging.getLogger(__name__)` — never the root logger.

**Every LLM call log record must include:** `run_id`, `session_id`, `turn_id`, `seed`, `config_hash`, `model_and_version`, `prompt_hash`, `timestamp`, `step_type`, token counts (input and output separately), latency. Use the `log_llm_call()` helper from `backend.logging_setup`. No `print()` as logs.

**Level semantics:**
- `DEBUG` — active debugging only; off in production.
- `INFO` — normal operational events ("session started", "convergence declared", "turn N completed").
- `WARNING` — deviation from expectation, system kept going.
- `ERROR` — a user-visible operation failed.
- `CRITICAL` — process is degraded or shutting down.

**Where to log:**
- At the HTTP boundary: log call and outcome; `WARNING` on unexpected branches; `log.error(..., exc_info=True)` if the underlying call raises.
- Inside each agent dir: log deviations and decisions (fallbacks, retries, drift events) at WARNING; successes at DEBUG.
- Never log on both sides of a re-raise. Log at the layer that *handles* the exception, not every layer it passes through.

---

## Testing conventions

- Write `tests/tests.md` (behavior spec, one section per component) before writing `test_*.py`.
- Every component test uses a fresh, empty state — no shared state between tests.
- **Component tests for each Agent** use the harness `dry_run` mode (no live LLM calls). They are re-run after any prompt file change.
- **`db_url` fixture** (`tests/db/test_config.py`) boots a throwaway pgvector container via `testcontainers` and applies all migrations into an isolated schema. Each test gets a clean Postgres schema; no state is shared between tests. The production DB is Postgres — no SQLite fallback.

---

## Code quality

- Lint with **ruff**: rules `S110` (try-except-pass), `BLE001` (broad `except Exception`), `T201` (`print`). Configured in `pyproject.toml`. Runs in CI before tests.
- **`pytest -W error`**: `filterwarnings = ["error"]` in `pyproject.toml`. Warnings become test failures.
- **Branch coverage** (`coverage.py`, `branch = True`): forces both sides of every `if` and every `except` to be tested.
- **mypy strict** (or pyright): functions returning `Optional[T]` force callers to handle `None` at static-check time.

---

## Comments and code style

- Every function has a docstring: purpose, parameters, return values.
- Inline comments explain non-obvious logic, not obvious mechanics.
- Blank line between code blocks with different purposes.
- Typed interfaces between modules (pydantic / dataclasses).
- NEVER REMOVE ANY COMMENTS
- NEVER ADD COMMENTS TO SEPARATE LOGICAL BLOCKS OF CODE OR FUNCTIONS SUCH as `# ---`

---

## See also

- `README.md` — setup, Docker instructions, catalogue ingestion (HF vs Kaggle paths)
- `backend/README.md` — endpoint table, env-var table, `log_llm_call()` usage
- `db/README.md` — migration conventions and file index
- `.env.example` — full env-var list
