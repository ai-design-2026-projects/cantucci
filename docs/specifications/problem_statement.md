# Problem Statement - Conversational Movie Clustering

## 1. Problem Definition

We build a conversational movie recommendation system in which the user (the **oracle**) interacts with an AI through a chat interface to discover films and TV series that match their taste or provide a set of suggestions. The key distinction from a standard recommender is that there is **no fixed objective function**: what constitutes a good recommendation is entirely determined by what the user accepts through a dialogue.

The system does not ask the user to fill out a profile or rate movies upfront. Instead, it starts from the user's first natural-language request, proposes an initial clustering of the available movie space into meaningful groups, then refines that clustering turn by turn as the user reacts. The **clustering is the recommendation**: the user is converging toward a group of titles they want, and the system's job is to reach that group as efficiently as possible, minimising cognitive load per turn while maximising the information extracted from each response.

**Concrete user journey:**
1. User types: *"I want something tense and psychological, not too violent, maybe a thriller from the last 10 years"*
2. System embeds the request, retrieves a candidate pool, produces an initial soft clustering of those titles into named groups (e.g., *"Slow-burn psychological"*, *"Action thriller"*, *"Crime procedural"*)
3. System shows the most relevant cluster's top titles with poster, year, rating, and asks a targeted question (e.g., *"Does something like Gone Girl work for you, or is it too dark?"*)
4. User replies. System updates cluster assignments, possibly merges or splits groups, and either shows the next best question or presents a refined recommendation
5. Repeat until the user is satisfied or a turn budget is exhausted

At the end, the system presents a finalised recommendation list from the user-accepted cluster, including poster images, a short synopsis, and average rating.

---

## 2. Dataset

### 2.1 Source

The catalogue is built directly from **The Movie Database (TMDB)** — no third-party redistribution, no CSV dump. Two TMDB channels are combined to produce a clean, timestamped snapshot of the catalogue:

- **Daily id export** — `http://files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz`. One gzipped JSON-Lines file per day, listing every public movie id along with `original_title`, `popularity`, `adult`, and `video`. We use it as the authoritative list of candidate ids.
- **TMDB v3 REST API** — `https://api.themoviedb.org/3/movie/{id}?append_to_response=credits,keywords`. One request per surviving id, returning the full movie record with credits and keywords appended in the same response.

There is no fixed coverage and no temporal cutoff: the catalogue is whatever survives the filters on the day the snapshot is produced. The snapshot timestamp pinned in `configs/default.yaml` under `ingestion.artifacts.*` is what ties an experimental run to a specific catalogue state, and that pin is folded into `config_hash` so existing sessions remain replayable against the snapshot they were created on.

Producing a snapshot requires `TMDB_API_KEY` (v3, free tier). Once snapshot + embedding parquets are on HuggingFace, downstream ingestion needs only `HF_TOKEN`, and only for private repos.

---

### 2.2 Pipeline overview

The catalogue passes through three stages, run on different machines because TMDB throttles by IP and Colab's shared egress makes sustained scraping unreliable:

| Stage | Where | Entrypoint | Output |
|---|---|---|---|
| 1. Scrape | Local (developer IP) | `python -m db.scrape [--upload]` | `data/local_scrape/tmdb_raw.jsonl` (resumable) → `snapshot_YYYYMMDD.parquet` → optionally pushed to `<hf_repo>/snapshots/` |
| 2. Embed | Colab T4 GPU | `notebooks/embed_in_colab.ipynb` | `<hf_repo>/embeddings/{main,mini,eval_holdout}_YYYYMMDD.parquet` |
| 3. Load | Local / CI | `python -m db.ingest [--set main\|mini\|all]` | Postgres rows (idempotent upsert) |

**Stage 1 filters.** Adult titles are dropped unconditionally. `popularity < ingestion.min_popularity` (default `0.4`) is applied to the id export before fetching, which keeps the candidate set in the low tens of thousands rather than the full ~1M ids in the export. After fetching, `vote_count < ingestion.min_vote_count` (default `5`) is applied to the cleaned DataFrame, dropping the long tail of titles with too little signal for the Bayesian rating to be meaningful. Both thresholds are CLI flags on `db/scrape.py` and become part of the snapshot's identity through `config_hash`.

