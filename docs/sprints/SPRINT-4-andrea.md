# CinePal – Sprint 4 | Andrea Blushi

## Overview
Sprint 4 was the final hardening sprint before the project presentation. With the core conversational clustering loop already working, the focus shifted to architectural cleanliness, interaction robustness, and system stability. My main effort went into taking the evaluation framework from an early prototype to a reliable, reproducible harness — oracle, judge, baseline, metrics, and dashboard — alongside shipping the concept-axis distribution visualisation and a round of hardening across the MCP server, deployment images, and the frontend.

## What I Did

**1. Axis Distribution Visualisation**
I introduced the axis distribution view: when the concept agent proposes a linear-axis clustering, the oracle can now inspect how the catalogue spreads along that axis before confirming. The plot is a beeswarm where each film sits at its concept score, with density-proportional vertical spread, the most representative films near each pole highlighted, and concept-generated pole labels anchoring the two ends. The work spanned the concept agent and scoring on the backend, a new message-axis migration, and a dedicated `AxisDistribution` frontend feature.
[[PR #144](https://github.com/ai-design-2026-projects/cantucci/pull/144)]

**2. Evaluation Framework — Completion & Hardening**
This was the bulk of my sprint: taking the evaluation harness from an initial prototype to a reliable, reproducible system. I tackled it iteratively, piece by piece:
* **Metrics rework:** Dropped three intrinsic HDBSCAN-fit metrics (`silhouette`, `mean_membership_prob`, `noise_fraction`) that measured clustering fit rather than conversational behaviour, and added a `concept_axis_quality` judge dimension that rates how well each constructed axis is built. [[PR #154](https://github.com/ai-design-2026-projects/cantucci/pull/154)]
* **Runtime refactor & builders:** Reorganised the evaluation into runtime modules, split the metrics into clear modules (conversation, clustering, turns, cost, recall, operations), and added a persona and ground-truth builder. [[PR #155](https://github.com/ai-design-2026-projects/cantucci/pull/155)]
* **A true single-prompt baseline:** Replaced the two-call "monolithic" baseline — which still leaned on HDBSCAN, embeddings, and sub-agents — with a genuine single-LLM-call baseline that emits the full grouping, labels, operation, concept, and oracle reply in one JSON response, using a 1-based index remap to eliminate film-ID hallucination. Renamed the condition `monolithic → baseline` throughout. [[PR #159](https://github.com/ai-design-2026-projects/cantucci/pull/159)]
* **LLM-component reliability:** Iterated the oracle, judge, and ground-truth-builder prompts; rewrote termination inference to use the oracle's own `session_rating` as the sole signal instead of brittle string-matching; removed the noisy `operation_recall` metric; and added per-component eval logging. [[PR #162](https://github.com/ai-design-2026-projects/cantucci/pull/162)]
* **Final eval fixes:** A new oracle prompt using the full transcript with turn-budget warnings and a post-explain clustering gate, `axis_concept_id` threading so the judge's axis dimension fires correctly, and per-turn resilience so a backend clustering failure no longer kills a whole session. [[PR #164](https://github.com/ai-design-2026-projects/cantucci/pull/164)]

**3. Evaluation Dashboard Rebuild**
I realigned the frontend evaluation dashboard with the new harness: a 7-card KPI row, per-persona stats, a judge radar across all dimensions, a cost Pareto, distribution and termination views, a full-transcript session-detail dialog, and live polling that stops when a run completes. On the backend I fixed the run-status lifecycle (runs previously stayed `running` forever), enriched the run aggregate with persona and ground-truth fields, and added intent prompt v13 so `concept` populates for the relevant operations.
[[PR #163](https://github.com/ai-design-2026-projects/cantucci/pull/163)]

**4. Unclustered Session Start**
I removed the `go_to_base` operation and made sessions start unclustered, matching the live HTTP path, and dropped the ingest-time HDBSCAN snapshot so the catalogue is no longer pre-partitioned at ingestion. I added a `GET /movies/umap_points` endpoint so the frontend can render a grey-dot silhouette of the full catalogue before any clustering exists, and gave the simulated oracle visibility of the pending concept axis.
[[PR #161](https://github.com/ai-design-2026-projects/cantucci/pull/161)]

**5. MCP Server Rewrite & Route Refactor**
I rewrote the MCP server from a flat `tools.py` / `client.py` / `resources.py` layout into a proper module structure — one typed HTTP client per domain over a shared base, and one capability registrar per domain — dropped the resources surface in favour of a tools-only interface, and added new tools for conversations, snapshot graphs, and cluster members.
[[PR #149](https://github.com/ai-design-2026-projects/cantucci/pull/149)]

**6. Frontend Visual Polish**
I fixed a batch of visual bugs: scatterplot tooltips suppressed for dimmed points when a cluster is selected, a static mascot expression for finished messages while the in-flight loading indicator keeps its animation, evolution-map UX (drag-to-pan with bounds, a widened zoom range, clearer node labels), and a pass over user-visible text copy.
[[PR #147](https://github.com/ai-design-2026-projects/cantucci/pull/147)]

**7. Deployment Hardening**
I fixed the backend Docker image, which was missing the `dataset` extra and crashed on CLIP model preload at startup. I baked the embedding models into the image at build time for a zero cold-start download, and split the build into a native per-arch matrix to avoid slow QEMU emulation of the large image.
[[PR #152](https://github.com/ai-design-2026-projects/cantucci/pull/152)]

## Future Developments

The current system is tightly coupled to the TMDB movie catalogue. There are several natural directions to extend and generalise the work:

1. **Domain-agnostic catalogues.** The core loop — oracle proposes a grouping, the system partitions the catalogue, the oracle refines — is not specific to movies. The architecture could be extended to support arbitrary item catalogues (books, music albums, research papers, products) by abstracting the embedding pipeline and making the metadata schema configurable. The main challenge is that the current prompts reference movie-specific attributes (genre, director, release year); these would need to be made dynamic.

2. **Intent agent improvements.** The intent agent is currently a bottleneck for complex operations. It struggles to parse multi-step instructions (e.g. "merge these two clusters and then focus on the first one") and often drops important details. A more robust parsing logic, potentially with a secondary verification step or a more structured output format, would make the interaction smoother and more powerful.

3. **Dataset diversity and scale.** Testing on a single curated catalogue limits what we can learn about the system's behaviour. Experimenting with catalogues of different sizes, attribute densities, and domain characteristics would surface edge cases in the clustering and labelling agents and help calibrate cost-limit settings.
