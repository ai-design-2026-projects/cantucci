# CinePal – Sprint 1 | Andrea Blushi

## Overview
The first sprint focused on laying the groundwork for CinePal: establishing project documentation, configuring the development environment, and delivering an initial MVP for the movie recommendation system.


## What I Did

**1. Project Documentation**
Together with Davide, I drafted the foundational project documentation covering the problem statement, system architecture, data schema, and evaluation strategy — a reference point for the whole team going forward.
*Initial commit + [PR #15](https://github.com/ai-design-2026-projects/cantucci/issues/15)*

**2. Roadmap & Planning**
With documentation in place, we built out a detailed roadmap for the upcoming sprints. To ensure a working MVP by the end of the sprint, we broke the work down into discrete components, opened a GitHub issue for each one, and distributed them across the team. This gave us clear ownership and made progress easy to track.

**3. MVP Development**
My hands-on work centered on the following components:

- **Orchestrator Agent** – Alongside the first backend components, including the initial Pydantic models, the FastAPI app, and the overall backend structure, I built the core orchestrator agent, which coordinates the system's components and interacts with the user.
*[PR #19](https://github.com/ai-design-2026-projects/cantucci/issues/19)*
- **Decision Agent** – I implemented the basis decision agent that takes the cluster agent output and along with the user query, decides if to recommend a cluster or to ask the user for more information to refine the query. 
*[PR #21](https://github.com/ai-design-2026-projects/cantucci/issues/21)*
- **Ambiguity Agent** – I developed an agent that if required, defines the sensitive boundaries titles and generates a follow-up question to the user to clarify their query and refine the search results. 
*[PR #23](https://github.com/ai-design-2026-projects/cantucci/issues/23)*
- **Minimal Frontend** – I created a minimal frontend using React to allow a human user to interact with the system in order to have a more structured overview of the system's capabilities and to test the backend components in a more user-friendly way. 
*[PR #5](https://github.com/ai-design-2026-projects/cantucci/issues/5)*

