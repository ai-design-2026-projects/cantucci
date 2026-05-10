# Best Practices — Conversational Clustering
*Guidelines for project structure, code style, and development workflow. This is a living document — update it as you learn what works and what doesn't.*

## 1. Start with a conceptual model, on paper, before code

Sketch the entities and their relationships before touching any file. The goal is a plausible v0.1, not a final schema. For this project the core entities are:

- **`session`** — one conversation between the oracle and the system. Carries status (`running`, `converged`, `abandoned`, `budget_exhausted`), the YAML config snapshot used for that run, the seed, and the experimental condition.
- **`turn`** — one oracle exchange within a session. Stores the oracle utterance, the system action (`show`/`ask`/`stop`), the content shown or asked, and the cognitive-load score for that turn.
- **`cluster_snapshot`** — the full soft-assignment matrix at a given turn. One row per turn, stored as JSON. This is what makes the session replayable without re-running the LLM.
- **`oracle_feedback`** — one row per feedback event within a turn. Linked to its parent turn; carries feedback type (`global`, `cluster`, `point`, `instructional`, `resolve_drift`) and content.
- **`persona`** — one simulated oracle. Write-once: created before the experiment run, never modified. If a persona needs to change, create a new row.
- **`run`** — one invocation of the evaluation harness across all conditions and personas. Carries the git commit hash, harness version, and a `completed` flag.

Commit a `docs/data_model.md` that lists every entity, its attributes, its relationships, and cascade rules. When the model changes, update the doc *first*, then the code. This is the document a new team member reads when they ask "how does this system work?"

---

## 2. One standard shape for every entity table

Every named entity follows the same default column set:

| Column | Purpose |
|---|---|
| `id` | Primary key — integer, auto-increment, internal |
| `slug` | URL/log-friendly handle — unique among live rows (`WHERE deleted_at IS NULL`) |
| `created_at` | Insert timestamp |
| `updated_at` | Last-write timestamp |
| `deleted_at` | `NULL` = alive; non-`NULL` = soft-deleted |
| *indexed cols* | Extra attributes you filter by (e.g., `status`, `condition_id`) |
| `details` | JSON blob for everything else |

**Why this matters for this project.** `session`, `persona`, `run` all benefit from slug-based references in logs and prompts (e.g., `session-abc123`, `persona-scifi-noir`) so a log line is self-describing without a lookup. `id` is the FK target internally; `slug` is what appears in filenames, reports, and replay commands.

**All timestamps are UTC, ISO-8601, server-set.** Never trust timestamps from the client or from the LLM response. Set them in the data layer at create/update/soft-delete time.

**Large known fields get their own column; everything else goes in `details`.** The preference profile produced by `f_assess` and the YAML config snapshot on `session` are examples — known shape, always loaded, never queried by content. They get dedicated `TEXT` columns, not a slot in the JSON blob.

---

## 3. One relationships table for everything (initially)

Use a single `rels` table to represent all links between entities:

| Column | Purpose |
|---|---|
| `src_id` / `src_type` | Source entity |
| `tgt_id` / `tgt_type` | Target entity |
| `rel_type` | `session_has_turn`, `turn_has_feedback`, `run_includes_session`, … |
| `details` | JSON metadata (e.g., ordering, role) |
| `created_at`, `deleted_at` | Same soft-delete semantics |

New relationship types cost zero schema changes. Constrain `src_type` and `tgt_type` to a known list of entity names via `CHECK` — this catches typos like `'sesion'` that would otherwise be silent data corruption with no FK to catch them.

Promote frequent traversals (e.g., `session → turn`) to dedicated indexed columns when query performance demands it. Start generic; specialize where it hurts.

---

## 4. Deletions: three choices made up-front, one orchestrator

**Make these three decisions explicitly before writing any deletion code:**

1. **Soft-delete is the default.** All `DELETE` calls set `deleted_at`. This is non-negotiable — it makes recovery from operational mistakes survivable and keeps the full audit trail for replay.
2. **Hard delete is restricted.** A separate code path, gated, for GDPR/storage cleanup only.
3. **Cascade rules written per entity, in one file.** When a `session` is deleted, what happens to its `turn`s, `cluster_snapshot`s, and `oracle_feedback` rows? Document the rule before writing any code. Implement all cascade logic in a single `deletion.py` orchestrator, never scattered across entity modules.

## 5. API layer: the only place that touches SQL

