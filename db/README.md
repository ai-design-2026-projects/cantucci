# Database migrations
Migrations are plain SQL files in `db/migrations/`, applied in lexicographic order by `db/apply.py`.

## Connecting to the psql terminal
```bash
docker exec -it cinepal-pg psql -U cinepal
```

## Running migrations
```bash
# Prerequisites: Postgres 15+ with pgvector extension available.
# See .env.example for DATABASE_URL format.
export DATABASE_URL=postgresql://cinepal:cinepal@localhost:5432/cinepal
python -m db.apply
```

Re-running `apply` is safe — files already recorded in `schema_migrations` are skipped.

## Adding a new migration
1. Create `db/migrations/NNN_description.sql` where `NNN` is the next integer (zero-padded to 3 digits).
2. Write idempotent DDL where possible (`CREATE TABLE IF NOT EXISTS`, etc.).
3. **Never edit a migration that has already been applied** to a shared environment. Create a new file instead.

## File index
| File | Contents |
|---|---|
| `001_extensions.sql` | `pgvector`, `pgcrypto` |
| `002_runs.sql` | `runs` — experimental run registry |
| `003_catalogue.sql` | Catalogue tables: `movies`, `collections`, `genres`, `people`, `cast_members`, `crew_members`, `keywords`, `production_companies`, `languages`, `countries` + join tables |
| `004_sessions.sql` | Session-runtime tables: `sessions`, `turns`, `clusters`, `cluster_assignments`, `oracle_feedback` |
| `005_eval_results.sql` | Evaluation tables: `session_metrics`, `judge_scores` |