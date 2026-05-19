# Database — migrations and catalogue ingestion

---

## Connecting to psql
To connect to the Postgres instance running in Docker, use:
```bash
docker exec -it cinepal-pg psql -U cinepal
```

---

## Migrations

Migrations are plain SQL files in `db/migrations/`, applied in lexicographic order by `db/apply.py`.

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

Two stages, run on different machines because TMDB throttles per IP and Colab's
shared egress makes sustained scraping unreliable:

**Stage 1 — local scrape** (your machine, `TMDB_API_KEY` set in env):

Pulls the TMDB daily id export
(`http://files.tmdb.org/p/exports/movie_ids_*.json.gz`), drops adult titles
and everything below `--min-popularity` (default `0.4`), then fetches
`/movie/{id}?append_to_response=credits,keywords` for each surviving id.
After cleaning, rows with `vote_count < --min-vote-count` (default `5`) are
dropped before the parquet is written.

```bash
python -m db.scrape --limit 500 --concurrency 5    # smoke first
python -m db.scrape --upload                       # full run + push to HF
```

Writes raw JSONL to `data/local_scrape/tmdb_raw.jsonl` (resumes on restart) and
a cleaned `snapshot_YYYYMMDD.parquet` to the same directory. With `--upload` the
parquet is pushed to the HF dataset repo under `snapshots/`. Paste the printed
path into `configs/default.yaml` under `ingestion.artifacts.snapshot`.

**Stage 2 — Colab embedding** (Runtime → T4 GPU):

1. Open `notebooks/embed_in_colab.ipynb`.
2. Add Colab secrets: `HF_TOKEN`, optional `GITHUB_TOKEN` for private repo clone.
3. Run all cells. The notebook downloads the snapshot pinned above, splits,
   embeds on GPU, and uploads three timestamped parquets via
   `db/ingestion/upload.upload_artifacts` under `embeddings/`.
4. Paste the three printed paths into `configs/default.yaml` under
   `ingestion.artifacts.{main,mini,eval_holdout}`; the `snapshot` path was
   already pinned in stage 1. The new dataset is now part of `config_hash`,
   so existing sessions remain replayable against the snapshot they were
   created on.

### Artifact files

The HF dataset repo is organised into two directories:

| Path-in-repo | Description |
|---|---|
| `snapshots/snapshot_YYYYMMDD.parquet`         | Stage-1 cleaned catalogue (no embeddings) — pinned via `ingestion.artifacts.snapshot` |
| `embeddings/main_YYYYMMDD.parquet`            | Stage-2 full set with embeddings — pinned via `ingestion.artifacts.main` |
| `embeddings/mini_YYYYMMDD.parquet`            | Stage-2 strict subset of main; fast to load in dev/CI |
| `embeddings/eval_holdout_YYYYMMDD.parquet`    | Stage-2 disjoint slice for system evaluation (never written to the DB) |

Re-running ingestion is safe — all inserts are idempotent (upsert).

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
