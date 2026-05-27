# Problem Statement - Conversational Movie Clustering

## 1. Problem Definition

We build a conversational movie recommendation system in which the user (the **oracle**) interacts with an AI through a chat interface to discover films and TV series that match their taste or provide a set of suggestions. The key distinction from a standard recommender is that there is **no fixed objective function**: what constitutes a good recommendation is entirely determined by what the user accepts through a dialogue.

The system does not ask the user to fill out a profile or rate movies upfront. Instead, it starts from the user's first natural-language request, proposes an initial clustering of the available movie space into meaningful groups, then refines that clustering turn by turn as the user navigates. The **clustering is the recommendation**: the user converges toward a group of titles they want, and the system's job is to reach that group as efficiently as possible, minimising cognitive load per turn while maximising the information extracted from each response.

**Concrete user journey:**
1. User types: *"I want something tense and psychological, not too violent, maybe a thriller from the last 10 years"*
2. System embeds the request, retrieves a candidate pool, produces an initial soft clustering of those titles into named groups (e.g., *"Slow-burn psychological"*, *"Action thriller"*, *"Crime procedural"*)
3. System shows the clusters with top titles, poster, year, and rating per cluster
4. User navigates in free-form language: *"merge the last two"*, *"break down the first group by how dark they are"*, *"only keep films from the 2010s"*
5. System parses the request into operations, executes them, and returns the updated clustering
6. Repeat until the user is satisfied or a turn budget is exhausted

---

## 2. Dataset

### 2.1 Source

The catalogue is built directly from **The Movie Database (TMDB)** — no third-party redistribution, no CSV dump. Two TMDB channels are combined to produce a clean, timestamped snapshot of the catalogue:

- **Daily id export** — `http://files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz`. One gzipped JSON-Lines file per day, listing every public movie id along with `original_title`, `popularity`, `adult`, and `video`. We use it as the authoritative list of candidate ids.
- **TMDB v3 REST API** — `https://api.themoviedb.org/3/movie/{id}?append_to_response=credits,keywords`. One request per surviving id, returning the full movie record with credits and keywords appended in the same response.

There is no fixed coverage and no temporal cutoff: the catalogue is whatever survives the filters on the day the snapshot is produced. The snapshot timestamp pinned in `configs/dev.yaml` under `ingestion.artifacts.*` is what ties an experimental run to a specific catalogue state, and that pin is folded into `config_hash` so existing sessions remain replayable against the snapshot they were created on.

Producing a snapshot requires `TMDB_API_KEY` (v3, free tier). Once snapshot + embedding parquets are on HuggingFace, downstream ingestion needs only `HF_TOKEN`, and only for private repos.

---

### 2.2 Pipeline overview

The catalogue passes through three stages, run on different machines because TMDB throttles by IP and Colab's shared egress makes sustained scraping unreliable:

| Stage | Where | Entrypoint | Output |
|---|---|---|---|
| 1. Scrape | Local (developer IP) | `python -m dataset.scraper [--upload]` | `data/local_scrape/tmdb_raw.jsonl` (resumable) → `snapshot_YYYYMMDD.parquet` → optionally pushed to `<hf_repo>/snapshots/` |
| 2. Embed | Colab T4 GPU | `notebooks/embed_in_colab.ipynb` | `<hf_repo>/embeddings/{main,mini,eval_holdout}_YYYYMMDD.parquet` |
| 3. Load | Local / CI | `python -m db.ingest [--set main\|mini\|all]` | Postgres rows (idempotent upsert) |

**Stage 1 filters.** Adult titles are dropped unconditionally. `popularity < ingestion.min_popularity` (default `0.4`) is applied to the id export before fetching, which keeps the candidate set in the low tens of thousands rather than the full ~1M ids in the export. After fetching, `vote_count < ingestion.min_vote_count` (default `5`) is applied to the cleaned DataFrame, dropping the long tail of titles with too little signal for the Bayesian rating to be meaningful. Both thresholds are CLI flags on `dataset/scraper.py` and become part of the snapshot's identity through `config_hash`.

