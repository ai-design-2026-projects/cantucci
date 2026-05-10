# Evaluation Strategy

---

## 1 Research questions

1. **Primary** — Does conversational refinement converge to an oracle-accepted recommendation faster (fewer turns, lower cognitive load per turn) than a one-shot vector search baseline?
2. **Secondary** — Which interaction strategy at each turn maximises information gain per unit of cognitive load: uncertainty-driven questioning, boundary-driven questioning, random, or popularity-first?

---

## 2 Baseline

The comparison is a **one-shot vector search**: the oracle's first message is embedded, the top-K most similar titles from the candidate pool are returned as a flat ranked list, and no follow-up questions are asked. The oracle rates the list as satisfying or not. This is the simplest possible recommender on the same embedding space — it tests whether the conversational loop adds value beyond what retrieval alone provides.

---

## 3 Experimental conditions

The central question is whether *how* the system selects its next question affects convergence speed and oracle satisfaction. All four conditions share the same conversational loop; only the routing logic inside `f_next_best_step` changes — specifically, the rule used to pick which title to ask about when the router decides to ask.

**Fixed across all conditions:**
- Retrieval: sentence-transformer + pgvector cosine similarity, top-K candidates
- LLM clustering model and prompt template
- State update logic (`f_next_state`), including drift detection
- Convergence detection (`f_assess`) and turn budget
- Cognitive-load budget: ≤ 5 titles shown per turn, 1 binary question per turn
- Show vs. ask vs. stop routing logic (only the *which title* selection changes)

**What varies:** the criterion used by `f_next_best_step` to select the title to ask about when it has decided to ask.

We are considering four types of selection criteria:

- **Uncertainty-driven:** Select the title with the smallest gap between its top-two cluster soft-assignment scores. If a title scores 0.48 on cluster X and 0.45 on cluster Y, the system is nearly indifferent — that title is asked about first. *Hypothesis:* Targeting the most uncertain title maximises expected information gain per question. The oracle's answer resolves the largest possible mass of ambiguous assignments in one reply, leading to faster convergence.

- **Random (control):** Select uniformly at random from the *ambiguous pool* — all titles where the gap between the top-two cluster scores is below a fixed threshold (configurable, default `0.2`). *Hypothesis:* Random selection within the ambiguous pool is the performance floor. A targeted strategy that cannot beat random is not worth its added complexity. This condition isolates the value of the *selection criterion* from the value of *restricting questions to ambiguous titles* at all.

- **Boundary-driven:** Select the title geometrically nearest to the midpoint between the two highest-weighted cluster centroids in embedding space, regardless of its soft-assignment scores. *Hypothesis:* The LLM's soft scores may be poorly calibrated early in a session, before sufficient oracle feedback has been incorporated. Geometric proximity to the cluster boundary in embedding space is a model-free signal that may identify more informative titles than score-based uncertainty, especially in the first 2–3 turns.

- **Popularity-first:** Among the ambiguous pool (same threshold as the random condition), select the title with the highest `vote_count`. Filter candidates to `score_rank1 − score_rank2 < 0.2`; within that pool, rank by `vote_count` descending; ask about the title at rank 1. *Hypothesis:* Asking about a well-known title anchors the oracle in shared cultural knowledge. A popular film is more likely to elicit a confident, unambiguous response than an obscure one — improving the *quality* of the oracle signal even if the question does not maximise information gain in an information-theoretic sense. The trade-off being tested is reliability of response vs. theoretical information value.

---

## 4 Component-level evaluation

Each `f_*` function is tested independently before the full conversational loop is evaluated. The goal is to isolate failures: a bad session could stem from poor retrieval, misclustered assignments, a bad routing decision, or a broken state update. Without component-level checks, these causes are conflated. All component tests run on a fixed held-out slice of the catalogue and a set of 10 scripted oracle transcripts; they are re-run after any prompt change.

### 4.1 `f_output` — Initial soft clustering

**What it does:** Produces initial soft clustering of candidates into 3–6 named groups.

**Test method:** Structural validation + LLM-judge coherence score.

**Input:** Fixed 50-title candidate pool, 5 seed queries.

**What is checked:**
- Cluster count in [3, 6]
- Every title has a valid soft-assignment vector summing to 1
- Cluster names are non-empty and distinct

