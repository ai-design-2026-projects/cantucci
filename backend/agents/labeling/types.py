from dataclasses import dataclass

from pydantic import BaseModel


@dataclass(frozen=True, slots=True)
class LabelResult:
    """Output of the Labeling agent.

    Attributes:
        label:   Short 2–4-word label for the cluster theme.
        summary: One-sentence description of the cluster's semantic theme, or None on failure.
    """
    label: str
    summary: str | None

    @classmethod
    def from_llm_response(cls, parsed: BaseModel) -> "LabelResult":
        """Construct from a structured LLM response.

        Args:
            parsed: Pydantic-validated payload with ``label`` and ``summary`` fields.
        """
        return cls(
            label=parsed.label,  # type: ignore[attr-defined]
            summary=parsed.summary,  # type: ignore[attr-defined]
        )
