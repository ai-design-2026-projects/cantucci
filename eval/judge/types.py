from dataclasses import dataclass
from dataclasses import field

from pydantic import BaseModel

from backend.llm.exceptions import LLMParseError


@dataclass(frozen=True, slots=True)
class AxisConceptContext:
    """Context about a single concept axis built during a session, fed to the judge.

    Attributes:
        concept_name:   Human-readable concept name (e.g. ``"emotional tone"``).
        positive_label: Short label for the HIGH end of the axis.
        negative_label: Short label for the LOW end of the axis.
        space:          Embedding space used (``"semantic"`` or ``"visual"``).
        high_pole_films: Up to 5 film titles from the highest-scoring end of the axis.
        low_pole_films:  Up to 5 film titles from the lowest-scoring end of the axis.
    """
    concept_name: str
    positive_label: str
    negative_label: str
    space: str
    high_pole_films: list[str] = field(default_factory=list)
    low_pole_films: list[str] = field(default_factory=list)


class JudgeDimensionScore(BaseModel):
    """A single dimension score within a judge LLM response.

    Attributes:
        dimension: Judge dimension name.
        score:     Integer score in [1, 5].
        rationale: One-sentence rationale from the judge.
    """
    dimension: str
    score: int
    rationale: str


class JudgeLLMResponse(BaseModel):
    """Structured output from the judge LLM call.

    Attributes:
        scores: One score entry per evaluated dimension.
    """
    scores: list[JudgeDimensionScore]


@dataclass(frozen=True, slots=True)
class JudgeResult:
    """Validated judge scores for a completed conversation.

    Attributes:
        scores:      Dict mapping dimension name to (score, rationale).
        cost:        LLM cost in USD for the judge call.
        prompt_hash: SHA-256 hex of the rendered judge prompt (for audit).
    """
    scores: dict[str, tuple[int, str]]
    cost: float
    prompt_hash: str

    @classmethod
    def from_llm_response(
        cls,
        parsed: JudgeLLMResponse,
        expected_dimensions: list[str],
        cost: float,
        prompt_hash: str,
    ) -> "JudgeResult":
        """Construct and validate a JudgeResult from the structured LLM response.

        Args:
            parsed:               Pydantic-validated judge payload.
            expected_dimensions:  Ordered list of dimension names to expect.
            cost:                 LLM cost in USD.
            prompt_hash:          SHA-256 hex of the rendered judge prompt.

        Raises:
            LLMParseError: If any expected dimension is missing or any score is
                           outside the [1, 5] range.
        """
        received = {item.dimension: item for item in parsed.scores}

        for dim in expected_dimensions:
            if dim not in received:
                raise LLMParseError(
                    step_type="judge",
                    raw=f"missing dimension {dim!r} in judge response",
                )

        scores: dict[str, tuple[int, str]] = {}
        for dim in expected_dimensions:
            item = received[dim]
            if not (1 <= item.score <= 5):
                raise LLMParseError(
                    step_type="judge",
                    raw=f"score {item.score} out of range [1, 5] for dimension {dim!r}",
                )
            scores[dim] = (item.score, item.rationale)

        return cls(scores=scores, cost=cost, prompt_hash=prompt_hash)
