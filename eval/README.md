# CinePal — Eval Harness

Offline evaluation of the CinePal conversational clustering system. Because there is no intrinsic ground truth — the human oracle's acceptance *is* the objective function — the harness uses an LLM-backed **Oracle** to stand in for the human and an LLM-as-**Judge** to score each session. The runner drives the full `(ground_truth × persona × seed)` cross-product through the live CinePal HTTP API and writes results to the database for analysis.

---

## Layout

```
eval/
├── runner.py                  CLI entry point — drives the gt × persona × seed cross-product.
├── oracle/
│   ├── oracle.py              Oracle class: LLM user-simulator embodying a taste target + persona.
│   ├── gt_builder.py          Offline tool that builds ground-truth YAMLs from the embedding holdout.
│   ├── prompts/
│   │   ├── oracle_system_v1.j2
│   │   ├── oracle_turn_v1.j2
│   │   └── ground_truth_description_v1.j2
│   └── utils/
│       ├── behavior.py        BehaviorRng — deterministic per-turn RNG (drift, contradiction, acceptance gating).
│       └── memory.py          OracleMemory — role-tagged chat history enforcing chat-completion ordering.
├── judge/
│   ├── judge.py               Judge class: post-session scorer (objective metrics + 3 subjective LLM dimensions).
│   ├── metrics.py             Pure functions: precision_at_k, recall, NDCG, avg cognitive load.
│   └── prompts/
│       ├── judge_clustering_coherence_v1.j2
│       ├── judge_question_quality_v1.j2
│       └── judge_profile_fidelity_v1.j2
└── shared/
    ├── ground_truths.py       GroundTruth / OracleGroundTruthView loaders for configs/ground_truths/*.yaml.
    ├── personas.py            PersonaProfile / PersonaDials loaders (behavioural overlay, no taste content).
    ├── http_client.py         CinePalClient — async httpx wrapper around the three API endpoints the Oracle needs.
    └── llm_gateway.py         LLMGateway — eval-side LLM client with separate cost budget + dry_run fixture mode.
```

---

## Architectural notes

- **The Oracle drives CinePal through the real HTTP API** (`/sessions`, `/sessions/{id}/turns`, `GET /sessions/{id}`). It never imports backend internals — it is a genuine external client.
- **Eval-side LLM spend is tracked separately.** Oracle and Judge calls go through `LLMGateway` (`eval/shared/llm_gateway.py`), not through `backend/llm/llm_harness.py`. A runaway Oracle cannot exhaust the user-facing cost budget.
- **The Oracle never sees `gt_movie_ids`.** `OracleGroundTruthView` exposes only the taste description; the ground-truth TMDB IDs are hidden by the type so the simulator cannot leak the answer it is being scored against.
- **Prompts are versioned Jinja2 files**, one per named prompt in each `prompts/` subdirectory, following the same `{function}_{version}.j2` convention as the backend agents. Prompt hashes are logged per run for auditability.
- **Dry-run mode** reads canned LLM responses from `tests/fixtures/eval_dry_run/<step_type>.json`. The full pipeline can be exercised without `OPENAI_API_KEY`. HTTP calls to the CinePal API are still live — start the API server first.
- **Replayability** is preserved via `runs.config_hash`. Every eval run is registered with the SHA-256 config prefix from `backend.settings.get_config_hash()`, so results can always be joined back to the exact YAML they ran under.

---

## Building ground truths

Ground-truth files (`configs/ground_truths/<slug>.yaml`) are built offline once and committed. To add a new one:

```bash
python -m eval.oracle.gt_builder \
    --n-seed 5 \
    --n-gt 30 \
    --seed 42 \
    --slug sci_fi_70s \
    --out configs/ground_truths/sci_fi_70s.yaml
```

The builder samples `--n-seed` films from the embedding holdout (`eval_holdout` parquet), expands via nearest-neighbour search to `--n-gt` candidates, and asks an LLM to write a neutral taste description. The result is deterministic for a given `--seed`.

---

## Running the harness

Prerequisites:

1. Migrations applied: `python -m db.apply`
2. API server running: `uvicorn backend.app:app`
3. Ground-truth and persona YAML files present under `configs/`

```bash
python -m eval.runner \
    --condition baseline \
    --ground-truths all \
    --personas all \
    --seeds 1,2,3 \
    [--base-url http://localhost:8000] \
    [--dry-run]
```

`--ground-truths all` and `--personas all` load every YAML in `configs/ground_truths/` and `configs/personas/` respectively. Pass a comma-separated slug list to run a subset.

---

## Outputs

For each session in the cross-product the runner writes:

| Table | Contents |
|---|---|
| `session_metrics` | Objective per-session scores (precision, recall, NDCG, avg cognitive load). |
| `judge_scores` | Three LLM-rated 1–5 scores: `clustering_coherence`, `question_quality`, `profile_fidelity`. |

Both tables carry `run_id` which joins to `runs.config_hash` (see `db/migrations/005_eval_results.sql`).

---

## Environment variables

The eval harness reuses the standard backend env — no `EVAL_*`-specific variables. See [`backend/README.md`](../backend/README.md) for the full table. The variables relevant here are:

| Variable | Purpose |
|---|---|
| `DATABASE_URL` | Postgres connection (required). |
| `OPENAI_API_KEY` | LLM calls for Oracle + Judge when provider is `openai`. |
| `OPENROUTER_API_KEY` | LLM calls when provider is `openrouter`. |
