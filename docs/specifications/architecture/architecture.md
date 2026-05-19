# Architecture Diagram

This diagram captures the **online conversational loop**: the **Retrieval System**, **Cluster Agent** (grouping), **Profile Agent** (preference tracking), **State Agent** (event detection), **Decision Agent** (routing and questioning), and **Orchestrator** (state & handoffs), with persistent state and vector retrieval support.

For high-level problem context and motivation for these agents, see [§3.2 of problem_statement.md](../problem_statement.md#system-on-each-turn).

## Diagram components

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
| **LLM Judge** | Offline evaluation | Reads archived sessions and scores transcripts on coherence, question quality, and profile fidelity. Strictly offline: the judge must not influence live session state or agent routing. |

## Agent Tools

Each agent operates through a well-defined tool interface. Tools are the only mechanism by which agents read from or write to external systems.

| Agent | Tool | Description |
|---|---|---|
| **Retrieval System** | `query_reformulator` | Expands the oracle's utterance or profile summary into hypothetical film-synopsis prose for embedding. |
| **Retrieval System** | `vector_search` | Queries the vector store for the top-K films by cosine similarity to the reformulated query. Accepts an exclusion list pushed into the SQL filter before the limit is applied. |
| **Retrieval System** | `metadata_fetcher` | Retrieves synopsis, genre, director, and rating metadata for each candidate to pass downstream. |
| **Cluster Agent** | `embedding_fetcher` | Fetches stored embeddings for the retrieved candidate IDs from the database. |
| **Cluster Agent** | `soft_cluster_engine` | Runs dimensionality reduction followed by HDBSCAN to produce per-film soft-membership scores across clusters. |
| **Cluster Agent** | `cluster_describer` | LLM tool that analyses cluster commonalities (top titles, genres, sample overviews) and returns an evocative name and short description for each cluster. |
| **Cluster Agent** | `cluster_refiner` | LLM tool that updates prior cluster boundaries, scores, and membership in light of the oracle's latest reply, without running a fresh embedding pass. |
| **Decision Agent** | `relevance_scorer` | Compares the oracle's query against cluster names and descriptions to produce a per-cluster relevance score. |
| **Decision Agent** | `entropy_calculator` | Measures spread across the cluster soft-score distribution; high entropy signals that further questioning is warranted. |
| **Profile Agent** | `profile_merger` | LLM tool that merges the oracle's latest message into the structured preference profile, updating constraints, preferences, attitudes, and the prose summary. |
| **State Agent** | `hard_limits` | Synchronous check for turn count and cost budget exhaustion; trips before any LLM work is scheduled. |
| **State Agent** | `llm_gate` | LLM tool that classifies the oracle's message against session state, detecting natural ends, preference contradictions, and re-retrieve triggers. |

## Workflow Summary

| Agent | Input | Output |
|---|---|---|
| State Agent | Oracle message + session history + preference profile | State verdict (proceed / natural\_end / clarify\_drift / drift\_confirmed / drift\_dismissed / re\_retrieve) |
| Profile Agent | Oracle message + prior profile + recent turns | Updated structured preference profile |
| Retrieval System | Oracle utterance or profile summary + exclusion list | Top-K film metadata |
| Cluster Agent | Film metadata (fresh) or prior clusters + oracle reply (refinement) | Named clusters with soft-assignment scores |
| Decision Agent | Clusters + oracle query + preference profile + prior questions | Routing decision (recommend / continue) + question when continuing |
| Orchestrator | All agent outputs + oracle response | Updated session state; next agent trigger; turn persisted to DB |

State Agent, Profile Agent, and the speculative clustering branch all run in parallel at the start of each turn. The state verdict is awaited first; terminal verdicts cancel the speculative branch immediately.

## Component Communication (paths, payloads, and constraints)

This section makes explicit which agents may call which others, what information is exchanged on each edge, and which direct calls are intentionally disallowed to preserve clear role boundaries and enable independent testing and logging.

- **Oracle → Orchestrator**
  - Payload: raw oracle utterance (text).
  - Responsibility: the Orchestrator records the message, checks hard limits synchronously, then spawns the parallel task wave.

- **Orchestrator → State Agent** *(parallel wave, turn start)*
  - Payload: oracle message, session history, preference profile, last-shown titles, seen films.
  - Semantics: the hard-limit check runs synchronously before any LLM work. The LLM gate runs concurrently with profile extraction and speculative clustering.

- **Orchestrator → Profile Agent** *(parallel wave, turn start)*
  - Payload: oracle message, prior preference profile, recent turns.
  - Semantics: runs concurrently with the state gate and speculative branch. Profile is consumed only if the state verdict is proceed, drift\_confirmed, or drift\_dismissed.

- **Orchestrator → Retrieval System** *(speculative or triggered)*
  - Payload: oracle utterance (speculative first-turn path) or profile summary (drift and re-retrieve path), exclusion list, retrieval parameters.
  - Semantics: on the speculative path, retrieval is issued optimistically and cancelled if the state verdict is terminal. On drift\_confirmed and re\_retrieve, the speculative result is discarded and a fresh profile-driven retrieval is issued.

- **Retrieval System → Cluster Agent**
  - Payload: top-K film metadata and reformulated query.
  - Semantics: the Retrieval System does not perform grouping; it hands off a flat candidate list. The Cluster Agent treats inputs as immutable.

- **Orchestrator → Cluster Agent** *(speculative refinement path)*
  - Payload: prior cluster snapshot, oracle message, last assistant message.
  - Semantics: when prior clusters exist, the Orchestrator speculatively fires a refinement pass concurrently with the state gate. If the state verdict is proceed or drift\_dismissed the refined clusters are used; otherwise the result is discarded.

- **Cluster Agent → Decision Agent**
  - Payload: named clusters with soft-assignment scores.
  - Semantics: the Cluster Agent does not decide whether to stop or continue; it returns pure descriptive outputs. The Decision Agent receives clusters as read-only.

- **Decision Agent → Orchestrator (routing signal)**
  - Payload: action (recommend / continue), best cluster reference, rationale, entropy score, and — when continuing — the clarifying question text and the cluster references it targets.
  - Semantics: question generation is part of the same LLM call as the routing decision. If the action is recommend, the Orchestrator surfaces the best cluster to the oracle. If continue, it surfaces the question.

- **Orchestrator → Vector Database**
  - Payload: write payloads for oracle feedback, clusters, cluster assignments, turns, and session profile updates; read queries to fetch candidate vectors.
  - Semantics: the Orchestrator is the single writer to the database. It enforces schema validation, writes audit metadata, and emits structured log entries so every mutation is replayable.

- **Database → LLM Judge (offline)**
  - Payload: archived transcripts, cluster snapshots per turn, oracle feedback log, and the converged preference profile.
  - Semantics: the judge reads but never writes; scoring outputs are stored in a separate evaluation table applied only after the session ends.

### Intentionally Disallowed Direct Calls

- The Retrieval System, Cluster Agent, Decision Agent, Profile Agent, and State Agent are disallowed from writing to the database directly. All state mutations flow exclusively through the Orchestrator, preserving a single canonical writer.
- The LLM Judge must not be called synchronously inside the live loop and must not have write access to session state. Its role is strictly evaluative and offline.
- The Retrieval System must not perform clustering or routing logic; it is a supplier of enriched candidates only.
- The Decision Agent must not read from or write to session state directly; prior questions are injected by the Orchestrator before the agent is called.

### Rationale for the Communication Pattern

1. **Testability & Ablation:** With clearly scoped, read-only agents and a single state writer (the Orchestrator), each agent can be unit-tested in isolation and swapped for ablation experiments without risk of hidden side effects.
2. **Latency:** The parallel wave (state gate + profile + speculative clustering) hides the cost of the state check behind work that would be needed anyway, keeping per-turn latency close to the longest single LLM call rather than the sum.
3. **Observability:** The Orchestrator logs token counts and a prompt hash per call, enabling per-step cost accounting and full session replay.
4. **Trust & User-Facing Correctness:** Routing all writes through the Orchestrator prevents silent overrides of oracle constraints and ensures that drift is surfaced explicitly before any state change is committed.
5. **Security & Safety:** Isolating the LLM Judge and restricting write access reduces the risk that an evaluation pass can mutate live sessions or leak sensitive preference state.

---
