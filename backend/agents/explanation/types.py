from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ExplanationResult:
    """Result of the explanation agent.

    Attributes:
        text:          Human-readable explanation text to return to the user.
        movie_title:   Title of the movie being explained.
        cluster_label: Label of the cluster being explained.
        cost:          LLM cost in USD for this call.
    """
    text: str
    movie_title: str
    cluster_label: str
    cost: float = 0.0

    @classmethod
    def from_llm_response(
        cls, content: str, movie_title: str, cluster_label: str, cost: float = 0.0
    ) -> "ExplanationResult":
        """Construct from a plain-text LLM response.

        Args:
            content:       Raw text produced by the model.
            movie_title:   Title of the movie being explained.
            cluster_label: Label of the cluster being explained.
            cost:          LLM cost in USD.
        """
        return cls(text=content, movie_title=movie_title, cluster_label=cluster_label, cost=cost)
