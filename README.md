# Conversational Clustering - CinePal

An AI system that clusters a dataset by *conversing* with a human, proposing a grouping, explaining it, and refining it through dialogue, where the human (the **oracle**) is the sole judge of quality and no intrinsic ground truth exists.

**Course:** Designing Large Scale AI Systems
**Professors:** Prof. Fabio Casati
**Authors:** Davide Donà, Andrea Blushi

----

## Overview

### Prerequisites

- Python 3.11+
- Docker (for Postgres with pgvector, and for running tests)
- [pgvector/pgvector:pg16](https://hub.docker.com/r/pgvector/pgvector) image

### Setup Environment

```bash
cp .env.example .env   # fill in API keys and DATABASE_URL
pip install -r requirements.txt
```

### Database

Start a pgvector-enabled Postgres instance and apply all migrations:

```bash
docker pull pgvector/pgvector:pg16

docker run -d \
  --name cinepal-pg \
  -e POSTGRES_USER=cinepal \
  -e POSTGRES_PASSWORD=cinepal \
  -e POSTGRES_DB=cinepal \
  -p 4321:5432 \
  pgvector/pgvector:pg16

# On subsequent runs, just start the existing container:
# docker start cinepal-pg

export DATABASE_URL=postgresql://cinepal:cinepal@localhost:4321/cinepal
python -m db.apply
```

Re-running `python -m db.apply` is safe — already-applied migrations are skipped.

See `db/README.md` for migration conventions.

### Running tests

Tests spin up a throwaway Postgres container automatically via `testcontainers` — no manual setup required.

```bash
pytest tests/
```

### Catalogue Ingestion

**Prerequisites:** Kaggle credentials at `~/.kaggle/kaggle.json` (or `KAGGLE_USERNAME` / `KAGGLE_KEY` env vars).

```bash
# Full pipeline: download → clean → embed → ingest main set into DB
python -m db.ingest

# Produce artifacts only (no DB writes) — useful to pre-generate data/artifacts/
python -m db.ingest --no-ingest

# Fast dev/CI path: ingest only the 200-movie mini set (requires artifacts to exist)
python -m db.ingest --ingest mini

# Skip re-download if data/raw/ is already populated
python -m db.ingest --no-download
```

The pipeline writes three parquet files under `data/artifacts/`:

| File | Description |
|---|---|
| `main.parquet` | Full training set with embeddings (~40k movies) |
| `mini.parquet` | 200 popular movies — fast to load in dev/CI |
| `eval_holdout.parquet` | Disjoint 10% slice for system evaluation (never in DB) |

`data/` is gitignored. Re-running ingestion is safe — all inserts are idempotent (upsert).

### Quick Start

_Conversational loop (HTTP layer, UI) is not yet implemented._

### Repository Structure

```
backend/
  api/           All SQL access (only layer that touches the DB)
  models/
  orchestrator/  EchoOrchestrator stub; real impl goes here
  routers/       HTTP endpoints
  app.py         FastAPI entry point
  config.py      Environment variable loader
  logging.py     Structured logging + log_llm_call() helper
db/              SQL migrations and migration runner
docs/            Architecture, specifications, requirements
tests/           Schema smoke tests (real Postgres via testcontainers)
```
