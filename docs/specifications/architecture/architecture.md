# Architecture Diagram

This captures the **online conversational loop**: a single **Coordinator** orchestrates one user
message at a time through a deterministic agent pipeline — **Intent** classification, an optional
**Clarifier** gate, one or more **Clustering** operations (each optionally guided by a **Concept**
and finalised by **Labeling**), an **Explanation** path, and a **Responder** that may volunteer a
follow-up suggestion. Cluster state is stored as a content-addressed tree of snapshots in the
vector database.


## System components

<img src="../../media/architecture_diagram.svg" style="background:#fff;padding:8px;" />

| Component | Role in system | Model | Purpose |
|---|---|---|---|
| **User (Oracle)** | Oracle | none | The source of truth: a human participant or an MCP/LLM client. Sends free-form natural-language messages requesting clustering operations, explanations, or navigation. |
| **Coordinator** | Orchestration & handoffs | none | The sole orchestrator and **only writer to the database**. Per message it loads current cluster state, labels any unlabeled clusters, classifies intent, applies a confidence gate, executes each requested action in order, and optionally asks the Responder for a suggestion. Holds no in-memory session state — every turn re-reads from the DB. |
| **Intent Agent** | Intent classification | strong | Parses the oracle's message into an ordered list of actions, each tagged with a `NavigationMode` or `DialogueMode`, a confidence score, and operation-specific parameters (concept, target cluster, merged label, metadata filter, embedding modalities, partition spec). |
| **Clustering** | Grouping & navigation | none | Nine Command classes (`ClusterCommand`, `MergeCommand`, `FocusCommand`, `ExcludeCommand`, `CrossFilterCommand`, `ResetCommand`, `UndoCommand`, `SmallTalkCommand`, `ExplainCommand`), each implementing `execute(ctx: ExecutionContext)` and selected by `build_command(action)` from the intent action's mode. The clustering computation itself lives in a pure layer — `core/clustering.py` (HDBSCAN) and `backend/coordinator/commands/helpers/clustering.py` (UMAP via `reduce_for_clustering`, multi-modal dispatch via `cluster_group`) — that runs no LLM and never writes to the DB. The Command classes call into this layer and then persist results via `persist_and_label`. |
| **Concept Agent** | Semantic axis building | strong | Turns a user concept string (e.g. "surrealism") into a `LinearAxisRep`: a unit vector built from the centroid difference of positive and negative pole descriptions, $\ell_2$-normalised. The `space` field determines the encoder: `"semantic"` → BGE text encoder (scored against `text_embedding`); `"visual"` → CLIP text tower (scored against `trailer_embedding`). Used to guide concept-driven `cluster` operations. |
| **Labeling Agent** | Naming | fast | A single batched LLM call that names and summarises all unlabeled clusters at once (root clusters are ingested unlabeled and labelled lazily on first access). When a cluster already has a deterministic label (e.g. a genre value or a numeric bin name from a partition), the agent echoes that label exactly and generates only the summary. |
| **Clarifier Agent** | Disambiguation gate | fast | When any state-changing action falls below the configured confidence threshold, produces a clarification question and the turn returns early without mutating state. |
| **Explanation Agent** | Placement rationale | strong | Generates a natural-language explanation for why a given movie sits in a given cluster, using the cluster label and exemplars. Read-only. |
| **Responder Agent** | Proactive suggestions | fast | After actions complete, computes deterministic signals (similar cluster pairs, a dominant cluster, high noise fraction) and only if a signal exceeds threshold calls the LLM to propose a next step. May decline. |
| **Vector Database** | Persistent memory | none | Stores catalogue embeddings (three modalities), conversations and messages, the content-addressed cluster-snapshot tree, clusters, soft memberships, and concepts. |


## Operations & natural-language control

The oracle never picks an operation from a menu — they type free-form text, and the **Intent agent**
maps it onto a fixed, closed set of operations.
We can distinguish two families: 
- **Navigation operations** (`NavigationMode`) re-cluster the data, producing a new snapshot;
- **Dialogue operations** (`DialogueMode`) navigate, explain, or chat without producing new clusters.

