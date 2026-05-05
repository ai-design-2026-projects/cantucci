# Universal Project Scaffolding

*Components every project in this course must include.* 

---

## How to read this doc

Each of the 13 components below has the same structure:

- **What it is** — one-line definition.
- **Why it matters** — the pedagogical / scientific reason. This is what you're being graded on *understanding*.
- **Minimum acceptable** — bullet list of what a project must have. Missing any of these = fail the scaffolding check.
- **Nice to have** — what an A+ project adds on top.
- **Common failure mode** — the anti-pattern we see most often. Avoid.

---

## 1. End-to-end Architecture, Data Model, and API

Before writing code, you need a blueprint: what entities exist, what flows between them, and what the contract is at each boundary. Three artifacts together make up the architecture:

- **Conceptual model** — the entities (User, Document, Persona, Task, Judge, Run, etc.), their relationships, and what each one *is* in your system. Independent of code.
- **Data model** — for each entity, what attributes it carries, how it's stored/serialized, where it lives across the system, and how it flows between components.
- **Public API / interfaces** — the named contracts between modules (and with external callers or systems): inputs, outputs, error cases. These are the handoffs that ablation and multi-person work depend on.

**Why it matters.** Without an architecture, every design decision is made locally, in whichever file the student happens to be editing. Integration surprises appear in week 5. The architecture artifact is the shared mental model that makes the team's work composable, and it's what you point a reader to when they ask "how does this system *work*?" before diving into code. Note: this is distinct from (6) Foundations — architecture is the *conceptual* blueprint; Foundations is how that blueprint is realized as modules and directories.

**Minimum acceptable:**

- A one-page architecture diagram showing components, data flows, and external dependencies.
- An explicit conceptual / data model committed to the repo (e.g., `docs/data_model.md`): entities, their attributes, relationships.
- A table or doc listing public APIs (inter-module, and external-facing) with input/output types and who owns each.
- Architecture artifacts are versioned — when the design changes, the diagram and data model change with it, in the same commit.

**Nice to have:**

- Sequence diagrams for the headline flows (a typical end-to-end run).
- A "decisions log" (ADRs) capturing why the architecture is *this* and not the obvious alternative.
- Machine-readable schemas (pydantic / JSON Schema / OpenAPI) that generate both docs and runtime validators, keeping code and model in sync.

**Common failure mode.** Architecture exists only as a whiteboard photo from week 1; by week 6 the code has diverged and nobody can explain the system end-to-end. Or: data flows through a dozen ad-hoc dicts with no declared shape, so "what the agent actually sees" becomes a guess.

---

## 2. Agentic Harness

**What it is.** The core runtime wrapping LLM calls, tool use, state, and turn orchestration into a reusable abstraction.

**Why it matters.** Without a harness, every experimental condition becomes bespoke code. Experiments become non-comparable, reproducibility dies, and bugs hide in copy-paste.

**It will include, as a minimum:**

- `'call'` functions that can make single calls
- async version, and batch version
- Robustness to failures (with retry) 
- Model/version configurable, not hard-coded.
- Quasi-Deterministic behavior under a fixed seed + config (modulo unavoidable model non-determinism — which should be documented).
- Stateless pure function where possible; state passed explicitly.

**Nice to have:**

- Typed schemas for agent inputs/outputs (pydantic or equivalent).
- A "dry-run" mode that returns stub outputs without hitting the API (for testing).

**Common failure mode.** A 600-line notebook that "is" the harness — no abstractions, impossible to run under a different condition without editing cells.



---

## 3. Memory, Context, and Tools 

**What it is.** How the agent remembers, what it knows in the moment, and what it can act on. These are three distinct concerns:

- **Working memory** — the current conversation, scratchpad, or intermediate reasoning traces.
- **Persistent memory** — long-term stores the agent reads/writes across runs (vector stores, KBs, files).
- **Tools / affordances** — external calls the agent can make; and the *authorization* governing which tools are available when.

