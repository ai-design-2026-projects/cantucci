# Smoke test spec

This suite is intentionally minimal. It proves the two things that can't be caught by static analysis:
migrations apply against a real Postgres, and the FastAPI app boots and serves against that migrated DB.
Do not add per-agent or per-function tests here.

## db smoke (`tests/db/`)

- All migrations in `db/migrations/` apply cleanly to a fresh pgvector container.
- Applying them a second time is idempotent (returns 0 new migrations).
- Every migration filename is recorded in `schema_migrations`.
- Migration 012 creates: `personas`, `ground_truths`, `eval_sessions`, `conversation_metrics`, `judge_scores`.
- Migration 012 ALTER TABLE adds: `name`, `condition`, `model_version`, `ended_at`, `status`, `notes` to `runs`.

## backend smoke (`tests/backend/`)

- `POST /movies/batch` with unknown IDs returns HTTP 200 and an empty list on the migrated DB.
- `GET /docs` returns HTTP 200 (app boots, OpenAPI schema generates).

## evaluation (`tests/evaluation/`)

- `oracle_turn` in dry_run mode (test.yaml has `dry_run: true`) returns a well-formed `OracleTurnResult`
  without hitting a live LLM API. Exercises the fixture at `tests/fixtures/dry_run/oracle_turn.json`.
- `compute_clustering_metrics` returns a positive silhouette score for two tight, well-separated clusters.
- `compute_clustering_metrics` returns `silhouette=None` when there is only one cluster or no members.