| Operation | Family | Definition | Illustrative phrasing |
|---|---|---|---|
| `cluster` | navigation | Split one cluster (or the full catalogue) into sub-groups via one of three paths depending on what the action carries. **Free** — no concept, no `partition_spec`: HDBSCAN runs on the chosen embedding modalities (`embedding_spaces`). **Concept-guided** — `concept` is set: two-turn flow — score movies on the concept axis and show a beeswarm proposal (turn 1), then 1-D HDBSCAN on the persisted scores (turn 2). **Deterministic partition** — `partition_spec` is set: group by a metadata attribute (`genre`, `runtime`, `release_year`, `director`, `vote_average`, `original_language`). Has three sub-cases: *(a)* no target and multiple clusters → ask which one and mark awaiting; *(b)* numeric attribute (`runtime`, `release_year`, `vote_average`) with no bins → compute distribution stats, propose round-number bin edges, mark awaiting — second turn executes with the confirmed `PartitionSpec`; *(c)* categorical attribute (`genre`, `director`, `original_language`) or numeric with bins already set → execute directly, group by value, merge sibling clusters, persist. | **Free**: "cluster these further", "regroup everything" · **Concept**: "break the noir group down by how violent they are" · **Partition**: "split by decade", "group by genre" |
| `merge` | navigation | Combine two or more clusters into one under a chosen label. | "these two are basically the same, combine them" |
| `focus` | navigation | Discard every cluster except the selected one, narrowing the working set to its members. | "just keep the sci-fi cluster" |
| `cross_filter` | navigation | Keep only movies matching a metadata predicate (genres, year range, director) | "only 90s movies directed by Spielberg, then regroup" |
| `exclude` | navigation | Remove one cluster from the snapshot, keeping all others. | "get rid of that noise cluster" |
| `reset` | dialogue | Return to the unclustered state (no active snapshot). | "start over" |
| `undo` | dialogue | Step back to the previous snapshot, undoing the last navigation operation. | "undo that", "go back" |
| `explain` | dialogue | Explain why a given movie sits in a given cluster. | "why is Blade Runner in this group?" |
| `small_talk` | dialogue | Casual, non-operational message; answered with a static help reply. | "what can you do?" |

The Intent agent emits an **ordered list of actions**, so a single message can request a compound
sequence (e.g. *"reset, then split everything by mood"* → `reset` then `cluster`); the Coordinator
executes them in order, threading each resulting snapshot into the next. 

Each action carries
`target_cluster_id`, `concept`, `metadata_filter`, `merged_label`, `embedding_spaces`, `confidence`,
`partition_spec`, `target_n_clusters`, and `reuse_concept_id` — all inferred from natural language.
When any action that creates a snapshot has a `confidence`
below the configured threshold, the **Clarifier** asks a disambiguating question instead of guessing
(see Turn Handling, Phase 3).

## Embeddings & fusion

Each movie carries up to three 1024-dimensional, $\ell_2$-normalised embeddings, matching the `Modality`
enum and the embedding columns in `data_schema.md`. The encoding primitives live in `core/` and are
shared with the offline ingest pipeline; the online loop only reads stored vectors.

| Modality | Model | Encodes | Column |
|---|---|---|---|
| `TEXT` | `BAAI/bge-large-en-v1.5` (sentence-transformers) | `composite_text` (title, overview, genres, cast, director, …) | `text_embedding` |
| `REVIEW` | `BAAI/bge-large-en-v1.5` | `reviews_text` (concatenated reviews) | `review_embedding` |
| `TRAILER` | open_clip `ViT-H/14` | 16 evenly-spaced trailer frames, CLIP-encoded then mean-pooled (fallback to the poster if no trailer is available) | `trailer_embedding` |

**Fusion** (`core/fusion.py`) takes two paths.
- Text and reviews share the same BGE space and are combined by a **weighted vector average** (`fuse_batch`); rows without a review stay text-only.
- BGE text and CLIP trailer embeddings are combined at the **distance level** (`combined_distance_matrix`): a full cosine-distance matrix is computed per modality and the matrices are weighted-summed:

  $$d_{\text{combined}}(A, B) = \frac{w_{\text{text}} \cdot d_{\text{text}}(A, B) + w_{\text{trailer}} \cdot d_{\text{trailer}}(A, B)}{w_{\text{text}} + w_{\text{trailer}}}$$

The intent agent picks which modalities to fuse per operation via `embedding_spaces`.

## Clustering

**Algorithm** — the path through UMAP and the membership model both depend on which clustering variant is running.

*TEXT-only free clustering* — embeddings are first passed through `reduce_for_clustering` (`backend/coordinator/commands/helpers/clustering.py`), which applies UMAP in three tiers based on set size: full reduction to `clustering_n_components` dimensions for large sets, a light reduction to $\max(2, \min(\lfloor n/3 \rfloor, 20))$ dimensions for mid-size sets, and no reduction for sets too small for UMAP to be reliable. The reduced embeddings are then passed to HDBSCAN with `metric="euclidean"`, which enables **true soft membership** via `all_points_membership_vectors` — each movie receives a continuous probability per cluster.

