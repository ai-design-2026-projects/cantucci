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

`python -m db.ingest` is the single entry point. It defaults to downloading pre-built artifacts from Hugging Face and ingesting the `mini` set.

The embedding step (`sentence-transformers/BAAI/bge-large-en-v1.5` over ~40k movies) is slow on CPU. **The team default is to embed once on a GPU and distribute the artifacts via Hugging Face Datasets.** The full local pipeline is still available for reproducibility or when artifacts need to be regenerated.

### Default path — pre-built artifacts from HF (recommended)

**Prerequisites:** `CINEPAL_ARTIFACTS_REPO` set in `.env`. `HF_TOKEN` is only required for private repos.

```bash
python -m db.apply              # apply migrations (idempotent)
python -m db.ingest             # HF download → ingest mini (200 popular movies; dev default)
python -m db.ingest --set main  # HF download → ingest full production set (~40k movies)
```

**For dev/CI use the default `mini` set.** Mini is a strict subset of main — all 200 popular movies are also present in main, so ingesting main later with `--set main` is safe (upsert) and won't duplicate or lose data.

### Full local pipeline — regenerate artifacts from Kaggle (slow)

**Prerequisites:** Kaggle credentials at `~/.kaggle/kaggle.json` (or `KAGGLE_USERNAME` / `KAGGLE_KEY` env vars).

```bash
# Full pipeline: download → clean → embed → ingest mini into DB
python -m db.ingest --source kaggle

# Build artifacts only (no DB writes) — useful when re-publishing to HF from Colab
python -m db.ingest --source kaggle --no-db

# Re-download raw data even if already present
python -m db.ingest --source kaggle --force-download
```

To regenerate artifacts using a GPU, open `notebooks/embed_in_colab.ipynb` in Google Colab (Runtime → T4 GPU), run all cells, and the notebook uploads fresh artifacts to the configured HF repo.

### Artifact files

The pipeline writes three parquet files under `data/artifacts/` (`data/` is gitignored):

| File | Description |
|---|---|
| `main.parquet` | Full set with embeddings (~40k movies) |
| `mini.parquet` | Top-200 popular movies — a **subset** of main; fast to load in dev/CI |
| `eval_holdout.parquet` | Disjoint 10% slice for system evaluation (never written to the DB) |

Re-running ingestion is safe — all inserts are idempotent (upsert).