**Primary metrics:**
- Structural pass rate (must = 100%)
- LLM-judge coherence score ≥ 3/5 on held-out sample

### 4.2 `f_uncertainty` — Assignment ambiguity scoring

**What it does:** Scores each title by assignment ambiguity.

**Test method:** Unit test against synthetic assignments.

**Input:** Hand-crafted soft-assignment vectors with known uncertainty ordering.

**What is checked:** Rank ordering of output scores matches ground truth ordering.

**Primary metric:** Spearman ρ between predicted and ground-truth uncertainty rank.

### 4.3 `f_next_best_step` — Turn routing and title selection

**What it does:** Routes each turn to show / ask / stop and selects the title to ask about.

**Test method:** Condition ablation (§3); per-turn action log.

**Input:** Session state snapshots extracted from replayed transcripts.

**What is checked:**
- Fraction of turns where action taken matches the condition's selection rule
- Cognitive-load constraint respected (≤ 5 titles shown)

**Primary metrics:**
- Action-rule compliance rate
- Mean cognitive load per turn

### 4.4 `f_next_state` — State update and drift detection

**What it does:** Updates session state from oracle reply; detects preference drift.

**Test method:** Injection test: scripted transcripts with known contradictions.

**Input:** 20 transcripts, each containing 1–2 planted contradictions.

**What is checked:** Fraction of contradictions surfaced before silent override.

**Primary metrics:**
- Drift detection rate (target ≥ 0.80)
- False-positive rate on non-contradictory turns

### 4.5 `f_assess` — Convergence declaration and preference profiling

**What it does:** Declares convergence; produces preference profile.

**Test method:** Calibration against human-labelled transcripts.

**Input:** 30–50 transcripts hand-labelled for convergence turn and preference rules.

**What is checked:**
- Whether declared convergence turn matches human label
- Whether extracted preference profile contains the oracle's explicit rules