**Stage 2 split** (`db/ingestion/split.three_way`). The eval holdout is sliced first as a random `eval_frac` (default `0.10`) of the full set; what remains becomes `main`; `mini` is then carved as the top `mini_size` rows of `main` (default `3000`) ranked by `(vote_count desc, popularity desc)`. By construction `mini ⊂ main` and `eval_holdout` is disjoint from both. `eval_holdout` is intentionally never written to the database — it is reserved for offline evaluation.

---

### 2.3 What each stage produces

Rather than duplicate the relational schema here, this section describes the **shape** of the artifact each stage emits. For column-level field types and the JSON-to-relational mapping consumed by stage 3, see [`architecture/data_schema.md`](architecture/data_schema.md).

- **Stage 1 — cleaned snapshot parquet.** One row per surviving TMDB id, produced by `db/ingestion/clean.build_dataframe`. The row carries the TMDB API fields (`title`, `original_title`, `overview`, `tagline`, `release_date`, `runtime`, `budget`, `revenue`, `popularity`, `vote_average`, `vote_count`, `status`, `adult`, `video`, `poster_path`, `homepage`, `belongs_to_collection`, `genres`, `production_companies`, `production_countries`, `spoken_languages`, `cast`, `crew`, `keywords`) plus three derived columns:
  - `release_year` — derived from `release_date[:4]`.
  - `bayesian_rating` — `(v * R + m * C) / (v + m)` where `v = vote_count`, `R = vote_average`, `m = 50`, and `C` is the vote-count-weighted mean across the snapshot. This, not raw `vote_average`, is the supported quality signal.
  - `composite_text` — `title [original_title] [year] genres tagline overview top3_cast director keywords`, concatenated in that order. This is the string fed to the embedding model in stage 2.
- **Stage 2 — embedded parquets.** Same row schema as stage 1, plus a single `embedding` column (`list[float]`, `representation.embedding_dim` long, L2-normalised) produced by `representation.model` on `composite_text`. Three files per snapshot timestamp: `main_*.parquet`, `mini_*.parquet`, `eval_holdout_*.parquet`.
- **Stage 3 — Postgres rows.** `db/ingest.py` pops the `embedding` column into the pgvector column on `movies`, normalises the remaining JSON columns (`genres`, `production_companies`, …) into their relational targets, and upserts on `id`. Re-ingesting the same snapshot is a no-op; ingesting `main` after `mini` does not duplicate rows because `mini ⊂ main`.

---

### 2.4 Data quality notes

- **Budget and revenue sparsity** — TMDB uses `0` for "unknown" on both fields. `clean.map_record` collapses `0` to `None` so it cannot contaminate ranking or filters.
- **Popularity is a daily snapshot** — TMDB's `popularity` is recomputed daily; the value in the parquet is whatever the API returned at scrape time. Treat it as a captured signal, not a stable ranking input.
- **Vote-count skew** — the long tail of low-vote titles is removed by the `min_vote_count` filter; the surviving rows are still skewed, and `bayesian_rating` is the correct ranking signal.
- **Live source, not frozen** — the catalogue reflects TMDB at the snapshot timestamp. Bumping `ingestion.artifacts.*` swaps in a fresh catalogue and flows into `config_hash`, so old sessions remain replayable against their original snapshot.
- **TMDB throttling** — `tmdb_fetch.fetch_movie` retries `429`s 3 times with a 10 s sleep before raising. Sustained throttling is addressed by lowering `--concurrency` on `db/scrape.py`, not by smarter retry logic.
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

