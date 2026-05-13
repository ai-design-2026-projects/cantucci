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