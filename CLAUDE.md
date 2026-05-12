# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Conversational Clustering** — an AI system that clusters a dataset by *conversing* with a human (the **oracle**) who is the sole judge of quality. There is no intrinsic ground truth; the oracle's acceptance *is* the objective function.

Course project for "Designing Large Scale AI Systems" (Prof. Fabio Casati). Authors: Davide Donà, Andrea Blushi. Declared profile: **build-heavy** (see `docs/requirements/deliverables.md` §2) — the system is the contribution, so engineering quality, UI, and robustness carry more weight than a long related-work survey.

**Current status:** DB layer and catalogue ingestion implemented (`db/migrations/`, `db/apply.py`, `db/ingest.py`). Agent logic, HTTP layer, and UI are next.

---

## Canonical docs — read before designing

### ALWAYS READ — source of truth
These contain implementation details and are consulted when designing or implementing specific components:

- `docs/specifications/architecture/data_schema.md` — MUST be READ before designing the DB layer or any code that interacts with it. Database schema, data types, session / turn / feedback entities, reproducibility invariants.
- `docs/specifications/architecture/api.md` — MUST BE READ before designing any code that implements or calls these interfaces. System interfaces: input/output contracts for `f_*` functions, session harness API, LLM call signatures.
- `docs/specifications/architecture/architecture.md` — MUST BE READ before designing any component, to understand its role and interactions in the system. System block diagram and component relationships.

### Reference — read on demand
These files define the project requirements and evaluation strategy. When a user request conflicts with them, surface the conflict before changing them.

- `docs/requirements/conversational_clustering.md` — project brief: MVB, `f_*` function decomposition, oracle feedback levels, evaluation strategy.
- `docs/requirements/deliverables.md` — what ships (code+UI, data artifacts, findings, report, presentation), build-heavy vs study-heavy framing, sprint rules, grading criteria.
- `docs/requirements/universal_scaffolding.md` — the 13 mandatory components. "Minimum acceptable" bullets per section are the floor, not the goal.
- `docs/specifications/problem_statement.md` — authoritative design spec: data model, agentic pattern, evaluation strategy, edge cases, and requirements summary (§8). When it conflicts with the above, raise the discrepancy before acting.
- `docs/specifications/evaluation.md` — detailed evaluation protocol: component-level tests, oracle satisfaction metrics, LLM-as-judge validation, experimental conditions A–D, system-level metrics, human study design.

---

## Architectural rules

**These are absolute. If a proposed change would violate one, flag it rather than quietly going along.**

### Layer boundaries
- **`api/` (or `src/api/`) is the ONLY layer that touches SQL.** SQL outside `api/` is a bug — fix it, do not work around it. HTTP routes, `f_*` agents, evaluation scripts, and notebooks all go through the API layer.
- **All LLM calls go through `llm_harness.py`.** Never instantiate a model client (Anthropic, OpenAI, etc.) directly in any other module.
- **Auth/authorization lives on the HTTP layer.** The `api/` layer takes IDs and trusts them. This keeps `api/` callable from tests, scripts, and MCP tools without dragging auth-aware logic into the data path.

### Data and state
- **Every session is replayable** from its stored seed + YAML config snapshot + turn history alone, with no live LLM calls required. `replay.py` must demonstrate this.
- **Working memory is per-session and reset between sessions.** No module-level caches, no global state that bleeds across runs. Cross-session leakage is a silent bug that invalidates experimental conditions.
- **Persistent memory (personas, configs) has a versioned initial state.** Persona rows are write-once: created before the experiment run, never mutated. Changes create new rows with new IDs.
- **All timestamps are UTC, ISO-8601, server-set.** Never trust timestamps from the client or from LLM responses.

### Prompts
- **Prompts are versioned Jinja2 files in a `prompts/` subdir colocated with the agent module that owns them** (e.g. `backend/orchestrator/prompts/orchestrator_system_v1.j2`). One file per named prompt, explicit Jinja2 variables, prompt-hash logged per run. Naming: `{function}_{version}.j2`.
- **Never embed prompts as f-strings or triple-quoted strings inside functions.** This is a scaffolding-check failure.
- When a prompt changes, create a new version file. Keep the old one. The prompt version used in a session must be reconstructible from the session log.

### Configuration
- **Each experimental condition (A–D) is a YAML config file, not a forked script.** Ablating a condition means switching the config, never editing code.
- **Model, version, and seed come from config — never hard-coded in calling code.** The YAML config snapshot is stored in the `sessions` table so a session is replayable with the exact model it used.
- **Cost hard-stop.** Every session has a `cost_limit_usd` from its config. The harness raises `CostLimitExceeded` (a named exception) when the limit is hit. Never a silent runover.

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

Stdlib `logging`, configured once in `src/logging_setup.py`. One JSON line per record. Level via `LOG_LEVEL` env var. Each module: `log = logging.getLogger(__name__)` — never the root logger.

**Every LLM call log record must include:** `run_id`, `session_id`, `turn_id`, `seed`, `config_hash`, `model_and_version`, `prompt_hash`, `timestamp`, `step_type`, token counts (input and output separately), latency. No `print()` as logs.

**Level semantics:**
- `DEBUG` — active debugging only; off in production.
- `INFO` — normal operational events ("session started", "convergence declared", "turn N completed").
- `WARNING` — deviation from expectation, system kept going
- `ERROR` — a user-visible operation failed.
- `CRITICAL` — process is degraded or shutting down.

**Where to log:**
- At the HTTP boundary: log call and outcome; `deviation()` on unexpected branches; `log.error(..., exc_info=True)` if the underlying call raises.
- Inside `agents/` (`f_*`): log deviations and decisions (fallbacks, retries, drift events) at WARNING; successes at DEBUG.
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
- NEVER ADD COMMENTS TO SEPARATE LOGICAL BLOCKS OF CODE OR FUNCTIONS SUCH as `# ---

---

## See also

- `README.md` — project overview, directory structure, run instructions
- `.env.example` — required environment variables