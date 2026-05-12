# Conversational Clustering

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

### Quick Start

_Catalogue ingestion and the conversational loop are not yet implemented._

### Repository Structure

```
db/                     SQL migrations and migration runner
docs/                   Architecture, specifications, requirements
src/
  api/                  All SQL access (only layer that touches the DB)
  config.py             Environment variable loader
  logging_setup.py      JSON-line structured logger
tests/                  Schema smoke tests (real Postgres via testcontainers)
```
