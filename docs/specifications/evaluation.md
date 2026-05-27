# Evaluation Strategy

---

## 1 Research question

Our main objective is to explore the following question:

> Does conversational refinement produce a higher-quality clustering for the oracle (fewer turns to convergence, lower cognitive load, better cluster coherence) than a one-shot baseline?

We approach this from three angles:

- **Questioning strategy**: how should the system decide what to ask at each turn, and what signals should drive that decision?
- **Cluster update strategy**: how should oracle feedback propagate into cluster boundaries, and what algorithms or heuristics best support incremental refinement?
- **Satisfaction**: how do we assess clustering quality when the oracle is an LLM agent, and how far do those assessments generalise?

---

## 2 Baselines

A **one-shot initial clustering**: the oracle's first message is used to produce the root clustering without any follow-up questions. The oracle rates the result as satisfying or not. This is the minimum bar for the conversational loop to justify its cost.

A **monolithic LLM conversation**: a single LLM acts as the clustering advisor without access to the database, relying on its own knowledge. This baseline removes structured components and tests whether the architecture's modularity and retrieval support provide benefits over a single-agent approach.

---

## 3 Ground-truth construction

Ground truths are built offline from a held-out partition of the catalogue that is never ingested into the main catalogue (the `eval_holdout` parquet artifact).

**Procedure:**
1. Sample N seed films from the holdout set using a fixed random seed.
2. Expand to ~40 films by computing cosine similarity from each seed embedding to the full holdout and taking the nearest neighbours.
3. Call an LLM to write a neutral, voice-agnostic taste description from the seed and expanded film lists.
4. Store the seed films, expanded film set, taste description, and a positive/negative preference spec as a versioned `ground_truths` row.

**Oracle access:** the oracle sees only the taste description. The target film set and the preference spec are held by the runner and used for spec-satisfaction scoring after the session ends. This separation is enforced so the oracle cannot reverse-engineer the target from the films shown during conversation.

---

## 4 Oracle

A simulated oracle is an LLM agent instantiated with a **ground truth** (taste description) overlaid with a **persona** (communication style). One oracle instance is used per session and must not be reused. The oracle is implemented in `eval/oracle/agent.py`.

### Persona dials

| Dial | Type | Description |
|---|---|---|
| `verbosity` | `terse \| medium \| verbose` | Controls reply length via a system-prompt hint. |
| `decisiveness` | `float [0, 1]` | Controls the minimum turn at which the oracle is willing to accept. `1.0` → accepts from turn 1; `0.0` → waits until turn 10+. |
| `drift_probability` | `float [0, 1]` | Per-turn probability of injecting a tangent. |
| `contradiction_rate` | `float [0, 1]` | Per-turn probability of injecting a self-contradiction. |

### Behavioural reproducibility

All per-turn behavioural rolls (drift, contradiction) are seeded and deterministic, keyed on a combination of persona slug, ground truth slug, session seed, and turn number. The same quadruple always produces the same sequence of conversational events, making behaviour reproducible across reruns even though the LLM output is stochastic.

### Acceptance gate

The acceptance gate is applied **after** the LLM expresses intent to accept. Low-decisiveness personas cannot accept before their minimum turn threshold regardless of how good the recommendation looks — the threshold is derived from the decisiveness dial.

### Oracle intents

Each oracle turn returns a message and one of three intents:
- `continue` — keep the session going.
- `accept` — the oracle is satisfied (subject to the acceptance gate).
- `abandon` — the oracle gives up.

---

## 5 Evaluation runner

The runner (`eval/runner.py`, CLI `python -m eval.run`) drives the full cross-product of ground truths, personas, and random seeds against the live system in-process. For each cell in the cross-product it creates a conversation, runs oracle turns, and after the session ends evaluates the conversation. All calls go through the same Coordinator and data-access path as live sessions.

**dry-run mode** (enabled via `dry_run: true` in the model config, e.g. `configs/test.yaml`) replaces all LLM calls with fixture responses for both the oracle and the judge without hitting real APIs.

---

## 6 Convergence detection

The runner and metric module detect convergence **post-hoc** from the message history — no changes are made to the live Coordinator loop. Two signals are checked in order:

- **Explicit acceptance** — an oracle message contains one of the configured `accept_phrases` (case-insensitive). This is the cleanest signal and always takes priority.
- **Behavioural stability** — `convergence_turns` consecutive oracle messages contain no state-changing vocabulary, indicating the oracle stopped offering corrections.

The turn number of the first fired signal is recorded as `turns_to_convergence`. The turn budget (`eval.max_turns` in config) caps the runner even without convergence.

---

## 7 Metrics

All metrics are persisted after each session in `conversation_metrics` (deterministic) and `judge_scores` (LLM-judge).

### Deterministic metrics (computed from DB state)

| Metric | How measured |
|---|---|
| **Turns to convergence** | Turn number when the first convergence signal fires; `NULL` if not converged. |
| **Num turns** | Total oracle turns in the conversation. |
| **Avg cognitive load** | Reserved for future instrumentation of clusters-shown and question-type per turn. |
| **Final num clusters** | Number of clusters in the final snapshot. |
| **Silhouette score** | `sklearn.metrics.silhouette_score` on fused text+review embeddings of all movies in the final snapshot, using their argmax cluster assignment. Cosine distance metric. `NULL` when fewer than 2 clusters or any cluster has fewer than 2 members. Diagnostic only — the oracle's acceptance is the objective function. |
| **Mean membership probability** | Mean argmax membership probability across all movies in the final snapshot. |
| **Noise fraction** | Fraction of movies with argmax probability below `eval.noise_prob_threshold`. |
| **Spec-satisfaction rate** | Fraction of final-snapshot movies that appear in the ground truth's hidden target film set. `NULL` for human-oracle sessions. |
| **Total cost (USD)** | `conversations.accumulated_cost_usd` — the running total of all LLM costs for the session. |

### LLM-judge scores (subjective, 1–5)

A separate judge (`eval/judge/agent.py`) reads the completed transcript and final cluster state (labels, summaries, exemplar titles). It scores four dimensions independently:

| Dimension | What is assessed |
|---|---|
| `clustering_coherence` | Are the named clusters internally consistent and meaningfully distinct throughout the session? |
| `question_quality` | Are the system's questions targeted, non-redundant, and specific enough to distinguish taste directions? |
| `label_accuracy` | Do the cluster labels and summaries accurately describe their exemplar films? |
| `intent_alignment` | Does the final clustering reflect what the oracle was actually asking for? |

