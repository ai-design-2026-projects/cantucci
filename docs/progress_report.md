# CinePal - Conversational Clustering Movie Recommender System

We build a conversational movie recommendation system in which the user (the **oracle**) interacts with an AI through a chat interface to discover films that match their taste or provide a set of suggestions.

https://github.com/user-attachments/assets/b308d0ea-cb32-4a1b-897f-7ba45f78df00

The system does not ask the user to fill out a profile or rate movies upfront. Instead, it starts from the user's first natural-language request, proposes an initial clustering of the available movie space into meaningful groups, then refines that clustering turn by turn as the user reacts. The **clustering is the recommendation**: the user is converging toward a group of titles they want, and the system's job is to reach that group as efficiently as possible.

For a detailed problem formulation and motivation, see [problem_statement.md](https://github.com/ai-design-2026-projects/cantucci/blob/main/docs/specifications/problem_statement.md).

## Research Scope

Our main objective is to explore the following question:

> Does conversational refinement result in a better recommendation for the oracle? (E.g., fewer turns, lower cognitive load, higher satisfaction) than a baseline?

We approach this from three angles:

- **Questioning strategy**: how should the system decide what to ask at each turn, and what signals should drive that decision?
- **Cluster update strategy**: how should oracle feedback propagate into cluster boundaries, and what algorithms or heuristics best support incremental refinement?
- **Satisfaction**: how do we assess recommendation quality when the oracle is an LLM agent, and how far do those assessments generalise?

## What Makes This Hard

- **Feedback is inherently ambiguous.** "Too dark" could mean genre, tone, visual style, or moral content. The system must map vague natural language onto structured cluster updates without demanding clarification at every turn.
- **No ground truth for convergence.** The oracle defines success, so sessions cannot be labelled correct or incorrect independently of the user. This makes offline evaluation genuinely difficult.
- **Retrieval and clustering are confounded.** A poor candidate pool on turn 1 limits every subsequent clustering decision, but slow convergence looks identical whether the retrieval or the clustering strategy is at fault.
- **Stability vs accuracy tension.** Cluster names and boundaries must feel consistent to the user across turns, yet the underlying content genuinely shifts as feedback narrows the pool. Too much stability means the labels lie; too much churn means the user loses their bearings.
- **Profile extraction**: how can I track and leverage the user's evolving preferences across turns, and how can I use that profile to improve retrieval and clustering in future sessions?
- **Conversation Drift**: A user might change their mind mid-session, or introduce new preferences that contradict earlier feedback. The system must be flexible enough to accommodate this without losing the thread of the conversation.
- **Already seen movies**: The user might have already seen some of the movies in the candidate pool, and their feedback might be based on that prior knowledge. The system must be able to handle this and adjust its recommendations accordingly.
- **Time and budget constraints**: The system must operate within reasonable time limits for each turn, accounting for token usage and the associated costs of LLM calls. This requires efficient algorithms and careful resource management.
- **Cognitive load**: The system must balance the amount of information presented to the user at each turn. Questions and cluster updates should be informative but not overwhelming, ensuring the user can easily understand and engage with the recommendations.

## Key Contributions

We propose an architectural framework for conversational clustering recommenders that addresses the above challenges through a modular design separating concerns and allowing flexible experimentation with different strategies. The main components are:

- **Orchestrator**: A *deterministic machine* that manages the conversation flow, decides which agent to call at each turn, and maintains the overall session state.
Rather than a monolithic loop, each turn dispatches agents in parallel waves, maintaining consistency and response-time efficiency.
It is the sole component with direct database access, enabling clean and secure management of data and interactions.

- **Retrieval Agent**: Instead of embedding the oracle's raw query directly, the agent expands it into *rich hypothetical prose* written as if it were a film synopsis. An embedding-based search (*BAAI/bge-large-en-v1.5*) then retrieves a candidate pool of K films whose overviews are closest to that prose.
At the start of the conversation, or when difts are perceived a retrieve event is issued, possibly keeping the clustered movies fixed along refinements. Howhever, a future direction is to retrieve continuously and let the clustering agent decide which films to add or remove, which would handle cases where the initial retrieval wasn't precise enough to capture the oracle's intent.

- **Clustering Agent**: Operates in two modes. On a fresh turn it applies dimensionality reduction (*UMAP*) to the candidate pool, produces an initial soft clustering (*HDBSCAN*) and applies an LLM-generated description.
On the other hand, when prior clusters exist, an LLM-based *refinement step* updates boundaries, scores, and membership based on oracle feedback.

- **Profile Agent**: Maintains a structured representation of the oracle's evolving taste across four fields: hard *constraints* (explicit requirements), soft *preferences* (stylistic leanings), *attitudes* (how the oracle engages), and a prose *summary* for downstream agents.
It also tracks excluded films and injects them into retrieval and clustering, both to avoid re-recommending them.

- **Decision Agent**: Analyses the current cluster configuration together with the oracle's query and profile to decide the next action: recommending a cluster or asking a question to disambiguate.
Clusters are first scored for relevance, then the entropy of that distribution is computed as a soft signal of how uncertain the best choice is — a guide rather than a hard threshold, since entropy alone cannot capture preference uncertainty.
When it decides to ask, the agent selects the question type based on cluster state: *open-ended* questions early on, when intent is too vague to separate clusters; *targeted* binary questions once clusters have diverged, identifying the sharpest axis of ambiguity between the two most confusable clusters. Prior questions are injected into context to prevent repetition, and a hard *eager-to-see override* bypasses entropy entirely, forcing an immediate recommendation whenever the oracle signals impatience.

- **State Agent**: Detects conversation-level events that override the normal pipeline: `natural_end` (oracle signals satisfaction), `clarify_drift` (current message contradicts a stated constraint), `drift_confirmed`/`drift_dismissed` (resolution of a prior drift clarification), and `re_retrieve` (oracle has already seen all recently recommended films). This guard layer keeps the orchestrator's main path clean while handling the full range of conversational edge cases.

Full component specifications and the architecture diagram are described in [architecture.md](https://github.com/ai-design-2026-projects/cantucci/blob/main/docs/specifications/architecture/architecture.md).

## Evaluation

The core challenge is that there is no external ground truth: the oracle *is* the objective function.
To address this, we defined the following approach:

**Ground-truth construction:** Each ground truth is built offline from a held-out partition of the catalogue. A script samples N seed films, expands the set to ~40 films via cosine similarity in embedding space, and calls an LLM to write a neutral, voice-agnostic taste description of the films. The result is saved as a versioned YAML file. During eval, the oracle receives only the generated description, and is asked to find a film based on that.
The TMDB IDs are held only by the runner and used for objective metric computation after the session ends.

**Oracle:** A simulated oracle is an LLM agent that embodies a **target description** overlaid with a **persona** that controls communication style. Personas are defined by four behavioral dials: `verbosity` (terse / medium / verbose), `decisiveness` (likelihood to accept early, 0–1), `drift_probability` (per-turn chance of introducing a tangent), and `contradiction_rate` (per-turn chance of self-contradicting). A seeded `BehaviorRng`, keyed on `(persona_hash, gt_id, session_seed)`, injects deterministic stage directions into the oracle's context to trigger drift or contradiction. An acceptance gate, derived from the decisiveness dial, prevents low-decisiveness personas from converging in fewer turns than their dial would allow.

**Metrics** (persisted per session in `session_metrics` and `judge_scores`):

- *Precision@K, Recall@K, NDCG@K*: fraction of the top-K recommended films that appear in the ground-truth TMDB ID set.
- *Turns to convergence*: turn number at which convergence is declared, or null if the session is abandoned.
- *Avg cognitive load per turn*: recommendation size × 0.3 + question word count normalised to a 0–2 scale, averaged across turns.
- *Explicit acceptance rate*: whether the oracle issued an `accept` intent vs. the system declaring convergence behaviourally.
- *Drift events*: count of `clarify_drift` events detected by the State Agent.
- *Oracle score*: a subjective rating from 1–5 provided by the oracle at the end of the session.
- *LLM-judge scores*: clustering coherence, question quality, and preference-profile fidelity, each rated 1–5 by a separate judge model reading the full transcript, converged cluster, and ground-truth description (but not the oracle persona traits).

**Baseline**: We compare our full system against two ablations designed to isolate retrieval and agentic benefits.

- *Dry-run retrieval*: perform a top-K embedding retrieval using the same embedding pipeline but omit any LLM-driven clustering, labelling, or question generation.
- *Plain LLM conversation*: a single monolithic LLM acts as the recommender: it receives the oracle's message and is prompted to either ask clarifying questions or return a ranked list of recommendations, without any attachment to the database, relying only on his knowledge. This baseline removes structured components.

A full specification of the evaluation setup is given in [evaluation.md](https://github.com/ai-design-2026-projects/cantucci/blob/main/docs/specifications/evaluation.md).

## What We Have Done
- **End-to-end pipeline.** All six agents — Orchestrator, Retrieval, Clustering, Profile, Decision, and State — are implemented and wired together. A human user can interact with the system through the chat interface, provide feedback, and receive updated clusters turn by turn as intended.
- **Logging and config.** A structured logging system emits one key=value line per event, with mandatory fields (`run_id`, `session_id`, `turn_id`, `model`, `prompt_hash`, `tokens`, `latency`) on every LLM call. All session parameters (model, seed, clustering strategy) are driven by a YAML config file loaded at startup, so experimental conditions can be switched by changing a single env variable with no code edits. Each session stores the full config snapshot and a SHA-256 hash, enabling exact replay.
- **Data pipeline.** We scrape and clean film metadata from TMDB, embed synopses using `BAAI/bge-large-en-v1.5` in a GPU Colab notebook, and upload the resulting parquet artifacts to Hugging Face. The backend ingests them into a pgvector-enabled Postgres instance on startup. Three catalogue splits are available: `mini` (dev), `main` (~40k films), and `eval_holdout` (reserved for ground-truth construction).
- **Test suite and CI/CD.** Smoke tests cover the full turn pipeline end-to-end in dry-run mode (no live LLM calls) using fixture responses. The CI pipeline runs ruff, mypy, and pytest on every push. A CD pipeline builds and pushes versioned Docker images on merge to main.
- **Frontend.** The React/TypeScript frontend handles authentication, the chat interface, and streaming cluster previews. An admin panel lets us view eval session transcripts and metrics through an interactive dashboard.

## Next Steps

- **Finalize experimental conditions and documentation:** Specify the experiment conditions we want to perform and analyze. Then refine the whole documentation to have a proper fixed evaluation plan.
- **Complete the evaluation setup**: Currently we have an non-functional placeholder for evaluation setup. We need to implement the missing components and refine the already defined ones.
- **Freeze and validate the agents**: Before running ablations, we need to ensure agents behaviour is stable and correct. Any prompt or logic bug in a fixed component corrupts every condition equally and makes ablation results uninterpretable.
- **Continuous retrieval**: Extend the clustering agent to accept fresh candidates every turn and decide internally which films to absorb or drop, rather than waiting for an explicit drift or re-retrieve event.
- **Refine decision agent strategies**: Analyse failure cases in the decision agent's questioning strategy and define possible strategies to enhance it.