**Stage 2 split** (`dataset.transform.split`). The eval holdout is sliced first as a random `eval_frac` (default `0.10`) of the full set; what remains becomes `main`; `mini` is then carved as the top `mini_size` rows of `main` (default `3000`) ranked by `(vote_count desc, popularity desc)`. By construction `mini ⊂ main` and `eval_holdout` is disjoint from both. `eval_holdout` is intentionally never written to the database — it is reserved for offline evaluation.

---

### 2.3 What each stage produces

Rather than duplicate the relational schema here, this section describes the **shape** of the artifact each stage emits. For column-level field types and the JSON-to-relational mapping consumed by stage 3, see [`architecture/data_schema.md`](architecture/data_schema.md).

- **Stage 1 — cleaned snapshot parquet.** One row per surviving TMDB id, produced by `dataset.transform.clean.build_dataframe`. The row carries the TMDB API fields (`title`, `original_title`, `overview`, `tagline`, `release_date`, `runtime`, `budget`, `revenue`, `popularity`, `vote_average`, `vote_count`, `status`, `adult`, `video`, `poster_path`, `homepage`, `belongs_to_collection`, `genres`, `production_companies`, `production_countries`, `spoken_languages`, `cast`, `crew`, `keywords`) plus three derived columns:
  - `release_year` — derived from `release_date[:4]`.
  - `bayesian_rating` — `(v * R + m * C) / (v + m)` where `v = vote_count`, `R = vote_average`, `m = 50`, and `C` is the vote-count-weighted mean across the snapshot. This, not raw `vote_average`, is the supported quality signal.
  - `composite_text` — `title [original_title] [year] genres tagline overview top3_cast director keywords`, concatenated in that order. This is the string fed to the text embedding model in stage 2.
- **Stage 2 — embedded parquets.** Same row schema as stage 1, plus embedding columns (`list[float]`, `representation.embedding_dim` long, L2-normalised) produced by `representation.model` (`BAAI/bge-large-en-v1.5`) on `composite_text`. Three files per snapshot timestamp: `main_*.parquet`, `mini_*.parquet`, `eval_holdout_*.parquet`.
- **Stage 3 — Postgres rows.** `db/ingest.py` pops the embedding columns into the pgvector columns on `movies`, normalises the remaining JSON columns (`genres`, `production_companies`, …) into their relational targets, and upserts on `id`. Re-ingesting the same snapshot is a no-op; ingesting `main` after `mini` does not duplicate rows because `mini ⊂ main`.

---

### 2.4 Data quality notes

- **Budget and revenue sparsity** — TMDB uses `0` for "unknown" on both fields. `clean.map_record` collapses `0` to `None` so it cannot contaminate ranking or filters.
- **Popularity is a daily snapshot** — TMDB's `popularity` is recomputed daily; the value in the parquet is whatever the API returned at scrape time. Treat it as a captured signal, not a stable ranking input.
- **Vote-count skew** — the long tail of low-vote titles is removed by the `min_vote_count` filter; the surviving rows are still skewed, and `bayesian_rating` is the correct ranking signal.
- **Live source, not frozen** — the catalogue reflects TMDB at the snapshot timestamp. Bumping `ingestion.artifacts.*` swaps in a fresh catalogue and flows into `config_hash`, so old sessions remain replayable against their original snapshot.
- **TMDB throttling** — `tmdb_fetch.fetch_movie` retries `429`s 3 times with a 10 s sleep before raising. Sustained throttling is addressed by lowering `--concurrency` on `dataset/scraper.py`, not by smarter retry logic.
- **Deleted or hidden ids** — `404` responses on the per-id fetch are dropped silently. The daily id export drifts ahead of the API view, so a non-trivial fraction of ids will not resolve.

