# CinePal – Sprint 2 | Andrea Blushi

## Overview
Sprint 2 progressed the core architecture, stabilised agent handoffs, and laid the first pieces of an evaluation harness to measure system behaviour under simulated runs.

## What I Did

**1. Architecture completion**
I completed several backend and orchestration changes that moved the project past the MVP plumbing and toward a reproducible pipeline. *[PR #60](https://github.com/ai-design-2026-projects/cantucci/pull/60)*

**2. Agents & decision flow**
I consolidated the decision and ambiguity paths so agent outputs flow cleanly through the orchestrator, and fixed a number of wiring issues that caused intermittent failures. *[PR #61](https://github.com/ai-design-2026-projects/cantucci/pull/61)*

**3. Frontend & demo tooling**
I improved the frontend to reliably present clusters and disambiguation prompts, and added a recordable demo harness to capture live sessions for replay and inspection. *[PR #69](https://github.com/ai-design-2026-projects/cantucci/pull/69)*

**4. Instrumentation & evaluation groundwork**
I added basic inspection endpoints and progress reporting used by early experiment runs, and began tracking latency and token-costs to guide optimisation. *[PR #87](https://github.com/ai-design-2026-projects/cantucci/pull/87)*

## Artifacts / PRs
- *[PR #60](https://github.com/ai-design-2026-projects/cantucci/pull/60)* — Orchestrator v2
- *[PR #61](https://github.com/ai-design-2026-projects/cantucci/pull/61)* — Merge decision and ambiguity agent
- *[PR #66](https://github.com/ai-design-2026-projects/cantucci/pull/66)* — Refine backend
- *[PR #69](https://github.com/ai-design-2026-projects/cantucci/pull/69)* — Update Frontend
- *[PR #70](https://github.com/ai-design-2026-projects/cantucci/pull/70)* — Add authentication
- *[PR #72](https://github.com/ai-design-2026-projects/cantucci/pull/72)* — Add session history
- *[PR #78](https://github.com/ai-design-2026-projects/cantucci/pull/78)* — Wiring Fix
- *[PR #87](https://github.com/ai-design-2026-projects/cantucci/pull/87)* — Add eval inspection
- *[PR #89](https://github.com/ai-design-2026-projects/cantucci/pull/89)* — Frontend bug fix
- *[PR #90](https://github.com/ai-design-2026-projects/cantucci/pull/90)* — Add recordable demo setup
- *[PR #91](https://github.com/ai-design-2026-projects/cantucci/pull/91)* — Progress report and documentation update