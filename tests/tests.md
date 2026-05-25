# Smoke test spec

This suite is intentionally minimal. It proves the two things that can't be caught by static analysis:
migrations apply against a real Postgres, and the FastAPI app boots and serves against that migrated DB.
Do not add per-agent or per-function tests here.

## db smoke (`tests/db/`)

- All migrations in `db/migrations/` apply cleanly to a fresh pgvector container.
- Applying them a second time is idempotent (returns 0 new migrations).
- Every migration filename is recorded in `schema_migrations`.

## backend smoke (`tests/backend/`)

- `POST /movies/batch` with unknown IDs returns HTTP 200 and an empty list on the migrated DB.
- `GET /docs` returns HTTP 200 (app boots, OpenAPI schema generates).
