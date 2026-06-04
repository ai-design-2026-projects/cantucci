# Database

Postgres schema migrations, catalogue ingestion, and user management for CinePal. Migrations are plain SQL applied in lexicographic order; ingestion downloads pre-built HuggingFace artifacts and upserts them into Postgres.

---

## Commands

Requires `DATABASE_URL` in your environment (see `.env.example`). Make sure the Postgres container is running before any of these commands:

```bash
docker run -d \
  --name cinepal-pg \
  -e POSTGRES_USER=cinepal \
  -e POSTGRES_PASSWORD=cinepal \
  -e POSTGRES_DB=cinepal \
  -p 4321:5432 \
  pgvector/pgvector:pg16
# Subsequent runs: docker start cinepal-pg
```

```bash
source .venv/bin/activate
python -m db.apply
python -m db.ingest
python -m db.create_user --email admin@example.com --password s3cr3t --role admin
```

**`db.ingest --set`**

| Value | Description |
|---|---|
| `mini` (default) | Small dev/CI subset — fast to load |
| `main` | Full production catalogue |
| `eval` / `eval_holdout` | Disjoint holdout split used by the eval harness |
| `all` | `main` + `mini` (deduplicated) |

**`db.create_user --role`**

| Value | Description |
|---|---|
| `admin` | Full access including the Evaluation Lab |
| `user` | Standard oracle access |

---

## Debug

Open a `psql` shell inside the running container to inspect tables and run SQL queries directly:

```bash
docker exec -it cinepal-pg psql -U cinepal -d cinepal
```

## Migrations

Migrations are plain SQL files in `db/migrations/`, applied in lexicographic order by `db/apply.py`. Re-running is safe — files already recorded in `schema_migrations` are skipped.

**Adding a new migration:**

1. Create `db/migrations/NNN_description.sql` with `NNN` as the next zero-padded integer.
2. Write idempotent DDL where possible (`CREATE TABLE IF NOT EXISTS`, …).
3. Never edit a migration already applied to a shared environment — create a new file instead.

---

## Catalogue ingestion

`python -m db.ingest` downloads artifacts pinned in `configs/dev.yaml` (`ingestion.hf_repo` + `ingestion.artifacts.*`) from HuggingFace, upserts them into Postgres, then computes fused embeddings and UMAP coordinates offline. `mini` is a strict subset of `main` — ingesting `main` later is safe.

`HF_TOKEN` is only needed when the HF dataset repo is private. To regenerate the catalogue from scratch see [`dataset/README.md`](../dataset/README.md).

---

## Directory layout

```
db/
├── apply.py           Migration runner — applies all pending .sql files idempotently
├── ingest.py          Ingestion entry point — downloads HF artifacts, upserts into Postgres
├── create_user.py     User provisioning CLI
├── migrations/        Numbered SQL files applied in lexicographic order
└── utils/
    └── load.py        Low-level upsert helpers used by ingest.py
```
