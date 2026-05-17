# Conversational Clustering — CinePal

An AI system that clusters a movie catalogue by *conversing* with a human oracle who proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function — no intrinsic ground truth exists.

**Course:** Designing Large Scale AI Systems — Prof. Fabio Casati
**Authors:** Davide Donà, Andrea Blushi

---

## Component docs

- [`backend/README.md`](backend/README.md) — FastAPI service, endpoints, env vars, logging helper.
- [`db/README.md`](db/README.md) — Postgres migrations and catalogue ingestion.
- [`frontend/README.md`](frontend/README.md) — React + Vite UI.

---

## Quick start

```bash
# 1. Environment
cp .env.example .env   # fill DATABASE_URL, OPENAI_API_KEY (HF_TOKEN if repo is private)

# 2. Python dependencies
pip install -r requirements.txt

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
#   python -m db.scrape --upload     # stage 1: TMDB → HF (snapshots/)
#   open notebooks/embed_in_colab.ipynb  # stage 2: HF snapshot → embed → HF (embeddings/)
# See db/README.md for the full workflow.

# 6. Run backend
uvicorn backend.app:app --reload
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
db/         Migrations + catalogue ingestion pipeline
frontend/   React + Vite UI
notebooks/  Colab GPU embedding notebook
tests/      Smoke tests (real Postgres via testcontainers; dry_run LLM via fixtures)
```

---

## License

See [LICENSE](LICENSE).
