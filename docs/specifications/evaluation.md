# Evaluation Strategy

---

## 1 Research question

Our main objective is to explore the following question:

> Does an intent-driven navigation loop produce more coherent clusterings of the catalogue, with less oracle effort, than other variants?

We approach this from three angles:

- **Operation choice**: given a free-form oracle message, does the Intent agent pick the right navigation operation (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`) and the right parameters (concept, target cluster, modalities)?
- **Cluster update strategy**: do concept-guided splits, soft HDBSCAN memberships, and the content-addressed snapshot tree yield more stable, more separable clusters than plain re-clustering on raw embeddings?
- **Satisfaction**: how do we assess clustering quality when there is no recommended film list — only a sequence of cluster snapshots — and how far do those assessments generalise?

---

## 2 Baseline

A **single-prompt baseline**: one LLM call per turn receives the full film list, the current cluster state, and the conversation transcript, and emits — in a single JSON response — the complete resulting cluster grouping (with labels, summaries, and film assignments), the declared navigation operation, and the oracle reply. No embeddings, HDBSCAN, concept-axis scoring, or labeling agent are used; the LLM performs all clustering decisions from text alone. This baseline removes structured components and tests whether the architecture's modularity provides benefits over a single-agent approach.

---

## 3 Ground-truth construction

A ground truth is a **target navigation trajectory**: an ordered list of operations — each tagged with its operation type and its concept — together with an *intent description* that paraphrases that trajectory in natural language.  Operations are drawn from the full navigation vocabulary: `cluster` (concept-guided split or numeric partition), `merge`, `focus`, `cross_filter`, `exclude`. Concept-guided `cluster` operations carry an optional `kind` (`axis`, `palette`, `open_ended`) and `space` (`semantic`, `visual`) to express richer exploration goals.

Persona and ground truth are bundled together as a **persona bundle** (`eval/personas/conf/<slug>.yaml`) — a builder-generated YAML file that is the canonical source of truth. Database rows are derived from the file at run time (idempotent upsert by slug); bundles are committed to the repo.

**Procedure (single LLM pass):**
1. Render `eval/builder/prompts/ground_truth_v3.j2` — a static app-context description plus operation vocabulary, concept-kind/space guidance, and five few-shot examples (no catalogue movie sampling). Emit one JSON object with both `intent_description` and `operations`.
2. Validate all ops against the canonical vocabulary (`eval/types.NAVIGATION_OPERATIONS`). Validation also enforces exactly one concept-axis op per trajectory (kind `axis`) and rejects empty or out-of-vocab ops. The generated trajectory length is random in `[gt_builder.min_ops, gt_builder.max_ops]` = `[2, 4]`.
3. Write `eval/personas/conf/<slug>.yaml`; DB rows are created lazily at simulation time.

---

## 4 Oracle

A simulated oracle is an LLM agent (`eval/oracle/agent.py`) instantiated with a **ground truth** (intent description) overlaid with a **persona** (communication style). One oracle instance is used per session and must not be reused.

### Per-turn context

Each turn the oracle receives a rendered prompt (`oracle_v7.j2`) built from the following inputs:

| Input | Source | Notes |
|---|---|---|
| `intent_description` | `ground_truth.intent_description` | The oracle's goal in natural language. The operation list is **never shown** — the oracle navigates by intent and observation alone. |
| `current_snapshot` | current cluster state | Per-cluster label, summary, and up to `exemplar_top_k` film titles. Empty when no clusters exist yet. |
| `evolution_trace` | turn-intent log | Compact list of `(turn, modes, concepts)` for every navigation op the system has executed so far. |
| `transcript` | conversation messages | Full exchange so far (role + content)|
| `turn_number` / `max_turns` | runner config | Signals approaching budget; the prompt forces `stop` on the final turn. |
| `pending_axis` | concept axis state | When the system has scored films along a concept axis but not yet split them, the oracle sees the top-k and bottom-k film titles from each pole and is required to reply with a group count. |
| `verbosity` | persona dial | `terse \| medium \| verbose` — controls reply length via a verbosity-hint string injected into the prompt. |
| `patience` | persona dial | `float [0, 1]` — controls give-up threshold. Three bands: `< 0.4` → gives up on a sub-goal after ~2 failed attempts; `0.4–0.7` → tolerates quite a few failures before disengaging; `> 0.7` → allows ~4 mistakes, rephrases freely, stops only when overall intent is broadly served. |

### Behavioural instructions

The prompt enforces a strict behavioural ruleset:

- **One request per message.** The oracle must ask for exactly one operation per turn and wait for the result before proceeding.
- **Answer clarifying questions.** When the system asks a clarifying question the oracle must answer it directly — ignoring is not permitted.
- **Mandatory explain.** It must ask why one specific exemplar film is in its cluster — exactly once per session, this to enforce a way to evaluate the explanation system.
- **STOP pre-flight.** Before choosing `stop`, the oracle must pass one gate: the message must contain no new request. Two valid stop reasons: *success* (intent substantially fulfilled, rating 4–5) or *give-up* (repeated clustering failures after rephrasing, rating 1–2). Stopping to restart is not allowed — the oracle must send a reset message and continue, in order to avoid oracles unsatisfactorily blaming the system for an empty.

### Output

The oracle emits structured JSON each turn:

| Field | Type | Notes |
|---|---|---|
| `message` | `str` | Natural-language message to send to the system. |
| `decision` | `"continue" \| "stop"` | Whether to end the session. |
| `rationale` | `str` | One-sentence explanation of the decision (not sent to the system). |
| `session_rating` | `int 1–5 \| null` | Required when `decision == "stop"`; omitted otherwise. Rates only how well clustering operations fulfilled the intent |

### Behavioural reproducibility

Persona dials are deterministic prompt-level controls. All non-determinism comes from LLM sampling, which is keyed on the quadruple `(persona slug, ground-truth slug, session seed, turn number)`. The same quadruple always produces the same oracle output, making sessions reproducible across reruns.

---

## 5 Evaluation runner

Two CLI entry points drive the harness:

- **`python -m eval.builder`** — build persona bundles (one or a random batch) and write them to `eval/personas/conf/`.
- **`python -m eval.run`** — run simulated sessions (in parallel, bounded by `runner.max_parallel`) and evaluate them. DB rows are created lazily from the bundle files at run time.

The runner (`eval/runtime/session.py`) calls the same Coordinator and data-access path as live HTTP sessions, so simulated sessions are indistinguishable from human sessions in the database. Evaluation (deterministic metrics + LLM judge) runs automatically at the end of each session.

**dry-run mode** (enabled per-model via `oracle.dry_run: true` / `judge.dry_run: true` in the `eval_harness:` section of `configs/eval.yaml`) replaces all LLM calls with fixture responses for both the oracle and the judge without hitting real APIs.

---

## 6 Session termination

The oracle decides termination each turn by weighing two signals against its intent; the runner enforces the turn-budget cap unconditionally:

- **Intent fulfilled** — the current cluster state and the evolution trace together satisfy the intent description. The oracle ends the session as satisfied.
- **System misbehaviour** — the system has repeatedly failed to understand the oracle's requests. Whether this ends the session depends on the oracle's `patience` dial: a patient oracle tolerates several misclassifications before giving up, an impatient oracle abandons sooner.
- **Turn budget** — `runner.max_turns` caps the runner as a safety net, regardless of oracle state.

After the oracle stops, the runner assigns a terminal status based on the oracle's decision and self-rating: `oracle_rating ≥ 4` produces `finished_trajectory`; a lower rating produces `finished_misbehaviour`; hitting `max_turns` without a terminal oracle decision produces `finished_budget`. No ground-truth comparison is performed at runtime.

At session end, the oracle emits a final **session rating** (1–5) summarising how well the system understood its intent and executed the requested operations. The rating is persisted in `eval_sessions.oracle_rating`.

---

## 7 Metrics

Deterministic metrics are persisted in `conversation_metrics`; oracle rating in `eval_sessions.oracle_rating`; LLM-judge scores in `judge_scores`. All results surface in the **Evaluation Lab** admin tab, which is fed by the `GET /eval/runs/{run_id}/aggregate` endpoint.

### Deterministic metrics (computed from DB state)

| Metric | How measured |
|---|---|
| **Clarifier trigger rate** | Fraction of turns on which the Clarifier gate fired and the turn returned without mutating state. |
| **Num turns** | Total oracle turns in the conversation. |
| **Num operations** | Total navigation operations executed across the session (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`). |
| **Final num clusters** | Number of clusters in the final snapshot. |
| **Total cost (USD)** | `conversations.accumulated_cost_usd` — the running total of all LLM costs for the session. |
| **Oracle rating** | Self-rating (1–5) emitted by the simulated oracle at session end, summarising how well the system understood its intent. Persisted in `eval_sessions.oracle_rating`. |


