# tests.md — smoke-test behavior spec

The suite is intentionally narrow: **smoke tests only**. Each test answers the
question "is component X correctly wired into the rest of the system?" and
nothing more. Quality, fairness, and clustering evaluation belong elsewhere.

## Shared infrastructure

- `tests/db/test_config.py` is registered as a pytest plugin in `pyproject.toml`
  (`addopts = "-p tests.db.test_config"`). It owns the session-scoped pgvector
  Postgres container, applies all migrations, and ingests the **mini** parquet
  artifact from Hugging Face via the real `db.ingest` pipeline.
- `configs/test.yaml` is the test config file. It is force-pinned via
  `CONFIG_PATH` by the same plugin. `model.dry_run: true` means no LLM bytes
  ever leave the test runner; `llm_harness.call()` loads a JSON fixture from
  `tests/fixtures/dry_run/{step_type}.json` instead.
- `tests/backend/conftest.py` exposes a session-scoped `client` fixture that
  enters the FastAPI lifespan, so the embedding model is preloaded once.

## DB smoke (`tests/db/test_smoke.py`)

1. **migrations recorded** — `schema_migrations` row count equals the number
   of `.sql` files in `db/migrations/`.
2. **embedding dimensionality** — `movies.embedding` matches
   `settings.representation.embedding_dim`.
3. **vector index exists** — there is an `ivfflat` index on `movies.embedding`.
4. **similarity query runs** — a cosine-distance ORDER BY against the ingested
   catalogue returns 5 rows in non-decreasing distance order.

## Backend smoke (`tests/backend/test_smoke.py`)

1. **route table matches spec** — `POST /sessions`, `POST /sessions/{id}/turns`,
   `GET /sessions/{id}` are present.
2. **dry_run is active** — guard test: `settings.model.dry_run is True` under
   `configs/test.yaml`. If this flips, every other backend smoke test silently
   becomes a real-API test.
3. **create session persists** — `POST /sessions` returns a 201 with a UUID,
   `GET /sessions/{id}` returns the same id.
4. **full turn runs end-to-end** — `POST /sessions/{id}/turns` returns a
   well-formed `TurnResult` whose `step_type` is one of `ask | show | stop`.
   This exercises retrieval, embedding, soft clustering, the cluster describer,
   the decision agent (fixture), and either the ambiguity agent (fixture) or
   the render step (fixture) depending on the decision branch taken.
5. **config-hash invariant** — the `runs.config_hash` row for the session
   equals `backend.settings.get_config_hash()`. Replay invariant from
   CLAUDE.md.

## What's intentionally NOT tested here

- Recommendation quality, cluster correctness, or convergence policy.
- Live LLM behaviour, prompt regressions, or model-version drift.
- Auth, rate limits, or multi-tenant isolation (none of these exist yet).
- Concurrency, race conditions, or pool exhaustion.

Those belong in a separate suite (or in the eval harness) — not here.
