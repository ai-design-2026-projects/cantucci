# CinePal – Sprint 2 | Andrea Blushi

## Overview
The second sprint was dedicated to completing the system architecture, improving prompt engineering, enhancing responsiveness, and setting up the groundwork for evaluation and experimentation. On my side, the work focused on re-architecting the orchestrator into a parallel multi-agent pipeline, securing the stack with JWT authentication and session management, modernizing the frontend, and standing up the first evaluation dashboard and demo-recording tooling.

## What I Did

**1. LLM Harness & Provider Configuration**: I added OpenRouter handling to the LLM harness, including the config and environment plumbing needed to switch providers. I centralized provider/model configuration in the YAML and settings layer instead of leaving it scattered across call sites, and cleaned up the agent and orchestrator wiring to read from this new config flow.
[
    [PR #34](https://github.com/ai-design-2026-projects/cantucci/pull/34)
]

**2. Orchestrator v2 — Multi-Agent Pipeline**: this was the centerpiece of my sprint. I refactored the orchestrator from a monolithic loop into a proper multi-agent pipeline with parallel execution. A later pass wired profile-driven exclusions into retrieval, added a drift confirmation flow, removed UUIDs from prompts to cut token usage, and renamed the convergence modules to *state*; a final wiring fix re-aligned the types and component flow broken by the merge.
[
    [PR #60](https://github.com/ai-design-2026-projects/cantucci/pull/60),
    [PR #66](https://github.com/ai-design-2026-projects/cantucci/pull/66),
    [PR #78](https://github.com/ai-design-2026-projects/cantucci/pull/78)
]

**3. Decision & Ambiguity Consolidation**: I merged the ambiguity agent into the decision agent so routing and follow-up question generation happen in a single LLM call.
[
    [PR #61](https://github.com/ai-design-2026-projects/cantucci/pull/61)
]

**4. Authentication & Session Management**: I added full JWT-based authentication across the stack — DB migrations for users, roles, and session ownership; login/register/current-user routes; and protected session/user APIs, with matching frontend login/register pages, token-backed auth state.
[
    [PR #70](https://github.com/ai-design-2026-projects/cantucci/pull/70),
    [PR #72](https://github.com/ai-design-2026-projects/cantucci/pull/72)
]

**5. Frontend Modernization**: I ran a UI/UX modernization pass over the frontend — converting styling to Tailwind CSS, replacing custom elements with `shadcn/ui` components.
[
    [PR #69](https://github.com/ai-design-2026-projects/cantucci/pull/69),
    [PR #89](https://github.com/ai-design-2026-projects/cantucci/pull/89)
]

**6. Evaluation Dashboard Harness**: I built the first evaluation inspection interface at `/admin`, replacing the placeholder.
[
    [PR #87](https://github.com/ai-design-2026-projects/cantucci/pull/87)
]

**7. Recordable Demo Setup**: I added an automated setup for recording video demos of the application, including the harness needed to capture a live session for later replay and inspection.
[
    [PR #90](https://github.com/ai-design-2026-projects/cantucci/pull/90)
]

**8. Written documentation**: Alongside my teammate, I contributed to the documentation of the system, structuring the progress report and updating the API specifications and the README files for both the backend and frontend components.
[
    [PR #91](https://github.com/ai-design-2026-projects/cantucci/pull/91)
]

## What's Next

After presenting our progress, we received critical feedback from the professor: the system we had built — a conversational-based retrieval engine that filters a fixed movie catalogue based on user queries — did not match the intended vision for the project. The goal was not retrieval but *conversational clustering*: the human oracle should be guiding an AI to progressively organize an entire catalogue into meaningful groups, with no intrinsic ground truth.

Sprint 3 will therefore be a full pivot:

1. **Rebuild from scratch.** We will design and implement a new system — CinePal — where the oracle proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function.

2. **Reuse what still applies.** The data pipeline (scrape → embed) and the database infrastructure remain valid. Everything else — agents, routing logic, prompts — will be replaced.

3. **Establish a cleaner architecture.** The new system will have a well-defined coordinator, a small set of typed commands, and versioned Jinja2 prompts from the start, avoiding the technical debt that accumulated in the current design.

4. **First working demo.** By the end of the sprint we aim to have a live, conversable system that can partition a movie catalogue based on oracle instructions and iterate on the result in real time.