**The `api/` constraint is absolute: it is the only layer that touches SQL.** If you find SQL outside `api/`, fix it. HTTP routes, `f_*` agents, evaluation scripts — all go through `api/`. This is what makes the `f_*` functions testable in isolation and the session replayable without running the full pipeline.

---

## 6. Internal Python API: same five operations on every entity

```python
sessions.create(db, data)                  # → SessionRead
sessions.get(db, id)                       # → SessionRead | None
sessions.get_by_slug(db, slug)             # → SessionRead | None
sessions.update(db, id, patch)             # → SessionRead
sessions.delete(db, id, hard=False)
sessions.query(db, filters, limit, offset) # → list[SessionRead]
```

Every entity gets `get` and `get_by_slug`. `id` is for internal FK joins; `slug` is what appears in logs, replay commands, and LLM prompts. The LLM should be able to construct a call from a slug without a translation step.

**Consistent error conventions across all entities:**

| Call | Not found | Conflict | HTTP maps to |
|---|---|---|---|
| `get` / `get_by_slug` | returns `None` | n/a | 404 if `None` |
| `query` | returns `[]` | n/a | 200 with empty list |
| `create` | n/a | raises `IntegrityError` | 409 |
| `update` | raises `NotFound` | raises `IntegrityError` | 404 / 409 |
| `delete` | raises `NotFound` | n/a | 404 |

`NotFound` is a single custom exception declared in `api/__init__.py`, caught by one `@app.exception_handler` in the HTTP layer. This keeps every route looking the same: call the API, return what it returned, let exceptions propagate.

---

## 7. Pydantic models: one triple per entity

For each entity, define:

- `SessionCreate` — input shape (no `id`, no timestamps).
- `SessionRead` — output shape (has `id`, `created_at`, etc.). Read ≠ Create; never share one model.
- `SessionUpdate` — patch shape (every field optional, so only fields the caller actually sent are touched).

Put the JSON `details` column behind a typed Pydantic sub-model (e.g., `SessionDetails`). This means `details` is parsed into typed fields on read and dumped back on write — no hand-rolled `json.dumps` / `json.loads`.

Validate at the boundary, not inside the API layer. By the time data reaches `api/`, types are guaranteed.

---

## 8. Prompts as versioned files, never embedded strings

**Every prompt used by any `f_*` function or the LLM judge is a versioned file in `prompts/`.** Never embed a prompt as a triple-quoted string inside a function. This is one of the non-negotiables from the scaffolding.

Naming convention: `{function}_{version}.txt` — e.g., `f_output_v1.txt`, `judge_coherence_v1.txt`. When a prompt changes, create a new version file; keep the old one. This makes prompt changes visible in git diffs and makes it possible to re-run a session with the exact prompt that was used.

The prompt version used in a session is logged alongside the model version and token counts. You must be able to reconstruct exactly what the LLM was told at any turn.

---

## 9. The LLM wrapper: one thin module for all model calls

All LLM calls go through a single `llm.py` module. It reads provider, model, and API key from environment variables. The wrapper handles:

- Provider dispatch (Anthropic / OpenAI / Azure / OpenRouter).
- Retry with exponential backoff (max 3 attempts) on transient errors.
- Logging of every call: model version, prompt hash, token counts (input and output separately), latency.
- A `dry_run` mode that returns a stub response without hitting the API — used in component tests.

```python
# usage everywhere in the project
from conv_clustering import llm

reply = llm.call(
    messages=[{"role": "system", "content": load_prompt("f_output_v1.txt")},
               {"role": "user", "content": oracle_query}],
    seed=session.seed,
)
```

**Model and version are never hard-coded in calling code.** They come from the session's YAML config, which is stored in the `sessions` table for replay. A session is replayable only if you can reconstruct exactly which model, at which version, with which prompt, was called at each turn.

**Cost hard-stop.** Every session has a `cost_limit_usd` from its YAML config. The wrapper accumulates token costs and raises `CostLimitExceeded` (a named exception) when the limit is hit — never a silent runover.

---

## 10. Logging: stdlib, structured, no silent failures

Configure once in `logging_setup.py`. One JSON line per record. Level via `LOG_LEVEL` env var. Each module: `log = logging.getLogger(__name__)` — never the root logger.

**The most important rule: no silent failures.** Every path that deviates from expectation is logged at WARNING or above with structured context.

Use a `deviation()` helper for unexpected paths:

```python
# in logging_setup.py
STRICT = os.getenv("STRICT_MODE", "0") == "1"

def deviation(msg: str, **kwargs) -> None:
    """Unexpected path. Logs WARNING normally; raises in STRICT_MODE=1."""
    if STRICT:
        raise UnexpectedDeviation(f"{msg} | {kwargs}")
    log.warning(msg, extra=kwargs)
```

