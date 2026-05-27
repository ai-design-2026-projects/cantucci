# CinePal – Sprint 2 | Davide Donà

## Overview
The second sprint was dedicated to completing the system architecture, improving prompt engineering, enhancing responsiveness, and setting up the groundwork for evaluation and experimentation.

## What I Did

**1. Architecture Refactoring and bug fixes**: most of the efforts went into refactoring the architecture to allow for better readability and maintainability, and to set the stage for the parallelization of LLM calls. This involved restructuring the backend codebase, defining clearer interfaces between components, and implementing a more modular design. 
[
    [PR #30](https://github.com/ai-design-2026-projects/cantucci/pull/30),
    [PR #31](https://github.com/ai-design-2026-projects/cantucci/pull/31),
    [PR #34](https://github.com/ai-design-2026-projects/cantucci/pull/34),
    [PR #45](https://github.com/ai-design-2026-projects/cantucci/pull/45),
    [PR #54](https://github.com/ai-design-2026-projects/cantucci/pull/54),
    [PR #55](https://github.com/ai-design-2026-projects/cantucci/pull/55),
    [PR #60](https://github.com/ai-design-2026-projects/cantucci/pull/60),
    [PR #83](https://github.com/ai-design-2026-projects/cantucci/pull/83)
]

**2. Added Eval structure**

[PR #79](https://github.com/ai-design-2026-projects/cantucci/pull/79)

**3. Add CI/CD pipeline**: I set up a CI/CD pipeline using GitHub Actions to automate testing and deployment. This ensures that our codebase remains stable and that new features can be deployed seamlessly. The pipeline includes steps for running unit tests, building Docker images, and deploying to our hosting environment.
[
    [PR #36](https://github.com/ai-design-2026-projects/cantucci/pull/36),
    [PR #80](https://github.com/ai-design-2026-projects/cantucci/pull/80),
    [PR #88](https://github.com/ai-design-2026-projects/cantucci/pull/88)
]


**4. Reduce LLM latency**: I implemented several optimizations to reduce the latency of LLM calls, including model differentiation (using smaller models for simpler tasks), loading states in the frontend to improve user experience during long operations, and parallelizing LLM calls where possible. These changes significantly improved the responsiveness of the system.
[
    [PR #58](https://github.com/ai-design-2026-projects/cantucci/pull/58),
    [PR #62](https://github.com/ai-design-2026-projects/cantucci/pull/62),
    [PR #63](https://github.com/ai-design-2026-projects/cantucci/pull/63),
    [PR #75](https://github.com/ai-design-2026-projects/cantucci/pull/75)
]


**5. Updated Dataset**: I focused on improving the dataset trying to make it more suitable for our use case. In particular, since the previous dataset was freezed in 2017, we decided to make an automated script to scrape the TMDB website and get more recent movies, to make the system more relevant and engaging for users. This involved writing a web scraper, cleaning and preprocessing the data, and updating our database with the new entries.
[
    [PR #67](https://github.com/ai-design-2026-projects/cantucci/pull/67)
]

**6. Written documentation**: Alongside my teammate, I contributed to the documentation of the system, including the API specifications and the README files for both the backend and frontend components.
[
    [PR #32](https://github.com/ai-design-2026-projects/cantucci/pull/32)
]