*Multi-modal clustering (TEXT + TRAILER)* — UMAP is skipped because UMAP requires raw feature vectors to learn a manifold projection; applying it on top of the already-fused cross-space distance matrix would be incorrect. `combined_distance_matrix` produces the fused representation directly, and HDBSCAN runs on it with `metric="precomputed"`. The precomputed-metric path does not support `all_points_membership_vectors`, so **hard assignment** is used: each movie gets probability $1.0$ for its assigned cluster and $0.0$ elsewhere.

*Concept-guided clustering* — UMAP is skipped because concept scores are inherently 1-dimensional (one score per movie on the axis); there is nothing to reduce. HDBSCAN runs directly on the $1$-D score array with `metric="euclidean"`, giving **true soft membership**.

In all three paths, noise points (label $-1$) have their row set to the uniform distribution $1/K$ across $K$ clusters, so every movie always belongs somewhere.

**Concept guide clustering** — on the proposal turn, scores are min-max normalised to $[-1, 1]$ and persisted to `concept_scores`. On the confirmation turn, `apply_pending_concept_override` patches the `CLUSTER` action with `reuse_concept_id`, skipping the Concept agent entirely. 1-D HDBSCAN finds natural density clusters on the score axis — no forced binary split; boundaries emerge from the distribution. The oracle may supply `target_n_clusters`; if omitted the emergent count is used.

**Persist & label** (`backend/coordinator/tools/persist.py`) — after the clustering compute layer
returns a draft, the Coordinator checks the **content-addressed cache** keyed by
`(parent_snapshot_id, operation, canonical_params, config_hash)`. On a cache hit the existing
snapshot is reused with no re-labelling cost. On a miss: a new `cluster_snapshots` row is created,
the Labeling Agent names all clusters in one batched LLM call, memberships are bulk-inserted, and
`conversations.current_cluster_snapshot_id` is updated.

## Navigating the execution graph

Every navigation operation is recorded as a node in a persistent graph rather than mutating state in
place, which is what lets the oracle move backward and sideways through the exploration — not just
forward. Two structures (defined in `data_schema.md`) make this work:

- **The snapshot lineage.** Each `cluster_snapshots` row stores the `parent_id` of the snapshot it
  was derived from, plus the `operation` and the canonical `params` that produced it. Following
  `parent_id` upward gives the exact chain of operations that built any state, back to the ingest-time
  root (`operation = 'base'`, `parent_id = NULL`). A single conversation's snapshots therefore form a
  tree: a linear path while the oracle keeps refining, branching whenever they back up and try a
  different operation from an earlier point.
- **Per-conversation membership.** `conversation_snapshot_refs` records every snapshot a conversation
  has touched, decoupled from lineage, so a conversation "owns" its visited states even though the
  snapshots themselves are shared.

**Going back** is just re-pointing `conversations.current_cluster_snapshot_id` at an earlier node — no
recomputation. `PATCH /conversations/{id}` (and the MCP `navigate_to_snapshot` tool) sets the active
snapshot to any prior snapshot id; `reset` clears the pointer to the unclustered state. `GET /conversations/{id}/snapshot-graph` returns the whole node set (id, parent_id, operation, created_at) so a client can render the tree and let the oracle click a past state to return to it.

**Branching and reuse** fall out of the same design. Issuing a new operation from a state the oracle
has rewound to simply creates a new child of that node — the prior branch is untouched and still
reachable. And because snapshots are **content-addressed** by `(parent_id, operation, params,
config_hash)`, re-deriving a state that already exists (in this or another conversation) reuses the
cached node instead of re-clustering, so revisiting and replaying paths is cheap. Deleting a snapshot
is restricted to leaves (`409` otherwise) and reparents any conversation pointing at it to the
snapshot's parent, so the graph never loses a state that is still on someone's path.

## Turn Handling

<img src="../../media/flowchart.svg" style="background:#fff;padding:8px;" />

Each user message is handled by a stateless `Coordinator.handle_message`
(`backend/coordinator/agent.py`), which loads current state from the DB, runs a
**deterministic sequential pipeline**, and writes results back. A `ProgressReporter` emits SSE
step events throughout (consumed by `GET /conversations/{id}/events`).

### Phase 1 — Load, label & context

The Coordinator reads the conversation's `current_cluster_snapshot_id` and its clusters. If any
cluster is unlabeled (true for freshly ingested root clusters), it emits a `labeling` step and
labels them all in one batched call, persisting the labels. It then calls `resolve_clarification_context(conversation_id)` (`pipeline/pending.py`), which consumes the in-memory awaiting flag via `take_awaiting`: if the prior turn ended with a clarification question, the Coordinator fetches that assistant message and passes it to the Intent agent so follow-up answers ("the first option", "yes, that one") resolve correctly. This awaiting state is intentionally ephemeral (module-level in-memory store, not
persisted — lost on server restart).

