# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**Conversational Clustering** — an AI system that clusters a dataset by *conversing* with a human (the **oracle**) who is the sole judge of quality. There is no intrinsic ground truth; the oracle's acceptance *is* the objective function.

Course project for "Designing Large Scale AI Systems" (Prof. Fabio Casati). Authors: Davide Donà, Andrea Blushi. Declared profile: **build-heavy** (see `docs/requirements/deliverables.md` §2) — the system is the contribution, so engineering quality, UI, and robustness carry more weight than a long related-work survey.

**Current status:** Directory structure and documentation scaffolding complete. `src/`, `scripts/`, `notebooks/`, `prompts/`, `configs/`, and `logs/` directories initialized. No executable code yet; when code is added, respect the scaffolding requirements below — they are graded as a first pass before any content evaluation.

## Canonical docs — read before designing


### Always read — source of truth
These contain implementation details and are consulted when designing or implementing specific components:

- `docs/specifications/data_model.md` — database schema, data types, session / turn / feedback entities, reproducibility invariants.
- `docs/specifications/api.md` — system interfaces: input/output contracts for `f_*` functions, session harness API, LLM call signatures.
- `docs/specifications/architecture_diagram.md` — system block diagram and component relationships.


### Reference — read on demand
These files define the project requirements and evaluation strategy. When a user request conflicts with them, surface the conflict before changing them.

- `docs/requirements/conversational_clustering.md` — project brief: MVB, `f_*` function decomposition, oracle feedback levels, evaluation strategy.
- `docs/requirements/deliverables.md` — what ships (code+UI, data artifacts, findings, report, presentation), build-heavy vs study-heavy framing, sprint rules, grading criteria.
- `docs/requirements/universal_scaffolding.md` — the 13 mandatory components. "Minimum acceptable" bullets per section are the floor, not the goal.
- `docs/specifications/problem_statement.md` — authoritative design spec: data model, agentic pattern, evaluation strategy, edge cases, and requirements summary (§8). When it conflicts with the above, raise the discrepancy before acting.
- `docs/specifications/evaluation.md` — detailed evaluation protocol: component-level tests, oracle satisfaction metrics, LLM-as-judge validation, experimental conditions A–D, system-level metrics, human study design.

## System decomposition — the `f_*` functions

The brief structures the system as functions over the current state. When adding features, map them to one of these rather than inventing a parallel structure:

- `f_output` — best-guess clustering given state ("here is my best recommendation right now")
- `f_uncertainty` — what's known vs. unknown; drives `f_next_best_step`'s ask/show decision
- `f_next_best_step` — **router agent**: returns one dispatch (`show`, `ask`, or `stop`) plus required content; does not implement execution logic
- `f_next_state` — update state from an oracle reply (latest intent wins, but surface drift explicitly before overriding)
- `f_assess` — **assessor**: determines convergence, distils a structured preference profile from the session's `oracle_feedback` log, validates LLM-judge outputs against human-labelled transcripts

> **Note:** `f_eval` was renamed `f_assess`. Do not use the old name in new code or docs.

Oracle input flows at four levels: **global**, **cluster-level**, **point-level**, **instructional**. Outputs are **soft assignments** (distribution over K clusters) plus a two-level **hierarchy** (coarse clusters generated on turn 1; fine levels generated lazily on oracle request), not hard labels only.

Separate from the conversational loop, an **LLM-as-Judge** scores completed session transcripts on clustering coherence, question quality, and preference-profile fidelity (1–5 each). It is an evaluation tool only — it never influences session state.

# Best practices and conventions

## Fail loudly — no silent errors

**The application must crash when it has to crash.** Do not swallow errors silently.

- Never use bare `except: pass` or `except Exception: pass` around any meaningful operation.
- Never use fallback values that hide a failure (e.g. returning `None` / an empty list / stale state) without raising or at minimum re-raising with context.
- The one sanctioned exception is the LLM harness retry loop: transient API errors (rate-limit, timeout) are retried with exponential backoff (max 3 attempts). If all retries fail, **raise** — do not silently return the previous turn's data.
- Any `try/except` block must either: (a) retry a transient error and eventually raise on exhaustion, or (b) catch a specific, well-understood exception and raise a richer one in its place. Catching `Exception` broadly to continue is always wrong here.
- Post-run integrity checks must `assert` or `raise` on missing data — do not log a warning and carry on.

## Comments

- For each function, include a docstring that explains its purpose, parameters, return values
- Inline comments should explain non-obvious logic
- Keep a space between code blocks with different purposes

## Scaffolding obligations (non-negotiable)

These are from `universal_scaffolding.md` and failing them = scaffolding check fail. Enforce them whenever you write or refactor code:

- **Prompts as versioned files.** `prompts/` directory, one file per named prompt, explicit variable substitution, prompt file-hash logged per run. Never embed prompts as f-strings inside functions.
- **Harness, not bespoke scripts.** LLM calls go through a reusable harness (`llm_harness.py`) with sync / async / batch `call`, retry with exponential backoff, model + version from config (never hard-coded), seed-controlled, stateless where possible.
- **Structured logging per run-step.** JSONL or Parquet. Every record includes `run_id`, `seed`, `config_hash`, `model_and_version`, `timestamp`, `step_type`, inputs, outputs, errors, token counts. No `print()` as logs. A `replay.py` must re-execute a run from its log.
- **Config-driven conditions.** Each experimental condition is a config file, not a forked script.
- **Memory separation.** Working memory is per-run and reset between runs unless explicitly shared; persistent memory has a versioned initial state; tool set is declared in config. Global module-level caches across runs are a bug — they cause silent cross-condition leakage.
- **Resilience.** Distinguish transient (retry) from permanent (fail loudly) errors. Never `try: except: pass` around an LLM call. Post-run integrity check must report holes.
- **Cost tracking.** Every run logs input/output token counts separately. Hard-stop guard if a declared budget (`session.cost_limit_usd`) is exceeded.
- **Quality spec before experiments.** Primary outcome dimension is pre-committed in writing. LLM-as-judge must be validated against a human-labeled subset (κ ≥ 0.6 against human consensus); report inter-rater / judge-vs-human agreement. Confidence intervals on every quantitative claim (means alone aren't acceptable).
- **Smoke test.** `scripts/smoke_test.sh` (or equivalent) runs the full pipeline on a 1-example toy dataset in < 1 minute and exercises the critical path (extractor → runtime → logger → analysis).

If a proposed change would violate one of these, flag it rather than quietly going along.

## Conventions to adopt when code lands

No code exists yet, so these are forward-looking defaults aligned with the scaffolding doc. Revisit if the team picks different tools:

- Python stack: `src/` library + `scripts/` entry points + `notebooks/` exploration, with `prompts/`, `configs/`, and `logs/` as sibling directories.
- Typed interfaces between modules (pydantic / dataclasses). The `f_*` functions are the obvious module boundaries.
- LLM-as-oracle simulations are a first-class evaluation path, not an afterthought. Human studies validate them on a small N ≥ 5–10 within-subject sample.
- Keep a frozen held-out subset of any dataset for the generalization question — do not let it leak into the conversational loop.
- Dataset: **The Movies Dataset** (Kaggle, Rounak Banik) — ~45k TMDB movies. JSON columns (`genres`, `credits`, `keywords`) are Python-style single-quoted strings; parse with `ast.literal_eval`. Deduplicate on `id`; drop 3 rows with null `id`. Use `links_small.csv` / `ratings_small.csv` for smoke tests and lightweight evaluation runs.
