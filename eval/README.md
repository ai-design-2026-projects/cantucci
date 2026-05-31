# Evaluation Harness

Offline pipeline that drives simulated oracle sessions against the live system and scores results with deterministic metrics and an LLM judge.

---

## Overview

```
build bundles  →  run sessions (parallel)  →  metrics + judge scores written automatically
python -m eval.build     python -m eval.run
```

Bundles (`eval/personas/conf/<slug>.yaml`) are the canonical source of truth for personas and ground truths. DB rows are created lazily at simulation time. Sessions are run in parallel with a Rich progress bar.

---

## Prerequisites

1. Migrations applied and data ingested:
   ```bash
   python -m db.apply
   python -m db.ingest          # mini (dev default)
   ```

2. Environment variables (see `.env.example`):
   - `DATABASE_URL` — Postgres connection string
   - `OPENAI_API_KEY` — OpenRouter key for the system under test and the eval harness
   - `CONFIG_PATH` — defaults to `configs/dev.yaml`; use `configs/prod.yaml` for production

3. Eval harness uses two model tiers (configured in `eval/eval.yaml`):
   - `eval_harness.oracle` — oracle simulation (current: `google/gemini-2.0-flash-001`)
   - `eval_harness.judge` — LLM judge (current: `anthropic/claude-opus-4-7`)

   Set `dry_run: true` under either to bypass real LLM calls during development.

---

## Step 1 — Build bundles

A bundle combines persona dials (verbosity, patience) with a ground truth trajectory in one YAML file under `eval/personas/conf/`.

**Random batch** (randomised themes and dials):
```bash
python -m eval.build --count 5
```

**Single explicit bundle** (you control the theme and dials):
```bash
python -m eval.build --slug exploration_v1 --verbosity medium --patience 0.7 --hint "psychological thrillers and visual style"
python -m eval.build --slug action_v1 --hint "action films, exclude superhero"
```

Each command prints the slug, operation count, and the file path written. Bundles are `eval/personas/conf/<slug>.yaml` — open them directly to inspect or hand-edit.

Re-running the same slug raises an error (slugs are unique per file).

---

## Step 2 — Run sessions

**Single persona (debug)**:
```bash
python -m eval.run --persona exploration_v1 --run-name baseline-v1 --seeds 42
```

**Multiple personas**:
```bash
python -m eval.run --personas exploration_v1 action_v1 --run-name baseline-v1 --seeds 1 2 3
```

