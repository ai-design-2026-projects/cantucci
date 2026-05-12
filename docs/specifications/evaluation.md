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

The central question is whether *how* the system selects its next question affects convergence speed and oracle satisfaction. In order to evaluate different approaches to question selection.

**Fixed across all experiments:**
- Retrieval: sentence-transformer + pgvector cosine similarity, top-K candidates
- LLM clustering model and prompt template
- State update logic in the Orchestrator, including drift detection
- Cognitive-load budget: ≤ 5 titles shown per turn, 1 binary question per turn

**What varies:** the criterion used by the Decision Agent and the Resolver Agent to select what to ask about each turn and when to stop. The cluster assignment and ambiguity scoring logic is the same across all conditions; only the selection rule changes.

We are considering four types of selection criteria:

- **Uncertainty-driven:** Select the question based on title with the smallest gap between its top-two cluster soft-assignment scores. If a title scores 0.48 on cluster X and 0.45 on cluster Y, the system is nearly indifferent — that cluster assignment is maximally uncertain and therefore most likely to yield informative feedback.

- **Random (control):** Select uniformly at random from the *ambiguous pool* — all titles where the gap between the top-two cluster scores is below a fixed threshold (configurable, default `0.2`). *Hypothesis:* Random selection within the ambiguous pool is the performance floor. A targeted strategy that cannot beat random is not worth its added complexity. This condition isolates the value of the *selection criterion* from the value of *restricting questions to ambiguous titles* at all.

- **Boundary-driven:** Select the title geometrically nearest to the midpoint between the two highest-weighted cluster centroids in embedding space, regardless of its soft-assignment scores. *Hypothesis:* The LLM's soft scores may be poorly calibrated early in a session, before sufficient oracle feedback has been incorporated. Geometric proximity to the cluster boundary in embedding space is a model-free signal that may identify more informative titles than score-based uncertainty, especially in the first 2–3 turns.

- **Popularity-first:** Among the ambiguous pool (same threshold as the random condition), select the title with the highest `vote_count`. Filter candidates to `score_rank1 − score_rank2 < 0.2`; within that pool, rank by `vote_count` descending; ask about the title at rank 1. *Hypothesis:* Asking about a well-known title anchors the oracle in shared cultural knowledge. A popular film is more likely to elicit a confident, unambiguous response than an obscure one — improving the *quality* of the oracle signal even if the question does not maximise information gain in an information-theoretic sense. The trade-off being tested is reliability of response vs. theoretical information value.

---

## 4 Component-level evaluation

Each agent/component is tested independently before the full conversational loop is evaluated. The goal is to isolate failures: a bad session could stem from poor retrieval, misclustered assignments, a bad routing decision, or a broken state update. Without component-level checks, these causes are conflated. All component tests run on a fixed held-out slice of the catalogue and a set of 10 scripted oracle transcripts; they are re-run after any prompt change.

### 4.1 Cluster Agent — Initial soft clustering

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

### 4.2 Decision Agent — Assignment ambiguity scoring

**What it does:** Scores each title by assignment ambiguity.

**Test method:** Unit test against synthetic assignments.

**Input:** Hand-crafted soft-assignment vectors with known uncertainty ordering.

**What is checked:** Rank ordering of output scores matches ground truth ordering.

**Primary metric:** Spearman ρ between predicted and ground-truth uncertainty rank.

### 4.3 Decision Agent — Turn routing and title selection

**What it does:** Routes each turn to show / ask / stop and selects the title to ask about.

**Test method:** Condition ablation (§3); per-turn action log.

**Input:** Session state snapshots extracted from replayed transcripts.

**What is checked:**
- Fraction of turns where action taken matches the condition's selection rule
- Cognitive-load constraint respected (≤ 5 titles shown)

**Primary metrics:**
- Action-rule compliance rate
- Mean cognitive load per turn

### 4.4 Orchestrator — State update and drift detection

**What it does:** Updates session state from oracle reply; detects preference drift.

**Test method:** Injection test: scripted transcripts with known contradictions.

**Input:** 20 transcripts, each containing 1–2 planted contradictions.

**What is checked:** Fraction of contradictions surfaced before silent override.

**Primary metrics:**
- Drift detection rate (target ≥ 0.80)
- False-positive rate on non-contradictory turns

### 4.5 Session Assessor — Convergence declaration and preference profiling

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

**Engineering notes.** Each component is tested with a minimal stub harness that bypasses the full pipeline: the Orchestrator can be called with a frozen session snapshot and a synthetic oracle reply without needing a live LLM session. This is the "dry-run mode" from the agentic harness spec. All component test runs are logged under `run_type = component_test` with the same structured logger used in full sessions.

---

## 5 Oracle satisfaction and cluster acceptance

### 5.1 Why this is hard

Evaluating whether a cluster satisfies the oracle's desires is the central unsolved problem in conversational clustering. There is no external ground truth: the oracle *is* the objective function. Using a database-derived proxy (e.g., TMDB genre labels) as a stand-in for oracle preference systematically fails because oracle preferences are frequently cross-genre, mood-based, or director-driven in ways that genre taxonomies do not capture. This is well-documented in the CRS literature: static ground-truth approaches over-emphasise catalogue structure and under-emphasise the subjective, emergent nature of user preferences 

