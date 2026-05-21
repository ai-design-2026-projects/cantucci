# Database — migrations and catalogue ingestion

---

## Connecting to psql
To connect to the Postgres instance running in Docker, use:
```bash
# Source install (standalone container named cinepal-pg)
docker exec -it cinepal-pg psql -U cinepal

# Docker Compose install
docker compose exec db psql -U cinepal -d cinepal
```

---

## Migrations

Migrations are plain SQL files in `db/migrations/`, applied in lexicographic order by `db/apply.py`.

**Docker Compose install:** migrations are applied automatically each time the backend container starts — no manual step needed.

**Source install:**
```bash
export DATABASE_URL=postgresql://cinepal:cinepal@localhost:4321/cinepal
python -m db.apply
```

Re-running `apply` is safe — files already recorded in `schema_migrations` are skipped.

### Adding a new migration

1. Create `db/migrations/NNN_description.sql` where `NNN` is the next integer (zero-padded to 3 digits).
2. Write idempotent DDL where possible (`CREATE TABLE IF NOT EXISTS`, etc.).
3. **Never edit a migration that has already been applied** to a shared environment. Create a new file instead.

### File index

| File | Contents |
|---|---|
| `001_extensions.sql` | `pgvector`, `pgcrypto` |
| `002_runs.sql` | `runs` — experimental run registry |
| `003_catalogue.sql` | Catalogue tables: `movies`, `collections`, `genres`, `people`, `cast_members`, `crew_members`, `keywords`, `production_companies`, `languages`, `countries` + join tables |
| `004_sessions.sql` | Session-runtime tables: `sessions`, `turns`, `clusters`, `cluster_assignments`, `oracle_feedback` |
| `005_eval_results.sql` | Evaluation tables: `session_metrics`, `judge_scores` |

---

## Catalogue ingestion

`python -m db.ingest` is the single entry point. It downloads the parquet files
pinned in `configs/default.yaml` (`ingestion.hf_repo` + `ingestion.artifacts.*`)
from Hugging Face and upserts them into Postgres.

**Docker Compose install** — run ingestion once after the stack is up:
```bash
docker compose run --rm backend python -m db.ingest             # mini (dev default)
docker compose run --rm backend python -m db.ingest --set main  # full production set
```

**Source install:**
```bash
python -m db.apply              # apply migrations (idempotent)
python -m db.ingest             # ingest mini (dev default)
python -m db.ingest --set main  # ingest full production set
python -m db.ingest --set all   # ingest main + mini
```

**Prerequisites:**

- `TMDB_API_KEY` in `.env` — only when producing a fresh snapshot (stage 1
  below). Ingesting an existing HF snapshot does not need it.
- `HF_TOKEN` in `.env` — only when the HF dataset repo is private.

**For dev/CI use the default `mini` set.** Mini is a strict subset of main, so
ingesting main later with `--set main` is safe (upsert) and won't duplicate
data.

### Producing a new snapshot

The offline data pipeline (TMDB scrape → clean → Colab embed → HF upload) lives in
`dataset/`. See [`dataset/README.md`](../dataset/README.md) for the full workflow.

---

## Creating users

A small helper script provisions a user row in the database. Roles must
already exist in the `roles` table (seeded by migration `006`).

Usage example (creates an admin):

```bash
# ensure `DATABASE_URL` points at your Postgres instance
export DATABASE_URL=postgresql://cinepal:cinepal@localhost:4321/cinepal

python -m db.create_user \
  --email admin@example.com \
  --password s3cr3t \
  --role admin
```

The script validates the email/password and prints the new user id on
success. See `db/create_user.py` for more details.