**Primary metrics:**
- Turn-level convergence agreement (Cohen's κ)
- Preference-rule recall on explicit oracle statements

---

**Engineering notes.** Each component is tested with a minimal stub harness that bypasses the full pipeline: `f_next_state` can be called with a frozen session snapshot and a synthetic oracle reply without needing a live LLM session. This is the "dry-run mode" from the agentic harness spec. All component test runs are logged under `run_type = component_test` with the same structured logger used in full sessions.

---

## 5 Oracle satisfaction and cluster acceptance

### 5.1 Why this is hard

Evaluating whether a cluster satisfies the oracle's desires is the central unsolved problem in conversational clustering. There is no external ground truth: the oracle *is* the objective function. Using a database-derived proxy (e.g., TMDB genre labels) as a stand-in for oracle preference systematically fails because oracle preferences are frequently cross-genre, mood-based, or director-driven in ways that genre taxonomies do not capture. This is well-documented in the CRS literature: static ground-truth approaches over-emphasise catalogue structure and under-emphasise the subjective, emergent nature of user preferences (Jannach et al., 2022; Wang et al., 2023).

The question is not "does the cluster match the catalogue's label for this oracle?" but "does the cluster match what the oracle actually wants, given that the oracle may not have known what they wanted before the conversation started?" These are fundamentally different questions, and only the second one is meaningful.

### 5.2 Evaluation approaches

We track a portfolio of approaches as complementary signals rather than picking one. Each has known strengths and failure modes; no single approach is authoritative in isolation.

**Approach 1 — Explicit acceptance (primary behavioral signal).** The oracle signals satisfaction explicitly (*"perfect"*, *"yes, that's it"*) or behaviorally (no corrective feedback for 2 consecutive turns). This is the cleanest, most direct signal available and is always the first criterion checked. It requires no proxy and no judge: the oracle's own behavior is the measurement. Weakness: it conflates genuine satisfaction with fatigue or giving up, particularly in long sessions. Behavioral convergence is therefore supplemented by the signals below, not replaced by them.

**Approach 2 — Pairwise probe (behavioral, no ground truth needed).** After convergence, the system (or the judge) samples pairs of titles from the final accepted cluster and asks the oracle: *"Do these two belong together, given what you told me you wanted?"* A high must-link agreement rate indicates that the cluster is internally coherent from the oracle's perspective; a high cannot-link rate on pairs straddling different output clusters indicates that the system's boundaries match the oracle's intuitions. This approach is grounded in the semi-supervised clustering literature (Wagstaff et al., 2001; Kim & Ghosh, 2017; Wang et al., 2022) and treats the oracle as a noisy pairwise comparator rather than a label source. For simulated oracles, pairwise probes are answered programmatically from the persona's hidden preference spec. For human oracles, a small sample of 10–15 pairs is presented post-session as a structured questionnaire. **Primary metric:** must-link agreement rate on 15 sampled within-cluster pairs; cannot-link agreement rate on 10 sampled across-cluster pairs (cluster boundary pairs from the final state).

**Approach 3 — Preference profile fidelity (after convergence).** When `f_assess` produces a preference profile at session end, that profile is checked against what the oracle explicitly stated during the session. This is not pure self-reference: the check is between the *profile* (produced by `f_assess` from the oracle's feedback log) and the *oracle's actual utterances* (the ground truth within the session). An LLM judge scores how completely and accurately the profile captures explicit rules, inferred preferences, and declared exceptions. For simulated oracles, the profile is also compared against the hidden persona spec. **Primary metric:** LLM-judge preference-rule recall score (1–5); for simulated oracles, rule coverage rate against hidden spec.

**Approach 4 — Hidden-spec overlap for simulated oracles (weak external signal).** In simulated sessions, each oracle persona has a structured preference specification (genres, director styles, exclusions, exceptions) written before the session. After convergence, the titles in the accepted cluster are scored against this spec: for each title, a binary signal indicates whether it satisfies the spec's positive criteria and avoids the negative ones. This is a *weak* external signal because the spec is not oracle-driven and the mapping from spec to title is imperfect (a title may satisfy a spec it was not tagged for in the catalogue). It is reported as a secondary diagnostic alongside Approaches 1–3, not as a primary outcome. **Primary metric:** spec-satisfaction rate of titles in the converged cluster (fraction of titles that satisfy all positive and no negative criteria from the hidden spec).

**Summary table:**

| Approach | Oracle type | Ground truth needed | Primary metric | Role |
|---|---|---|---|---|
| Explicit acceptance | Human + simulated | None | Oracle satisfaction rate | Primary behavioral |
| Pairwise probe | Human + simulated | None (oracle is comparator) | Must/cannot-link agreement | Primary outcome |
| Preference profile fidelity | Human + simulated | Oracle utterances | LLM-judge recall score | Primary outcome |
| Hidden-spec overlap | Simulated only | Hidden persona spec | Spec-satisfaction rate | Secondary / diagnostic |

### 5.3 Position in the literature

The standard evaluation paradigm for CRS — hide a target item, check if the system recommends it — is known to be poorly suited to subjective, preference-driven tasks. Wang et al. (2023) demonstrate that this protocol penalises systems that ask good clarifying questions rather than guessing early, which is exactly the behavior we want to encourage. Jannach et al. (2022) note that offline CRS evaluation systematically discards the interactive dimension that makes these systems useful. The pairwise probe approach used here is closest in spirit to COBRAS (Brus et al., 2018) and ABCDE (Ainslie et al., 2024), both of which evaluate clustering quality through oracle-answered same-cluster questions rather than against a fixed label set. The preference profile fidelity approach is closest to the iEvaLM framework (Wang et al., 2023), which proposes LLM-based user simulators and explainability evaluation as replacements for item-matching metrics.

---

## 6 Retrieval system evaluation

The retrieval system (sentence-transformer embedding + pgvector cosine search) is a non-LLM component; its evaluation is deterministic and offline. It runs once against a fixed benchmark before any live session and is re-run if the embedding model or index configuration changes.

**Test set construction.** A hand-labeled query set of 30 queries is constructed, each paired with a list of relevant titles identified by one of the authors (not the same person who prompted the queries). Queries span a range of specificity: broad mood queries (*"something tense and psychological"*), attribute queries (*"Fincher films"*, *"Italian neorealism"*), and negative queries (*"good thriller but not violent"*). Relevance is binary: a title is relevant if an author would recommend it given the query, regardless of its position in the result list.

**Metrics:**

| Metric | How measured | Target |
|---|---|---|
| **Recall@K** (K = 10, 20, 50) | Fraction of hand-labeled relevant titles appearing in the top-K returned results | Recall@20 ≥ 0.70 on the hand-labeled set |
| **MRR** (Mean Reciprocal Rank) | 1 / rank of the first relevant title, averaged across queries | Reported for reference; no hard target |
| **Search latency (p95)** | Wall-clock time from query embedding to ranked list returned, over 100 repeated queries at the same catalogue size | < 200 ms (matches the NFR in the system spec) |

**Hard-negative sanity check.** For 10 of the 30 queries, a deliberately wrong title is identified (a title a reasonable person would not recommend given the query). The check verifies that no hard-negative title appears in the top-5 for its query. Failure here indicates an embedding or indexing problem that would corrupt the session before any LLM call is made.

**What is not evaluated here.** The retrieval system does not filter by oracle preferences — that is `f_output`'s job. The evaluation above tests only the embedding model's ability to retrieve thematically relevant titles from an unconstrained query. Filter correctness (year, genre, runtime) is tested in `f_output`'s component test (§4).

---

## 7 System-level metrics

These metrics are computed over full sessions, across all conditions, after the component and retrieval checks pass.

| Metric | How measured | Type |
|---|---|---|
| **Turns to convergence** | Count of oracle turns from session start to convergence signal (explicit or behavioural); capped at `session.max_turns` | Primary |
| **Cognitive load per turn** | Sum of: titles shown (weight 1 each) + clusters shown (weight 1 each) + question complexity (1 = binary, 2 = open); logged per turn, averaged across the session | Primary |
| **Oracle satisfaction rate** | Fraction of sessions where convergence is declared before the turn budget is exhausted | Primary |
| **Drift detection rate** | In simulated sessions with injected contradictions, fraction of contradictions correctly surfaced by `f_next_state` before being silently overridden | Secondary |
| **LLM-judge scores** | Clustering coherence, question quality, preference profile fidelity — each 1–5, averaged across sessions per condition (see §8) | Secondary |
| **Silhouette score** | How well each title fits its assigned cluster versus the next closest one (−1 = wrong cluster, +1 = clearly correct); tracked per turn to monitor whether cluster assignments are geometrically coherent | Diagnostic only |

All quantitative claims carry **95% bootstrap confidence intervals**. Point estimates alone are not acceptable. Conditions are compared using paired tests where the same oracle persona appears in multiple conditions; unpaired otherwise.

---

## 8 Oracle types

**LLM-simulated oracles** provide the scale needed for ablation. Each simulated oracle receives a persona, a preference specification, and a cognitive-load budget. Conditions A–D are each run over N ≥ 20 sessions per condition using the same set of 20 distinct personas, giving within-persona comparisons and sufficient power to detect a 1-turn difference at 80%.

**Human oracles** provide ground truth. A within-subject study (N ≥ 5, randomised condition order, scripted opening prompt, consented recording) runs each participant through at least two conditions. The key validation question is whether the relative ordering of conditions by turns-to-convergence agrees between LLM and human oracles. If they disagree, the human results are the authoritative finding and the LLM simulation is reported as approximate with its known biases stated.

---

## 9 Database schema for experiment reproducibility

This section specifies the invariants that the experiment database must satisfy to support coherent replay, condition isolation, and audit. Column-level schema is left to the data model document (`docs/data_model.md`); only the logical structure and the reproducibility guarantees are specified here.

**Entities required:**

- **`personas`** — one row per simulated oracle persona. Stores the full preference specification, cognitive-load budget, and the random seed used to instantiate the persona. A persona row is write-once: it is created before the experiment run and never modified. If a persona needs to change, a new row is created with a new ID.

- **`sessions`** — one row per conversation. Linked to exactly one persona (or `null` for human sessions) and exactly one experimental condition. Stores the session seed, the YAML config snapshot used for that session (serialised), and a status field (`running`, `converged`, `abandoned`, `budget_exhausted`). The config snapshot is what makes the session replayable: given the same seed and config, the same transcript is reproduced.

- **`turns`** — one row per oracle turn within a session. Stores the full oracle utterance, the system's response, the action taken (`show` / `ask` / `stop`), the cognitive-load score for that turn, and a foreign key to the session. Turn rows are immutable once written.

- **`cluster_snapshots`** — one row per turn, storing the full soft-assignment matrix as JSON. This is what makes clustering state replayable without re-running the LLM: any turn's clustering state can be reconstructed from its snapshot.

- **`oracle_feedback`** — one row per feedback event within a turn. Stores the feedback type (`global`, `cluster`, `point`, `instructional`, `resolve_drift`), the target entity, and the content. Linked to its parent turn.

- **`runs`** — one row per full experimental run (one invocation of the evaluation harness across all conditions and personas). Stores the git commit hash, the harness version, the start/end time, and a `completed` flag. All sessions created in a run reference their parent run ID.

**Isolation invariants:**

- No session shares working memory with any other session. All state for a session is reconstructible from its rows in `sessions`, `turns`, `cluster_snapshots`, and `oracle_feedback` alone — no in-memory caches, no module-level state.
- Condition assignment is stored on the `sessions` row and never inferred from code. Ablating a condition means filtering by `condition_id`; it does not require any code change.
- The persona spec stored in `personas` is the spec that was *actually used*, not the template. If the template changes between runs, old sessions are still replayable from their stored spec.
- Every LLM call is logged with its prompt hash, model version, and token counts. A session can be re-scored (e.g., with a new LLM judge) without re-running the conversation, because the full turn history is persisted.

**Replay guarantee.** Given a `session_id`, the command `python replay.py --session <id>` must reproduce the full transcript deterministically from the stored seed, config snapshot, and turn history, without any live LLM calls. This is the single cheapest check of experiment integrity.

---

## 10 LLM-as-Judge for automated benchmarking

A dedicated **LLM-as-Judge** scores completed session transcripts on three dimensions that cannot be computed from logs alone:

| Dimension | What is assessed | Scale |
|---|---|---|
| **Clustering coherence** | Are the named clusters internally consistent and meaningfully distinct from each other throughout the session? | 1–5 |
| **Question quality** | Are the system's questions targeted, binary, and non-redundant? | 1–5 |
| **Preference profile fidelity** | Does the `f_assess` output accurately reflect the oracle's stated and inferred rules? | 1–5 |

The judge returns a structured JSON response with one score and a one-sentence rationale per dimension. It operates entirely outside the conversational loop — it reads transcripts, scores them, and has no influence on any session.

**Validation gate.** Before use, the judge is calibrated against 30–50 session transcripts hand-labelled independently by both authors. Inter-rater agreement between the human annotators is computed first. The judge is then compared against the human consensus. A dimension is cleared for automated scoring only if the judge reaches κ ≥ 0.6 against the human consensus. Dimensions below threshold are reported as "not auto-benchmarkable" and scored manually.

**Scope.** The judge does not replace deterministic metrics (turns to convergence, cognitive load, oracle satisfaction) — those are read directly from logs. It does not replace the pairwise probe or the human study. It is strictly an efficiency tool for scaling the ablation scoring.

---

## 11 Null result policy

A result where conversational refinement does not outperform the one-shot baseline is a valid, reportable finding — not a failure to be buried. If the primary claim does not hold, the report will state this directly, discuss plausible explanations (e.g., the oracle's first query is already specific enough that retrieval saturates quality), and present it as a contribution to understanding the limits of conversational clustering. Negative results are reported with the same confidence intervals and the same level of detail as positive ones.

---

## References

Ainslie et al. (2024). *ABCDE: Application-Based Cluster Diff Evals.* arXiv:2407.21430.

Brus et al. (2018). *COBRAS: Fast, Iterative, Active Clustering with Pairwise Constraints.* arXiv:1803.11060.

Jannach, D. et al. (2022). *Evaluating conversational recommender systems.* Artificial Intelligence Review. Springer.

Kim, T. & Ghosh, J. (2017). *Semi-Supervised Active Clustering with Weak Oracles.* arXiv:1709.03202.

Lajewska, W. et al. (2025). *On the Reliability of User-Centric Evaluation of Conversational Recommender Systems.* arXiv:2602.17264.

Lajewska, W. et al. (2025). *Limitations of Current Evaluation Practices for Conversational Recommender Systems and the Potential of User Simulation.* SIGIR-AP 2025. arXiv:2510.05624.

Wagstaff, K. et al. (2001). *Constrained K-means Clustering with Background Knowledge.* ICML 2001.

Wang, Y. et al. (2022). *Oracle-guided Contrastive Clustering.* arXiv:2211.00409.

Wang, Y. et al. (2023). *Rethinking the Evaluation for Conversational Recommendation in the Era of Large Language Models (iEvaLM).* arXiv:2305.13112.