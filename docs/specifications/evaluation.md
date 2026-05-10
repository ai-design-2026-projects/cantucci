# Evaluation Strategy

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

---

#### Condition A — Uncertainty-driven

**Selection rule:** Select the title with the smallest gap between its top-two cluster soft-assignment scores. If a title scores 0.48 on cluster X and 0.45 on cluster Y, the system is nearly indifferent — that title is asked about first.

**Hypothesis:** Targeting the most uncertain title maximises expected information gain per question. The oracle's answer resolves the largest possible mass of ambiguous assignments in one reply, leading to faster convergence.

---

#### Condition B — Random (control)

**Selection rule:** Select uniformly at random from the *ambiguous pool* — all titles where the gap between the top-two cluster scores is below a fixed threshold (configurable, default `0.2`).

**Hypothesis:** Random selection within the ambiguous pool is the performance floor. A targeted strategy that cannot beat random is not worth its added complexity. This condition isolates the value of the *selection criterion* from the value of *restricting questions to ambiguous titles* at all.

---

#### Condition C — Boundary-driven

**Selection rule:** Select the title geometrically nearest to the midpoint between the two highest-weighted cluster centroids in embedding space, regardless of its soft-assignment scores.

**Hypothesis:** The LLM's soft scores may be poorly calibrated early in a session, before sufficient oracle feedback has been incorporated. Geometric proximity to the cluster boundary in embedding space is a model-free signal that may identify more informative titles than score-based uncertainty, especially in the first 2–3 turns.

---

#### Condition D — Popularity-first

**Selection rule:** Among the ambiguous pool (same threshold as Condition B), select the title with the highest `vote_count`.

**Operationally:** filter candidates to `score_rank1 − score_rank2 < 0.2`; within that pool, rank by `vote_count` descending; ask about the title at rank 1.

**Hypothesis:** Asking about a well-known title anchors the oracle in shared cultural knowledge. A popular film is more likely to elicit a confident, unambiguous response than an obscure one — improving the *quality* of the oracle signal even if the question does not maximise information gain in an information-theoretic sense. The trade-off being tested is reliability of response vs. theoretical information value.

---

## 4 Metrics

| Metric | How measured | Type |
|---|---|---|
| **Turns to convergence** | Count of oracle turns from session start to convergence signal (explicit or behavioural); capped at `session.max_turns` | Primary |
| **Cognitive load per turn** | Sum of: titles shown (weight 1 each) + clusters shown (weight 1 each) + question complexity (1 = binary, 2 = open); logged per turn, averaged across the session | Primary |
| **Oracle satisfaction rate** | Fraction of sessions where convergence is declared before the turn budget is exhausted | Primary |
| **Drift detection rate** | In simulated sessions with injected contradictions, fraction of contradictions correctly surfaced by `f_next_state` before being silently overridden | Secondary |
| **LLM-judge scores** | Clustering coherence, question quality, preference profile fidelity — each 1–5, averaged across sessions per condition (see §7.7) | Secondary |
| **Silhouette score** | How well each title fits its assigned cluster versus the next closest one (−1 = wrong cluster, +1 = clearly correct); tracked per turn to monitor whether cluster assignments are geometrically coherent, not used to drive decisions | Diagnostic |

All quantitative claims carry **95% bootstrap confidence intervals**. Point estimates alone are not acceptable. Conditions are compared using paired tests where the same oracle persona appears in multiple conditions; unpaired otherwise.

---

## 5 Oracle types

**LLM-simulated oracles** provide the scale needed for ablation. Each simulated oracle receives a persona, a preference specification, and a cognitive-load budget (see §3.4). Conditions A–D are each run over N ≥ 20 sessions per condition using the same set of 20 distinct personas, giving within-persona comparisons and sufficient power to detect a 1-turn difference at 80%.

**Human oracles** provide ground truth. A within-subject study (N ≥ 5, randomised condition order, scripted opening prompt, consented recording) runs each participant through at least two conditions. The key validation question is whether the relative ordering of conditions by turns-to-convergence agrees between LLM and human oracles. If they disagree, the human results are the authoritative finding and the LLM simulation is reported as approximate with its known biases stated.

---

## 6 LLM-as-Judge for automated benchmarking

Scaling the evaluation across 80+ sessions (4 conditions × 20 personas) requires automated scoring. A dedicated **LLM-as-Judge** scores completed session transcripts on three dimensions that cannot be computed from logs alone:

| Dimension | What is assessed | Scale |
|---|---|---|
| **Clustering coherence** | Are the named clusters internally consistent and meaningfully distinct from each other throughout the session? | 1–5 |
| **Question quality** | Are the system's questions targeted, binary, and non-redundant? | 1–5 |
| **Preference profile fidelity** | Does the `f_assess` output accurately reflect the oracle's stated and inferred rules? | 1–5 |

The judge returns a structured JSON response with one score and a one-sentence rationale per dimension. It operates entirely outside the conversational loop — it reads transcripts, scores them, and has no influence on any session.

**Validation gate.** Before use, the judge is calibrated against 30–50 session transcripts hand-labelled independently by both authors. Inter-rater agreement between the human annotators is computed first. The judge is then compared against the human consensus. A dimension is cleared for automated scoring only if the judge reaches κ ≥ 0.6 against the human consensus. Dimensions below threshold are reported as "not auto-benchmarkable" and scored manually.

**Scope.** The judge does not replace deterministic metrics (turns to convergence, cognitive load, oracle satisfaction) — those are read directly from logs. It does not replace the pairwise probe or the human study. It is strictly an efficiency tool for scaling the ablation scoring.

---

## 8 Null result policy

A result where conversational refinement does not outperform the one-shot baseline is a valid, reportable finding — not a failure to be buried. If the primary claim does not hold, the report will state this directly, discuss plausible explanations (e.g., the oracle's first query is already specific enough that retrieval saturates quality), and present it as a contribution to understanding the limits of conversational clustering. Negative results are reported with the same confidence intervals and the same level of detail as positive ones.