Call `deviation(...)` for: LLM returning malformed JSON (before retry), drift detected in `f_next_state`, empty candidate pool after filters, turn budget reached without convergence, retry exhausted, config value falling back to default.

Run `STRICT_MODE=1 pytest` in CI. In production, `STRICT_MODE=0` — the same call logs and keeps going.

**What and where to log:**
- **HTTP boundary:** log the call and outcome; `deviation()` on unexpected branches; `log.error(..., exc_info=True)` if the underlying call raises.
- **Inside `agents/`:** log deviations and decisions (fallbacks, retries, drift events). Successes go at DEBUG — too noisy at INFO in production.
- **Never log on both sides of a re-raise.** Log at the layer that *handles* the exception, not every layer it passes through.
- **Log token counts and latency on every LLM call.** These are primary observability signals for cost and performance.

**Logging level semantics:**
- `DEBUG` — only useful when actively debugging. Off in production.
- `INFO` — normal operational events ("session started", "convergence declared", "turn completed").
- `WARNING` — deviation from expectation, system kept going.
- `ERROR` — a user-visible operation failed.
- `CRITICAL` — process is degraded or shutting down.

---

## 11. Make mistakes loud, early, and unmergeable 

Four cheap project-config decisions that catch the problems `deviation()` doesn't:

1. **Lint with ruff.** Enable `S110` (try-except-pass), `BLE001` (broad `except Exception`), `T201` (`print` statements). Configure in `pyproject.toml`. CI runs `ruff check .` on every PR — sloppy code can't merge.
2. **`pytest -W error`.** `filterwarnings = ["error"]` in `pyproject.toml`. `DeprecationWarning`, `ResourceWarning`, and library warnings become test failures.
3. **Branch coverage, not line coverage.** `coverage.py` with `branch = True`. Forces tests to exercise both sides of every `if` — catches the error paths lazy programmers skip.
4. **Type-check with mypy strict.** Functions returning `Optional[T]` force every caller to handle `None` at static-check time. The "I forgot to handle the failure case" bug disappears before the code runs.

**CI matrix: two legs, both must pass.**

```yaml
strategy:
  fail-fast: false
  matrix:
    strict: ["0", "1"]   # lax + strict; both must pass
```

The lax leg (`STRICT_MODE=0`) proves production behavior. The strict leg (`STRICT_MODE=1`) crashes on every annotated deviation — the thing that enforces "no silent failures" even for paths tests accidentally exercise. `fail-fast: false` keeps both legs running independently.

**Secrets never in YAML.** API keys and provider tokens go in GitHub Secrets (*Settings → Secrets*), not in the workflow file or `.env.example`.

---

## 14. Tests: write the spec before the code

Before writing a single `test_*.py`, write `tests/tests.md`. One section per component and per API endpoint. For each, document:

- **What it does** — one sentence.
- **Valid input example.**
- **Expected output / DB side effects.**
- **Error cases** — what counts as invalid; one example each.
- **Soft-delete behavior** — does a deleted session appear in `get`? in `query`? in logs?

Then translate each entry into a pytest function.

**Use fresh in-memory state per test for isolation.** Each test gets a fresh, empty state. No test shares working memory with any other test. This is the rule from the scaffolding: working memory is per-run and reset between runs.

**Component tests for each `f_*` function run under `run_type = component_test`** using the same structured logger as full sessions. They use stub inputs (frozen session snapshots, synthetic oracle replies) without a live LLM session. These tests are re-run after any prompt change.

**Dry-run the harness.** The agentic harness must have a mode that returns stub outputs without hitting the API. Use this mode in all component tests and in CI.

---

## 15. Environment variables and secrets

Check a `.env.example` into git as the template. Never check in the actual `.env`.

```bash
# .env.example — copy to .env and fill in
LLM_PROVIDER=anthropic         # one of: anthropic, openai, azure
LLM_MODEL=claude-sonnet-4-6
LLM_API_KEY=sk-ant-...

# Retrieval
EMBEDDING_MODEL=all-MiniLM-L6-v2
PGVECTOR_URL=postgresql://...

# Experiment flags
LOG_LEVEL=INFO
STRICT_MODE=0                  # set to 1 in CI
SESSION_MAX_TURNS=15
SESSION_COST_LIMIT_USD=0.50
```

`.env` lives at the repo root, never inside the Python package. `python-dotenv` finds it by walking up from the working directory.
