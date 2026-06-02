# Problem Statement - Conversational Movie Clustering

## 1. Problem Definition

> This document describes the problem and the high-level design decisions behind it. For detailed technical documentation see [`data_schema.md`](architecture/data_schema.md), [`architecture.md`](architecture/architecture.md), and [`api.md`](architecture/api.md).

---

We build a **conversational clustering** system: the user (the **oracle**) sends natural-language messages, and the system responds by grouping a movie catalogue into named clusters that the oracle can then inspect, navigate, and refine. There is **no fixed objective function** — clustering quality is defined entirely by the oracle's acceptance. What the oracle accepts through dialogue *is* the objective.

The system starts from the first natural-language message, produces an initial soft clustering of the relevant catalogue slice into a handful of named groups, and then refines those groups turn by turn as the oracle navigates. The oracle converges toward a clusteriring of titles they want.

**Concrete user journey:**
1. User opens a new session; the system starts from the full ingested catalogue with no clusters yet.
2. User types: *"Split by genre"* — the system produces an initial soft clustering into named groups (e.g., *"Action & Adventure"*, *"Drama"*, *"Horror"*)
3. System shows the clusters with top titles, poster, year, and rating per cluster
4. User navigates in free-form language: *"merge the last two"*, *"break down drama by how dark they are"*, *"only keep films from the 2010s"*, *"remove the horror group"*
5. System parses the request into operations, executes them, and returns the updated clustering
6. Repeat until the user is satisfied or a turn budget is exhausted

---

## 2. Dataset

### 2.1 Source

The catalogue is built directly from **The Movie Database (TMDB)** — a community-maintained, openly-accessible database covering over one million film titles with rich metadata including cast, crew, genres, keywords, ratings, runtime, and poster images. We do not rely on third-party CSV dumps or proprietary licensing: every record is fetched live from TMDB at snapshot time, giving us a reproducible, timestamped slice of the catalogue.

Four channels should be combined to produce each snapshot:

