from dataclasses import dataclass


@dataclass
class ExplanationResult:
    """Result of the explanation agent.

    Attributes:
        text:        Human-readable explanation text to return to the user.
        movie_title: Title of the movie being explained.
        cluster_label: Label of the cluster being explained.
    """
    text: str
    movie_title: str
    cluster_label: str
