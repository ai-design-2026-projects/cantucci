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
| `002_users.sql` | `users`, `roles`, `user_roles` — user registry and role-based access |
| `003_catalogue.sql` | Catalogue tables: `movies`, `genres`, `people`, `keywords`, `cast_members`, `crew_members`, `movie_genres`, `movie_keywords` + IVFFlat vector indexes |
| `004_runs.sql` | `runs` — experimental run registry keyed on config hash |
| `005_conversations.sql` | `conversations`, `messages` — per-user conversation history |
| `006_cluster_snapshots.sql` | `cluster_snapshots`, `clusters`, `cluster_memberships` — snapshot tree |
| `007_concepts.sql` | `concepts`, `concept_scores` — oracle-derived linear axes and prototype concepts |
| `008_nullable_cluster_label.sql` | Allow `clusters.label` to be NULL (labels generated lazily) |
| `009_snapshot_cache.sql` | `config_hash` column, `conversation_snapshot_refs` join table, cache-key unique index on `cluster_snapshots` |
| `010_trailer_embedding_index.sql` | IVFFlat index on `movies.trailer_embedding` for fast cosine-similarity search |

---

## Catalogue ingestion

`python -m db.ingest` is the single entry point. It downloads the parquet files
pinned in `configs/dev.yaml` (`ingestion.hf_repo` + `ingestion.artifacts.*`)
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

- `HF_TOKEN` in `.env` — only when the HF dataset repo is private. Not needed for public repos.
- `TMDB_API_KEY` — only needed when producing a fresh snapshot via `dataset.scraper`. Ingesting a pre-built HF artifact does not require it.

**For dev/CI use the default `mini` set.** Mini is a strict subset of main, so
ingesting main later with `--set main` is safe (upsert) and won't duplicate
data.

### Producing a new snapshot

The offline data pipeline (TMDB scrape → clean → Colab embed → HF upload) lives in
`dataset/`. See [`dataset/README.md`](../dataset/README.md) for the full workflow.

---

## Creating users

A small helper script provisions a user row in the database. Roles must
already exist in the `roles` table (seeded by migration `002_users.sql`).

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
