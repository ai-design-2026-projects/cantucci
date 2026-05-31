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

## 2 Baselines

A **single-prompt baseline**: one LLM call per turn receives the full film list, the current cluster state, and the conversation transcript, and emits — in a single JSON response — the complete resulting cluster grouping (with labels, summaries, and film assignments), the declared navigation operation, and the oracle reply. No embeddings, HDBSCAN, concept-axis scoring, or labeling agent are used; the LLM performs all clustering decisions from text alone. This baseline removes structured components and tests whether the architecture's modularity provides benefits over a single-agent approach.

---

## 3 Ground-truth construction

A ground truth is a **target navigation trajectory**: an ordered list of operations — each tagged with its operation type and its concept — together with an *intent description* that paraphrases that trajectory in natural language.  Operations are drawn from the full navigation vocabulary: `cluster`, `merge`, `focus`, `cross_filter`, `exclude`. Concept-guided `cluster` and `exclude` operations carry an optional `kind` (`axis`, `palette`, `open_ended`) and `space` (`semantic`, `visual`) to express richer exploration goals.

Persona and ground truth are bundled together as a **persona bundle** (`eval/personas/<slug>.yaml`) — a human-editable YAML file that is the canonical source of truth. Database rows are derived from the file at run time (idempotent upsert by slug).

**Procedure (single LLM pass):**
1. Render `eval/build/prompts/ground_truth_v1.j2` — a static app-context description plus operation vocabulary, concept-kind/space guidance, and five few-shot examples (no catalogue movie sampling). Emit one JSON object with both `intent_description` and `operations`.
2. Validate all ops against the canonical vocabulary (`eval/types.NAVIGATION_OPERATIONS`).
3. Write `eval/personas/<slug>.yaml`; DB rows are created lazily at simulation time.

**Oracle access.** The oracle is given the intent description, the current cluster state, and a compact evolution trace of what the system has done so far. It receives **no private to-do list** — it drives the conversation from intent and observation alone. The trajectory is used only for offline scoring (operation recall) and is never shown to the oracle or the system.

---

## 4 Oracle

A simulated oracle is an LLM agent instantiated with a **ground truth** (intent description) overlaid with a **persona** (communication style). One oracle instance is used per session and must not be reused. The oracle is implemented in `eval/oracle/agent.py`.

The oracle's task is to **drive the system toward its intent**: each turn it reads the current cluster state and a compact evolution trace (what the system has done so far), then writes the next natural-language message in the voice of its intent description. The oracle receives no private to-do list — it navigates by intent and observation alone. The system never sees the trajectory; operation recall is computed offline from turn_intents.

### Persona dials

| Dial | Type | Description |
|---|---|---|
| `verbosity` | `terse \| medium \| verbose` | Controls reply length via a system-prompt hint. |
| `patience` | `float [0, 1]` | Controls how many turns the oracle is willing to spend before disengaging. `1.0` → runs to the full turn budget; `0.0` → disengages after a few turns regardless of progress. |


### Behavioural reproducibility

