# Architecture Diagram

This diagram captures the **online conversational loop**: the **Retrieval System**, **Cluster Agent** (grouping), **Profile Agent** (preference tracking), **State Agent** (event detection), **Decision Agent** (routing and questioning), and **Orchestrator** (state & handoffs), with persistent state and vector retrieval support.

![Architecture Diagram](../../media/architecture_diagram.png)

## System components

| Component | Role in system | Purpose |
|---|---|---|
| **User (Oracle)** | Oracle | The source of truth for preferences: may be a human participant or an LLM-simulated persona. Provides free-form feedback interpreted at four levels (global, cluster, point, instructional). |
| **Retrieval System** | Retrieval stage | Converts the oracle's natural language into rich hypothetical prose, embeds it, and fetches the top-K candidate films from the vector store. Has two entry points: one for raw oracle utterances (first turn and proceed path) and one for profile summaries (drift and re-retrieve path). Returns enriched film metadata (synopsis, genre, director) for downstream agents. |
| **Cluster Agent** | Grouping & labelling | Operates in two modes. On a fresh candidate pool it runs dimensionality reduction followed by soft clustering, then names each group via a separate LLM pass. When prior clusters exist, an LLM-based refinement step updates boundaries, scores, and membership based on the oracle's latest reply. In both modes the output is a set of named clusters with per-film soft-assignment scores. Never writes to session state directly. |
| **Profile Agent** | Preference extraction | Maintains a structured representation of the oracle's evolving taste across four fields: hard constraints, soft preferences, attitudes, and a prose summary. Also tracks excluded and seen films, which are injected into retrieval to prevent re-recommending titles the oracle has rejected or already seen. |
| **State Agent** | Event detection | Detects conversation-level events before the main pipeline runs. Hard limits (max turns, cost) are checked synchronously; an LLM call then classifies the oracle's message as one of: proceed, natural end, drift clarification needed, drift confirmed, drift dismissed, or re-retrieve. When a terminal event is detected, the rest of the pipeline is discarded and the orchestrator takes the appropriate bypass path. |
| **Decision Agent** | Routing & convergence | Scores clusters for relevance against the oracle's query, then computes entropy across the soft-score distribution as a signal of how uncertain the best choice is. An LLM call uses these signals together with the preference profile and prior questions to decide: **recommend** if one cluster dominates, or **continue** if entropy is high. When continuing, the question is generated in the same LLM call — open-ended early in a session, targeted and binary once clusters have diverged. |
| **Orchestrator** | State management & handoffs | Maintains conversation state across the full session and coordinates agent handoffs. On each turn it runs a parallel wave — state gate, profile extraction, and speculative retrieval or cluster refinement — then routes based on the state verdict. It is the sole writer to the database. |
| **Vector Database** | Persistent memory | Stores catalogue embeddings, session history, clusters, soft assignments, and oracle feedback. Supports both live retrieval and offline replay and analysis. |


## Agent Tools

Each agent operates through a well-defined tool interface. Tools are the only mechanism by which agents read from or write to external systems.

| Agent | Tool | Description |
|---|---|---|
| **Retrieval System** | `query_reformulator` | Expands the oracle's query or profile summary into hypothetical film-synopsis prose for embedding. |
| **Retrieval System** | `vector_search` | Queries the vector store for the top-K films by cosine similarity to the reformulated query. Accepts an exclusion list pushed into the SQL filter before the limit is applied. |
| **Retrieval System** | `metadata_fetcher` | Retrieves synopsis, genre, director, and rating metadata for each candidate to pass downstream. |
| **Cluster Agent** | `embedding_fetcher` | Fetches stored embeddings for the retrieved candidate IDs from the database. |
| **Cluster Agent** | `soft_cluster_engine` | Runs UMAP dimensionality reduction followed by HDBSCAN to produce per-film soft-membership scores across clusters. |
| **Cluster Agent** | `cluster_describer` | LLM tool that analyses cluster commonalities (top titles, genres, sample overviews) and returns an evocative name and short description for each cluster. |
| **Cluster Agent** | `cluster_refiner` | LLM tool that updates prior cluster boundaries, scores, and membership in light of the oracle's latest reply, without running a fresh embedding pass. |
| **Decision Agent** | `relevance_scorer` | Compares the oracle's query against cluster names and descriptions to produce a per-cluster relevance score. |
| **Decision Agent** | `entropy_calculator` | Measures spread across the cluster soft-score distribution; high entropy signals that further questioning is warranted. |
| **Profile Agent** | `profile_merger` | LLM tool that merges the oracle's latest message into the structured preference profile, updating constraints, preferences, attitudes, and the prose summary. |
| **State Agent** | `check_hard_limits` | Synchronous check for turn count and cost budget exhaustion; trips before any LLM work is scheduled. |
| **State Agent** | `check_session_state` | LLM tool that classifies the oracle's message against session state, detecting natural ends, preference contradictions, and re-retrieve triggers. |

## Turn Handling

---
