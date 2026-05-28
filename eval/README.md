# Evaluation Harness

Offline pipeline that drives simulated oracle sessions against the live system and scores results with deterministic metrics and an LLM judge.

---

## Overview

A complete eval run has four stages:

```
seed personas → build ground truths → simulate sessions (--run-name auto-creates the run)
                                              ↓
                                    metrics + judge scores written automatically
```

`create-run` is optional — passing `--run-name` to `simulate` creates the run automatically if it does not exist. The `evaluate` subcommand re-scores an existing conversation without re-running it.

---

## Prerequisites

1. Migrations applied and data ingested:
   ```bash
   python -m db.apply
   python -m db.ingest          # mini (dev default)
   ```

2. Environment variables set (see `.env.example`):
   - `DATABASE_URL` — Postgres connection string
   - `OPENAI_API_KEY` — used by the system under test
   - `CONFIG_PATH` — defaults to `configs/dev.yaml`; use `configs/prod.yaml` for production

3. The eval harness uses two additional model tiers configured in `eval/eval.yaml`:
   - `eval_harness.oracle` — oracle simulation (default: `google/gemini-flash-1.5`)
   - `eval_harness.judge` — LLM judge (default: `anthropic/claude-3.5-sonnet`)

   Both are called via OpenRouter. Ensure `OPENAI_API_KEY` is an OpenRouter key, or override in `eval/eval.yaml`.

---

## Step 1 — Seed personas

Personas are write-once rows (`slug` is the stable identifier). Create them once before any runs; they are reused across runs.

```bash
python -m eval.run create-persona --slug explorer_medium  --verbosity medium  --patience 0.7
python -m eval.run create-persona --slug explorer_terse   --verbosity terse   --patience 0.5
python -m eval.run create-persona --slug explorer_verbose --verbosity verbose --patience 0.9
```

Each command prints the UUID of the created persona. Re-running the same slug raises an error (slugs are unique).

`verbosity` controls reply length (`terse | medium | verbose`); `patience` (`[0, 1]`) controls the oracle's willingness to keep going after unexpected system behaviour.

---

## Step 2 — Build ground truths

Ground truths are LLM-generated navigation trajectories anchored to a random sample of catalogue movies. Each takes two LLM calls (judge model tier).

```bash
python -m eval.run build-gt --slug exploration_v1
python -m eval.run build-gt --slug action_focus_v1 --hint "action and thriller films"
```

`--hint` is optional free text that biases the generated trajectory theme. The command prints the assigned `ground_truth_id` and number of operations on success.

Ground truth slugs are unique. Re-running the same slug raises an error.

---

## Step 3 — Create a run

A run is a registry entry that groups eval sessions under one UUID.

```bash
python -m eval.run create-run --name "baseline-conversational" --condition conversational
```

This prints the `run_id` UUID. Copy it for the next step.

Available conditions:

| Condition | System under test |
|---|---|
| `conversational` | Full multi-agent coordinator (default) |
| `no_agents` | Baseline without sub-agents |
| `monolithic` | Single-prompt monolithic baseline |

`--notes` accepts free text for audit purposes.

---

## Step 4 — Simulate sessions

Each `simulate` call drives one complete oracle session (up to `eval_harness.runner.max_turns` turns, default 15), then automatically computes and persists all metrics and judge scores.

```bash
python -m eval.run simulate \
  --run   <run_id>            \
  --persona  explorer_medium  \
  --ground-truth  exploration_v1 \
  --seed  42
```

The command prints the `conversation_id` on completion. Run multiple sessions under the same `run_id` with different persona/ground-truth/seed combinations:

```bash
python -m eval.run simulate --run <run_id> --persona explorer_terse    --ground-truth action_focus_v1   --seed 1
python -m eval.run simulate --run <run_id> --persona explorer_verbose  --ground-truth exploration_v1    --seed 2
python -m eval.run simulate --run <run_id> --persona explorer_medium   --ground-truth action_focus_v1   --seed 3
```

Each session terminates with one of three statuses:

| Status | Meaning |
|---|---|
| `finished_trajectory` | Oracle stopped after completing all GT operations |
| `finished_misbehaviour` | Oracle stopped but GT was not fully executed |
| `finished_budget` | Turn budget exhausted (`max_turns` reached) |

---

## Step 5 — Re-evaluate (optional)

`evaluate` is idempotent. Use it to re-score a conversation after changing the judge prompt or to recompute deterministic metrics:

```bash
python -m eval.run evaluate --conversation <conversation_id>
python -m eval.run evaluate --conversation <conversation_id> --ground-truth exploration_v1
```

Passing `--ground-truth` enables `operation_recall` computation and passes GT context to the judge.

---

## Metrics reference

### Deterministic (no LLM)

| Metric | Description |
|---|---|
| `num_turns` | Oracle turns in the conversation |
| `num_operations` | Navigation operations executed (`drill_down`, `merge`, `focus`, `cross_filter`, `partition_by`) |
| `operation_recall` | Fraction of GT `(op, concept)` pairs found in turn intents (requires GT) |
| `clarifier_trigger_rate` | Fraction of turns where the clarifier gate fired |
| `silhouette` | Silhouette score of the final cluster snapshot (`None` if < 2 clusters) |
| `mean_membership_prob` | Mean argmax HDBSCAN membership probability |
| `noise_fraction` | Fraction of movies below `noise_prob_threshold` (default 0.3) |
| `total_cost_usd` | Accumulated LLM cost for the conversation |

### LLM judge (5 dimensions, score 1–5)

| Dimension | What it measures |
|---|---|
| `operation_appropriateness` | Whether applied operations match the oracle's expressed intent |
| `label_accuracy` | Accuracy and clarity of cluster labels |
| `suggestion_meaningfulness` | Relevance of system-generated suggestions |
| `explanation_quality` | Quality of cluster explanations shown to the oracle |
| `intent_alignment` | Overall alignment between oracle intent and final clustering state |

Judge scores are appended per `(conversation_id, dimension, judge_prompt_hash)`. Multiple judge versions coexist; the latest score per dimension is used in aggregates.

---

## Configuration

All harness knobs live in `eval/eval.yaml` under the `eval_harness:` key. This section is read only by eval scripts — `get_settings()` ignores it.

| Key | Default | Description |
|---|---|---|
| `runner.max_turns` | `15` | Turn budget per simulated session |
| `oracle.cost_limit_usd` | `2.0` | Per-session oracle LLM cost ceiling |
| `judge.cost_limit_usd` | `2.0` | Per-conversation judge LLM cost ceiling |
| `scorer.noise_prob_threshold` | `0.3` | Membership probability below which a movie is noise |
| `scorer.silhouette_metric` | `cosine` | Distance metric for silhouette score |
| `gt_builder.max_movies` | `30` | Catalogue sample size for GT generation |
| `gt_builder.min_ops` | `3` | Minimum operations in a generated GT |
| `gt_builder.max_ops` | `6` | Maximum operations in a generated GT |

Set `dry_run: true` under `eval_harness.oracle` or `eval_harness.judge` to short-circuit LLM calls during development.

---

## Directory layout

```
eval/
  run.py              CLI entry point (subcommands: create-run, simulate, evaluate, build-gt)
  runner.py           run_simulated_session + evaluate_conversation
  metrics.py          Deterministic metrics (no LLM)
  config.py           eval/eval.yaml loader (eval_harness: section only)
  eval.yaml           All harness knobs + system config for eval runs
  oracle/
    agent.py          oracle_turn() — single LLM call per turn
    types.py          OracleLLMResponse, OracleTurnResult
    prompts/oracle_v1.j2
  judge/
    agent.py          judge_conversation() — single LLM call per conversation
    types.py          JudgeLLMResponse, JudgeResult
    prompts/judge_v1.j2
  ground_truths/
    builder.py        build_ground_truth() — two LLM calls, persists GT row
    types.py          TrajectoryProposal, IntentDescriptionProposal
    prompts/trajectory_v1.j2
    prompts/intent_description_v1.j2
```

SQL schema lives in `db/migrations/012_evaluation.sql`. Data access is in `backend/data_access/eval/queries.py`.
