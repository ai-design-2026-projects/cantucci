# Architecture Diagram

![Architecture Diagram](../media/architecture_diagram.png)

This diagram captures the **online conversational loop** from the problem statement: `f_next_best_step` (router), `f_uncertainty`, `f_output`, `f_next_state`, and `f_assess`, with persistent state and retrieval support.

## Diagram components (from `architecture_diagram.tex`)

| Component | Function in problem statement | Purpose |
|---|---|---|
| **User (Oracle)** | Oracle | The source of truth for preferences: may be a human participant or an LLM-simulated persona. Provides free-form feedback that is interpreted at four levels (global, cluster, point, instructional). |
| **`f_next_best_step` (Router Agent)** | Router | Decision-maker that chooses exactly one dispatch per turn: **Show**, **Ask**, or **Stop**. It reasons over `f_output`, `f_uncertainty`, and `f_assess` outputs but does not execute their logic itself. The router's output is a typed action descriptor consumed by executors. |
| **`f_uncertainty` (Ambiguity Agent)** | Uncertainty estimator | Analyses soft-assignment scores and cluster centroids to surface boundary cases and rank candidate titles for questioning. Produces a ranked ambiguous-pool with provenance and uncertainty metrics. |
| **`f_output` (Recommendation Agent)** | Output function | Responsible for producing the user-facing recommendation view: named clusters, short descriptions, and top titles (poster, year, rating). Returns structured cluster objects and soft-assignment JSON; it never mutates session state directly. |
| **`f_assess` (Convergence & Profile)** | Assessor | Independently evaluates whether the session should converge (explicit acceptance, behavioural signal, or turn budget) and, on convergence, extracts a structured preference profile from the full `oracle_feedback` log. Operates as an auditor, not part of routing decisions once declared final. |
| **`f_next_state` (Update Model & Drift)** | State update | The single writer to session state: ingests parsed oracle feedback, resolves drift (with surfacing), applies constraints, persists `oracle_feedback`, `clusters`, and `cluster_assignments`, and updates `sessions` metadata. |
| **Retrieval System** | Retrieval stage | Embedding-based candidate fetcher (pgvector); returns top-K vectors and metadata to the clustering prompt. Considered a support service, not an agent in the conversational loop. |
| **Database (`pgvector` + relational data)** | Persistent memory | Stores catalogue embeddings, session history, clusters, assignments, and feedback; supports replay and offline analysis. |
| **LLM Judge (Independent Evaluator)** | Offline evaluation | Reads stored sessions and scores transcripts on coherence, question quality, and profile fidelity. Strictly offline: the judge must not influence live session state or routing. |


## Component Communication (paths, payloads, and constraints)

This section makes explicit which components may call which others, what information is exchanged on each edge, and which direct calls are intentionally disallowed to preserve clear role boundaries and enable independent testing and logging.

- **Oracle → Router (`f_next_best_step`)**
	- Payload: raw oracle utterance (text) and optional structured metadata (e.g., click/select events).
	- Responsibility: router accepts the utterance as the input signal for deciding the next action. The router does not apply feedback rules itself; it forwards the utterance (or a parsed summary) to `f_next_state` for persistence.

- **Router → `f_output` / `f_uncertainty` / `f_assess` (fan-out)**
	- Payload: read-only snapshot of session state (clusters, assignments, recent `oracle_feedback`, candidate pool) and typed request ("compute clusters for display", "rank ambiguous titles", or "evaluate convergence").
	- Semantics: router may invoke one or more executors in parallel; executors must treat inputs as immutable and return structured outputs (JSON) with prompt_hash and token accounting logged by the harness.

- **`f_output` / `f_uncertainty` / `f_assess` → Router (responses)**
	- Payload: structured output objects. Examples:
		- `f_output` → clusters: [{id, name, description, centroid, top_titles, soft_scores}] + prompt_hash
		- `f_uncertainty` → ambiguous_pool: [{movie_id, gap_score, top2_clusters, rationale}] + prompt_hash
		- `f_assess` → assessment: {converged: bool, reason: enum, recommendation_profile: JSON|null}
	- Semantics: router uses these outputs to choose the next dispatch; executors must not modify DB state as part of their response.

- **Executors → `f_next_state` (update path)**
	- Payload: executor signals and the selected dispatch (router's decision) are handed to `f_next_state` when they imply a state mutation (e.g., the oracle accepted a cluster, or an explicit merge/split command).
	- Semantics: only `f_next_state` writes to the DB. Executors must never write directly to persistent tables.

- **`f_next_state` → Retrieval / Database**
	- Payload: queries to fetch candidate vectors, and write payloads for `oracle_feedback`, `clusters`, `cluster_assignments`, and `sessions` updates.
	- Semantics: `f_next_state` enforces schema validation, writes audit metadata (prompt_hash, run_id, turn_number), and emits structured log entries so every mutation is replayable.

- **Database → LLM Judge (offline)**
	- Payload: archived transcripts, clusters per turn, `oracle_feedback` log, and `sessions.preference_profile`.
	- Semantics: judge reads but never writes; any scoring outputs are stored in a separate evaluation table or files and are applied only after human-validation gates, per policy.

### Intentionally Disallowed Direct Calls

- Executors (`f_output`, `f_uncertainty`, `f_assess`) are disallowed from writing to the database directly. This prevents side-effectful prompts and keeps the state-writer (`f_next_state`) as the canonical single writer.
- The LLM Judge must not be called synchronously inside the live loop or be given write access to session state. Its role is strictly evaluative and offline.
- Retrieval service should not perform routing or question-selection logic; it is a supplier of candidates only.

### Rationale for the Communication Pattern

1. **Testability & Ablation:** With clear read-only executors and a single writer, each `f_*` function can be unit-tested in isolation and swapped for ablation experiments without risk of hidden side effects.
2. **Observability:** Every edge carries typed payloads and a `prompt_hash`; the harness logs token counts per call, enabling per-step cost accounting and replay.
3. **Trust & User-Facing Correctness:** Surfacing drift and requiring `f_next_state` to confirm changes prevents silent overrides of oracle constraints, preserving trust.
4. **Security & Safety:** Isolating judge and writer roles reduces the risk that an evaluation or external scoring pass can mutate live sessions or leak sensitive state.

---

Update: the expanded component descriptions and the explicit communication rules align with the `f_*` separation described in the problem statement and `llm.md`, ensuring documentation and implementation remain consistent.