### LLM-judge scores (subjective, 1–5)

A separate judge (`eval/judge/agent.py`) reads the completed transcript, the per-turn action log, and the final cluster state (labels, summaries, exemplar titles). It scores the following dimensions (always-present unless noted):

| Dimension | What is assessed |
|---|---|
| `operation_appropriateness` | Across the session, did the system pick the right operation (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`) given each oracle message, with sensible parameters (concept, target cluster, modalities)? |
| `label_accuracy` | Do the cluster labels and summaries accurately describe their exemplar films at each snapshot, and do they remain consistent across snapshots and turns? |
| `clustering_coherence` | Do the films within each cluster genuinely belong together? For each cluster, do the exemplar films share a common characteristic consistent with the cluster's label, and is the grouping tight rather than overly broad? |
| `suggestion_meaningfulness` | When the Responder volunteers a follow-up suggestion, is it relevant to the current snapshot state, well-timed, and non-redundant with what the oracle has already requested? Only emitted when at least one suggestion was offered. |
| `explanation_quality` | When the Explanation agent justifies why a movie sits in a given cluster, is the rationale faithful to the cluster's label and exemplars, and specific enough to be informative rather than generic? Only emitted when at least one explain turn occurred. |
| `intent_alignment` | Does the system's executed sequence of operations and the resulting final snapshot reflect what the oracle was trying to elicit through the intent description? |
| `concept_axis_quality` | For each concept axis the system built: do the two poles form a coherent, genuinely opposing spectrum? Are the axis name and pole labels concise and non-generic? Was the embedding space (semantic vs visual) appropriate for the concept? Is the axis discriminative — would the poles meaningfully separate films? Only emitted when the session built ≥1 concept axis. |

---

## 8 Notes

- **Three LLM families.** The judge, the oracle, and the system under test must each run on a different family of LLMs. Same-family pairs (e.g. judge and system both on the same vendor or fine-tune lineage) bias scores upward because models reward outputs that match their own conventions.
- **Oracle model class.** The oracle does not need a strong reasoning model. Its job is to paraphrase the next pending operation in the voice of the intent description — consistency matters more than depth. Cheap, small models are acceptable and reduce eval cost meaningfully across large cross-products.
- **Confidence intervals.** The Evaluation Lab displays a **t-based 95% CI of the mean** for each metric and judge dimension. The interval is `mean ± t₀.₉₇₅,ₙ₋₁ · SEM` where `SEM = sample_std / √n` (Bessel's correction, `n−1` denominator). The t-critical value is looked up for `df = n − 1` (e.g. df=2 → 4.30, df=9 → 2.26) and falls back to 1.96 for `df ≥ 30`. Bootstrapping was not used: at typical group sizes of n ≈ 3–10 sessions per persona, resampling cannot recover information the small sample does not contain and yields intervals no more reliable than the t-distribution. CIs are computed **client-side** from the raw per-session rows returned by `GET /eval/runs/{run_id}/aggregate`; groups with `n = 1` show no CI. Non-overlapping intervals are a practical signal for differences between conditions, though not a formal hypothesis test.