The system runs a named-agent loop on each turn:
1. **Retrieval System** embeds the current query and fetches the top-K candidates from the vector store.
2. **Cluster Agent** produces soft clusters with names and short descriptions.
3. **Decision Agent** evaluates relevance and uncertainty to choose **Recommend** (show titles) or **Continue** (ask a clarifying question).
4. **Ambiguity Resolver** generates a focused question when the Decision Agent chooses **Continue**.
5. **Orchestrator** records state updates, prevents duplicate questions, and surfaces the UI response (recommendations or question).

Persistent storage lives in the **Vector Database**, and the **LLM Judge** scores archived sessions offline without influencing live decisions.

**For detailed component descriptions, communication paths, and the design rationale**, see [architecture/architecture_diagram.md](architecture/architecture_diagram.md). The architecture document provides a component table, communication constraints, and explanations for role separation.

---

### 3.3 How the user can give feedback

The user does not have to interact in any fixed way. Although the system will ask targeted yes/no questions about specific titles or cluster boundaries, the user is free to respond in their own words and at their own level of granularity. We expect the user to react at four levels, and the system is designed to handle all of them:

- **Global feedback** : a comment about the whole session or its overall direction.
  *"Too many groups, just give me one list"* / *"I want something less mainstream"*

- **Cluster-level feedback** : a reaction to a named group as a whole.
  *"This 'action thriller' cluster is too broad, split it"* / *"Merge the two drama groups"*

- **Point-level feedback** : a reaction to a specific title.
  *"Parasite is exactly what I'm looking for"* / *"No, Transformers is not what I want"*

- **Instructional feedback** : an explicit rule the user wants to apply.
  *"Treat Nolan and Villeneuve as stylistically equivalent"* / *"Ignore anything before 2000"*


### 3.4 The oracle is an LLM

So far we have spoken about the "user" as if it were always a person sitting at a keyboard. In practice, running a real human study for every experiment — across different questioning strategies, different personas, different configurations — would be far too slow and expensive. 

Instead, for the evaluation runs, **the oracle is simulated by an LLM**. Setting up a simulated oracle allows us to run hundreds of sessions under controlled conditions, systematically ablate variables, and get statistically meaningful results. 

The LLM is prompted to behave like a real user with specific tastes and, a limited attention span and the possibility of contradictions. As any other human would, it interacts with the system through the provided API, reacts to the recommendations, and gives feedback in free-form language. The only difference is that the LLM's "brain" is a prompt rather than a human mind.

---

## 4 Key Design Decisions

### What does the system cluster over?

The pipeline runs in two stages to handle a catalogue on the order of tens of thousands of titles (exact size depends on the snapshot — see section 2).

**Stage 1 — Retrieval.** At ingest time, each movie is embedded by a sentence-transformer (`all-MiniLM-L6-v2`) applied to its composite text: title, synopsis, genres, top-3 cast, and director. These vectors are stored in PostgreSQL via `pgvector`. 

On the first oracle message, the system embeds the query and retrieves the top-K most relevant movies by cosine similarity, producing a candidate pool of ~50–200 titles.
We will consider also fine-tuned transformers for the movie domain like `fine-tuned_movie_retriever-all-minilm-l6-v2`.

**Stage 2 — Clustering.** The system produces a soft clustering of the candidate pool into N groups, using an hybrid approach:
- A **clustering algorithm** (e.g., K-Means, HDBSCAN) produces an initial partitioning based on the embedding vectors alone;
- The **Cluster Agent** then labels each cluster with a name and description, and adjusts the cluster boundaries by moving borderline titles based on the cluster's overall theme and the oracle's feedback history.

On each subsequent turn, oracle feedback (**accept, reject, split, merge**) is injected as explicit constraints into the next clustering prompt. The embeddings never change — only the grouping and labels update. The config exposes `representation.model` and `representation.embedding_dim` to swap the embedding model without touching the rest of the pipeline.

All this behaviour should be abstract to the user. They just see a conversation and a set of recommendations that evolve turn by turn.

---

### Hierarchy: top-down or incremental?

