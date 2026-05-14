# CinePal – Sprint 1 | Davide Donà

## Overview
The first sprint focused on laying the groundwork for CinePal: establishing project documentation, configuring the development environment, and delivering an initial MVP for the movie recommendation system.

## What I Did

**1. Project Documentation**
Together with Andrea, I drafted the foundational project documentation covering the problem statement, system architecture, data schema, and evaluation strategy — a reference point for the whole team going forward.
*Initial commit + [PR #15](https://github.com/ai-design-2026-projects/cantucci/issues/15)*

**2. Roadmap & Planning**
With documentation in place, we built out a detailed roadmap for the upcoming sprints. To ensure a working MVP by the end of the sprint, we broke the work down into discrete components, opened a GitHub issue for each one, and distributed them across the team. This gave us clear ownership and made progress easy to track.

**3. MVP Development**
My hands-on work centered on the following components:

- **Database Schema** – Designed and set up the schema to store movie information and session data. *[PR #18](https://github.com/ai-design-2026-projects/cantucci/issues/18)*
- **Data Ingestion Pipeline** – Built a pipeline to pull movie data from external sources (Kaggle and Hugging Face) and populate the database. *[PR #20](https://github.com/ai-design-2026-projects/cantucci/issues/20)*
- **Retrieval System** – Implemented a system to fetch relevant movie recommendations in response to user queries. *[PR #22](https://github.com/ai-design-2026-projects/cantucci/issues/22)*
- **Colab-Runnable Notebook** – Added a notebook to run the ingestion pipeline on Google Colab, bypassing the long processing times caused by the lack of a local GPU. Data is uploaded to Hugging Face and fetched from there as needed. *[PR #26](https://github.com/ai-design-2026-projects/cantucci/issues/26)*
- **Clustering Agent** – Developed an agent that takes a user query, refines it for better retrieval, fetches relevant movies, and clusters them by similarity. Each cluster is then given a generated title and summary, providing users with a more structured and insightful set of recommendations. *[PR #29](https://github.com/ai-design-2026-projects/cantucci/issues/29)*

## What's Next

Sprint 2 will focus on four main areas:

1. **Complete the architecture.** Several components are still stubs or missing entirely — notably the convergence check (currently a placeholder) and user profile handling (not yet implemented).

2. **Improve prompt engineering.** MVP prompts were kept as-is once functional, but there's clear room for improvement. The disambiguation agent produces unhelpful questions; the clustering agent would benefit from more structured prompts.

3. **Improve responsiveness.** LLM API calls make the system slow. We plan to parallelize calls across two rounds: the first running convergence check, profile computation, and retrieval+clustering simultaneously; the second (triggered if not converged) running disambiguation in parallel with cluster selection. To guide this, we'll track time and token costs per component to identify bottlenecks. We'll also explore using smaller models for less critical agents.

4. **Evaluation and experimentation setup.** At the moment, the system lacks an LLM Oracle and an LLM Judge. We will structure an experimentation setup to test the system at a larger scale and iterate on its components based on the experiment results. We will also define a set of metrics to evaluate performance and guide our iterations.

5. **Frontend & evaluation dashboard.** On the frontend, we'll show representative movies alongside disambiguation questions to help users better understand and answer them, and add loading animations to mask latency. For evaluation, we aim to set up a dashboard to visualize results and track the system's performance. This implies the need for a sort of "admin panel" to manage the experiments and present the results in a more structured way.