**Why it matters.** Conflating the three causes silent leakage across experimental conditions (condition A's memory carries into condition B) and makes tool-capability studies impossible. Clean separation is what lets you *ablate* each dimension.

**Consider the following:**

- Working memory is **per-run** and **reset between runs** unless explicitly shared.
- Any persistent memory has a versioned, reproducible initial state.
- Tool set available to the agent is declared in config, not hidden in code.
- A "which tools did the agent actually use?" log per run.

**Nice to have:**

- Context-window management strategy (truncation / summarization / RAG) is a named, swappable component.
- Tool authorization at a finer grain than binary (e.g., "read-only vs. read-write" on a KB).

**Common failure mode.** Global state / module-level caches leaking across runs, polluting control conditions. A 90%-accuracy result that was actually memory-leak.

---

## 4. Agentic Patterns (Orchestration Beyond Single-Agent)

Very few serious projects are "one agent, one call in a loop." Real systems compose multiple agent calls in structured ways: a planner that hands off to an executor, a council that debates, a judge that scores, a critic that rewrites. These are **patterns** — named design moves with known strengths, costs, and failure modes.

**Why it matters.** The pattern you choose is one of the biggest determinants of quality, cost, and latency — and it's a *design* decision, not a prompt decision. Naming the pattern makes it explicit, swappable, and studyable. If your project is essentially "we added an LLM judge and results improved," the judge *is* your contribution: treat it that way, not as incidental plumbing.

**Common patterns to know (non-exhaustive):**

- **Planner / Executor** — one agent decomposes a task into steps; another executes them. Often cheaper and more reliable than asking a single agent to do both.
- **Critic / Reviser / Reflection** — an agent produces a draft, another (or the same one with a different prompt) critiques it, the output is revised. Improves some tasks, degrades others — always measure.
- **LLM-as-Judge** — a separately-configured model scores or compares outputs. Core to automatic evaluation at scale; must be validated against human labels (see §10).
- **Council / Panel / Debate** — N agents with different personas or roles produce answers, then aggregate by vote, merge, or debate-to-consensus. High cost, sometimes high quality.
- **Router / Dispatcher** — a lightweight agent classifies the request and routes to a specialist. Cost-saving pattern.
- **Supervisor / Hierarchical** — a top-level agent delegates to subordinate agents and aggregates their results.
- **Map-Reduce / Fan-out-Aggregate** — the same prompt across N chunks in parallel, then a reducer combines. Standard for long-document tasks.

**Minimum acceptable:**

- The project names its top-level pattern(s) explicitly, and says *why* this pattern was chosen over obvious alternatives.
- Each pattern is implemented as a composition of the `Agent` harness (§2) — not hand-rolled per experimental condition.
- Inter-agent messages go through the same logging (§5) and prompt-versioning (§7) as single-agent calls.
- Role boundaries are clean: a judge doesn't also revise, a planner doesn't also execute — unless the fusion is itself the studied variable.

**Nice to have:**

- Ablation across patterns as an experimental condition (single agent vs. critic-loop vs. council).
- Cost/quality Pareto plots showing what each pattern buys you.
- A small "pattern library" subdirectory where each pattern is a testable, documented module composable from the harness.

**Common failure mode.** Multi-agent code where all agents share a global scratchpad, so "the council" is really one agent talking to itself through four prompts. Or: LLM-as-judge scored outputs produced *by the same model on the same prompt*, introducing circularity that inflates scores.

---

## 5. Logging & Observability

Structured, replayable records of every run: inputs, seeds, model/version, prompts (resolved with their variables filled in), intermediate outputs, final outputs, tool calls, timestamps, token counts, errors.

**Why it matters.** No logged run = no claim. This is the audit trail for your science. It's also what lets you re-analyze weeks later when a reviewer asks "what was the confidence interval on the style-scrubbed subset?".



- One structured record per run-step (JSONL or Parquet); one run = one file or one indexed batch.
- Every record includes: run_id, seed, config_hash, model_and_version, timestamp, step_type, inputs, outputs, errors.
- `replay.py` (or equivalent) re-executes a run from its log, or reproduces it deterministically given seed + model version.
- Logs are committed to version control (for small N) or tracked with hashes (for large N).

**Nice to have:**

- A log-viewer CLI that slices by condition, persona, date, error-state.
- Automatic diffing of prompts across runs.
- Cost per run computed from token counts and logged.

**Common failure mode.** `print()`-based logs scattered across notebooks. Impossible to replay. Impossible to audit. Results become unverifiable.

---

## 6. Foundations: API, Modularization, Code Organization

Clean module boundaries. Named, typed interfaces between components. 

**Why it matters.** Lets you build over solid foundations. Enable multi person (multi agent) and multi version project. Manages complexity

**Minimum acceptable:**

- Project has a declared module structure (`src/`, `scripts/`, `notebooks/`, etc.) with clear responsibilities per directory.
- Components communicate through named interfaces (function signatures, protocol classes, or typed dicts) — not shared globals.
- Each experimental condition is a config file, not a forked script.
- Interactions happen through APIs.

**Nice to have:**

- Proper typing (pydantic / dataclasses / mypy).
- Pluggable implementations via a registry pattern.
- Separation of "library" code (importable, testable) from "script" code (runnable entry points).



---

## 7. Prompts as First-Class, Versioned Artifacts

Prompts live in their own named files under `prompts/`, not embedded in f-strings. They are imported by name, parameterized by variables, and versioned.

**Why it matters.** Prompts are the single biggest source of experimental variance in LLM projects. If they're embedded strings you can't diff them, review them, or report exactly what you ran. This is the single cheapest improvement to reproducibility you can make.

**Minimum acceptable:**

- `prompts/` directory with one file per named prompt.
- Prompts use explicit variable substitution (e.g., `{persona_description}`).
- The prompt file-hash is recorded in every run log (so "which prompt was used" is auditable).
- Changes to prompts are git commits, not in-place edits.

## 8. Resilience & Error Handling

Graceful handling of LLM-call failures: rate-limits, timeouts, malformed JSON, refusals, context-window overflows, API outages.

**Why it matters.** Without resilience, long experiments silently truncate. You think you ran N=200; you actually got N=137 because the API rate-limited you halfway through and your script silently continued. Your CIs are wrong.

**Minimum acceptable:**

- Retry with exponential backoff on transient failures.
- Clear distinction between transient errors (retry) and permanent errors (fail loudly).
- Structured failure logging: which step failed, why, with what inputs.
- A post-run integrity check: did every intended run complete, or are there holes? Report to the user.
- Statistical assertions and expectations

**Nice to have:**

- Parsing layer that validates LLM output against a schema, re-prompts on failure.
- Graceful degradation paths (fall back to simpler model if rate-limited on the expensive one, with the fallback logged).
- Dead-letter queue for permanently-failed runs so they can be inspected.

**Common failure mode.** `try: except: pass` around the LLM call. Experiment "succeeds" with silently-missing data. CI reports what the surviving data says, not what you intended to measure.

---

## 9. Cost & Rate-Limit Management

Token accounting per run, per-experiment budget, cost estimation before execution, alarm on overrun.

**Minimum acceptable:**

- Every run logs token counts (input/output separately).
- Per-experiment total cost is computable from logs.
- Before running a main experiment, the team produces a cost estimate (trivial back-of-envelope is fine).
- A hard stop / guard in the orchestration script that aborts if total cost exceeds a declared budget.

**Nice to have:**

- Live cost tracking during long runs.
- Cost-per-data-point reported alongside accuracy, so scaling trade-offs are visible.
- Cached responses for deterministic sub-steps to save money.

---

## 10. Quality — What It Means and How We Measure It

Before you can study whether something improves a system, you need a *definition of "better."* Quality in LLM systems is multi-dimensional and task-dependent; treating it as a single scalar ("accuracy") is the most common experimental-design error in the field.

**Why it matters.** Every claim in your report is of the form "X improved quality on Y." If "quality" isn't defined, the claim is unfalsifiable. If it's defined post-hoc (after looking at results), the study is circular. Pre-committing to *what quality is* and *how it is measured* is what separates a study from a demo — and it is the direct input to the Behavior Study (§13).

**Dimensions of quality to consider (pick what's relevant, not all):**

- **Correctness / task success** — did the system produce the right answer? Binary or graded.
- **Faithfulness / grounding** — are the output's claims supported by provided sources? (Hallucination's opposite.)
- **Coherence / fluency** — is the output well-formed and readable?
- **Safety / refusal behavior** — does the system avoid harmful outputs; and does it *over-refuse* legitimate requests?
- **Helpfulness / user-facing utility** — does the output advance the user's actual goal?
- **Robustness** — does quality hold under paraphrases, adversarial inputs, noisy context, distribution shift?
- **Efficiency** — cost, latency, token count per successful output.
- **Calibration** — when the system says it's confident, is it actually right more often?

**Measurement strategies:**

- **Rule-based / deterministic** — exact-match, regex, schema-validation. Cheap, unambiguous, narrow.
- **Programmatic graders** — code that checks a property (compiles, passes tests, sums to target).
- **LLM-as-judge** — another model scores or pairs outputs. Cheap at scale but introduces judge-bias; must be validated against human labels on a subset (see also §4 Agentic Patterns).
- **Human evaluation** — gold standard for subjective dimensions; expensive; requires rater training and inter-rater reliability reporting.
- **User / proxy-user metrics** — behavioral signals from real or simulated users (task completion, follow-up rate, satisfaction).

**Minimum acceptable:**

- A written **quality spec** committed *before* the main experiment runs: which dimensions matter for this project, how each is operationalized, which is the *primary* outcome.
- Every metric reported in the paper comes with a measurement method documented in that spec.
- If LLM-as-judge is used, it is validated against a human-labeled subset; inter-rater (or judge-vs-human) agreement is reported.
- Confidence intervals on every quantitative quality claim (bootstrap or equivalent).
- Any change to the quality spec after the experiment has started is tracked and flagged as exploratory, not confirmatory.

**Nice to have:**

- Multi-dimensional quality reported as a table or radar chart, not collapsed to a single scalar.
- Cost-per-unit-of-quality (quality Pareto) alongside raw quality.
- A "quality under distribution shift" analysis explicitly testing robustness.
- Independent re-annotation of a subset by a second rater / second judge to quantify measurement noise.

**Common failure mode.** "We measured accuracy." Accuracy of what? How graded? By whom? On which split? With what CI? The one-word-metric project. Also: redefining the metric after seeing the results so the story is cleaner — garden-of-forking-paths dressed up as a primary analysis.

---

## 11. READMEs, Onboarding, and Build-on-Top

Enough documentation that another team member, a future student, or an LLM can pick up the repo and reproduce a result, or extend the system.

**Why it matters.** If you can't hand your project to the next student (or to yourself in 3 months), it's not reproducible, and it wasn't science.

**Minimum acceptable:**

- `README.md` at the repo root with: project description, setup instructions, how to run the headline experiment, where logs go, where the pre-registration is.
- `README.md` in each major subdirectory explaining what's in it.
- A single command (or documented 3-step sequence) that reproduces the MVB end-to-end on a toy example.
- An `AGENTS.md` or `CLAUDE.md` describing the project to an LLM: architecture, conventions, how to extend. (Even if you're not using an LLM, this doc benefits humans.)

**Nice to have:**

- Example notebooks showing how to load logs and run custom analyses.
- A "contribution guide" for future extenders.
- Recorded walkthrough video.

---

## 12. Fast Sanity Checks / Smoke Tests

**What it is.** A 30-second end-to-end pipeline check distinct from the full experimental run.

**Why it matters.** Your main experiment takes 6 hours. You won't run it per commit. Without a fast smoke test, bugs sit in the pipeline for days before being found — usually on day 30 when you're trying to finalize results.

**Minimum acceptable:**

- `scripts/smoke_test.sh` (or equivalent) runs the full pipeline on a 1-example toy dataset in < 1 minute.
- CI integration is nice but not required; manual invocation at least.
- Smoke test actually exercises the critical path (extractor → runtime → logger → analysis).

**Nice to have:**

- Golden-output comparison: smoke test's output is compared against a known-good baseline; regressions flagged.
- A `pytest` suite for unit-level behavior of pure functions.
- Pre-commit hook that runs the smoke test.

**Common failure mode.** No smoke test. Pipeline breaks silently. Student discovers on the morning of the deadline.

---

## 13. Behavior Study & Report

The actual scientific artifact: the report, figures, and analysis that answers the headline hypothesis and documents what was learned.

**Why it matters.** Everything else exists to enable *this*. A beautifully-engineered harness with no report is a failed project. A clean report with shaky scaffolding is also a failed project. Both must be present.

**Minimum acceptable:**

- Written report (8–15 pages) with: intro, related work, methods, experimental design, results with CIs, discussion, limitations, ethics, references.
- All figures and tables in the report are regenerated by committed analysis scripts from committed logs.
- Results include the pre-registered primary analysis **first**, any secondary analyses clearly marked as such.
- Explicit "what we can and cannot conclude" section.

**Nice to have:**

- Sensitivity analyses (results under alternative choices).
- Comparisons against explicit baselines.
- A "negative results" subsection honestly documenting what didn't work.
- Public-facing summary (blog post, video).

**Common failure mode.** Report cites results that analysis scripts don't reproduce. Post-hoc analyses presented as pre-registered. Figures without CIs. "Cherry picked" without admitting it.

---

## Cross-references and relationships

- (1) Architecture sets the blueprint that (2) Harness, (3) Memory/Tools, (4) Patterns, and (6) Foundations implement; when any of them diverges from it, fix the one that's wrong.
- (5) Logging, (7) Prompts-as-artifacts, (8) Resilience, (9) Cost, and (10) Quality all feed into (13) Behavior Study — they're the audit trail and the definition of "better" that make the report trustworthy.
- (2) Harness + (4) Agentic Patterns + (6) Modularization + (3) Memory-separation are what make experiments comparable across conditions.
- (4) Agentic Patterns without (10) Quality is a demo: you can't claim a council "works" if quality is undefined.
- (11) READMEs + (12) Smoke tests are what keep the project alive past week 1.

If you cut corners, cut them in this priority order (least-damaging first):

1. Nice-to-haves in Observability (dashboarding, fancy viewers).
2. Nice-to-haves in Onboarding (example notebooks beyond the README).
3. Unit tests beyond the smoke test.

**Never cut:**

- Logging minimum-acceptable.
- Prompt versioning.
- Resilience on the critical path.
- Pre-registration of the primary analysis.
- Seed control.

These are non-negotiable because they're what distinguishes science from demo.

---

## Grading hook

At proposal time, the team declares which of the 13 components they'll go beyond "minimum acceptable" on. This is where build-heavy teams allocate their engineering budget. Minimum-build teams commit to "minimum acceptable across all 13" and invest the freed time in experimental depth.

The grader's first pass: *does the project meet minimum-acceptable on all 13?* If not, scaffolding fails and feedback is methodology-focused. If yes, content grading begins.