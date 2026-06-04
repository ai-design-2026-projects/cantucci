# CinePal – Sprint 3 | Davide Donà

## Overview
After understanding that the system we had built in the previous sprints was not compatible with the professor's vision for the project, we decided to pivot and build a new system starting from scratch, reusing only the components that were still relevant for the new design. 

The new system, which we named CinePal, is an AI system that clusters a movie catalogue by *conversing* with a human oracle who proposes groupings, explains them, and refines them through dialogue. The oracle's acceptance is the objective function — no intrinsic ground truth exists.

This took us a lot of time and effort, but we are happy with the result, which is a more coherent and engaging system that better aligns with the professor's vision and the course objectives.

## What I Did

**1. Full Backend Rebuild (Project Pivot)**
This was the centerpiece of the sprint. Working together with Andrea (who led the frontend), I rebuilt the entire backend from scratch to support our new conversational clustering model. Instead of just filtering movies, the system now re-partitions the whole catalog every turn. My main contributions included setting up a cleaner project structure, overhauling the data pipeline (scrape → embed → cluster), adding support for multimodal embeddings (text, images, trailers), and building the first version of our AI agents with proper safety guardrails. 
[[PR #94](https://github.com/ai-design-2026-projects/cantucci/pull/94)]

**2. Iterative Steps Toward the Goal**
The pivot wasn't a one-and-done deal, but an iterative process of design, feedback, and refinement. To get the new system working smoothly, I tackled several core improvements piece by piece:
* **Agent & Coordinator Cleanup:** Broke down the massive main coordinator into smaller, specific modules (actions, labeling, saving, progress). I clearly separated structural commands (like "merge") from conversational ones (like "explain") and added a way to track the exact API cost of every single conversation turn. [[PR #109](https://github.com/ai-design-2026-projects/cantucci/pull/109)]
* **Multi-Step Commands:** Upgraded the intent agent so it can handle compound requests—like "merge these two clusters and then focus on the first one"—in a single round-trip without dropping the second instruction. [[PR #98](https://github.com/ai-design-2026-projects/cantucci/pull/98)]
* **Exact Sorting & Faster Processing:** Added the ability to group movies by exact metadata (like sorting strictly by Genre or Director) instead of just fuzzy AI similarity. For numbers like Release Year, the system now creates logical, labeled bins. I also batched our data processing so the system handles text embeddings much faster. [[PR #114](https://github.com/ai-design-2026-projects/cantucci/pull/114)]
* **Drill-Down Refactoring:** Split the "drill-down" operation into two separate functions, making the underlying mechanics much clearer and easier to manage behind the scenes. [[PR #122](https://github.com/ai-design-2026-projects/cantucci/pull/122)]

**3. Bug Fixes & System Stability**
I knocked out several rounds of bugs, especially around how clusters scope their data. I also built a new "advisor" agent that automatically suggests logical groupings (like decades) when you sort by numbers. To make the system more stable, we switched our main models to OpenAI (GPT-4o), which are significantly more reliable at returning properly formatted data. 
[[PR #117](https://github.com/ai-design-2026-projects/cantucci/pull/117), [PR #119](https://github.com/ai-design-2026-projects/cantucci/pull/119), [PR #120](https://github.com/ai-design-2026-projects/cantucci/pull/120)]

**4. Automated Testing**
Added a suite of automated "smoke tests" that run against a real database to make sure the core app doesn't break during updates. 
[[PR #102](https://github.com/ai-design-2026-projects/cantucci/pull/102)]

**5. MCP Server Integration**
Added Model Context Protocol (MCP) support, which exposes CinePal's clustering capabilities as a tool that other AI systems can directly interact with. 
[[PR #105](https://github.com/ai-design-2026-projects/cantucci/pull/105)]

## What's Next

With the new system working end-to-end, Sprint 4 will focus on hardening the architecture, completing the evaluation framework, and polishing the interaction model:

1. **Agent and coordinator architecture cleanup.** The coordinator has grown organically; we will extract a proper abstract base class for all LLM agents to eliminate duplicated render→call→log→parse boilerplate, and reorganise the coordinator into a pipeline of well-typed command objects.

2. **New clustering operations.** We plan to add *undo* (revert the last clustering state) and *exclude* (remove a cluster from the working set permanently) so the oracle has finer control without restarting a session.

3. **Stabilise clustering colours and labels.** Cluster colours currently shift between turns; we will introduce stable colour slots so the oracle can track clusters visually across the whole conversation. The labelling agent also needs further prompt work for consistent, meaningful cluster names.

4. **Concept axis visualisation.** We will surface the linear concept axes in the frontend so the oracle can see where movies sit along a named dimension (e.g. "dark → light tone" or "art-house → blockbuster"). This requires the concept agent to produce a scored axis, the backend to attach scores to each cluster snapshot, and the frontend to render an annotated axis view alongside the scatter plot.

5. **Finalise the evaluation framework.** The LLM oracle and LLM judge are in place but the baseline runs and deterministic metrics still need to be wired up and validated end-to-end.

6. **Demo recording and documentation.** We will record a scripted walkthrough of a full session and update all READMEs and API specs to reflect the current state of the system.