Persona dials are deterministic prompt-level controls (they shape the oracle's system prompt; they do not roll per-turn dice). All non-determinism comes from LLM sampling, which is keyed on the quadruple `(persona slug, ground-truth slug, session seed, turn number)`. The same quadruple always produces the same oracle output, making sessions reproducible across reruns.

---

## 5 Evaluation runner

Two CLI entry points drive the harness:

- **`python -m eval.build`** — build persona bundles (one or a random batch) and write them to `eval/personas/`.
- **`python -m eval.run`** — run simulated sessions (parallel, with a Rich progress bar) and evaluate them. DB rows are created lazily from the bundle files at run time.

The runner (`eval/runtime/session.py`) calls the same Coordinator and data-access path as live HTTP sessions, so simulated sessions are indistinguishable from human sessions in the database. Evaluation (deterministic metrics + LLM judge) runs automatically at the end of each session.

**dry-run mode** (enabled via `dry_run: true` in the model config in `eval/eval.yaml`) replaces all LLM calls with fixture responses for both the oracle and the judge without hitting real APIs.

---

## 6 Session termination

The oracle decides termination each turn by weighing two signals against its intent; the runner enforces the turn-budget cap unconditionally:

- **Intent fulfilled** — the current cluster state and the evolution trace together satisfy the intent description. The oracle ends the session as satisfied.
- **System misbehaviour** — the system has repeatedly failed to understand the oracle's requests. Whether this ends the session depends on the oracle's `patience` dial: a patient oracle tolerates several misclassifications before giving up, an impatient oracle abandons sooner.
- **Turn budget** — `runner.max_turns` caps the runner as a safety net, regardless of oracle state.

After the oracle stops, the runner infers a terminal status (`finished_trajectory`, `finished_misbehaviour`, `finished_budget`) by comparing the executed ``(op, concept)`` pairs from ``turn_intents`` against the ground truth operations.

At session end, the oracle emits a final **session rating** (1–5) summarising how well the system understood its intent and executed the requested operations. The rating is persisted alongside the deterministic metrics.

---

## 7 Metrics

All metrics are persisted after each session in `conversation_metrics` (deterministic) and `judge_scores` (LLM-judge).

### Deterministic metrics (computed from DB state)

| Metric | How measured |
|---|---|
| **Operation recall vs GT** | Fraction of ground-truth operations (matched by operation type and concept) that the system actually executed during the session. `NULL` for human-oracle sessions. The primary structural quality signal. |
| **Clarifier trigger rate** | Fraction of turns on which the Clarifier gate fired and the turn returned without mutating state. |
| **Num turns** | Total oracle turns in the conversation. |
| **Num operations** | Total navigation operations executed across the session (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`) |
| **Final num clusters** | Number of clusters in the final snapshot. |
| **Total cost (USD)** | `conversations.accumulated_cost_usd` — the running total of all LLM costs for the session. |
| **Oracle rating** | Self-rating (1–5) emitted by the simulated oracle at session end, summarising how well the system understood its intent and executed the requested operations. `NULL` for human-oracle sessions. |


### LLM-judge scores (subjective, 1–5)

A separate judge (`eval/judge/agent.py`) reads the completed transcript, the per-turn action log, and the final cluster state (labels, summaries, exemplar titles). It scores five dimensions independently:

| Dimension | What is assessed |
|---|---|
| `operation_appropriateness` | Across the session, did the system pick the right operation (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`) given each oracle message, with sensible parameters (concept, target cluster, modalities)? |
| `label_accuracy` | Do the cluster labels and summaries accurately describe their exemplar films at each snapshot, and do they remain consistent across snapshots and turns (no cosmetic thrashing between synonyms when cluster contents are unchanged)? |
| `suggestion_meaningfulness` | When the Responder volunteers a follow-up suggestion, is it relevant to the current snapshot state, well-timed, and non-redundant with what the oracle has already requested? |
| `explanation_quality` | When the Explanation agent justifies why a movie sits in a given cluster, is the rationale faithful to the cluster's label and exemplars, and specific enough to be informative rather than generic? |
| `intent_alignment` | Does the system's executed sequence of operations and the resulting final snapshot reflect what the oracle was trying to elicit through the intent description? |
| `concept_axis_quality` | For each concept axis the system built: do the two poles form a coherent, genuinely opposing spectrum? Are the axis name and pole labels concise and non-generic? Was the embedding space (semantic vs visual) appropriate for the concept? Is the axis discriminative — would the poles meaningfully separate films? Scored 1–5. Only emitted when the session built ≥1 concept axis; omitted otherwise. |

---

## 8 Notes

- **Three LLM families.** The judge, the oracle, and the system under test must each run on a different family of LLMs. Same-family pairs (e.g. judge and system both on the same vendor or fine-tune lineage) bias scores upward because models reward outputs that match their own conventions.
- **Oracle model class.** The oracle does not need a strong reasoning model. Its job is to paraphrase the next pending operation in the voice of the intent description — consistency matters more than depth. Cheap, small models are acceptable and reduce eval cost meaningfully across large cross-products.
- **Confidence Interval.** All the metrics are delivered with their 95% confidence intervals computed via bootstrapping across sessions. The confidence intervals are the primary signal for comparing variants: non-overlapping intervals indicate statistically significant differences in performance.