# LLM Usage & Design

This document consolidates all LLM-related design decisions, constraints, and requirements across the conversational clustering system. It is organized by agent/function, with a system-level section covering shared rules and requirements.

---

## System-Level Rules

### Prompts as Versioned Files

**Principle:** Prompts are first-class artifacts, not embedded strings.

- All prompts live in a `prompts/` directory with one file per named prompt.
- Prompts use explicit variable substitution (e.g., `{persona_description}`, `{oracle_feedback_log}`).
- The prompt file-hash is recorded in every run log so "which prompt was used" is auditable.
- Changes to prompts are git commits; never in-place edits without version tracking.

**Why:** Prompts are the single biggest source of experimental variance in LLM projects. Without versioning and audit trails, reproducibility dies. This is the cheapest improvement to scientific rigor you can make.

---

### LLM Harness

**Principle:** Reusable abstraction for all LLM calls; no bespoke code per condition.

- A unified harness (`llm_harness.py`) wraps all LLM calls with:
  - **`call()`** — single synchronous call
  - **`async_call()`** — async variant
  - **`batch_call()`** — batch processing
  - Retry with exponential backoff on transient failures (rate-limit, timeout, API outage); max 3 attempts
  - Model + version configurable via config (never hard-coded)
  - Seeded for quasi-deterministic behavior under fixed seed + config
  - Stateless where possible; state passed explicitly
- Retry logic distinguishes transient (retry) from permanent (fail loudly) errors
- Schema-aware parsing that validates LLM output against declared types (pydantic / JSON Schema)
- Re-prompting on parse failure up to a fixed limit before logging and raising

**Why:** Without a harness, every condition becomes a variant script. Experiments become non-comparable, bugs hide in copy-paste, and reproducibility becomes impossible.

---

### Structured Logging & Observability

**Principle:** Every run is fully replayable and auditable from logs.

**Per-run log structure (JSONL or Parquet):**
- `run_id` — unique session identifier
- `turn_number` — sequential turn within a session
- `seed` — random seed for reproducibility
- `config_hash` — hash of the config used
- `model_and_version` — e.g., "claude-3-sonnet-20250514"
- `step_type` — e.g., "f_output", "f_uncertainty", "f_next_best_step", etc.
- `timestamp` — when the step executed
- `prompt_hash` — hash of the resolved prompt (variables filled in)
- `inputs` — full input to the LLM call
- `outputs` — full output from the LLM (raw text or parsed JSON)
- `tokens_in` — input tokens consumed
- `tokens_out` — output tokens generated
- `cost` — compute cost of the call (derived from tokens + model pricing)
- `errors` — if any, what went wrong and why

**Replay capability:**
- A `replay.py` script re-executes a session from its log, or reproduces it deterministically given seed + model version + config
- Log files are committed to version control (for small N) or tracked with hashes (for large N)

**Why:** No logged run = no claim. This is the audit trail for science. It also enables deep post-hoc analysis, debugging, and validation.

---

### Resilience & Error Handling

**Principle:** Fail loudly on permanent errors; retry on transient ones; never swallow errors silently.

**Transient errors (retry with exponential backoff):**
- Rate-limit (HTTP 429)
- Timeout
- Temporary API unavailability
- Transient connection issues

Retry up to 3 times with exponential backoff. If all retries fail, **raise** — do not silently return stale data.

**Permanent errors (fail loudly):**
- Malformed JSON in LLM response that cannot be repaired by re-prompting
- Schema validation failure after max re-prompt attempts
- Invalid inputs that the caller constructed wrong
- Refusal or safety filter triggers (unless explicitly handled by the prompt)

When a permanent error occurs, log the full context (inputs, outputs, validation failure reason) and raise with a descriptive message.

**Common failure mode to avoid:**
- Bare `except: pass` or `except Exception: pass` around any meaningful LLM operation
- Silently returning None / empty list / previous turn's data without raising
- Continuing with cached/stale state when fresh data failed to fetch

**Post-run integrity check:**
Every run must produce a check that reports:
- Total turns initiated vs. turns completed (holes are a red flag)
- Total LLM calls made vs. intended
- Any errors encountered during the run, with context
- If N < intended due to failures, the analysis must note this, not silently proceed with smaller N