### 2.5 Poster and synopsis availability

Every TMDB API response carries `overview` and `poster_path`, so no extra enrichment step is needed for either. Poster URLs are built at serve time as `https://image.tmdb.org/t/p/w500{poster_path}`. If a title has no poster, the UI shows a placeholder.

---

## 3. How Conversational Clustering Applies Here

### 3.1 The core idea

Most recommender systems optimise for a fixed signal — clicks, ratings, watch-time — which only loosely approximates what a person actually wants. Our system takes a different stance: **there is no fixed objective**. The user tells us, turn by turn, whether the suggestions are heading in the right direction. **The user's acceptance is the objective function**.

This is the conversational clustering setting: instead of asking the user to fill out a taste profile upfront, we start from a single natural-language message, immediately group the catalogue into a handful of candidate clusters, and then refine those groups based on what the user says next. The conversation is the optimisation loop.

---

### 3.2 What the system does on each turn {#system-on-each-turn}

The system runs a stateless **Coordinator** pipeline on each user message:

1. **Load & label** — the Coordinator reads the conversation's current cluster snapshot. If any clusters are unlabeled (true for freshly ingested root clusters), the **Labeling Agent** names them all in one batched LLM call before proceeding.
2. **Intent classification** — the **Intent Agent** parses the oracle's message into an ordered list of actions, each tagged as a `NavigationMode` or `DialogueMode` operation with a confidence score and inferred parameters (target cluster, concept, metadata filter, etc.).
3. **Confidence gate** — if any state-changing action's confidence falls below the configured threshold, the **Clarifier Agent** returns a disambiguation question and the turn exits early without mutating any state.
4. **Sequential execution** — the Coordinator dispatches each action in order. Navigation operations invoke the **Clustering Agent** (a pure computation layer) and optionally the **Concept Agent** for concept-guided splits, then persist results via a content-addressed cache keyed by `(parent_snapshot_id, operation, params, config_hash)`. Cache hits reuse existing snapshots at zero re-clustering cost.
5. **Suggestion** — the **Responder Agent** computes deterministic signals on the final snapshot and optionally proposes a follow-up action to the oracle.

For detailed component descriptions and turn-handling phases, see [`architecture/architecture.md`](architecture/architecture.md).

---

### 3.3 How the user can give feedback

The oracle never picks an operation from a menu. They type free-form text; the **Intent Agent** maps it onto a fixed, closed set of operations. There are two families:

- **Navigation operations** — re-cluster the data, producing a new snapshot:
  - `drill_down` — split a cluster further along a concept, or re-cluster from scratch (*"break the noir group down by how violent they are"*)
  - `merge` — combine two or more clusters (*"these two are basically the same, combine them"*)
  - `focus` — discard every cluster except one (*"just keep the sci-fi cluster"*)
  - `cross_filter` — keep only movies matching a metadata predicate (*"only 90s films directed by Spielberg"*)
  - `partition_by` — bucket a numeric attribute into contiguous ranges (*"split by decade"*, *"group by runtime"*)

- **Dialogue operations** — navigate or query without producing new clusters:
  - `reset` / `go_to_base` — return to unclustered state or the ingest-time root
  - `explain` — ask why a specific movie sits in a given cluster (*"why is Blade Runner in this group?"*)
  - `small_talk` — casual, non-operational message

A single message can request a compound sequence (e.g. *"reset, then split everything by mood"*); the Coordinator executes them in order. The oracle does not need to conform to any fixed vocabulary — the Intent Agent handles natural variations.

---

### 3.4 The oracle is an LLM

So far we have spoken about the "user" as if it were always a person sitting at a keyboard. In practice, running a real human study for every experiment — across different questioning strategies, different personas, different configurations — would be far too slow and expensive.

Instead, for the evaluation runs, **the oracle is simulated by an LLM**. Setting up a simulated oracle allows us to run hundreds of sessions under controlled conditions, systematically ablate variables, and get statistically meaningful results.

