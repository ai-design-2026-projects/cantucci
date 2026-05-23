# Dataset/ — offline data pipeline

This directory owns everything between raw TMDB data and the HuggingFace embeddings artifact that `db.ingest` loads into Postgres. It runs outside the backend server and does not share any code with the live request path.

---

## Two-stage pipeline

The pipeline is split across two machines for two main reasons:
1) The embedding stage is GPU-accelerated and can be sped up by using a Colab T4 instance;
2) TMDB throttles requests per IP and Colab's shared egress makes sustained scraping unreliable.

### Stage 1 — local scrape (`dataset/scraper.py`)

Run on your machine with `TMDB_API_KEY` set in the environment.

Pulls the TMDB daily ID export, drops adult titles and entries below `--min-popularity` (default `5`), then fetches `/movie/{id}?append_to_response=credits,keywords` for each surviving ID. After cleaning, rows with `vote_count < --min-vote-count` (default `10`) are dropped before the parquet is written.

```bash
python -m dataset.scraper --limit 500 --concurrency 5   # smoke test first
python -m dataset.scraper --upload                      # full run + push to HF snapshots/
```

Writes raw JSONL to `data/local_scrape/tmdb_raw.jsonl` (resumes on restart) and a cleaned `snapshot_YYYYMMDD.parquet` to the same directory. With `--upload` the parquet is pushed to the HF dataset repo under `snapshots/`. Paste the printed path into `configs/default.yaml` under `ingestion.artifacts.snapshot`.

**Required env vars:** `TMDB_API_KEY`. Optional: `CINEPAL_ARTIFACTS_REPO` (HF repo ID), `HF_TOKEN` (private repos only).

### Stage 2 — Colab embedding (`notebooks/embed_in_colab.ipynb`)

Run on a Colab T4 GPU instance.

1. Open `notebooks/embed_in_colab.ipynb`.
2. Add Colab secrets: `HF_TOKEN`, optional `GITHUB_TOKEN` for private repo clone.
3. Mount Google Drive when prompted — trailer embedding shards are saved there so the job can resume if a Colab session ends before all trailers are embedded.
4. Run all cells. The notebook downloads the snapshot pinned in `configs/default.yaml`, splits into mini/main/eval-holdout sets, embeds text on GPU, embeds trailers in resumable shards (persisted on Google Drive), and uploads three timestamped parquets via `dataset.hub.upload.upload_artifacts` under `embeddings/`.
5. Paste the three printed paths into `configs/default.yaml` under `ingestion.artifacts.{main,mini,eval_holdout}`. The new artifact paths become part of `config_hash`, so existing conversations remain replayable against the snapshot they were created with.

---

## Module reference

Modules are grouped by *what they do*, not by which pipeline stage uses them.

| Module | Description |
|---|---|
| `scraper.py` | Stage-1 CLI entry point: TMDB scrape → cleaned parquet → HF snapshots/ |
| `fetch/tmdb.py` | TMDB API client: daily export download, `/movie/{id}` bulk fetch, review fetch |
| `fetch/trailer.py` | Download a YouTube trailer via yt-dlp and sample evenly-spaced frames |
| `embed/trailer.py` | Trailer-specific orchestration: frames → `core.image_encoder.encode_images` → mean-pool |
| `transform/clean.py` | Filter, deduplicate, and normalise raw TMDB JSONL into a cleaned DataFrame |
| `transform/split.py` | Produce mini / main / eval-holdout splits |
| `transform/offline.py` | Offline pipeline: `core.fusion.fuse_batch` → UMAP 2D → `core.clustering.hdbscan_soft`. Called by `db.ingest` |
| `hub/upload.py` | Push timestamped parquets to HuggingFace Hub |
| `hub/fetch.py` | Download a pinned artifact from HuggingFace Hub (shared with `db.ingest`) |

The text encoder, image encoder, fusion, and HDBSCAN primitives live in the
top-level `core/` package and are imported by both this offline pipeline and
the live backend.

---

## Artifact layout on HuggingFace

| Path in repo | Description |
|---|---|
| `snapshots/snapshot_YYYYMMDD.parquet` | Stage-1 cleaned catalogue (no embeddings) |
| `embeddings/main_YYYYMMDD.parquet` | Full set with embeddings |
| `embeddings/mini_YYYYMMDD.parquet` | Strict subset of main; fast to load in dev/CI |
| `embeddings/eval_holdout_YYYYMMDD.parquet` | Disjoint slice for evaluation (never written to DB) |

All ingestion inserts are idempotent (upsert), so re-running with newer artifacts is safe.
