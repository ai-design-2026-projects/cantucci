# CinePal – Sprint 3 | Andrea Blushi

## Overview
After understanding that the system we had built in the previous sprints was not compatible with the professor's vision for the project, we decided to pivot and build a new system starting from scratch, reusing only the components that were still relevant for the new design. 

The new system, which we named CinePal, is an AI system that clusters a movie catalogue by *conversing* with a human oracle who proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function — no intrinsic ground truth exists.

This took us a lot of time and effort, but we are happy with the result, which is a more coherent and engaging system that better aligns with the professor's vision and the course objectives. Within this rebuild my focus was the frontend and interaction layer — I co-led the work owning the new branching snapshot-navigation model and cluster visualisation — alongside live progress streaming, an automated demo-replay harness, the Docker deployment, and the first evaluation subsystem and documentation.

## What I Did

**1. Full Rebuild (Project Pivot)**
This was the centerpiece of the sprint. Working together with Davide (who led the backend), I co-led the rebuild from scratch, owning the frontend and the new navigation model that moves CinePal from conversational *retrieval* to conversational *clustering*. Instead of producing a ranked list of recommendations, every turn now produces a new cluster snapshot derived from the previous one, and a session is a branching tree of snapshots the oracle can navigate and reset. I rebuilt the frontend around this model and helped shape the persistence layer for snapshots, clusters, and memberships that the new product loop depends on.
[[PR #94](https://github.com/ai-design-2026-projects/cantucci/pull/94)]

**2. Frontend Rebuild & Visualisation**
With the new architecture in place, I rebuilt and stabilised the frontend around the snapshot model. I fixed authentication token handling and user-state management in the browser, then overhauled the cluster scatterplot: per-dot opacity driven by soft-membership probability, enlarged exemplar dots, per-cluster centroids, a vortex animation on snapshot change, and light mode set as the default.
[[PR #108](https://github.com/ai-design-2026-projects/cantucci/pull/108), [PR #110](https://github.com/ai-design-2026-projects/cantucci/pull/110)]

**3. Progress Streaming**
I added real per-turn progress streaming so the frontend can show granular loading status while the multi-agent pipeline runs, wiring a coordinator progress channel through to the chat loading UI instead of leaving the user staring at a generic spinner.
[[PR #106](https://github.com/ai-design-2026-projects/cantucci/pull/106)]

**4. Bug Fixes & Stability**
I knocked out a round of backend and frontend bugs across the clarifier, clustering helpers, concept agent, coordinator, intent and responder agents, and the evolution-map visualisation, improving the overall reliability and consistency of the system after the pivot.
[[PR #112](https://github.com/ai-design-2026-projects/cantucci/pull/112)]

**5. Automated Demo Replay**
I introduced a Playwright-driven demo replay that records a live CinePal chat session and replays it later with zero LLM calls — useful for deterministic screen-recording demos and re-takes.
[[PR #116](https://github.com/ai-design-2026-projects/cantucci/pull/116)]

**6. Deployment & Docker Setup**
I added Docker build configuration for the CD deployment of the backend, frontend, and MCP server.
[[PR #121](https://github.com/ai-design-2026-projects/cantucci/pull/121)]

**7. Evaluation Initial Setup & Documentation**
I implemented the initial evaluation subsystem to run reproducible, multi-seed simulation experiments and compute deterministic metrics: a `simulate` CLI and runner with `--persona` / `--ground-truth` flags, deterministic metrics for session quality and clustering performance, and config-hash / cost-limit layering off the same YAML source of truth, plus a first admin evaluation dashboard in the frontend. Alongside it I updated the project documentation — problem statement, evaluation plan, architecture (with diagram and new flowchart), data scheme, and API model.
[[PR #123](https://github.com/ai-design-2026-projects/cantucci/pull/123)]

## What's Next

With the new system working end-to-end, Sprint 4 will focus on hardening the architecture, completing the evaluation framework, and polishing the interaction model:

1. **Agent and coordinator architecture cleanup.** The coordinator has grown organically; we will extract a proper abstract base class for all LLM agents to eliminate duplicated render→call→log→parse boilerplate, and reorganise the coordinator into a pipeline of well-typed command objects.

2. **New clustering operations.** We plan to add *undo* (revert the last clustering state) and *exclude* (remove a cluster from the working set permanently) so the oracle has finer control without restarting a session.

3. **Stabilise clustering colours and labels.** Cluster colours currently shift between turns; we will introduce stable colour slots so the oracle can track clusters visually across the whole conversation. The labelling agent also needs further prompt work for consistent, meaningful cluster names.

4. **Concept axis visualisation.** We will surface the linear concept axes in the frontend so the oracle can see where movies sit along a named dimension (e.g. "dark → light tone" or "art-house → blockbuster"). This requires the concept agent to produce a scored axis, the backend to attach scores to each cluster snapshot, and the frontend to render an annotated axis view alongside the scatter plot.

5. **Finalise the evaluation framework.** The LLM oracle and LLM judge are in place but the baseline runs and deterministic metrics still need to be wired up and validated end-to-end.

6. **Demo recording and documentation.** We will record a scripted walkthrough of a full session and update all READMEs and API specs to reflect the current state of the system.