The LLM is prompted to behave like a real user with specific tastes, a limited attention span, and the possibility of contradictions. As any other human would, it interacts with the system through the provided API, reacts to the clustering state, and gives feedback in free-form language. The only difference is that the LLM's "brain" is a prompt rather than a human mind.

---

## 4 Key Design Decisions

### What does the system cluster over?

The pipeline runs in two stages to handle a catalogue on the order of tens of thousands of titles (exact size depends on the snapshot — see section 2).

**Stage 1 — Retrieval.** At ingest time, each movie is embedded across up to three modalities:
- **TEXT** — `BAAI/bge-large-en-v1.5` on `composite_text` (title, synopsis, genres, cast, director, keywords)
- **REVIEW** — `BAAI/bge-large-en-v1.5` on concatenated review text
- **TRAILER** — `open_clip ViT-H/14` on 16 evenly-spaced trailer frames, mean-pooled (fallback to poster if no trailer)

Vectors are stored in PostgreSQL via `pgvector`. On the first oracle message, the system embeds the query and retrieves the top-K most relevant movies by cosine similarity, producing a candidate pool of ~50–200 titles.

**Stage 2 — Clustering.** The system produces a soft clustering of the candidate pool using UMAP dimensionality reduction followed by **HDBSCAN soft clustering**. Each movie receives a per-cluster membership probability. The Clustering Agent is a pure computation layer — it receives embeddings or a precomputed distance matrix and returns a draft snapshot; it never writes to the DB and makes no LLM calls. Labeling is handled separately by the Labeling Agent after the snapshot is persisted.

The Intent Agent picks which modalities to fuse per operation, enabling text-only, review-guided, or visual (trailer-aware) groupings within the same conversation.

---

### Hierarchy: top-down or incremental?

The system exposes a **two-level hierarchy**: a coarse level (3–6 broad clusters) visible from the start, and a fine level within any cluster the oracle chooses to drill into. Fine levels are generated lazily only when the oracle issues a `drill_down` operation on a specific cluster. This avoids overwhelming the oracle upfront while keeping the hierarchy navigable.

The `drill_down` operation optionally accepts a **concept** (e.g. *"how violent they are"*): the Concept Agent turns this into a linear axis or prototype, scores every movie in scope against it, splits at the median, and clusters each half independently — producing groups that are coherent along that dimension.

---

### When does the system withhold action?

By default, the system always executes what the oracle requests. The **Clarifier Agent** is the sole exception: it fires when any state-changing action's confidence falls below the configured threshold (`intent.confidence_threshold`), returning a disambiguation question without mutating state. The oracle's reply is stored as the awaited message and re-routed correctly on the next turn.

This is intentionally minimal — the system does not evaluate whether to show or ask, does not score uncertainty across the cluster space, and does not decide when recommendations are "ready". The oracle drives the pace.

---

### How to handle evolving preferences?

People change their minds. What looks like a contradiction is usually **preference evolution** — the oracle has seen more options and is refining their taste. The system handles this naturally: every navigation operation produces a new snapshot node in the content-addressed tree, and the oracle can always navigate backward (`go_to_base`, `reset`) or issue a new operation from any prior node. The Coordinator executes the latest instruction without conflict detection; the full snapshot lineage is queryable if the oracle wants to retrace their path.

---

### Cluster names and descriptions

Cluster names are the oracle's primary handle for navigating the recommendation space — they need to be stable enough to feel familiar across turns and accurate enough to reflect material changes in the cluster's contents.

Naming is handled by the **Labeling Agent** in a single batched LLM call. Clusters are ingested unlabeled and labeled lazily on first access; once a snapshot is labeled its names are stored and reused on cache hits. The labeling prompt includes the previous turn's names as anchors and instructs the model to keep them unless the cluster's titles have changed significantly, preventing cosmetic thrashing between synonyms while still allowing genuine updates after splits or merges.