- **[Daily ID export](http://files.tmdb.org/p/exports/movie_ids_MM_DD_YYYY.json.gz)** — a free, unauthenticated gzipped JSON-Lines file published each day at `files.tmdb.org`. It lists every public movie ID with `original_title`, `popularity`, `adult`, and `video` flags. Replace `MM_DD_YYYY` in the URL with the target date to retrieve the corresponding file. This is used as the authoritative list of candidate IDs; adult titles and entries below the popularity threshold should be dropped before any API calls are made.
- **[TMDB movie details](https://api.themoviedb.org/3/movie/{id}?append_to_response=credits,keywords,videos)** — requires a free API key from the TMDB developer portal. One request per surviving ID, with `credits`, `keywords`, and `videos` appended in the same response. Returns the full metadata record (title, overview, genres, cast, crew, release date, runtime, ratings, poster path) plus a list of associated video keys. The full field reference is in the [TMDB movie details documentation](https://developer.themoviedb.org/reference/movie-details).
- **[TMDB reviews](https://api.themoviedb.org/3/movie/{id}/reviews)** — a separate TMDB endpoint returning user and critic reviews for each film. English reviews should be concatenated into a single text field per title. This is the source for the **review embedding** modality, capturing audience reception and critical tone that the film's own metadata does not express.
- **[YouTube](https://www.youtube.com/watch?v={video_key})** — trailer videos are not hosted by TMDB directly; the movie details response includes a YouTube key for each associated video. The trailer should be downloaded via that key (e.g. using yt-dlp), frames extracted at uniform intervals, and a visual embedding computed by mean-pooling a vision encoder over those frames. Titles with no available trailer should fall back to the poster image for the visual modality.

The result is a self-contained snapshot parquet that captures the catalogue as it stood on a specific date.

---

### 2.2 Pipeline overview

Turning raw TMDB records into a clusterable, embedded catalogue requires three conceptually distinct stages that should run on separate machines. TMDB rate-limits aggressively by IP, and GPU embedding is expensive locally but cheap on cloud notebooks — splitting the pipeline lets each stage run where it is most practical.

**Stage 1 — Scrape and clean.** The daily ID export should be downloaded and filtered down to a manageable candidate set: adult content must be excluded unconditionally, and titles below a minimum popularity threshold should be dropped before any API calls are made (keeping the set in the low tens of thousands rather than the full ~1M IDs). The surviving IDs should then be enriched via the TMDB v3 REST API and written to a timestamped snapshot parquet. A second filter on minimum vote count should be applied after fetching to remove titles with too little signal for meaningful quality ranking. Both thresholds should be configurable and tied to the snapshot's identity, so changing them produces a new, distinct snapshot rather than silently mutating an existing one.

**Stage 2 — Embed and split.** The snapshot should be split into three disjoint subsets before embedding: a held-out eval slice (a random ~10% of the full set, never written to the main database), a `main` set covering the rest, and a `mini` set — the top ~3 000 titles by vote count and popularity, carved from `main` for fast local development. By construction `mini ⊂ main` and `eval_holdout` should be disjoint from both. Each subset should then be embedded across up to three modalities and uploaded as parquets to a shared artifact store:

- **Text** — a sentence-transformer (e.g. `BAAI/bge-large-en-v1.5`) on a composite text field concatenating title, synopsis, genres, cast, director, and keywords. This is the primary signal for semantic clustering.
- **Review** — the same text encoder applied to aggregated review text, capturing audience reception and critical tone as a complementary signal to the film's own metadata.
- **Visual / trailer** — a vision encoder (e.g. `open_clip ViT-H/14`) on a set of evenly-spaced frames extracted from the film's trailer, mean-pooled into a single vector. This captures cinematographic style, colour palette, and visual mood that text cannot express. Titles with no available trailer should fall back to the poster image.

Embedding is the only GPU-heavy step in the pipeline and should be isolated here so all other stages can run without GPU access.

**Stage 3 — Load.** The embedded parquets should be ingested into PostgreSQL: embedding vectors into pgvector columns, nested JSON fields normalised into relational tables, rows upserted on TMDB ID so re-ingesting the same snapshot is a safe no-op. The `eval_holdout` parquet should be ingested separately and never mixed with the main catalogue.

### 2.4 Data quality notes

- **Budget and revenue sparsity** — TMDB uses `0` for "unknown" on both fields. Zero values should be mapped to null during cleaning so they cannot contaminate ranking or filters.
- **Popularity is a daily snapshot** — TMDB's `popularity` score is recomputed daily; the value captured in the parquet is whatever the API returned at scrape time. It should be treated as a point-in-time signal, not a stable ranking input.
- **Vote-count skew** — the long tail of low-vote titles is removed by the vote-count filter; the surviving rows are still skewed, and a Bayesian-adjusted rating is the correct quality signal rather than raw vote average.
- **Live source, not frozen** — the catalogue reflects TMDB at the snapshot timestamp. Swapping in a newer snapshot should be a configuration change, not a code change, and old sessions must remain replayable against the snapshot they were created on.
- **TMDB throttling** — the TMDB API rate-limits by IP. Rate-limit responses (`429`) should be retried with a fixed sleep; timeout errors should use exponential backoff. Sustained throttling is best addressed by reducing concurrency rather than adding more complex retry logic.
- **Deleted or hidden ids** — the daily ID export drifts ahead of the API view; a non-trivial fraction of IDs will return 404 and should be dropped silently during the fetch phase.

### 2.5 Poster and synopsis availability

Every TMDB API response carries `overview` and `poster_path`, so no extra enrichment step is needed for either. Poster URLs are built at serve time as `https://image.tmdb.org/t/p/w500{poster_path}`. If a title has no poster, the UI shows a placeholder.

---

## 3. How Conversational Clustering Applies Here

### 3.1 The core idea

In the conversational clustering setting, **there is no pre-defined objective function**. The oracle tells us, turn by turn, whether the current grouping is heading in the right direction. **The oracle's acceptance is the objective function**.

---

### 3.2 What the system does on each turn {#system-on-each-turn}

Each turn should be orchestrated by a central **Coordinator** that routes the oracle's message through a fixed sequence of specialised agents:

1. **Label** — before acting, the **Labeling Agent** should name any unlabelled clusters in the current snapshot so the oracle always sees meaningful group titles rather than bare IDs.
2. **Understand** — the **Intent Agent** should parse the oracle's message into one or more typed operations, each with a confidence score and inferred parameters (target cluster, concept, attribute, etc.).
3. **Clarify if uncertain** — if confidence falls below a threshold, the **Clarifier Agent** should ask a single disambiguation question and halt without touching cluster state. The oracle's reply is re-routed on the next turn.
4. **Ground the concept** — for operations that reference a concept (e.g. *"split by emotional tone"*), the **Concept Agent** should turn the natural-language concept into a scoreable representation — a linear axis or set of prototypes — that the clustering step can operate on.
5. **Execute** — the **Clustering Agent** should apply the operations in order, each producing a new snapshot that becomes the input to the next. Identical operations on identical states should be cached so repeated navigation is instant and cost-free.
6. **Explain** — when the oracle asks why a specific film sits in a given cluster, the **Explanation Agent** should produce a natural-language rationale grounded in the cluster's label and the film's attributes, without mutating any state.
7. **Suggest** — the **Responder Agent** should optionally propose one follow-up action based on signals observable in the resulting snapshot. The oracle is free to ignore it.

For detailed component descriptions and turn-handling phases, see [`architecture/architecture.md`](architecture/architecture.md).

---

### 3.3 How the user can give feedback

The oracle never picks an operation from a menu. They type free-form text; the **Intent Agent** maps it onto a fixed, closed set of operations. There are two families:

- **Navigation operations** — re-cluster the data, producing a new snapshot:
  - `cluster` — split by concept, mood, style, or a numeric attribute (*"break the noir group down by how violent they are"*, *"split by decade"*)
  - `merge` — combine two clusters (*"these two are basically the same, combine them"*)
  - `focus` — discard every cluster except one (*"just keep the sci-fi cluster"*)
  - `cross_filter` — keep only films matching a broad criterion, then split (*"only 90s films, then group them"*)
  - `exclude` — drop one cluster, keep all others (*"remove the horror group"*)

- **Dialogue operations** — navigate or query without producing new clusters:
  - `reset` — return to the unclustered state
  - `undo` — step back to the previous clustering snapshot, reversing the last operation
  - `explain` — ask why a specific movie sits in a given cluster (*"why is Blade Runner in this group?"*)
  - `small_talk` — casual, non-operational message

A single message can request a compound sequence (e.g. *"reset, then split everything by mood"*); the Coordinator executes them in order. The oracle does not need to conform to any fixed vocabulary — the Intent Agent handles natural variations.

---

### 3.4 The oracle is an LLM

So far we have spoken about the "user" as if it were always a person sitting at a keyboard. In practice, running a real human study for every experiment — across different questioning strategies, different personas, different configurations — would be far too slow and expensive.

Instead, for the evaluation runs, **the oracle is simulated by an LLM**. Setting up a simulated oracle allows us to run hundreds of sessions under controlled conditions, systematically ablate variables, and get statistically meaningful results.

The LLM is prompted to behave like a real user with specific tastes and a limited attention span. 
As any other human would, it interacts with the system through the provided API, reacts to the clustering state, and gives feedback in free-form language. The only difference is that the LLM's "brain" is a prompt rather than a human mind.

---

## 4 Key Design Decisions

### What does the system cluster over?

The system should operate on the full ingested catalogue from the start — there is no initial query-based retrieval. The oracle begins with the whole set and narrows it down through explicit navigation operations such as `cross_filter`, `focus`, and `exclude`. This is a deliberate design choice: rather than guessing what the oracle wants upfront, the system should let intent emerge through the conversation itself.

On each clustering operation, the in-scope films should be projected into a lower-dimensional space and grouped using a soft clustering algorithm (e.g. UMAP followed by HDBSCAN). Each film should receive a membership probability for every cluster rather than a hard assignment, preserving ambiguity for genuinely boundary-straddling titles. The clustering step should be a pure computation layer — stateless, deterministic, and free of LLM calls — so that labeling and clustering remain cleanly separated responsibilities.

The system should support multiple embedding modalities and fuse them per operation, enabling text-only, review-guided, or visual (trailer-aware) groupings within the same conversation. The Intent Agent should determine which modalities are most appropriate given the oracle's request.

---

### Hierarchy: top-down or incremental?

Rather than presenting a fixed two-level hierarchy upfront, the system should build depth incrementally through the oracle's own navigation. The oracle should be able to `focus` on any cluster and issue a new `cluster` operation inside it, producing a finer sub-grouping without affecting the rest. There should be no fixed depth limit — how far the oracle drills is entirely up to them.

---

### When does the system withhold action?

By default, the system should execute whatever the oracle requests. The only exception should be when parsed intent is too ambiguous to act on safely: in that case, the **Clarifier Agent** should ask a single targeted question and halt without mutating any cluster state. The oracle's reply should be re-routed on the next turn as if it were the original message.

This gate should be intentionally narrow — the system should not second-guess the oracle, evaluate whether a request is wise, or decide when clustering is "done". The oracle drives the pace; the system's job is to execute faithfully and ask only when truly necessary.

---

### How to handle evolving preferences?

Oracles change their minds. What looks like a contradiction is usually **preference evolution** — the oracle has seen more of the catalogue and is refining what they want. The system should accommodate this naturally by treating every navigation operation as a new node in a content-addressed snapshot tree. The oracle should be able to `undo` the last step, `reset` to the unclustered state, or branch from any prior snapshot at any time. The Coordinator should execute the latest instruction without conflict detection or history pruning — the full lineage should remain intact and queryable.

---

### Cluster names and descriptions

Cluster names are the oracle's primary handle for navigating the space — they need to be stable enough to feel familiar across turns and accurate enough to reflect genuine changes in cluster contents.

Not all labeling requires an LLM. When the oracle splits by an exact metadata attribute — genre, decade, runtime range, director — the label is already known from the attribute value itself (e.g. *"Action"*, *"1990s"*, *"90–120 min"*) and should be assigned directly without any model call. A catch-all bucket (e.g. *"Other"* or *"Unspecified"*) should be created for films that fall outside the defined categories.

For semantic and concept-guided clusters, where names cannot be derived mechanically from the data, the **Labeling Agent** should assign names in a single batched LLM call. It should use the previous turn's names as anchors, preserving them unless cluster membership has changed materially — avoiding cosmetic label churn between synonyms while still updating names after genuine splits or merges.

Every label should be scoped to the snapshot that produced it so any past state remains fully auditable.

---

### Soft assignments

Rather than assigning each film to exactly one cluster, the system should produce a **soft assignment**: a per-cluster membership probability for every in-scope film, where probabilities sum to 1. This preserves genuine ambiguity — a film that sits equally between two groups should not be forced into one arbitrarily.

For example, a film like *Parasite* might receive:

```
Crime & thriller   0.55
Dark comedy        0.35
Drama              0.10
```

Films with a dominant score are confident placements; films with roughly equal scores across two clusters are **boundary cases** — meaningful signal for the oracle about where the grouping is uncertain, and natural candidates for a concept-guided split.

---

### Stopping signal

The system should not attempt to detect convergence autonomously. The oracle navigates until satisfied and stops sending messages. Three conditions should bound session length:

- **Turn budget** — a hard cap on the number of oracle turns, configurable per run. When exhausted the session ends with status `finished_budget`.
- **Oracle satisfied** — the oracle signals success with a high self-rating. Status: `finished_trajectory`.
- **Oracle gives up** — the oracle signals failure after repeated misunderstandings. Status: `finished_misbehaviour`.

Terminal status and oracle rating should be assigned by the evaluation harness after the session ends, keeping the live Coordinator path identical across experimental conditions.

---

## 5 Requirements Summary

### 5.1 Functional capabilities

| Area | Capability | Owner | Priority |
|---|---|---|---|
| **Data ingestion** | Scrape TMDB catalogue, embed across three modalities (text, review, visual), and load into PostgreSQL | Scraper + Ingestion pipeline | MVP |
| **Data ingestion** | Display poster, title, year, and rating for every film shown in a cluster | Frontend | MVP |
| **Clustering** | Produce soft clustering of in-scope films into named groups with descriptions | Clustering Agent + Labeling Agent | MVP |
| **Clustering** | Maintain per-film membership probabilities across all turns | Coordinator | MVP |
| **Clustering** | Support five navigation operations: `cluster`, `merge`, `focus`, `cross_filter`, `exclude` | Clustering Agent | MVP |
| **Clustering** | Cache snapshots content-addressed so identical operations on identical states are instant and cost-free | Coordinator | MVP |
| **Interaction** | Parse free-form oracle messages into typed operations with confidence scores | Intent Agent | MVP |
| **Interaction** | Gate low-confidence actions with a single clarifying question, without mutating state | Clarifier Agent | MVP |
| **Interaction** | Ground concept-guided clustering requests into scoreable axes or prototypes | Concept Agent | MVP |
| **Interaction** | Explain why a specific film sits in a given cluster | Explanation Agent | MVP |
| **Interaction** | Optionally propose one follow-up action after each turn | Responder Agent | MVP |
| **Session** | Persist full conversation history and snapshot tree — every turn replayable from seed + config | Coordinator | MVP |
| **Session** | Allow the oracle to undo, reset, or branch from any prior snapshot | Coordinator | MVP |
| **Evaluation** | Run LLM-simulated oracle sessions with seeded personas and ground-truth trajectories | Oracle Agent + Eval runner | MVP |
| **Evaluation** | Score completed sessions across 7 quality dimensions via an LLM judge | Judge Agent | MVP |
| **Evaluation** | Compute deterministic metrics (num clusters, cost, clarifier rate, num turns, num operations) | Eval metrics | MVP |

### 5.2 Non-functional requirements

| Requirement | Target |
|---|---|
| Chat response latency (p95) | < 3 s including LLM call |
| Catalogue size | ≥ 40,000 titles after dedup and quality filter |
| Session state persistence | Database only — no in-memory-only state |
| LLM call logging | Token counts (input/output separately), model version, prompt hash — every call |
| Cost hard-stop | Configurable per session; the system raises rather than silently overrunning |
| Reproducibility | Same seed + config → same session transcript |

### 5.3 Edge cases

| Trigger | System response |
|---|---|
| Oracle message is too vague to parse confidently | The Clarifier Agent returns a single targeted question without mutating cluster state; the oracle's reply is re-routed on the next turn as if it were the original message. |
| Oracle navigates back and re-explores | Any new operation from a prior snapshot creates a new child node; the previous branch remains intact and reachable. |
| Title not in catalogue | The system acknowledges the gap and surfaces the most similar available titles by embedding distance as alternatives. |
| Poster unavailable | The UI falls back to a placeholder image; the card layout is never broken or left blank. |
| Oracle turn budget exhausted | The eval runner stops iteration, assigns `finished_budget`, and treats the current clustering state as the session result. The live Coordinator is not involved in this decision. |
| LLM returns malformed output | The harness retries with exponential backoff; on persistent failure it raises rather than silently returning stale state. |
| In-scope film set is empty after a filter operation | The Coordinator notifies the oracle that the filter produced no results and prompts them to broaden or reset. |
