# Test spec

This suite is intentionally minimal. It proves the things that can't be caught by static analysis:
migrations apply against a real Postgres, the FastAPI app boots and serves correctly, and the
data-access layer round-trips rows faithfully. Do not add per-agent or per-function tests here.

All tests use a real throwaway pgvector container (via `testcontainers`) seeded by the `db_url`
fixture in `tests/db/test_config.py`. The fixture is registered globally via
`addopts = "-p tests.db.test_config"` in `pyproject.toml`.

### `conftest.py` — shared fixtures

`tests/conftest.py` provides the fixtures used across all test modules:

- **`_clean_db`** (autouse, function-scoped) — runs `TRUNCATE users, runs, personas, ground_truths, conversations RESTART IDENTITY CASCADE` before every test. `CASCADE` automatically clears all dependent tables (`eval_sessions`, `turn_intents`, `conversation_metrics`, `judge_scores`, `messages`, `conversation_snapshot_refs`, …). The movie catalogue and `schema_migrations` are never truncated.
- **`admin_token`** — calls `create_user(..., role_name="admin")` then `encode_token(user_id)`. Returns a signed JWT for use as `Authorization: Bearer <token>`.
- **`user_token`** — same as above with `role_name="user"`.
- **`client`** — returns `TestClient(app)` with the full lifespan context active.
- **`seed_run(name, condition, seed)`** — calls `create_run(config_hash, config_snapshot, seed, name, condition)` and returns the run UUID.
- **`seed_persona(slug)`** — calls `create_persona(slug=slug)` and returns the persona UUID.
- **`seed_ground_truth(slug)`** — calls `create_ground_truth(slug, intent_description, operations, prompt_hash)` and returns the UUID.
- **`seed_conversation()`** — calls `create_conversation(user_id=None, config_snapshot=...)` and returns the UUID.
- **`seed_eval_session(run_id, conversation_id, persona_id, ground_truth_id, seed)`** — calls `create_eval_session(...)` and returns the session UUID.

`seed_*` helpers are plain functions, not pytest fixtures — tests call them directly to assemble the DB state they need.

---

## `tests/db/` — migration smoke

### `test_smoke.py`

Calls `db.apply.apply()` a second time on an already-migrated DB and asserts it returns `0` (idempotent). Then queries `schema_migrations` and asserts the recorded set matches every `.sql` file present in `db/migrations/`.

---

## `tests/backend/` — API smoke

### `test_smoke.py`

Two baseline checks that the app is functional: `GET /docs` returns 200 (OpenAPI schema generates without error), and `POST /movies/batch` with an unknown ID returns 200 with an empty list (exercises the full app → data_access → Postgres path on an empty catalogue).

### `test_auth_deps.py`

Exercises `require_admin` / `get_current_user` / `decode_token` through `GET /eval/personas` as a stable, side-effect-free admin-gated route. Covers: missing `Authorization` header → 401; malformed `Bearer` prefix or garbage token body → 401; expired JWT (past `exp`) → 401; valid token with `role=user` → 403; valid token with `role=admin` → 200.

### `test_conversations_api.py`

Covers `POST /conversations` (anonymous and authenticated creation, DTO field shape), `GET /conversations/{id}` (unknown id → 404, fresh conversation → empty messages, `limit=0` and `limit=N` both accepted), `GET /conversations` (unauthenticated → 401), and `DELETE /conversations/{id}` (unauthenticated → 401).

### `test_cluster_snapshots_api.py`

Covers the three cluster-snapshot routes against unknown UUIDs: `GET /cluster-snapshots/{id}` → 404, `GET /cluster-snapshots/{id}/clusters/{id}/members` → 404, `DELETE /cluster-snapshots/{id}` → 404. Note: the router has no auth dependency on `DELETE` — the 401 path documented in `api.md` is not enforced in the current code.

### `test_movies_api.py`

Covers `GET /movies/umap-points` on an empty catalogue (200, empty list) and `GET /movies/{id}` with an unknown integer id (404). `POST /movies/batch` is already covered by `test_smoke.py`.

### `test_concepts_api.py`

Single scope: `GET /concepts/{concept_id}/axis` with an unknown UUID returns 404.

---

## `tests/eval/` — eval data-access and API

### `test_eval_queries.py`

Directly exercises every function in `backend/data_access/eval/queries.py` against a real DB — no HTTP layer involved. Organised into seven test classes:

- **`TestRunCRUD`** — create/get, not-found, get-by-name, count-by-name, list empty, list ordered newest-first, list with `limit`/`offset`.
- **`TestPersonaCRUD`** — create/get, not-found, get-by-slug, list empty, list all.
- **`TestGroundTruthCRUD`** — create/get, not-found, get-by-slug, list empty, list all.
- **`TestEvalSessionCRUD`** — create/get, not-found, session with linked persona and ground truth, list sessions for run, list for unknown run, get by conversation id.
- **`TestTurnIntents`** — insert and list, list empty, duplicate insert is a no-op (`ON CONFLICT DO NOTHING`).
- **`TestConversationMetrics`** — upsert and get, upsert overwrites previous row, not-found.
- **`TestJudgeScores`** — insert and get by conversation, get empty.
- **`TestGetRunAggregate`** — aggregate with one session, unknown run raises `NotFoundError`, empty run returns zero-session aggregate.

### `test_runs_api.py`

HTTP smoke for the four eval run endpoints: `GET /eval/runs`, `GET /eval/runs/{id}`, `GET /eval/runs/{id}/aggregate`, `GET /eval/runs/{id}/sessions`. Each is tested for 401 (no auth), 403 (non-admin), and the happy-path shape (empty list or 404 on unknown id). Notable: `GET /eval/runs/{id}/sessions` returns an empty list (not 404) for an unknown run.

### `test_sessions_api.py`

HTTP smoke for `GET /eval/sessions/{session_id}`: 401, 403, 404, and verifies the 404 response body `detail` field contains the string `"eval session"` to confirm the correct resource type is reported. Also serves as a regression guard for the path parameter rename from `{eval_session_id}` to `{session_id}`.

### `test_personas_api.py`

HTTP smoke for `GET /eval/personas`: 401 (no auth), 403 (non-admin), 200 with empty list (admin on clean DB).

### `test_ground_truths_api.py`

HTTP smoke for `GET /eval/ground-truths`: 401 (no auth), 403 (non-admin), 200 with empty list (admin on clean DB).
