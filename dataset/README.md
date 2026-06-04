# Dataset — offline data pipeline

Everything between raw TMDB data and the HuggingFace embeddings artifact that `db.ingest` loads into Postgres. Runs outside the backend and shares no code with the live request path.

---

## Two-stage pipeline

The pipeline is split across two machines:

1. **Stage 1 — local scrape** (`dataset/scraper.py`): TMDB throttles by IP and Colab's shared egress makes sustained scraping unreliable. Run from your machine with `TMDB_API_KEY` set.
2. **Stage 2 — Colab embedding** (`notebooks/embed_in_colab.ipynb`): GPU-accelerated text and trailer/poster embedding. Run on a Colab T4 instance.

---

## Stage 1 — local scrape

```bash
source .venv/bin/activate
uv sync --extra dataset   # installs pandas, httpx, tqdm, yt-dlp, sentence-transformers, …
python -m dataset.scraper --limit 500 --concurrency 5   # smoke test
python -m dataset.scraper --upload                       # full run + push to HF snapshots/
```

Pulls the TMDB daily ID export, drops adult titles and entries below `--min-popularity`, fetches `/movie/{id}?append_to_response=credits,keywords` for each surviving ID, then writes a cleaned `snapshot_YYYYMMDD.parquet` to `data/local_scrape/`. Raw responses are streamed to `tmdb_raw.jsonl` as they arrive — the scraper resumes automatically on restart, skipping already-fetched IDs. With `--upload` the parquet is pushed to HF under `snapshots/`.

| Argument | Default | Description |
|---|---|---|
| `--limit` | none | Cap on number of IDs to fetch |
| `--concurrency` | `8` | Parallel fetch workers |
| `--min-vote-count` | `10` | Drop movies with fewer votes |
| `--min-popularity` | `5` | Drop movies below this TMDB popularity score |
| `--output-dir` | `data/local_scrape` | Local output directory |
| `--upload` | false | Push parquet to HF after scraping |
| `--repo-id` | from config | HF dataset repo ID (overrides `ingestion.hf_repo` from `configs/dev.yaml`) |
| `--skip-reviews` | false | Skip fetching review text |

**Required env vars:** `TMDB_API_KEY`. Optional: `HF_TOKEN` (private repos only).

Output lands in `data/local_scrape/` — gitignored, never committed.

Paste the printed snapshot path into `configs/dev.yaml` under `ingestion.artifacts.snapshot`.

---

## Stage 2 — Colab embedding

1. Open `notebooks/embed_in_colab.ipynb` on a Colab T4 GPU instance.
2. Add Colab secrets: `HF_TOKEN`, optional `GITHUB_TOKEN` for private repo clone.
3. Mount Google Drive when prompted — trailer embedding shards are saved there so the job can resume across sessions.
4. Run all cells. The notebook downloads the snapshot pinned in `configs/dev.yaml`, splits into mini/main/eval-holdout sets (`mini_size=500`, `eval_frac=0.10`, configurable under `split:` in `configs/dev.yaml`), embeds text on GPU, embeds trailer frames in resumable shards (falling back to poster images in the same CLIP space when a trailer is unavailable), and uploads three timestamped parquets to HF under `embeddings/`.
5. Paste the three printed paths into `configs/dev.yaml` under `ingestion.artifacts.{main,mini,eval_holdout}`.

---

## Embedding parameters

| Modality | Model | Output dim | Notes |
|---|---|---|---|
| Text (`composite_text`) | `BAAI/bge-large-en-v1.5` (SentenceTransformers) | 1024 | Title, original title, year, genres, tagline, overview, top-3 cast, director, keywords |
| Review (`reviews_text`) | `BAAI/bge-large-en-v1.5` (SentenceTransformers) | 1024 | TMDB review text; zero vector when unavailable |
| Trailer | `ViT-H/14` open_clip (`laion2b_s32b_b79k`) | 1024 | 16 evenly-spaced frames → per-frame CLIP → mean-pool → L2-norm |
| Poster (fallback) | Same `ViT-H/14` open_clip | 1024 | Used when trailer is unavailable; same CLIP space as trailer |
| Fused (text + review) | — | 1024 | Weighted sum: `text_weight=0.6`, `review_weight=0.4` |
| Clustering UMAP | — | 50 | Pre-HDBSCAN dimensionality reduction (`clustering_n_components`) |
| Visualization UMAP | — | 2 | Final (x, y) stored in `movies.umap_x / umap_y` |

---

## Artifact layout on HuggingFace

| Path | Description |
|---|---|
| `snapshots/snapshot_YYYYMMDD.parquet` | Stage-1 cleaned catalogue (no embeddings) |
| `embeddings/main_YYYYMMDD.parquet` | Full set with embeddings |
| `embeddings/mini_YYYYMMDD.parquet` | Strict subset of main; fast to load in dev/CI |
| `embeddings/eval_holdout_YYYYMMDD.parquet` | Disjoint slice for evaluation |

---

## Module layout

```
dataset/
├── scraper.py          Stage-1 CLI entry point
├── fetch/
│   ├── tmdb.py         TMDB API client: daily export download, bulk movie fetch
│   ├── trailer.py      Download YouTube trailer via yt-dlp, sample evenly-spaced frames
│   └── poster.py       Download poster images from TMDB
├── transform/
│   ├── clean.py        Filter, deduplicate, and normalise raw TMDB JSONL
│   ├── split.py        Produce mini / main / eval-holdout splits
│   └── offline.py      Fused embeddings → UMAP 50D → HDBSCAN → UMAP 2D (called by db.ingest)
└── hub/
    ├── fetch.py        Download a pinned artifact from HuggingFace Hub
    └── upload.py       Push timestamped parquets to HuggingFace Hub
```

Text, image, and trailer encoding primitives live in `core/` and are imported by both this pipeline and the live backend.