---

### Cost Tracking & Hard-Stop Guards

**Principle:** Every run is tracked for cost; experiments have budgets that are enforced.

**Per-run cost accounting:**
- Every LLM call logs `tokens_in`, `tokens_out`, and `cost` separately
- Per-experiment total cost is computable from logs
- Before running a main experiment, produce a cost estimate (back-of-envelope is fine)
- A hard stop / guard in orchestration aborts if total cost exceeds a declared budget (configurable per session in YAML as `session.cost_limit_usd`)
- Live cost tracking during long-running experiments; alarm on overrun

**Why:** LLM experiments can bleed money silently if not tracked. A budget guard prevents surprises and makes scaling decisions explicit.

---

### Model Version & Configuration

- Model and version are never hard-coded in function bodies
- They are specified in config files (YAML) with a version number
- All calls log the model/version used
- Changing the model/version requires a config change and is tracked as a distinct experimental condition

**Why:** Reproducibility requires knowing exactly which model was used. Silent upgrades of Claude or other models corrupt comparisons across experiments.

---

### Validation Against Human Labels (for LLM-as-Judge)

**Principle:** LLM-as-Judge outputs must be validated before use in headline claims.

- Any claim that relies on LLM-as-Judge scoring must be preceded by a validation gate
- Validation gate: hand-label 30–50 session transcripts independently by both authors
- Compute inter-rater agreement (e.g., Cohen's κ) between human annotators first
- Compare judge outputs against the human consensus
- A scoring dimension is cleared for automated use only if judge reaches **κ ≥ 0.6** against human consensus
- Dimensions below threshold are reported as "not auto-benchmarkable" and scored manually
- Judge-vs-human agreement is reported in the final findings (not just passed/failed internally)

---

## `f_output` — Best-Guess Clustering

### Role

Return the system's best-guess recommendation at any point: a soft clustering of the candidate pool into 3–6 named groups with short descriptions and ranked recommendations from the top cluster.

### What it does

On the first oracle message:
1. Embed the oracle's query using a sentence-transformer (`all-MiniLM-L6-v2` by default)
2. Retrieve the top-K most relevant movies by cosine similarity against pre-computed embeddings stored in pgvector (K ≈ 50–200)
3. Prompt the LLM to cluster those candidates into 3–6 named groups with soft assignments
4. Return the clusters with names, descriptions, and the top titles from the best cluster

On subsequent turns:
1. Apply oracle feedback constraints (**accept, reject, split, merge**) to the clustering prompt
2. Re-cluster the candidate pool with the updated constraints injected
3. Generate or update cluster names and descriptions (see below)
4. Return updated clusters and top titles

### Cluster Naming & Stability

**Design choice:** Names must be stable across turns to avoid cognitive thrashing, yet accurate to reflect material changes.

**Implementation:**
- The LLM clustering prompt includes the **previous turn's cluster name** as a starting point
- The prompt instructs the LLM to keep the name unless the cluster's titles have changed significantly
- A good name is short (2–4 words), descriptive of tone and genre rather than just genre alone
- If the oracle has used a phrase like *"slow-burn stuff"* to describe a cluster, that phrasing is a stronger candidate for the name than a generic LLM-generated label
- Both the name and description are stored scoped to the turn (columns on the `clusters` table); past state is fully auditable by `session_id` and `turn_number`

### Soft Assignments & Confidence Scoring

**Design choice:** Every title receives a soft assignment (distribution over clusters), not a hard label.

**Implementation:**
- The LLM produces a structured JSON response assigning each title a confidence score per cluster
- Scores sum to 1.0 across all clusters for a given title
- Scores are stored as a `float` in the `cluster_assignments` table per (cluster, title) pair
- Titles with a dominant score (e.g., 0.8+) in one cluster are safe recommendations
- Titles with roughly equal scores across two clusters (e.g., 0.45, 0.45, 0.10) are **boundary cases**—genuinely ambiguous and the most informative ones to ask about next

**Validation:** At session end, soft-assignment calibration is checked: boundary-flagged titles should be ones the oracle also finds ambiguous on a pairwise check. If the system flags titles as uncertain that the oracle finds obvious, scoring calibration needs revision.

### Hierarchy: Two-Level, Lazy Expansion

**Design choice:** Coarse clusters are shown on turn 1; fine clusters are generated only when the oracle asks to drill in.

**Implementation:**
- Turn 1 produces 3–6 coarse clusters (e.g., *"Psychological thriller"*, *"Action"*, *"Drama"*)
- When the oracle asks to drill into or expand a cluster, the LLM is prompted to sub-divide that cluster into 2–3 fine-level groups (e.g., *"Psychological thriller"* → *"Slow-burn / art-house"* vs. *"Mainstream / crowd-pleaser"*)
- Fine clusters reference their parent via `parent_cluster_id` in the `clusters` table
- This avoids overwhelming the oracle upfront while keeping the space navigable

### Edge Case: Title Not in Catalogue

If the oracle names a title the system cannot find in the catalogue (which stops at July 2017):
1. Acknowledge the gap
2. Return the 3 most similar titles by cosine distance as alternatives
3. Note the cutoff date in the response

### Edge Case: Broad Queries (Entire Catalogue)

If the oracle's query embedding produces uniformly high similarity scores across all genres (candidate pool is effectively the entire catalogue):
1. Detect this by comparing the query vector to the global catalogue diversity
2. Return a targeted clarifying question instead of a cluster display
3. Example: *"What kind of mood are you in — something intense, something light, or something in between?"*

---

## `f_uncertainty` — Boundary Detection & Scoring

### Role

Identify and score the ambiguity in the current clustering. Used by `f_next_best_step` to decide which title to ask about.

### What it does

1. Inspect the soft-assignment scores for all titles in the candidate pool
2. Identify boundary titles: those with small gaps between their top-two cluster scores (configurable threshold; default 0.2)
3. Rank boundary titles by uncertainty (smallest gap = most uncertain)
4. Optionally apply experimental selection criteria (see §4 of Evaluation for ablation conditions)
5. Return a ranked list of the most ambiguous/informative titles to ask about next

### Selection Criteria (Experimental Variation)

The project tests four different criteria for selecting which boundary title to ask about:

- **Uncertainty-driven (Condition A):** Select the title with the smallest gap between its top-two cluster scores
- **Random (Condition B, control):** Select uniformly at random from titles where `gap < threshold`
- **Boundary-driven (Condition C):** Select the title geometrically nearest to the midpoint between the two highest-weighted cluster centroids in embedding space
- **Popularity-first (Condition D):** Among the ambiguous pool, select the title with the highest `vote_count`

Each condition is a different implementation of the selection logic; they all use the same uncertainty detection upstream.

### Drift Detection & Surfacing

**Design choice:** Before silently overriding earlier feedback, surface the conflict explicitly.

When `f_next_state` detects a contradiction (oracle feedback contradicts earlier `oracle_feedback` log entries), `f_uncertainty` is called to surface it:

> *"Earlier you said no horror — does The Babadook work as an exception, or should I drop that rule entirely?"*

This gives the oracle three natural paths:
- **Exception** — the old rule stays, but this one title is allowed
- **Rule update** — the old rule is replaced; the new preference is now in scope
- **Reaffirm** — the oracle confirms the old rule and rejects the new title

The resolution is logged as a new `oracle_feedback` row with `feedback_type = 'resolve_drift'`, maintaining the full preference history.

---

## `f_next_best_step` — Router Agent

### Role

Decide what to do next: show a set of titles, ask a targeted question, or stop the session.

### Dispatch Logic

The router receives the current session state (clusters, soft assignments, oracle feedback log) and returns one of three actions:

1. **Show** — Display top titles from the current best cluster
   - High cognitive load (5+ titles, 1 cluster)
   - High information yield if oracle reacts
   - Chosen when uncertainty is low (most titles have clear assignments)

2. **Ask** — Pose a targeted binary question about a boundary title or proposed split/merge
   - Low cognitive load (0 new titles, 1 binary question)
   - High precision (oracle's answer directly resolves ambiguity)
   - Chosen when uncertainty is high (many titles near cluster boundaries)

3. **Stop** — Declare convergence (see `f_assess` for convergence conditions)
   - Stops accepting oracle turns
   - Triggers `f_assess` to produce preference profile

### Cognitive-Load Budget

Every turn has a cost. The router enforces a strict per-turn budget:

| Signal | Per-turn target |
|---|---|
| Titles shown | ≤ 5 |
| Clusters shown | ≤ 6 |
| Question complexity | 1 binary yes/no (not open-ended or multi-part) |

**Example:** Showing 8 titles in one turn is actively discouraged even if uncertainty is low, because it exceeds the titles budget. A strategy that converges in 6 turns at 8 titles per turn is worse than one that takes 8 turns at 4 titles per turn — cognitive load is a first-class evaluation metric, not a footnote.

### Edge Case: Very Broad First Query

If the oracle's first query is extremely broad (e.g., *"a good movie"*), the candidate pool would be the entire catalogue. Detection logic:
- If the query embedding produces uniformly high similarity across all genres, flag as underconstrained
- Return a targeted clarifying question instead of a cluster display
- Example: *"What kind of mood are you in — something intense, something light, or something in between?"*

### Edge Case: Empty Candidate Pool After Filters

If active filters (year, genre, runtime, rating) eliminate all candidates:
1. Relax filters one at a time in order of least impact: rating threshold → year range → runtime
2. Continue until at least 20 candidates are available
3. Notify the oracle of the relaxation

---

## `f_next_state` — State Update & Drift Handling

### Role

Fold oracle feedback into session state: update cluster assignments, detect contradictions, and prepare the next turn's clustering.

### What it does

On each oracle turn:
1. Parse the oracle's message (natural language)
2. Extract feedback at all four levels:
   - **Global** (*"too many groups"*, *"too mainstream"*)
   - **Cluster-level** (*"split this"*, *"merge A and B"*)
   - **Point-level** (*"Parasite is perfect"*, *"no Transformers"*)
   - **Instructional** (*"treat Nolan and Villeneuve as equivalent"*, *"ignore pre-2000"*)
3. Log the feedback in the `oracle_feedback` table with metadata: `feedback_level`, `feedback_type`, `target_id`, `content`
4. **Detect drift:** Compare the new feedback against the full `oracle_feedback` log
   - If a contradiction is found, surface it before updating state (see `f_uncertainty`)
   - Wait for oracle resolution (exception / rule update / reaffirm)
   - Log the resolution as `feedback_type = 'resolve_drift'`
5. Apply constraints to the next clustering prompt: all feedback (accept, reject, split, merge, instructional rules) becomes hard constraints
6. Update `updated_at` on the `sessions` table

### Design Choice: Latest Intent Wins

**Rule:** If the oracle said *"no horror"* in turn 2 and then reacts positively to a horror title in turn 5, the turn-5 signal overrides the turn-2 rule.

**Rationale:** People change their minds as they see more options. Treating this as error is wrong; treating it as preference evolution is correct.

**But:** Silently applying the new intent erodes trust. So before overriding, surface the drift explicitly and wait for clarification.

### Edge Case: Oracle Requests Title Type Excluded by Filter

If the oracle asks for a title type excluded by an active filter (short film, documentary):
1. Notify the oracle that the filter excludes that type
2. Offer to relax the filter with a single confirm
3. If confirmed, store the relaxation as an instructional feedback row

---

## `f_assess` — Convergence & Preference Profile

### Role

Determine whether the session has converged and, if so, codify the oracle's preferences into a structured, reusable profile.

### Convergence Conditions

The session ends when *any one* of these fires first:

1. **Explicit acceptance** — The oracle says something that clearly signals satisfaction
   - Examples: *"perfect"*, *"yes, that's it"*, *"show me the full list"*
   - This is the cleanest signal and always takes priority
   - No ambiguity; immediate convergence

2. **Behavioural convergence** — No corrective feedback for 2 consecutive turns
   - The oracle is only confirming or making minor tweaks
   - The clustering has stabilised even if not explicitly accepted
   - Configurable parameter: `session.convergence_turns` (default 2)
   - Signals user satisfaction via inaction, not explicit statement

3. **Turn budget exhausted** — Hard cap configured per session in YAML (`session.max_turns`, default 15)
   - Bounds cost and prevents endless drift
   - When reached, present the current best cluster as final result
   - Notify the oracle that the turn budget is exhausted
   - Trigger `f_assess` to produce preference profile even without explicit convergence

When convergence is declared:
1. Set `sessions.status` to `converged`
2. Run preference-profile extraction (see below)
3. Stop accepting oracle turns
4. Store the profile in `sessions.preference_profile` as JSONB

### Preference Profile Extraction

**Input:** The full `oracle_feedback` log for the session (all feedback entries from turn 1 to final turn)

**Process:** Prompt the LLM with the log and ask it to extract:
1. Explicit rules stated by the oracle (*"no gore"*, *"director = Nolan"*)
2. Inferred preferences from accepted titles (*"these films have slow pacing in common"*)
3. Exceptions (*"The Silence of the Lambs is OK even though it has gore"*)
4. Rejected clusters or title types

**Output format:**
```json
{
  "genres": ["Thriller", "Drama"],
  "director_style": ["slow-burn", "psychological"],
  "exclude": ["gore", "pre-2000", "mainstream action"],
  "cast_preferences": ["understated acting", "ensemble casts"],
  "exceptions": ["The Silence of the Lambs"],
  "metadata": {
    "confidence": "high",
    "turns_to_convergence": 6,
    "oracle_satisfaction": "explicit"
  }
}
```

**Reusability:** The profile can be applied to new datasets or used to bootstrap a future session without replaying the conversation.

**Validation:** Per scaffolding requirements, profile fidelity is validated against human-labelled transcripts on a held-out sample (κ ≥ 0.6) before use in headline claims.

### Edge Case: Turn Budget Exhausted

When `session.max_turns` is reached:
1. Present the current best clustering as the final result
2. Notify the oracle that the turn budget is exhausted
3. Trigger `f_assess` to produce the preference profile even without explicit convergence
4. No further oracle turns are accepted

---

## Oracle Simulation (LLM-as-Oracle)

### Why Simulate?

Running a real human study for every experiment — across different questioning strategies, different personas, different configurations — is far too slow and expensive. **LLM-simulated oracles enable scale.**

Setting up a simulated oracle allows the team to:
- Run hundreds of sessions under controlled conditions
- Systematically ablate variables (e.g., routing strategy, question selection criterion)
- Get statistically meaningful results with confidence intervals
- Validate findings against a small human study (N ≥ 5–10)

### Oracle Persona & Specification

Each simulated oracle receives:
1. **Persona description** — e.g., *"You are a film enthusiast who loves slow-burn psychological thrillers with strong female leads, dislikes gore and jumpscares, has a soft spot for indie films from the 1990s"*
2. **Preference specification** — a structured JSON with:
   - Preferred genres, directors, actors, keywords
   - Explicit exclusions
   - Exceptions or edge cases
   - Optional implicit ground truth (for calibration)
3. **Cognitive-load constraints** — maximum titles to evaluate per turn, tolerance for open-ended questions

### Oracle Behavior

The LLM-as-oracle is prompted to:
- Behave like a real user with the specified tastes and attention span
- Interact through the same API as a human would (chat interface)
- Provide feedback at all four levels (global, cluster, point, instructional) when natural
- Change mind or refine preferences as they see more options (preference evolution)
- Reject poorly-targeted questions or irrelevant titles
- Accept or converge when satisfied

**Seeding:** Each oracle session is seeded so the oracle's responses are deterministic given the seed + model version + prompt hash. This enables replay and cross-session comparison.

### Validation Against Human Oracles

**Critical gate:** Before trusting any quantitative claim based on LLM-simulated oracles, validate against human oracles.

- **Sample size:** N ≥ 5–10 within-subject (each human evaluates 2+ conditions)
- **Randomization:** Condition order is randomized per participant
- **Measurement:** Same metrics as simulated oracles (turns to convergence, cognitive load, satisfaction)
- **Comparison:** Do the relative rankings of conditions (e.g., "Condition A is faster than Condition B") agree between LLM and human oracles?
- **Reporting:** Report whether the agreement holds. If they disagree, human results are authoritative; LLM simulation is reported as approximate with biases noted.

---

## LLM-as-Judge for Automated Evaluation

### Role

Score completed session transcripts on dimensions that cannot be computed from logs alone. Used to scale evaluation across many sessions without manual annotation.

### Dimensions Scored

| Dimension | What is assessed | Scale |
|---|---|---|
| **Clustering coherence** | Are the named clusters internally consistent and meaningfully distinct throughout the session? | 1–5 |
| **Question quality** | Are the system's questions targeted, binary, and non-redundant? | 1–5 |
| **Preference profile fidelity** | Does the `f_assess` output accurately reflect the oracle's stated and inferred rules? | 1–5 |

### Judge Input & Output

**Input:**
- Full session transcript (all turns: oracle message + system response)
- Cluster assignments and names at each turn
- Extracted preference profile (output of `f_assess`)
- Oracle feedback log

**Output:**
```json
{
  "clustering_coherence": 4,
  "clustering_coherence_rationale": "Clusters remained stable and distinct across turns; one merge was justified by oracle feedback.",
  "question_quality": 5,
  "question_quality_rationale": "All questions were binary and targeted boundary cases; no redundancy across turns.",
  "profile_fidelity": 3,
  "profile_fidelity_rationale": "Profile captured major preferences but missed oracle's secondary interest in indie films.",
  "overall_score": 4.0
}
```

### Validation Gate (Critical)

**Principle:** Judge outputs must be validated against human labels before use in headline claims.

**Process:**
1. Hand-label 30–50 session transcripts independently by both authors using the same 1–5 scale + rationale
2. Compute inter-rater agreement (Cohen's κ) between the human annotators
3. Compute judge vs. human consensus agreement
4. A dimension is cleared for automated scoring **only if judge reaches κ ≥ 0.6** against human consensus
5. Dimensions below κ 0.6 are reported as "not auto-benchmarkable" and scored manually

**Reporting:**
- The final paper reports judge-vs-human agreement for all three dimensions (not just pass/fail internally)
- Any claim relying on judge scores includes the agreement coefficient and explicit caveats about judge bias

### Judge Operation

- The judge operates entirely **outside the conversational loop** — it reads transcripts, scores them, has no influence on session state
- Judge is a separately-configured model (not necessarily the same as the clustering model)
- Judge configuration (model, version, prompt) is logged like any other LLM call

### Judge Does NOT Replace

- Deterministic metrics (turns to convergence, cognitive load) — read directly from logs
- Pairwise validation (oracle's ambiguity on sampled pairs)
- Human studies — if LLM and human oracles disagree, human findings are authoritative

---

## Configuration & Experimental Conditions

### Config Structure

Each experiment is a config file (YAML), not a forked script. Configs specify:

```yaml
session:
  max_turns: 15
  convergence_turns: 2
  cost_limit_usd: 10.0

retrieval:
  top_k: 100
  embedding_model: "all-MiniLM-L6-v2"

representation:
  strategy: "sentence-transformer"  # swappable

clustering:
  num_clusters_min: 3
  num_clusters_max: 6

routing:
  strategy: "uncertainty-driven"  # or "random", "boundary-driven", "popularity-first"
  uncertainty_threshold: 0.2

model:
  name: "claude-3-5-sonnet-20241022"
  temperature: 0.7
  max_tokens: 2048

oracle:
  type: "simulated"  # or "human"
  persona: "..."
  preference_spec: {...}

logging:
  format: "jsonl"
  path: "logs/"
```

### Reproducibility

**Invariant:** Same seed + config → same session transcript (modulo unavoidable model non-determinism, which is documented).

---

## Summary: Design Principles

1. **Prompts are versioned files**, not f-strings — diff-able, reviewable, auditable
2. **All LLM calls go through the harness** — consistent retry, logging, schema validation
3. **Logging is structured and complete** — every run is replayable
4. **Fail loudly; never swallow errors** — silent failures corrupt science
5. **Cost is tracked and budgeted** — no runaway experiments
6. **Judge outputs are validated against human labels** — no circular scoring
7. **Soft assignments, not hard labels** — uncertainty is explicit and scored
8. **Latest intent wins, but drift is surfaced** — preference evolution is real and user trust matters
9. **Hierarchy is lazy** — coarse clusters shown first; fine clusters on request
10. **Cognitive load is budgeted from turn one** — not discovered at study time