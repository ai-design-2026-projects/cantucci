# CinePal - Conversational Clustering Movie Recommender System

We build a conversational movie recommendation system in which the user (the **oracle**) interacts with an AI through a chat interface to discover films that match their taste or provide a set of suggestions. 

The system does not ask the user to fill out a profile or rate movies upfront. Instead, it starts from the user's first natural-language request, proposes an initial clustering of the available movie space into meaningful groups, then refines that clustering turn by turn as the user reacts. The **clustering is the recommendation**: the user is converging toward a group of titles they want, and the system's job is to reach that group as efficiently as possible.

## Research Scope

Our main objective is to explore the following question:

> Given a candidate pool of titles, what questioning and clustering strategy minimises turns to convergence while maximising recommendation quality as judged by the oracle?

We approach this from four angles:

- **Questioning strategy**: how should the system decide what to ask at each turn, and what signals should drive that decision?
- **Cluster update strategy**: how should oracle feedback propagate into cluster boundaries, and what algorithms or heuristics best support incremental refinement?
- **Convergence and satisfaction**: how do we define and measure the point at which the system is ready to commit to a recommendation?
- **Simulated oracle evaluation**: how do we assess recommendation quality when the oracle is an LLM agent, and how far do those assessments generalise?

## What Makes This Hard

- **Feedback is inherently ambiguous.** "Too dark" could mean genre, tone, visual style, or moral content. The system must map vague natural language onto structured cluster updates without demanding clarification at every turn.
- **No ground truth for convergence.** The oracle defines success, so sessions cannot be labelled correct or incorrect independently of the user. This makes offline evaluation genuinely difficult.
- **Retrieval and clustering are confounded.** A poor candidate pool on turn 1 limits every subsequent clustering decision, but slow convergence looks identical whether the retrieval or the clustering strategy is at fault. Then, how can I know that the first retrieval is enough to support good clustering, and that the clustering is doing its job?
- **Stability vs. accuracy tension.** Cluster names and boundaries must feel consistent to the user across turns, yet the underlying content genuinely shifts as feedback narrows the pool. Too much stability means the labels lie; too much churn means the user loses their bearings.
- **Profile extraction**: how can I track and leverage the user's evolving preferences across turns, and how can I use that profile to improve retrieval and clustering in future sessions?
- **Conversation Drift**: An user might change their mind mid-session, or introduce new preferences that contradict earlier feedback. The system must be flexible enough to accommodate this without losing the thread of the conversation.
- **Already seen movies**: The user might have already seen some of the movies in the candidate pool, and their feedback might be based on that prior knowledge. The system must be able to handle this and adjust its recommendations accordingly.
- **Time and budget constraints**: The system must operate within reasonable time limits for each turn, considering also the token usage and associated costs of LLM calls. This requires efficient algorithms and careful management of resources.
- **Cognitive load**: The system must balance the amount of information presented to the user at each turn. The questions and cluster updates should be informative but not overwhelming, ensuring that the user can easily understand and engage with the recommendations.

## Key Contributions

We propose an architectural framework for conversational clustering recommenders, that tries to adress the above challenges through a modular design that separates concerns and allows for flexible experimentation with different strategies. The main components are:

- **Orchestrator**:
- **Retrieval Agent**:
- **Clustering Agent**:
- **Profile Agent**:
- **Decision Agent**:
- **State Agent**: