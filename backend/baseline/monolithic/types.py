from pydantic import BaseModel


class MonolithicCluster(BaseModel):
    """A single cluster proposed by the monolithic LLM.

    Attributes:
        label:     Human-readable cluster label.
        summary:   One-sentence description.
        movie_ids: TMDB integer IDs of member movies.
    """
    label: str
    summary: str | None = None
    movie_ids: list[int]


class MonolithicLLMResponse(BaseModel):
    """Structured output from the monolithic LLM turn.

    Attributes:
        reply:    Reply text to send back to the oracle.
        clusters: Proposed cluster partition of the catalogue.
    """
    reply: str
    clusters: list[MonolithicCluster]
