# Conversational Clustering — CinePal

An AI system that clusters a movie catalogue by *conversing* with a human oracle who proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function — no intrinsic ground truth exists.

**Course:** Designing Large Scale AI Systems — Prof. Fabio Casati
**Authors:** Davide Donà, Andrea Blushi

---
## Demo video

https://github.com/user-attachments/assets/b308d0ea-cb32-4a1b-897f-7ba45f78df00


---

## Component docs

- [`backend/README.md`](backend/README.md) — FastAPI service, endpoints, env vars, logging helper.
- [`frontend/README.md`](frontend/README.md) — React + Vite UI (forthcoming).
- [`db/README.md`](db/README.md) — Postgres migrations and loading pre-built HF artifacts.
- [`dataset/README.md`](dataset/README.md) — Offline data pipeline: TMDB scrape → Colab embed → HF upload.
- [`demo/README.md`](demo/README.md) — Record/replay demo scripts
- [`eval/README.md`](eval/README.md) — Offline evaluation harness (forthcoming).


---

## Quick start — Docker (recommended)

Requires Docker and Docker Compose. Pulls versioned images from GitHub Container Registry — no local build needed.

```bash
# 1. Copy and fill the environment file
cp .env.example .env
# Required: AUTH_SECRET, and one LLM key (OPENAI_API_KEY or OPENROUTER_API_KEY).
# Generate AUTH_SECRET with: openssl rand -hex 32
# Optional: set CINEPAL_VERSION=vX.Y.Z to pin a release (defaults to latest).

# 2. Start all services (Postgres + backend + frontend)
docker compose up -d

# 3. Load the catalogue — one-time, takes a few minutes
docker compose run --rm backend python -m db.ingest

# UI at http://localhost — Swagger at http://localhost:8000/docs
```

On subsequent starts: `docker compose up -d` (migrations are re-applied automatically on each backend start; `db.ingest` only needs to run once unless you switch datasets).

To stop: `docker compose down` (data is preserved in the `cinepal-pgdata` volume).

### Releases

Every `v*` tag on `main` produces two versioned images via the CD pipeline (`.github/workflows/release.yml`):

- `ghcr.io/ai-design-2026-projects/cinepal-backend:vX.Y.Z`
- `ghcr.io/ai-design-2026-projects/cinepal-frontend:vX.Y.Z`

Both are also tagged `latest`. Pin a release in `.env` with `CINEPAL_VERSION=vX.Y.Z`.

---

## Quick start — from source (for contributors)

```bash
# 1. Environment
cp .env.example .env   # fill DATABASE_URL, OPENAI_API_KEY (HF_TOKEN if repo is private)
# AUTH_SECRET is required — generate one and add it to .env:
#   echo "AUTH_SECRET=$(openssl rand -hex 32)" >> .env

# 2. Python dependencies
uv sync --extra test   # core + test deps; add --extra dataset for the scrape pipeline

# 3. Start Postgres + pgvector
docker run -d \
  --name cinepal-pg \
  -e POSTGRES_USER=cinepal \
  -e POSTGRES_PASSWORD=cinepal \
  -e POSTGRES_DB=cinepal \
  -p 4321:5432 \
  pgvector/pgvector:pg16
# On subsequent runs: docker start cinepal-pg

# 4. Apply migrations
python -m db.apply

# 5. Ingest catalogue (mini set — fast, ingestion artifact pinned in configs/default.yaml)
python -m db.ingest
# Producing a fresh snapshot is two stages — scrape locally, embed in Colab:
#   python -m dataset.scraper --upload    # stage 1: TMDB → HF (snapshots/)
#   open notebooks/embed_in_colab.ipynb  # stage 2: HF snapshot → embed → HF (embeddings/)
# See dataset/README.md for the full workflow.

# 6. Run backend
uvicorn backend.app:app
# API at http://127.0.0.1:8000 — Swagger at /docs

# 7. Run frontend
cd frontend && npm install && npm run dev
# UI at http://127.0.0.1:5173

# 8. Run smoke tests (testcontainers spins a throwaway pgvector container automatically;
#    configs/test.yaml forces dry_run mode so no OPENAI_API_KEY is needed).
CONFIG_PATH=configs/test.yaml pytest tests/

# 9. Evaluation
# The eval harness is forthcoming. The current suite under tests/ is intentionally
# narrow — smoke tests that verify wiring between the DB, ingestion, and the
# orchestrator/agents. Scoped CI runs them on every PR; see .github/workflows/smoke.yml.
```

---

## Repository structure

```
backend/    FastAPI service, agents, LLM harness, DB access layer
configs/    YAML experimental-condition configs (model, clustering, …)
dataset/    Offline data pipeline: TMDB scrape, clean, embed, HF upload
db/         Postgres schema migrations + load pre-built HF artifacts
demo/       Record/replay demo scripts and manifests
eval/       Offline evaluation harness — Oracle simulator, judge, runner
frontend/   React + Vite UI
notebooks/  Colab GPU embedding notebook
tests/      Smoke tests (real Postgres via testcontainers; dry_run LLM via fixtures)
```

---

## License

See [LICENSE](LICENSE).
