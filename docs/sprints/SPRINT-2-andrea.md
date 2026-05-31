# CinePal – Sprint 2 | Andrea Blushi

## Overview
The second sprint was dedicated to completing the system architecture, improving prompt engineering, enhancing responsiveness, and setting up the groundwork for evaluation and experimentation.

## What I Did

**1. Architecture completion**
I completed several backend and orchestration changes that moved the project past the MVP plumbing and toward a reproducible pipeline.
[
	[PR #60](https://github.com/ai-design-2026-projects/cantucci/pull/60),
	[PR #66](https://github.com/ai-design-2026-projects/cantucci/pull/66),
	[PR #78](https://github.com/ai-design-2026-projects/cantucci/pull/78)
]

**2. Agents & decision flow**
I consolidated the decision and ambiguity paths so agent outputs flow cleanly through the orchestrator, introduced the authentication setup for the protected flows, and fixed a number of wiring issues that caused intermittent failures.
[
	[PR #61](https://github.com/ai-design-2026-projects/cantucci/pull/61),
	[PR #70](https://github.com/ai-design-2026-projects/cantucci/pull/70),
	[PR #72](https://github.com/ai-design-2026-projects/cantucci/pull/72)
]

**3. Frontend & demo tooling**
I improved the frontend to reliably present recommendation and disambiguation prompts, and added a recordable demo harness to capture live sessions for replay and inspection.
[
	[PR #69](https://github.com/ai-design-2026-projects/cantucci/pull/69),
	[PR #89](https://github.com/ai-design-2026-projects/cantucci/pull/89),
	[PR #90](https://github.com/ai-design-2026-projects/cantucci/pull/90),
	[PR #91](https://github.com/ai-design-2026-projects/cantucci/pull/91)
]

**4. Evaluation Dashboard Harness**
I added basic inspection endpoints and created a first dashboard for evaluation inspection of multiple runs.
[
	[PR #87](https://github.com/ai-design-2026-projects/cantucci/pull/87)
]

**5. Written documentation**: Alongside my teammate, I contributed to the documentation of the system, including the API specifications and the README files for both the backend and frontend components.
[
    [PR #32](https://github.com/ai-design-2026-projects/cantucci/pull/32),
    [PR #91](https://github.com/ai-design-2026-projects/cantucci/pull/91)
]

## What's Next
For the next sprint, I expected the work to shift toward reframing the problem itself rather than just polishing the current implementation. The main idea was to reconsider all the project from the ground up, in order to shift from a conversational retrieval to a conversational cluster.
None of the current components were expected to be reusable.