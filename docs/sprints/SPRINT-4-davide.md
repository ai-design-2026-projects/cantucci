# CinePal – Sprint 4 | Davide Donà

## Overview
Sprint 4 was the final hardening sprint before the project presentation. With the core conversational clustering loop already working, the focus shifted to architectural cleanliness, interaction robustness, and system stability. The main themes were: extracting a clean agent abstraction, making the coordinator truly modular, adding the missing undo/exclude operations the oracle had been missing, and eliminating a long tail of UX bugs that made the system hard to use in practice.

## What I Did

**1. Major Agent & Coordinator Refactor**
This was the largest structural change of the sprint. I extracted an `LLMAgent` abstract base class (`backend/agents/base.py`) that encapsulates the render → call → log → parse loop shared by every agent. Previously each agent reimplemented this from scratch, creating a maintenance nightmare. I also moved the coordinator entirely out of `backend/agents/` into its own top-level module `backend/coordinator/`, splitting it into 11 typed command classes under `coordinator/commands/` (`DrillDown`, `Merge`, `Focus`, `CrossFilter`, `PartitionBy`, `Exclude`, `Undo`, `Reset`, `GoToBase`, `Explain`, `SmallTalk`) with a `CommandFactory`. New prompt versions for the labeling and intent agents (`label_v5.j2`, `label_v6.j2`, `intent_v9.j2`, `intent_v10.j2`) were introduced as part of this cleanup.
[[PR #130](https://github.com/ai-design-2026-projects/cantucci/pull/130)]

**2. New Operations: Undo & Exclude**
Added two operations the oracle had been missing. *Undo* reverts the clustering state to the previous turn, allowing the oracle to backtrack without restarting. *Exclude* permanently removes a selected cluster from the working set so it is not considered in subsequent re-partitions. Both operations are fully typed command classes and go through the same pipeline as all other commands.
[[PR #130](https://github.com/ai-design-2026-projects/cantucci/pull/130)]

**3. Unified Drill-Down**
The `DrillDown` and `PartitionBy` commands shared identical external behaviour — both narrow the working set to a single cluster and re-partition it — but were maintained as separate code paths, causing duplication and diverging logic. I unified them into a single command with an internal dispatch, making the codebase significantly easier to reason about.
[[PR #135](https://github.com/ai-design-2026-projects/cantucci/pull/135)]

**4. Bug Fixes & Stability**
Several rounds of bug fixing:
* **Intent clarification cluster reference lost** — when a clarification involved an action that needed to reference a specific cluster, the cluster context was being dropped after the clarification round-trip. Fixed the reference propagation so the downstream command receives the correct cluster.
  [[PR #138](https://github.com/ai-design-2026-projects/cantucci/pull/138)]
* **Stable cluster colours** — cluster colours were reassigned every turn, making it impossible for the oracle to track a cluster visually across a conversation. Introduced a *colour slot* field on each cluster in the backend (persisted in the snapshot) and wired the frontend to assign colours using the slot index with a golden-ratio hue step, so the same cluster keeps the same colour for the whole session.
  [[PR #139](https://github.com/ai-design-2026-projects/cantucci/pull/139)]
* **Labeller consistency** — the labelling agent was producing different names for the same cluster across turns, breaking the oracle's mental model. Fixed the prompt and generation logic for stable, consistent cluster names.
  [[PR #143](https://github.com/ai-design-2026-projects/cantucci/pull/143)]

**5. Concept Agent Update**
Cleaned up the concept agent by removing the exemplar-concept building path, which was never used in practice and added latency. Extended the linear-axis concept to support both BAAI and CLIP embeddings, so the axis visualisation works regardless of which encoder is active.
[[PR #146](https://github.com/ai-design-2026-projects/cantucci/pull/146)]

**6. Coordinator Refactor & CLIP Preloading**
A second pass at the coordinator module to clean up the pipeline and agent interfaces introduced in PR #130. Also added CLIP encoder preloading at application startup so the first user turn that requires visual embeddings does not pay a cold-start penalty.
[[PR #150](https://github.com/ai-design-2026-projects/cantucci/pull/150)]

**7. Remove Default K & Demo Files**
The intent agent was automatically proposing a default cluster count `k` even when the oracle had not asked for a specific number, biasing the clustering outcome. Removed this behaviour — `k` is now passed to the clustering core only when the oracle explicitly requests it. Also updated the demo video script and Playwright automation to reflect the current system state.
[[PR #160](https://github.com/ai-design-2026-projects/cantucci/pull/160)]

## Future Developments

The current system is tightly coupled to the TMDB movie catalogue. There are several natural directions to extend and generalise the work:

1. **Domain-agnostic catalogues.** The core loop — oracle proposes a grouping, the system partitions the catalogue, the oracle refines — is not specific to movies. The architecture could be extended to support arbitrary item catalogues (books, music albums, research papers, products) by abstracting the embedding pipeline and making the metadata schema configurable. The main challenge is that the current prompts reference movie-specific attributes (genre, director, release year); these would need to be made dynamic.

2. **Intent agent improvements.** The intent agent is currently a bottleneck for complex operations. It struggles to parse multi-step instructions (e.g. "merge these two clusters and then focus on the first one") and often drops important details. A more robust parsing logic, potentially with a secondary verification step or a more structured output format, would make the interaction smoother and more powerful.

3. **Dataset diversity and scale.** Testing on a single curated catalogue limits what we can learn about the system's behaviour. Experimenting with catalogues of different sizes, attribute densities, and domain characteristics would surface edge cases in the clustering and labelling agents and help calibrate cost-limit settings.

