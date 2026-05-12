# Architecture Diagram

This diagram captures the **online conversational loop**: the **Retrieval System**, **Cluster Agent** (grouping), **Decision Agent** (routing), **Ambiguity Resolver** (dialogue), and **Orchestrator** (state & handoffs), with persistent state and vector retrieval support.

For high-level problem context and motivation for these agents, see [§3.2 of problem_statement.md](../problem_statement.md#system-on-each-turn).

## Diagram components (from `architecture_diagram.tex`)

| Component | Role in system | Purpose |
|---|---|---|
| **User (Oracle)** | Oracle | The source of truth for preferences: may be a human participant or an LLM-simulated persona. Provides free-form feedback interpreted at four levels (global, cluster, point, instructional). |
| **Retrieval System** | Retrieval stage | Converts the user's natural language into a technical search query, embeds it, and fetches the top-K candidate films from the vector store. Looks beyond titles to capture vibes, themes, and cinematic style. Returns enriched film metadata (synopsis, genre, director) for downstream agents. |
| **Cluster Agent** | Grouping & labelling | Performs soft clustering over the retrieved candidates. Produces overlapping theme distributions (e.g., a film may be 70% "Cyberpunk Noir" and 30% "Existential Drama") and synthesises each group into a human-readable name and short description. Never writes to session state directly. |
| **Decision Agent (The Strategist)** | Routing & convergence | Reviews cluster purity and relevance to decide the next move: **Recommend** if one cluster dominates with high relevance, or **Continue** if entropy is high and more signal is needed. Ranks clusters against the original user query and determines whether stopping is warranted. |
| **Ambiguity Resolver (Dialogue Strategist)** | Clarification & disambiguation | Activated when the Decision Agent chooses to continue. Identifies the sharpest point of divergence between the top 2–3 clusters and generates a focused question (forced-choice or weighted preference) to extract the most information from the user in a single turn. Formats the question for the target UI. |
| **Orchestrator** | State management & handoffs | Maintains conversation memory across the full session, prevents duplicate questions, and coordinates agent handoffs. Triggers the Retrieval system whenever new information warrants re-retrieval and passes updated candidates to the Cluster Agent. Acts as the single source of truth for current top-K and user response history. |
| **Vector Database (pgvector)** | Persistent memory | Stores catalogue embeddings, session history, clusters, soft assignments, and oracle feedback. Supports both live retrieval and offline replay and analysis. |
| **LLM Judge (Independent Evaluator)** | Offline evaluation | Reads archived sessions and scores transcripts on coherence, question quality, and profile fidelity. Strictly offline: the judge must not influence live session state or agent routing. |

## Agent Tools

Each agent operates through a well-defined tool interface. Tools are the only mechanism by which agents read from or write to external systems.

| Agent | Tool | Signature | Description |
|---|---|---|---|
| **Retrieval System** | `vector_search` | `(embedding, k)` | Queries the vector store for the top-K films by semantic similarity. |
| **Librarian** | `metadata_fetcher` | `(film_ids)` | Retrieves synopsis, genre, and director for each candidate to pass downstream. |
| **Cluster Agent** | `soft_cluster_engine` | `(embeddings)` | Runs a clustering algorithm to produce per-film cluster probability distributions. |
| **Cluster Agent** | `cluster_describer` | `(metadata_subset)` | LLM tool that analyses cluster commonalities and returns a creative name and short description. |
| **Decision Agent** | `relevance_scorer` | `(user_query, cluster_summaries)` | Compares user intent against cluster descriptions to rank clusters and flag dominant matches. |
| **Decision Agent** | `entropy_calculator` | `()` | Measures spread across the cluster distribution; high entropy signals that further questioning is warranted. |
| **Ambiguity Resolver** | `disambiguation_generator` | `(cluster_a, cluster_b)` | Produces a forced-choice or weighted-preference question targeting the sharpest divergence between two clusters. |
| **Ambiguity Resolver** | `ui_formatter` | — | Formats the generated question for the target interface (e.g., buttons, natural-language response). |
| **Orchestrator** | `state_manager` | — | Key-value store (or LangGraph-style state object) tracking current top-K, turn history, and past oracle responses. |

## Workflow Summary

| Agent | Input | Output |
|---|---|---|
| Retrieval System | User query (natural language) | Top-K film metadata |
| Cluster Agent | Film metadata | N named and described clusters with soft-assignment scores |
| Decision Agent | Clusters + original user query | Decision (Recommend / Continue) + best-matching cluster |
| Ambiguity Resolver | Top 2–3 clusters | Clarifying question formatted for the UI |
| Orchestrator | All agent outputs + oracle response | Updated state; next agent trigger |

## Component Communication (paths, payloads, and constraints)

This section makes explicit which agents may call which others, what information is exchanged on each edge, and which direct calls are intentionally disallowed to preserve clear role boundaries and enable independent testing and logging.

- **Oracle → Orchestrator**
  - Payload: raw oracle utterance (text) and optional structured metadata (e.g., click/select events).
  - Responsibility: the Orchestrator logs the response into session state via `state_manager`, checks whether it introduces new preference signal warranting re-retrieval, and triggers the appropriate next agent.

- **Orchestrator → Retrieval System**
  - Payload: current user query (original or refined by accumulated oracle feedback) and retrieval parameters (k, any active constraints).
  - Semantics: triggered at session start and whenever the Orchestrator determines that new oracle feedback meaningfully shifts the query. The Retrieval System treats the query as read-only input.

- **Retrieval System → Cluster Agent**
  - Payload: top-K film metadata objects (film IDs, embeddings, synopses, genres, directors) and a `prompt_hash` for auditability.
  - Semantics: the Retrieval System does not perform grouping; it hands off a flat candidate list. The Cluster Agent treats inputs as immutable.

- **Cluster Agent → Decision Agent**
  - Payload: structured cluster objects — `[{id, name, description, centroid, top_titles, soft_scores}]` — plus `prompt_hash` and token accounting.
  - Semantics: the Cluster Agent does not decide whether to stop or continue; it returns pure descriptive outputs. The Decision Agent receives clusters as read-only.

- **Decision Agent → Orchestrator (routing signal)**
  - Payload: `{action: "recommend" | "continue", best_cluster_id, rationale, entropy_score}`.
  - Semantics: if `action` is `"recommend"`, the Orchestrator surfaces the best cluster to the user and moves toward convergence. If `"continue"`, it passes the top clusters to the Ambiguity Resolver.

- **Decision Agent → Ambiguity Resolver (conditional fan-out)**
  - Payload: read-only snapshot of the top 2–3 cluster objects and the current entropy score.
  - Semantics: invoked only when the Decision Agent returns `"continue"`. The Ambiguity Resolver must not modify cluster state; it consumes cluster data to generate a question.

- **Ambiguity Resolver → Orchestrator (question payload)**
  - Payload: `{question_text, ui_format, cluster_refs: [cluster_id_a, cluster_id_b]}`.
  - Semantics: the Orchestrator records the question in session history (preventing re-asking) and surfaces it to the Oracle. The Ambiguity Resolver has no write access to session state.

- **Orchestrator → Vector Database**
  - Payload: write payloads for `oracle_feedback`, `clusters`, `cluster_assignments`, and `sessions` updates; read queries to fetch candidate vectors.
  - Semantics: the Orchestrator is the single writer to the database. It enforces schema validation, writes audit metadata (`prompt_hash`, `run_id`, `turn_number`), and emits structured log entries so every mutation is replayable.

- **Database → LLM Judge (offline)**
  - Payload: archived transcripts, clusters per turn, `oracle_feedback` log, and `sessions.preference_profile`.
  - Semantics: the judge reads but never writes; scoring outputs are stored in a separate evaluation table or files and applied only after human-validation gates.

### Intentionally Disallowed Direct Calls

- The Retrieval System, Cluster Agent, Decision Agent, and Ambiguity Resolver are disallowed from writing to the database directly. All state mutations flow exclusively through the Orchestrator, preserving a single canonical writer.
- The LLM Judge must not be called synchronously inside the live loop and must not have write access to session state. Its role is strictly evaluative and offline.
- The Retrieval System must not perform clustering or question-selection logic; it is a supplier of enriched candidates only.
- The Ambiguity Resolver must not re-ask questions that appear in the Orchestrator's session history; the `state_manager` is the authoritative deduplication source.

### Rationale for the Communication Pattern

1. **Testability & Ablation:** With clearly scoped, read-only agents and a single state writer (the Orchestrator), each agent can be unit-tested in isolation and swapped for ablation experiments without risk of hidden side effects.
2. **Observability:** Every inter-agent edge carries typed payloads and a `prompt_hash`; the Orchestrator logs token counts per call, enabling per-step cost accounting and full session replay.
3. **Trust & User-Facing Correctness:** Routing all writes through the Orchestrator prevents silent overrides of oracle constraints and ensures that drift is surfaced explicitly before any state change is committed.
4. **Security & Safety:** Isolating the LLM Judge and restricting write access reduces the risk that an evaluation pass can mutate live sessions or leak sensitive preference state.

---
