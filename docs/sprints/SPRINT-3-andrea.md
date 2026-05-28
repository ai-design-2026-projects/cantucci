# CinePal – Sprint 3 | Andrea Blushi

## Overview
After understanding that the system we had built in the previous sprints was not compatible with the professor's vision for the project, we decided to pivot and build a new system starting from scratch, reusing only the components that were still relevant for the new design. 

The new system, which we named CinePal, is an AI system that clusters a movie catalogue by *conversing* with a human oracle who proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function — no intrinsic ground truth exists.

This took us a lot of time and effort, but we are happy with the result, which is a more coherent and engaging system that better aligns with the professor's vision and the course objectives.


## What I Did

**1. Stability & hardening**
Performed a project rebuild and a set of dependency/wiring fixes to stabilise the repo after the pivot. This made local runs and CI more predictable and resolved several reproducibility issues. *[PR #94](https://github.com/ai-design-2026-projects/cantucci/pull/94)*

**3. Evaluation & reporting**
Added an initial evaluation harness, documentation, and a dashboard prototype to run reproducible experiments and inspect results. Also added progress-streaming hooks used by long-running runs. 

**4. Frontend rebuild**
Fixed UI issues that affected demos and visualisations (scatterplot, representative movie display) and applied frontend bug fixes to improve demo reliability. *[PR #110](https://github.com/ai-design-2026-projects/cantucci/pull/110), [PR #108](https://github.com/ai-design-2026-projects/cantucci/pull/108)*

## Artifacts / PRs / Commits
- *[PR #94](https://github.com/ai-design-2026-projects/cantucci/pull/94)* — Project Rebuild
- *[PR #106](https://github.com/ai-design-2026-projects/cantucci/pull/106)* — Add progress streaming
- *[PR #108](https://github.com/ai-design-2026-projects/cantucci/pull/108)* — Frontend fixes
- *[PR #110](https://github.com/ai-design-2026-projects/cantucci/pull/110)* — Fix scatterplot
- *[PR #112](https://github.com/ai-design-2026-projects/cantucci/pull/112)* — Fix bugs
- *[PR #116](https://github.com/ai-design-2026-projects/cantucci/pull/116)* — Demo