**All bundles in eval/personas/conf/**:
```bash
python -m eval.run --all --run-name baseline-v1 --seeds 1 2 3 --condition conversational
```

Passing `--run-name` auto-creates the run row if it does not exist; the most recent is used if multiple share the same name.

Sessions run in parallel (bounded by `eval_harness.runner.max_parallel`; default 4). A Rich progress bar shows live status per session. Each session's conversation UUID is printed on completion.

Available conditions:

| Condition | System under test |
|---|---|
| `conversational` | Full multi-agent coordinator (default) |
| `baseline` | Single-prompt baseline (one LLM call per turn) |

---

## Step 3 — Re-evaluate (optional)

Re-score an existing conversation after changing the judge prompt or recomputing metrics:

```bash
python -m eval.run --evaluate-only <conversation_id>
python -m eval.run --evaluate-only <conversation_id> --ground-truth exploration_v1
```

`--ground-truth` enables `operation_recall` computation and passes GT context to the judge. The call is idempotent (upserts metrics; appends judge scores under a unique prompt hash).

---

## Session termination statuses

| Status | Meaning |
|---|---|
| `finished_trajectory` | Oracle stopped; all GT operations were executed |
| `finished_misbehaviour` | Oracle stopped but GT was not fully executed |
| `finished_budget` | Turn budget exhausted (`max_turns` reached) |

---

## Metrics reference

### Deterministic (no LLM)

| Metric | Description |
|---|---|
| `num_turns` | Oracle turns in the conversation |
| `num_operations` | Navigation operations executed (`cluster`, `merge`, `focus`, `cross_filter`, `exclude`) |
| `operation_recall` | Fraction of GT `(op, concept)` pairs found in turn intents (requires GT) |
| `clarifier_trigger_rate` | Fraction of turns where the clarifier gate fired |
| `final_num_clusters` | Clusters in the final snapshot |
| `total_cost_usd` | Accumulated LLM cost for the conversation |
| `oracle_rating` | Self-rating (1–5) emitted by the oracle at session end |

### LLM judge (score 1–5 per dimension)

| Dimension | What it measures |
|---|---|
| `operation_appropriateness` | Whether applied operations match the oracle's expressed intent |
| `label_accuracy` | Accuracy and clarity of cluster labels |
| `suggestion_meaningfulness` | Relevance of system-generated suggestions |
| `explanation_quality` | Quality of cluster explanations |
| `intent_alignment` | Alignment between oracle intent and final clustering state |
| `concept_axis_quality` | Coherence of concept axes (emitted only when ≥1 axis was built) |

---

## Configuration (`eval/eval.yaml` — `eval_harness:` section)

| Key | Default | Description |
|---|---|---|
| `runner.max_turns` | `15` | Turn budget per simulated session |
| `runner.transcript_tail` | `6` | Recent messages shown to the oracle per turn |
| `runner.exemplar_top_k` | `5` | Max exemplar titles per cluster shown in oracle prompts |
| `runner.max_parallel` | `4` | Max concurrent simulated sessions |
| `runner.run_seed` | `0` | Seed for auto-created run rows |
| `oracle.cost_limit_usd` | `2.0` | Per-session oracle LLM cost ceiling |
| `oracle.dry_run` | `false` | Short-circuit oracle LLM calls with fixture responses |
| `judge.cost_limit_usd` | `2.0` | Per-conversation judge LLM cost ceiling |
| `judge.dry_run` | `false` | Short-circuit judge LLM calls with fixture responses |
| `scorer.pole_sample_k` | `5` | Films sampled per pole for `concept_axis_quality` |
| `scorer.exemplar_k` | `5` | Max exemplar titles shown per cluster in judge prompts |
| `gt_builder.min_ops` | `3` | Minimum operations in a generated GT |
| `gt_builder.max_ops` | `6` | Maximum operations in a generated GT |

---

## Directory layout

```
eval/
  run.py                CLI — run sessions (python -m eval.run)
  config.py             eval/eval.yaml loader (eval_harness: section only)
  eval.yaml             All harness knobs + system config for eval runs
  types.py              Canonical operation vocabulary (NAVIGATION_OPERATIONS, OpSpec, PERSONAS_DIR)
  build/                Bundle builder
    __main__.py         CLI — build bundles (python -m eval.build)
    builder.py          build_bundle() / build_random_batch()
    types.py            GroundTruthProposal, OpProposal (pydantic wire)
    prompts/
      ground_truth_v1.j2  Single-pass merged intent+trajectory prompt
  personas/             Bundle store
    conf/               Bundle YAML files (generated artifacts — gitignored)
    store.py            File I/O + idempotent DB upsert
    types.py            PersonaBundle dataclass
  runtime/              Session driver internals
    session.py          run_simulated_session()
    batch.py            run_personas() / run_all_personas() — parallel + Rich progress
    evaluate.py         evaluate_conversation() — metrics + judge
    handlers.py         select_handler() + system-under-test adapters
    termination.py      infer_termination_status()
    snapshot.py         build_cluster_info() — shared by session and judge
  oracle/
    agent.py            oracle_turn() — intent-driven, no to-do list
    types.py            OracleLLMResponse, OracleTurnResult
    prompts/oracle_v2.j2  Intent + cluster state + evolution trace
  judge/
    agent.py            judge_conversation() — single LLM call
    types.py            JudgeLLMResponse, JudgeResult
    prompts/judge_v4.j2   Single template with conditional axes block
  metrics/
    conversation.py     cost, num_turns, num_operations, clarifier_trigger_rate, operation_recall
    snapshot.py         num_clusters
```

SQL schema lives in `db/migrations/012_evaluation.sql`. Data access is in `backend/data_access/eval/queries.py`.
