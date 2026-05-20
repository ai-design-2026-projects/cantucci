# Evaluation Strategy

---

## 1 Research questions

1. **Primary** — Does conversational refinement converge to an oracle-accepted recommendation faster (fewer turns, lower cognitive load per turn) than a one-shot vector search baseline?
2. **Secondary** — Which question-selection strategy in the Decision Agent maximises recommendation quality while minimising turns to convergence?

---

## 2 Baseline

A **one-shot vector search**: the oracle's first message is embedded, the top-K most similar titles are returned as a flat ranked list, and no follow-up questions are asked. This is the simplest possible recommender on the same embedding space. Beating it is the minimum bar for the conversational loop to justify its cost.

---

## 3 Experimental conditions

All components are held fixed across conditions. What varies is the Decision Agent's **question-selection criterion** and the Cluster Agent's **refinement strategy**.

**Decision Agent question-selection criteria:**
| Condition | Selection rule |
|---|---|
| `baseline` | One-shot vector search (no questions asked). |
| `uncertainty` | Ask about the cluster axis where the two most confusable clusters have the smallest soft-score gap. |
| `boundary` | Ask about the title geometrically nearest the midpoint between the two highest-weighted cluster centroids in embedding space. |
| `popularity` | Among titles in the ambiguous pool (score gap < threshold), ask about the one with the highest vote count. |
| `random` | Sample uniformly from the ambiguous pool (control). |

**Cluster Agent refinement strategies:**
| Condition | Refinement method |
|---|---|
| `baseline` | No refinement; clusters are fixed after the initial embedding pass. |
| `single_retrieve` | On drift, run a fresh embedding pass on the full holdout catalogue and let the agent re-cluster from scratch. |
| `continuous_retrieve` | On drift, keep the same candidate pool but let the agent update cluster boundaries also considering new candidates. |

---

## 4 Ground-truth construction

Ground truths are built offline from a held-out partition of the catalogue that is never used during ingestion.

**Procedure:**
1. Sample N seed films from the holdout set using a fixed random seed.
2. Expand to ~40 films by computing cosine similarity from each seed embedding to the full holdout and taking the nearest neighbours.
3. Call an LLM to write a neutral, voice-agnostic taste description from the seed and expanded film lists.
4. Store the seed films, expanded film set, and description as a versioned ground-truth entry.

**Oracle access:** the oracle sees only the taste description. The target film set is held by the runner and used for objective metric computation after the session ends. This separation is enforced so the oracle cannot reverse-engineer the target from the films it is shown during the conversation.

---

## 5 Oracle

A simulated oracle is an LLM agent instantiated with a **ground truth** (taste description) overlaid with a **persona** (communication style). One oracle instance is created per session and must not be reused.

### Persona dials

| Dial | Type | Description |
|---|---|---|
| `verbosity` | `terse \| medium \| verbose` | Controls reply length via a system-prompt hint. |
| `decisiveness` | `float [0, 1]` | Controls the minimum turn at which the oracle is willing to accept. `1.0` → accepts from turn 1; `0.0` → waits until turn 10+. |
| `drift_probability` | `float [0, 1]` | Per-turn probability of injecting a tangent. |
| `contradiction_rate` | `float [0, 1]` | Per-turn probability of injecting a self-contradiction. |

### Behavioural reproducibility

All per-turn behavioural rolls are seeded and deterministic, keyed on a combination of persona, ground truth, and session seed. The same triple always produces the same sequence of conversational events, making behaviour reproducible across reruns even though the LLM output is stochastic.

### Acceptance gate

The acceptance gate is applied **after** the LLM expresses intent to accept. Low-decisiveness personas cannot accept before their minimum turn threshold regardless of how good the recommendation looks — the threshold is derived from the decisiveness dial.

### Oracle intents

Each oracle turn returns a message and one of three intents:
- `continue` — keep the session going.
- `accept` — the oracle is satisfied (subject to the acceptance gate).
- `abandon` — the oracle gives up.

---

## 6 Eval runner

The runner drives the full cross-product of ground truths, personas, and random seeds against the live system API. For each cell in the cross-product it runs a session, streams turn events, and after the session ends hands the transcript to the judge for scoring.

**Dry-run mode** enables fixture responses for the oracle and judge without suppressing real API calls to the system. This lets the harness be exercised end-to-end without incurring LLM costs.

---

## 7 Metrics

All metrics are persisted after each session. Aggregates (mean + 95% percentile bootstrap CI) are computed per run and exposed via admin endpoints.

### Objective metrics (computed from logs and ground truth)

| Metric | How measured |
|---|---|
| **Precision@K** | Fraction of top-K recommended films appearing in the ground-truth film set. Binary relevance. |
| **Recall@K** | Fraction of the ground-truth film set recovered in the top-K recommendation. |
| **NDCG@K** | Normalised Discounted Cumulative Gain at K. Binary relevance, logarithmic rank discount. |
| **Turns to convergence** | Turn number when convergence is declared; null if the session is abandoned before the turn limit. |
| **Avg cognitive load per turn** | Weighted combination of recommendation size and question length, averaged across all turns. |
| **Explicit acceptance rate** | Whether the oracle issued an accept intent vs. convergence declared behaviourally by the system. |
| **Drift events** | Count of drift events detected per session. |
| **Total cost** | Sum of token costs across all system LLM calls in the session. |

### LLM-judge scores (subjective, 1–5)

A separate judge reads the completed transcript, the converged cluster description, and the ground-truth taste description (not the persona traits). It scores three dimensions independently:

| Dimension | What is assessed |
|---|---|
| `clustering_coherence` | Are the named clusters internally consistent and meaningfully distinct throughout the session? |
| `question_quality` | Are the system's questions targeted, non-redundant, and binary? |
| `profile_fidelity` | Does the final recommendation match the ground-truth taste description? |

Each score is stored alongside the rendered judge prompt hash so multiple judge versions can coexist and all scoring variations are auditable.

---

## 8 Aggregation and reporting

After each run, all session metrics and judge scores are aggregated into a metric bundle — one point estimate with 95% percentile bootstrap CI per metric (2000 resamples, seeded for reproducibility). The same aggregation can be broken down by persona, enabling per-persona sensitivity analysis. Both views are exposed via admin-only endpoints.