The system exposes a **two-level hierarchy**: a coarse level (3–6 broad clusters, e.g., *"Psychological thriller"*, *"Action"*, *"Drama"*) and a fine level within any cluster the oracle chooses to drill into (e.g., *"Psychological thriller"* → *"Slow-burn / art-house"* vs. *"Mainstream / crowd-pleaser"*). The coarse level is produced on the first turn; fine levels are generated lazily only when the oracle asks to drill in. This avoids overwhelming the oracle upfront while keeping the hierarchy navigable.

---

### What does the system ask, and when?

Every turn has a cognitive-load cost. The **Decision Agent** chooses between:

1. **Show** — display top titles from the current best cluster (high load, high information if oracle reacts)
2. **Ask** — pose a targeted binary question about a boundary title or a proposed split/merge (low load, high precision)
3. **Stop** — declare convergence

The default strategy for the MVP is: **ask if uncertainty is high, show if uncertainty is low**.
In order to define "high" vs. "low" uncertainty, we use the soft cluster assignments: if there are many titles with scores close to the cluster boundary, that's a sign that the system is unsure about the oracle's intent and should ask for clarification. If most titles have a clear assignment, it's safer to show some recommendations and let the oracle react.
However, we will experiment different strategies in the **Decision Agent** to see how they affect convergence speed and oracle satisfaction.

For example:
- Always ask until the oracle accepts, then show the full cluster
- Always show the top 3 titles from the best cluster, then ask if the oracle wants to drill into it or see another cluster

---

### How to handle contradictory feedback?

People change their minds. What looks like a contradiction is usually **preference evolution** — the oracle has seen more options and is refining their taste, not making a mistake. The system must treat it that way.

The rule is: **latest intent wins**. If the oracle said "no horror" in turn 2 and then reacts positively to a horror title in turn 5, the turn-5 signal overrides the turn-2 rule. However, silently applying the new intent without acknowledgement erodes trust — the oracle starts to feel the system ignores what was said. So before overriding, the **Orchestrator** surfaces the conflict explicitly and the **Ambiguity Resolver** frames it as a question:

> *"Earlier you said no horror — does The Babadook work as an exception, or should I drop that rule entirely?"*

This gives the oracle three natural paths:
- **Exception** — the old rule stays, but this one title is allowed.
- **Rule update** — the old rule is replaced; horror is now in scope.
- **Reaffirm** — the oracle confirms the old rule and rejects the new title.

If the oracle preference is contradicting the old rule, the system should retrieve new top-K candidates based on the updated intent and re-cluster from scratch, rather than trying to patch the old clusters. This is because the original clusters were formed under a different intent and may not make sense with the new one. A fresh retrieval and clustering ensures the system's understanding is aligned with the oracle's current preferences.

---

### Cluster names and descriptions

Cluster names are the oracle's primary handle for navigating the recommendation space — they need to be stable enough to feel familiar across turns, and accurate enough to reflect any material change in the cluster's contents.

Names and short descriptions are generated by the **Cluster Agent** on every re-clustering. The generation prompt includes the **previous turn's name** as a starting point and instructs the LLM to keep it unless the cluster's titles have changed significantly. This prevents cosmetic thrashing — names drifting between synonyms turn after turn for no meaningful reason — while still allowing genuine updates when a split or merge changes what the cluster actually contains.

A good name is short (2–4 words), descriptive of tone and genre rather than just genre alone, and consistent with the oracle's own vocabulary where possible. If the oracle has used a phrase like *"slow-burn stuff"* to describe a cluster, that phrasing is a stronger candidate than a generic LLM-generated label.

Both the name and the description are stored as columns on the `clusters` table, scoped to the turn that produced them. This means every past state is auditable: if the oracle disputes how a cluster changed, the full name history is queryable by `session_id` and `turn_number`.

---

### Soft assignments

The system does not assign each title to a single cluster with a hard label. Instead, every title in the candidate pool receives a **soft assignment**: a confidence score per cluster representing how strongly the LLM/cluster algorithm believes the title belongs there. The scores across all clusters for a given title sum to 1.

For example, a film like *Parasite* might be assigned:

```
Crime & thriller   0.55
Dark comedy        0.35
Drama              0.10
```

