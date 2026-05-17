"""Types for the Profile Agent."""

from pydantic import BaseModel


class UserProfile(BaseModel):
    """Structured oracle preference profile extracted by the Profile Agent.

    Attributes:
        constraints:  Hard, non-negotiable requirements the oracle has stated
                      explicitly (e.g. "no horror", "English-language only").
        preferences:  Soft stylistic or thematic preferences (e.g. "likes slow burn",
                      "enjoys ensemble casts", "drawn to 70s aesthetics").
        attitudes:    Observable signals about how the oracle engages with the
                      process — not what they want, but how they explore (e.g.
                      "decisive", "exploratory", "open to surprises").
        summary:      1–2 sentence prose synthesis of the oracle's current taste
                      profile, suitable for injecting into other agents' prompts.
        anchor_films: Film titles the oracle named as positive anchors this turn
                      (e.g. "something like Interstellar"). Extracted by the Profile
                      Agent; merged into seen_films by the orchestrator.
        seen_films:   Accumulated list of film titles the oracle has been shown or
                      mentioned as anchors across the session. Maintained deterministically
                      by the orchestrator — the Profile Agent never writes this field.
    """

    constraints: list[str]
    preferences: list[str]
    attitudes: list[str]
    summary: str
    anchor_films: list[str] = []
    seen_films: list[str] = []
