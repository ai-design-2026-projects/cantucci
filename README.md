# CinePal — Conversational Movie Clustering

**CinePal** turns natural-language dialogue into a structured, evolving clustering of a movie catalogue. A human oracle proposes groupings, refines them across turns, and the system continuously restructures the catalogue to match their intent, providing an interactive, conversational way to explore and organize large movie collections.

**Course:** Designing Large Scale AI Systems — Prof. Fabio Casati

**Authors:** Davide Donà, Andrea Blushi

---
## Demo video

https://github.com/user-attachments/assets/95a79f0f-2e41-40f0-88f5-f9e8a581a8bf

---

## Component docs

- **[`backend/README.md`](backend/README.md)** — FastAPI service: HTTP endpoints, multi-agent coordinator pipeline, LLM harness with cost limits, JWT auth.
- **[`frontend/README.md`](frontend/README.md)** — React + Vite + TypeScript UI: component tree, Zustand + react-query state.
- **[`db/README.md`](db/README.md)** — Postgres: all 17 migration files indexed with descriptions, `db.apply` / `db.ingest` / `db.create_user` CLI reference.
- **[`dataset/README.md`](dataset/README.md)** — Offline catalogue pipeline: Stage 1 scrapes TMDB locally; Stage 2 embeds text, images, and trailer frames on a Colab GPU and uploads to HuggingFace.
- **[`demo/README.md`](demo/README.md)** — Record live sessions to JSONL manifests and replay them deterministically with zero LLM calls; includes Playwright browser automation scripts.
- **[`eval/README.md`](eval/README.md)** — Evaluation harness: build persona bundles (`eval.builder`), run parallel simulated sessions (`eval.run`), auto-compute deterministic metrics and 7-dimension LLM-judge scores.
- **[`mcp_server/README.md`](mcp_server/README.md)** — MCP server that exposes CinePal as 10 callable tools (conversations, snapshots, movies, concepts) for AI agents.

---

## Quick start — Docker (recommended)

Go to **[Releases](https://github.com/ai-design-2026-projects/cantucci/releases)**, pick the latest release, and download the two attached files: `docker-compose.yml` and `.env.example`.

```bash
# 1. Create your env file from the example and fill in the required values
cp .env.example .env

# 2. Pull the images and start all services (Postgres + backend + frontend)
#    The catalogue is loaded automatically on first start — this takes a few minutes.
docker compose up -d

# UI at http://localhost:8080 — Swagger at http://localhost:8000/docs
```

On subsequent starts: `docker compose up -d`. Migrations re-apply automatically; `db.ingest` only needs to be run once unless you switch datasets.

To stop: `docker compose down` (data is preserved in the `cinepal-pgdata` volume).

**MCP server** — the [MCP server](mcp_server/README.md) is included but off by default. Start it alongside the other services with:

```bash
docker compose --profile mcp up -d
```

---

## Quick start — from source (for contributors)

For local development, active contributions, or running the evaluation harness. Requires Python 3.11+, Node 18+, and Docker (for the Postgres container).

### 1. Environment

```bash
# Fill out the required values in your .env file (see .env.example for reference)
cp .env.example .env

# Generate AUTH_SECRET:
echo "AUTH_SECRET=$(openssl rand -hex 32)" >> .env
```

### 2. Python dependencies

```bash
uv sync --extra test              		# core + test deps
uv sync --extra test --extra dataset  	# add dataset pipeline deps (sentence-transformers, pandas, …)

source .venv/bin/activate         		# activate the virtual environment
```

### 3. Postgres + pgvector

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

### 4. Schema + catalogue

```bash
python -m db.apply    # apply migrations (idempotent)
python -m db.ingest   # load mini set — fast; artifact pinned in configs/dev.yaml
```

To regenerate the catalogue from scratch see [`dataset/README.md`](dataset/README.md).

### 5. Run backend + frontend

```bash
uvicorn backend.app:app --reload   			# API at http://127.0.0.1:8000 — Swagger at /docs
cd frontend && npm install && npm run dev   # UI at http://127.0.0.1:5173
```

### 6. Tests

```bash
CONFIG_PATH=configs/test.yaml pytest tests/
```

`testcontainers` spins a throwaway pgvector instance automatically; `configs/test.yaml` forces `dry_run` so no live LLM key is needed.

### 7. Evaluation

```bash
python -m eval.builder   # build persona bundles
python -m eval.run       # run simulated oracle sessions
```

See [`eval/README.md`](eval/README.md) for the full workflow.

---

## Repository structure

```
├── backend/      FastAPI service, agents, LLM harness, DB access layer
├── configs/      YAML experimental-condition configs (model, clustering, …)
├── core/         Shared primitives: text/image/trailer encoders, fusion, clustering
├── dataset/      Offline data pipeline: TMDB scrape, clean, embed, HF upload
├── db/           Postgres schema migrations + load pre-built HF artifacts
├── demo/         Record/replay demo scripts and manifests
├── docs/         Specifications: evaluation strategy, API reference, data schema
├── eval/         Offline evaluation harness — Oracle simulator, judge, runner
├── frontend/     React + Vite UI
├── mcp_server/   MCP server exposing CinePal tools to AI agents
├── notebooks/    Colab GPU embedding notebook
└── tests/        Smoke tests (real Postgres via testcontainers; dry_run LLM via fixtures)
```

---

## License

See [LICENSE](LICENSE).