Titles with a dominant score in one cluster are safe recommendations — the system is confident. Titles with roughly equal scores across two clusters are **boundary cases** — genuinely ambiguous, and the most informative ones to ask the oracle about next (see the **Ambiguity Resolver**).

Soft scores are produced by the **Cluster Agent** in a structured JSON response and stored in the `cluster_assignments` table as a `score` float per (cluster, title) pair. At the end of a session, soft-assignment calibration is validated: boundary-flagged titles should be ones the oracle also finds ambiguous on a pairwise check ("should X and Y be in the same group?"). If the system flags titles as uncertain that the oracle finds obvious, the scoring needs revision.

---

### Cognitive load per turn

Every turn has a cost for the oracle — reading titles, evaluating a question, deciding how to respond. If that cost is too high the oracle disengages or gives low-quality feedback.

Cognitive load per turn is defined as three logged signals:

| Signal | Definition | Per-turn target |
|---|---|---|
| Titles shown | Number of movie cards displayed | ≤ 5 |
| Clusters shown | Number of named groups visible at once | ≤ 6 |
| Question complexity | Binary yes/no = 1; open-ended or multi-part = 2+ | 1 binary question |

The **Decision Agent** uses the same budget when deciding whether to show or ask, and the **Orchestrator** enforces title and cluster caps in the UI: showing 8 titles in one turn is discouraged even when uncertainty is low, because it exceeds the per-turn title budget. Cognitive load is a primary evaluation metric alongside turns to convergence — a strategy that converges in 6 turns but shows 15 titles per turn is not better than one that takes 8 turns at 4 titles per turn.

---

### Generalization: codifying oracle preferences

Accepting a clustering is not the end of the session's usefulness. Once the oracle converges, the **Orchestrator** triggers a preference-profile extraction step to distil everything learned during the conversation into a **preference profile** — a structured, portable summary of the oracle's stated and inferred rules. For example:

```json
{
  "genres": ["Thriller", "Drama"],
  "director_style": ["slow-burn", "psychological"],
  "exclude": ["gore", "pre-2000"],
  "exceptions": ["The Silence of the Lambs"]
}
```

This profile is produced by prompting the LLM with the full `oracle_feedback` log for the session and asking it to extract explicit rules, inferred preferences, and any exceptions the oracle declared. It is stored in the `sessions` table so it can be reused without replaying the conversation.

This also makes the system useful beyond a single session: a preference profile from a converged conversation can in principle be applied to new datasets or used to bootstrap a future session without starting from scratch.

### Stopping signal

Knowing when to stop is as important as knowing what to ask. Stopping too early wastes the oracle's trust; stopping too late wastes their time. Three conditions trigger convergence — whichever fires first:

- **Explicit acceptance** — the oracle says something that clearly signals satisfaction (*"perfect"*, *"yes, that's it"*, *"show me the full list"*). This is the cleanest signal and always takes priority.
- **Behavioural convergence** — no corrective feedback for 2 consecutive turns. The oracle is only confirming or making minor tweaks, which means the clustering has stabilised even if they haven't said so explicitly. The threshold of 2 turns is a configurable parameter (`session.convergence_turns`).
- **Turn budget** — a hard cap configured per session in YAML (`session.max_turns`, default 15). This exists to bound cost and prevent sessions that drift without converging. When the budget is hit, the system presents the current best clustering as the final result and notifies the oracle that the session has ended.

When convergence is declared, the session status is set to `converged`, the preference profile is produced, and no further oracle turns are accepted.

---

## 5 Requirements Summary

### 5.1 Functional capabilities

