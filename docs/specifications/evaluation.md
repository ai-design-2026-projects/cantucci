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

A ground truth is a **target cluster structure**: a labelled partition of N films from the holdout into K named groups, together with a short *intent description* of the partition (the theme, axis, or split the partition encodes) and a list of seed films used to anchor each group.

- NO CLUSTER, ONLY INTENT LIST 

**Procedure (TODO — open question on the right generation strategy):**
1. Sample K × M seed films from the holdout set using a fixed random seed.
2. Call an LLM to propose a labelled K-way partition over the sampled films, together with a short intent description ("split by tone vs. plot complexity", "European arthouse vs. American mainstream", …).
3. The LLM expands each group to its target size by selecting the nearest holdout neighbours of the group's exemplars in fused embedding space.
4. Store the seeds, target partition, intent description, and the LLM prompt hash as a versioned `ground_truths` row.

> ⚠ **To check.** Pure LLM-only generation is the current choice for speed but has not been validated against human judgment. The fallback options — manual curation, or offline HDBSCAN + LLM labelling — should be revisited before committing to large-scale runs.

**Oracle access.** The oracle sees only the intent description. The target partition (film-to-group mapping) is held by the runner and used for structural scoring after the session ends. This separation is enforced so the oracle cannot reverse-engineer the target from the snapshots it produces during the conversation.

---

## 4 Oracle

A simulated oracle is an LLM agent instantiated with a **ground truth** (intent description) overlaid with a **persona** (communication style). One oracle instance is used per session and must not be reused. The oracle is implemented in `eval/oracle/agent.py`.

The oracle's task is to **articulate the target partition through navigation operations**: it reads the current snapshot's labels and summaries, and emits messages that should drive the system toward the target structure (asking for splits along the right axis, merging groups that should be one, focusing on the right subset). The oracle is not given the target film list — only the intent description and the current snapshot state.

### Persona dials

| Dial | Type | Description |
|---|---|---|
| `verbosity` | `terse \| medium \| verbose` | Controls reply length via a system-prompt hint. |
| `patience` | `float [0, 1]` | Controls how many turns the oracle is willing to spend before disengaging. `1.0` → runs to the full turn budget; `0.0` → disengages after a few turns regardless of progress. |


### Behavioural reproducibility

All per-turn behavioural rolls (drift, contradiction, disengagement) are seeded and deterministic, keyed on a combination of persona slug, ground-truth slug, session seed, and turn number. The same quadruple always produces the same sequence of conversational events, making behaviour reproducible across reruns even though the LLM output is stochastic.

---

## 5 Evaluation runner

The runner (`eval/runner.py`, CLI `python -m eval.run`) drives the full cross-product of ground truths, personas, and random seeds against the live system in-process. For each cell in the cross-product it creates a conversation, runs oracle turns, and after the session ends evaluates the conversation. All calls go through the same Coordinator and data-access path as live sessions.

**dry-run mode** (enabled via `dry_run: true` in the model config, e.g. `configs/test.yaml`) replaces all LLM calls with fixture responses for both the oracle and the judge without hitting real APIs.

---

## 6 Session termination

The runner ends a session when the first of three signals fires:

- **ORACLE CHOICE BASED ON HAS PERFOMED ALL ACTION, OR THE CLUSTERING AGENT PERFORMS A UNDESIRED ACTION FOR THE ORACLE HE CHOICES IF TO CONTINUE OR NOT**
- **Turn budget** — `eval.max_turns` caps the runner unconditionally.

WHEN YOU FINISH RATE THE CONVERSATION

---

## 7 Metrics

All metrics are persisted after each session in `conversation_metrics` (deterministic) and `judge_scores` (LLM-judge).

### Deterministic metrics (computed from DB state)

| Metric | How measured |
|---|---|
| **Silhouette score** | `sklearn.metrics.silhouette_score` on the fused embeddings of the final snapshot's members, using argmax cluster assignment and cosine distance. `NULL` when fewer than 2 clusters or any cluster has fewer than 2 members. Diagnostic only — structural alignment with the target partition is the objective function. | (EXTEND WITH FORMULAS AND EXPLANATION OF THE METRIC)
| **Mean membership probability** | Mean argmax membership probability across all movies in the final snapshot. Measures cluster firmness. |
| **Noise fraction** | Fraction of movies with argmax probability below `eval.noise_prob_threshold`. |
| **iNTET GROUND TRUTH vs target** | Adjusted Rand Index between the final snapshot's partition and the ground-truth target partition, computed over the films that appear in both. `NULL` for human-oracle sessions. The primary structural quality signal. |
| **Clarifier trigger rate** | Fraction of turns on which the Clarifier gate fired and the turn returned without mutating state. |
| **Num turns** | Total oracle turns in the conversation. |
| **Num operations** | Total navigation operations executed across the session (drill_down, merge, focus, cross_filter). |
| **Final num clusters** | Number of clusters in the final snapshot. |
| **Total cost (USD)** | `conversations.accumulated_cost_usd` — the running total of all LLM costs for the session. |


### LLM-judge scores (subjective, 1–5)

A separate judge (`eval/judge/agent.py`) reads the completed transcript, the per-turn action log, and the final cluster state (labels, summaries, exemplar titles). It scores four dimensions independently:

| Dimension | What is assessed |
|---|---|
| `operation_appropriateness` | Across the session, did the system pick the right operation (`drill_down`, `merge`, `focus`, `cross_filter`) given each oracle message, with sensible parameters (concept, target cluster, modalities)? |
| `label_accuracy` | Do the cluster labels and summaries accurately describe their exemplar films at each snapshot? | (ACROSS THE CLUSTER SNAPSHOTS AND ON DIFFERENT TURN THEY REMAIN PERSISTENT)
| seuggestion meningfullness |
| explanation quality |
| `intent_alignment` | Does the final clustering reflect the partition the oracle was trying to articulate, as conveyed by the intent description? |

## Notes
judge, oracle and system, should use three different families of LLMs
Oracle can have dumb models.