Both the name and the description are stored on the `clusters` table, scoped to the snapshot that produced them, so every past state is auditable.

---

### Soft assignments

The system does not assign each title to a single cluster with a hard label. Instead, every title in the candidate pool receives a **soft assignment**: a per-cluster membership probability from HDBSCAN, where scores across all clusters sum to 1.

For example, a film like *Parasite* might be assigned:

```
Crime & thriller   0.55
Dark comedy        0.35
Drama              0.10
```

Titles with a dominant score in one cluster are confident placements. Titles with roughly equal scores across two clusters are **boundary cases** — genuinely ambiguous, and useful candidates for a concept-guided `drill_down`. Soft scores are stored in the `cluster_memberships` table as a `score` float per (cluster, movie) pair.

---

### Cognitive load per turn

Every turn has a cost for the oracle — reading titles, evaluating cluster names, deciding how to navigate. If that cost is too high the oracle disengages or gives low-quality feedback.

Cognitive load per turn is defined as three logged signals:

| Signal | Definition | Per-turn target |
|---|---|---|
| Titles shown | Number of movie cards displayed | ≤ 5 |
| Clusters shown | Number of named groups visible at once | ≤ 6 |
| Question complexity | Binary yes/no = 1; open-ended or multi-part = 2+ | 1 binary question |

Cognitive load is a primary evaluation metric alongside turns to convergence — a strategy that converges in 6 turns but shows 15 titles per turn is not better than one that takes 8 turns at 4 titles per turn.

---

### Stopping signal

The live Coordinator loop does not detect convergence. The oracle navigates until they are satisfied and stops sending messages. Three conditions bound session length:

- **Turn budget** — a hard cap configured per session in YAML (`session.max_turns`, default 15). When the budget is hit, the runner stops and the final clustering state is treated as the session result.
- **Oracle accept** — the eval runner monitors oracle outputs for an explicit `accept` signal and stops iteration.
- **Oracle abandon** — the eval runner stops on an `abandon` signal when the oracle gives up without converging.

Convergence is detected **post-hoc** by the evaluation harness (`eval/metrics.py`) scanning the message history after the session ends. This separation keeps the production Coordinator path unmodified across evaluation conditions.

---

## 5 Requirements Summary

### 5.1 Functional capabilities

| Area | Capability | Implemented by | Priority |
|---|---|---|---|
| **Data ingestion** | Ingest catalogue into PostgreSQL: genre normalisation, crew linkage, embedding generation | `dataset/scraper.py`, `db/ingest.py` | MVP |
| **Data ingestion** | Construct poster URLs from `poster_path`; verify synopsis field presence | `db/ingest.py` | MVP |
| **Retrieval** | Embed oracle query and retrieve top-K candidate titles by cosine similarity | `core/text_encoder.py` + pgvector | MVP |
| **Retrieval** | Filter candidate pool by year range, genre, runtime, rating threshold | `cross_filter` operation / Clustering Agent | MVP |
| **Clustering** | Produce initial soft clustering of candidates into 3–6 named groups with descriptions | Clustering Agent + Labeling Agent | MVP |
| **Clustering** | Maintain soft assignment scores (per title, per cluster) across all turns | `cluster_memberships` table | MVP |
| **Clustering** | Support five navigation operations: drill_down, merge, focus, cross_filter, partition_by | Clustering Agent operations | MVP |
| **Clustering** | Cache snapshots content-addressed on (parent_id, operation, params, config_hash) | `persist_and_label` in Coordinator | MVP |
| **Interaction** | Accept oracle feedback as free-form natural language mapped to operations | Intent Agent | MVP |
| **Interaction** | Gate low-confidence actions with a clarification question, no state mutation | Clarifier Agent | MVP |
| **Interaction** | Support concept-guided drill_down via linear axis or prototype | Concept Agent | MVP |
| **Interaction** | Explain why a movie sits in a given cluster | Explanation Agent | MVP |
| **Interaction** | Optionally propose a follow-up action after operations complete | Responder Agent | MVP |
| **Session** | Persist full conversation history and clustering snapshot tree — every turn replayable | PostgreSQL + Coordinator | MVP |
| **Session** | Allow oracle to navigate back to any prior snapshot | `PATCH /conversations/{id}` + snapshot lineage | MVP |
| **Session** | Provide shareable conversation URL (UUID-based) | conversations API | MVP |
| **UX** | Display poster, title, year, and rating for every recommended title | `TitleCard` component | MVP |
| **Evaluation** | Run LLM-simulated oracle sessions with seeded persona and preference spec | `eval/oracle/agent.py`, `eval/runner.py` | MVP |
| **Evaluation** | Score sessions via LLM-as-Judge (4 dims: clustering_coherence, question_quality, label_accuracy, intent_alignment) | `eval/judge/agent.py` | MVP |
| **Evaluation** | Compute deterministic clustering metrics (silhouette, turns-to-convergence, cost, spec-satisfaction) post-hoc | `eval/metrics.py` | MVP |