The question is not "does the cluster match the catalogue's label for this oracle?" but "does the cluster match what the oracle actually wants, given that the oracle may not have known what they wanted before the conversation started?" These are fundamentally different questions, and only the second one is meaningful.

### 5.2 Evaluation approaches

We track a portfolio of approaches as complementary signals rather than picking one. Each has known strengths and failure modes; no single approach is authoritative in isolation.

**Approach 1 — Explicit acceptance (primary behavioral signal).** The oracle signals satisfaction explicitly (*"perfect"*, *"yes, that's it"*) or behaviorally (no corrective feedback for 2 consecutive turns).

**Approach 2 — Pairwise probe (behavioral, no ground truth needed).** After convergence, the system (or the judge) samples pairs of titles from the final accepted cluster and asks the oracle: *"Do these two belong together, given what you told me you wanted?"* 

**Approach 4 — Hidden-spec overlap for simulated oracles (weak external signal).** In simulated sessions, each oracle persona has a structured preference specification (genres, director styles, exclusions, exceptions) written before the session. After convergence, the titles in the accepted cluster are scored against this spec: for each title, a binary signal indicates whether it satisfies the spec's positive criteria and avoids the negative ones. **Primary metric:** spec-satisfaction rate of titles in the converged cluster (fraction of titles that satisfy all positive and no negative criteria from the hidden spec).

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

---

## 7 System-level metrics

These metrics are computed over full sessions, across all conditions, after the component and retrieval checks pass.

| Metric | How measured | Type |
|---|---|---|
| **Turns to convergence** | Count of oracle turns from session start to convergence signal (explicit or behavioural); capped at `session.max_turns` | Primary |
| **Cognitive load per turn** | Sum of: titles shown (weight 1 each) + clusters shown (weight 1 each) + question complexity (1 = binary, 2 = open); logged per turn, averaged across the session | Primary |
| **Oracle satisfaction rate** | Fraction of sessions where convergence is declared before the turn budget is exhausted | Primary |
| **Drift detection rate** | In simulated sessions with injected contradictions, fraction of contradictions correctly surfaced by the Orchestrator before being silently overridden | Secondary |
| **LLM-judge scores** | Clustering coherence, question quality, preference profile fidelity — each 1–5, averaged across sessions per condition (see §8) | Secondary |
| **Silhouette score** | How well each title fits its assigned cluster versus the next closest one (−1 = wrong cluster, +1 = clearly correct); tracked per turn to monitor whether cluster assignments are geometrically coherent | Diagnostic only |

All quantitative claims carry **95% bootstrap confidence intervals**. Point estimates alone are not acceptable. Conditions are compared using paired tests where the same oracle persona appears in multiple conditions; unpaired otherwise.

---

## 8 Oracle types

**LLM-simulated oracles** provide the scale needed for ablation. Each simulated oracle receives a persona, a preference specification, and a cognitive-load budget. Conditions A–D are each run over N ≥ 20 sessions per condition using the same set of 20 distinct personas, giving within-persona comparisons and sufficient power to detect a 1-turn difference at 80%.

**Human oracles** provide ground truth. A within-subject study (N ≥ 5, randomised condition order, scripted opening prompt, consented recording) runs each participant through at least two conditions. The key validation question is whether the relative ordering of conditions by turns-to-convergence agrees between LLM and human oracles. If they disagree, the human results are the authoritative finding and the LLM simulation is reported as approximate with its known biases stated.

---

## 10 LLM-as-Judge for automated benchmarking

A dedicated **LLM-as-Judge** scores completed session transcripts on three dimensions that cannot be computed from logs alone:

| Dimension | What is assessed | Scale |
|---|---|---|
| **Clustering coherence** | Are the named clusters internally consistent and meaningfully distinct from each other throughout the session? | 1–5 |
| **Question quality** | Are the system's questions targeted, binary, and non-redundant? | 1–5 |
| **Preference profile fidelity** | Does the session-end preference profile accurately reflect the oracle's stated and inferred rules? | 1–5 |

The judge returns a structured JSON response with one score and a one-sentence rationale per dimension. It operates entirely outside the conversational loop — it reads transcripts, scores them, and has no influence on any session.

**Validation gate.** Before use, the judge is calibrated against 30–50 session transcripts hand-labelled independently by both authors. Inter-rater agreement between the human annotators is computed first. The judge is then compared against the human consensus. A dimension is cleared for automated scoring only if the judge reaches κ ≥ 0.6 against the human consensus. Dimensions below threshold are reported as "not auto-benchmarkable" and scored manually.

**Scope.** The judge does not replace deterministic metrics (turns to convergence, cognitive load, oracle satisfaction) — those are read directly from logs. It does not replace the pairwise probe or the human study. It is strictly an efficiency tool for scaling the ablation scoring.

---