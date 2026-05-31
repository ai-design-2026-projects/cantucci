# Evaluation Strategy

---

## 1 Research question

Our main objective is to explore the following question:

> Does an intent-driven navigation loop produce more coherent clusterings of the catalogue, with less oracle effort, than other variants?

We approach this from three angles:

- **Operation choice**: given a free-form oracle message, does the Intent agent pick the right navigation operation (`drill_down`, `merge`, `focus`, `cross_filter`) and the right parameters (concept, target cluster, modalities)?
- **Cluster update strategy**: do concept-guided splits, soft HDBSCAN memberships, and the content-addressed snapshot tree yield more stable, more separable clusters than plain re-clustering on raw embeddings?
- **Satisfaction**: how do we assess clustering quality when there is no recommended film list — only a sequence of cluster snapshots — and how far do those assessments generalise?

---

## 2 Baselines

A **no-agents pipeline**: the oracle's first message is embedded, plain HDBSCAN is run on their fused embeddings. No Intent, Clarifier, Concept, Labeling, or Responder agent runs; clusters are presented unnamed. This is the minimum bar for the modular pipeline to justify its cost.

A **monolithic LLM**: a single LLM acts as the clustering agent end-to-end, holding the conversation, deciding which operation to perform, and emitting a free-form description of the resulting groups without going through the typed agent boundary. This baseline removes structured components and tests whether the architecture's modularity provides benefits over a single-agent approach.

---

## 3 Ground-truth construction

Ground truths are built offline from a held-out partition of the catalogue that is never ingested into the main catalogue (the `eval_holdout` parquet artifact).

A ground truth is a **target navigation trajectory**: an ordered list of operations — each tagged with its operation type (`drill_down`, `merge`, `focus`, `cross_filter`) and its concept (the semantic axis or target the operation applies to) — together with an *intent description* that paraphrases that trajectory in natural language.

**Procedure:**
1. Call an LLM to propose a plausible navigation trajectory: 3–6 operations with their concepts, such that the trajectory tells a coherent exploration story over the catalogue ("drill_down by tone", "focus on slow-burn", "drill_down by setting", …).
2. Call a second LLM pass to write a neutral, voice-agnostic intent description that resembles the trajectory in natural language ("I want to split modern thrillers by their tone, then zoom in on the slow-burn ones and break those down by setting").
3. Store the operation list, the intent description, and the LLM prompt hash as a versioned `ground_truths` row.

**Oracle access.** The oracle is given both the intent description (as conversational style and framing) and the operation trajectory (as a private to-do list). Each turn it paraphrases the next pending operation into a free-form message; the system sees only that message and must recover the intended operation from natural language alone. The trajectory is never exposed to the system.

---

## 4 Oracle

A simulated oracle is an LLM agent instantiated with a **ground truth** (intent description) overlaid with a **persona** (communication style). One oracle instance is used per session and must not be reused. The oracle is implemented in `eval/oracle/agent.py`.

The oracle's task is to **drive the system through its target trajectory**: it reads the current snapshot's labels and summaries, picks the next pending operation from its private to-do list, and paraphrases it into a free-form message in the voice of the intent description. The system never sees the trajectory — only the messages the oracle emits.

### Persona dials

| Dial | Type | Description |
|---|---|---|
| `verbosity` | `terse \| medium \| verbose` | Controls reply length via a system-prompt hint. |
| `patience` | `float [0, 1]` | Controls how many turns the oracle is willing to spend before disengaging. `1.0` → runs to the full turn budget; `0.0` → disengages after a few turns regardless of progress. |


### Behavioural reproducibility

Persona dials are deterministic prompt-level controls (they shape the oracle's system prompt; they do not roll per-turn dice). All non-determinism comes from LLM sampling, which is keyed on the quadruple `(persona slug, ground-truth slug, session seed, turn number)`. The same quadruple always produces the same oracle output, making sessions reproducible across reruns.

---

## 5 Evaluation runner

The runner (`eval/runner.py`, CLI `python -m eval.run`) drives the full cross-product of ground truths, personas, and random seeds against the live system in-process. For each cell in the cross-product it creates a conversation, runs oracle turns, and after the session ends evaluates the conversation. All calls go through the same Coordinator and data-access path as live sessions.

**dry-run mode** (enabled via `dry_run: true` in the model config, e.g. `configs/test.yaml`) replaces all LLM calls with fixture responses for both the oracle and the judge without hitting real APIs.

---

## 6 Session termination

The oracle decides termination at each turn from its own state; the runner only enforces the turn-budget cap. On every turn the oracle weighs three signals and chooses to continue or stop:

- **Trajectory completion** — every operation in the oracle's to-do list has been requested and executed appropriately by the system. The oracle ends the session as satisfied.
- **System misbehaviour** — the system has performed an undesired or off-target operation in response to a paraphrased request. Whether this ends the session depends on the oracle's `patience` dial: a patient oracle tolerates several misclassifications before giving up, an impatient oracle abandons sooner.
- **Turn budget** — `eval.max_turns` caps the runner unconditionally as a safety net, regardless of oracle state.

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
| **Num operations** | Total navigation operations executed across the session |
| **Final num clusters** | Number of clusters in the final snapshot. |
| **Total cost (USD)** | `conversations.accumulated_cost_usd` — the running total of all LLM costs for the session. |
| **Oracle rating** | Self-rating (1–5) emitted by the simulated oracle at session end, summarising how well the system understood its intent and executed the requested operations. `NULL` for human-oracle sessions. |


### LLM-judge scores (subjective, 1–5)

A separate judge (`eval/judge/agent.py`) reads the completed transcript, the per-turn action log, and the final cluster state (labels, summaries, exemplar titles). It scores five dimensions independently:

| Dimension | What is assessed |
|---|---|
| `operation_appropriateness` | Across the session, did the system pick the right operation (`drill_down`, `merge`, `focus`, `cross_filter`) given each oracle message, with sensible parameters (concept, target cluster, modalities)? |
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