### 5.2 Non-functional requirements

| Requirement | Target |
|---|---|
| Chat response latency (p95) | < 3 s including LLM call |
| Embedding vector search latency | < 200 ms via pgvector IVFFlat index |
| Catalogue size | ≥ 40,000 titles after dedup and quality filter |
| Session state persistence | PostgreSQL only — no in-memory-only state |
| LLM call logging | Token counts (input/output separately), model version, prompt hash — every call |
| Cost hard-stop | Configurable per session in YAML (`session.cost_limit_usd`) |
| Reproducibility | Same seed + config → same session transcript |

### 5.3 Edge cases

| Trigger | System response | Component |
|---|---|---|
| Oracle issues a vague or ambiguous operation | The Intent Agent assigns low confidence. The Clarifier Agent returns a disambiguation question without mutating state; the oracle's reply is stored as the awaited message and re-routed on the next turn. | Clarifier Agent |
| Very broad first query (*"a good movie"*) | The candidate pool would be effectively the entire catalogue. The Intent Agent flags low specificity; the Clarifier Agent returns a targeted clarifying question instead of clustering (*"What kind of mood are you in — something intense, something light, or something in between?"*). | Intent Agent + Clarifier Agent |
| Oracle navigates back and re-explores | `PATCH /conversations/{id}` re-points the active snapshot. Any new operation from that node creates a new child; the prior branch is untouched and still reachable. | Coordinator + snapshot lineage |
| Title not in catalogue | The catalogue reflects TMDB at the pinned snapshot timestamp; titles released afterwards, or filtered out by `min_vote_count` / `min_popularity`, will not be present. The system acknowledges the gap, names the snapshot date, and returns the 3 most similar titles by cosine distance as alternatives. | Coordinator |
| TMDB poster unavailable | `poster_path` is null or the CDN returns a 404. The UI falls back to a genre-specific placeholder image. The card layout is never broken or left blank. | `TitleCard` |
| Oracle requests a title type excluded by active filter (e.g. short film, documentary) | The system notifies the oracle that the current filter excludes that type and offers to relax it with a single confirm. The relaxed filter is stored as an instructional feedback row. | Coordinator |
| Oracle turn budget exhausted (`session.max_turns`) | The eval runner stops iteration and treats the current clustering state as the session result. The Coordinator is not involved in this decision. | eval runner |
| LLM returns malformed output for clustering or labeling | The harness catches the parse failure, retries with exponential backoff (max 3 attempts), and on persistent failure raises — sessions do not silently return stale state. | `llm_harness.py` |
| Candidate pool is empty after filters are applied | Filters are relaxed one at a time in order of least impact (rating threshold first, then year range, then runtime) until at least 20 candidates are available. The oracle is notified of the relaxation. | Clustering Agent + Coordinator |