| Area | Capability | Implemented by | Priority |
|---|---|---|---|
| **Data ingestion** | Ingest catalogue into PostgreSQL: genre normalisation, crew linkage, embedding generation | `catalogue_loader.py` | MVP |
| **Data ingestion** | Construct poster URLs from `poster_path`; verify synopsis field presence | `catalogue_loader.py` | MVP |
| **Retrieval** | Embed oracle query and retrieve top-K candidate titles by cosine similarity | `embedding.py` + pgvector | MVP |
| **Retrieval** | Filter candidate pool by year range, genre, runtime, rating threshold | Retrieval System | MVP |
| **Clustering** | Produce initial soft clustering of candidates into 3–6 named groups with descriptions | Cluster Agent | MVP |
| **Clustering** | Maintain soft assignment scores (per title, per cluster) across all turns | `cluster_assignments` table | MVP |
| **Clustering** | Support two-level hierarchy: coarse clusters expanded lazily on oracle request | Cluster Agent + Orchestrator | MVP |
| **Interaction** | Accept oracle feedback at all four levels: global, cluster, point, instructional | Orchestrator | MVP |
| **Interaction** | Decide next action (show / ask / stop) within cognitive-load budget | Decision Agent | MVP |
| **Interaction** | Detect and surface preference drift before silently overriding earlier feedback | Orchestrator | MVP |
| **Interaction** | Emit convergence signal and produce preference profile when session ends | Orchestrator | MVP |
| **Session** | Persist full conversation history and clustering snapshots — every turn replayable | PostgreSQL + `replay.py` | MVP |
| **Session** | Provide shareable session URL (UUID-based) | `sessions` API | MVP |
| **Session** | Mark session `abandoned` after 24 h of inactivity | background job | Post-MVP |
| **UX** | Display poster, title, year, and rating for every recommended title | `TitleCard` component | MVP |
| **Evaluation** | Run LLM-simulated oracle sessions with seeded persona and preference spec | `oracle_simulator.py` | MVP |
| **Evaluation** | Score sessions via LLM-as-Judge (coherence, question quality, profile fidelity) | `judge.py` | MVP |

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
| Oracle contradicts earlier feedback | The Orchestrator detects the conflict by comparing the new message against the full `oracle_feedback` log. It surfaces the contradiction explicitly (*"Earlier you said no horror — is this an exception or should I drop that rule?"*) and waits for resolution before updating state. The resolution is stored as `feedback_type = 'resolve_drift'`. | Orchestrator |
| Very broad first query (*"a good movie"*) | The candidate pool would be effectively the entire catalogue. The Decision Agent flags low specificity and the Ambiguity Resolver returns a targeted clarifying question instead of a cluster display (*"What kind of mood are you in — something intense, something light, or something in between?"*). | Decision Agent + Ambiguity Resolver |
| Title not in catalogue | The catalogue reflects TMDB at the pinned snapshot timestamp; titles released afterwards, or titles that were filtered out by `min_vote_count` / `min_popularity`, will not be present. The system acknowledges the gap, names the snapshot date, and returns the 3 most similar titles by cosine distance as alternatives. | Orchestrator |
| TMDB poster unavailable | `poster_path` is null or the CDN returns a 404. The UI falls back to a genre-specific placeholder image. The card layout is never broken or left blank. | `TitleCard` |
| Oracle requests a title type excluded by active filter (e.g. short film, documentary) | The system notifies the oracle that the current filter excludes that type and offers to relax it with a single confirm. The relaxed filter is stored as an instructional feedback row. | Orchestrator |
| Session idle > 24 h | The session status is set to `abandoned`. All state remains queryable and replayable, but no cluster is kept in active memory. If the oracle returns, they are shown the last clustering state and offered to resume or start a new session. | background job |
| Oracle turn budget exhausted (`session.max_turns`) | The system presents the current best cluster as the final result, notifies the oracle that the turn budget has been reached, and produces the preference profile even without explicit convergence. | Decision Agent + Orchestrator |
| LLM returns malformed JSON for cluster assignments | The harness catches the parse failure, retries with exponential backoff (max 3 attempts), and on persistent failure logs the error and returns the previous turn's clustering unchanged rather than crashing the session. | `llm_harness.py` |
| Candidate pool is empty after filters are applied | Filters are relaxed one at a time in order of least impact (rating threshold first, then year range, then runtime) until at least 20 candidates are available. The oracle is notified of the relaxation. | Retrieval System + Orchestrator |