### Phase 2 — Intent classification

It emits an `intent` step and calls the Intent agent, which returns one or more ordered actions.
Compound requests (e.g. *reset then cluster*) come back as a multi-element list.

If `was_awaiting` is set, the actions are immediately patched before the confidence gate:
`apply_pending_spec_override` restores the stored `PartitionSpec` into the `CLUSTER` action (so the oracle's confirmation does not need to re-specify bins); `apply_pending_concept_override` injects `reuse_concept_id` so the Concept agent is skipped on the second turn.

### Phase 3 — Confidence gate (routing gate)

If **any** action whose Command has `CREATES_SNAPSHOT = True` has confidence below `intent.confidence_threshold`, the Coordinator emits a `clarifier` step, returns a clarification question, and **exits early without mutating state**.
The commands that are gated (`CREATES_SNAPSHOT = True`) are: `ClusterCommand`, `MergeCommand`, `FocusCommand`, `ExcludeCommand`, `CrossFilterCommand`, and `UndoCommand`. The commands that are **not** gated (`CREATES_SNAPSHOT = False`) are: `ResetCommand`, `ExplainCommand`, and `SmallTalkCommand`. Otherwise it proceeds to dispatch.

### Phase 4 — Sequential action execution

For each action in order, the Coordinator re-reads the current snapshot's clusters if there is an
active snapshot (so later actions see the post-operation state), or passes an empty cluster list
when no snapshot exists yet. It bundles this into an immutable `ExecutionContext` and dispatches
to the matching Command via `build_command(action)`. Each command returns an `ActionResult` with
a reply fragment, resulting snapshot id (unchanged or `None` for non-snapshot commands), and cost.

| Mode | Command | Behaviour | DB write |
|---|---|---|---|
| `DialogueMode.SMALL_TALK` | `SmallTalkCommand` | Static help reply | none |
| `DialogueMode.RESET` | `ResetCommand` | Clear active snapshot (unclustered state) | `set_current_cluster_snapshot(None)` |
| `DialogueMode.EXPLAIN` | `ExplainCommand` | Explain a movie's placement (`explain` step) | none (read-only) |
| `DialogueMode.UNDO` | `UndoCommand` | Re-point to parent snapshot; emits `labeling` if parent has unlabeled clusters | `set_current_cluster_snapshot` + `record_conversation_snapshot_ref` |
| `NavigationMode.CLUSTER` | `ClusterCommand` | **Free / direct**: no concept → `clustering` step → `persist_and_label`. **Deterministic-partition** (`partition_spec` set): `clustering` step → `persist_and_label`. **Concept proposal** (concept + no `target_n_clusters`): `concept` step → score + persist concept scores → `clustering` step (scoring only) → return beeswarm proposal, mark awaiting — no snapshot written. **Concept execute** (`reuse_concept_id` set, second turn): load persisted scores → `clustering` step (1-D HDBSCAN) → `persist_and_label`. | via `persist_and_label` (free / partition / execute paths); `upsert_concept_scores` only (proposal path) |
| `NavigationMode.MERGE` | `MergeCommand` | Merge first two clusters → `clustering` step → `persist_and_label` | via `persist_and_label` |
| `NavigationMode.FOCUS` | `FocusCommand` | Narrow to one cluster → `clustering` step → `persist_and_label` | via `persist_and_label` |
| `NavigationMode.EXCLUDE` | `ExcludeCommand` | Drop one cluster, keep the rest → `clustering` step → `persist_and_label` | via `persist_and_label` |
| `NavigationMode.CROSS_FILTER` | `CrossFilterCommand` | SQL metadata filter (genres / year range / director) over the current snapshot's movies → `clustering` step (single flat cluster) → `persist_and_label` | via `persist_and_label` |

### Phase 5 — Suggestion & return

The Coordinator joins reply fragments (numbered `1) … 2) …` when there is more than one). If
dispatch itself ended with a new awaiting state (e.g. a concept-axis or partition-bin proposal),
the suggester is skipped entirely and no `suggester` SSE step is emitted. Otherwise it emits a
`suggester` step and calls the Responder's `maybe_suggest` on the final snapshot — deterministic
signals are computed and the LLM is called only if one trips. A `turn_done` event is emitted, and
the Coordinator returns a `CoordinatorResult` with the combined reply, final snapshot id, this
turn's cost, and the optional suggestion. The router then persists the assistant message and adds
the turn cost to the conversation.

**SSE progress steps**, in emission order: `labeling`, `intent`, `clarifier`, `concept`,
`clustering`, `explain`, `suggester`, then the terminal `turn_done`. Note that `labeling` can also
fire mid-turn inside `UndoCommand` when the parent snapshot has unlabeled clusters.
