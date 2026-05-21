"""Pure helper: prepare prompt variables from prior profile and recent turns.

No LLM calls, no DB access.
"""

from typing import Any

from backend.profile.types import UserProfile
from backend.repository.sessions import TurnRow


def build_prompt_vars(
    *,
    user_message: str,
    prior_profile: UserProfile | None,
    recent_turns: list[TurnRow],
) -> dict[str, Any]:
    """Build template variables for the profile_extract_v2.j2 prompt.

    Args:
        user_message:  Oracle's message for the current turn.
        prior_profile: Previously persisted profile, or None on the first turn.
        recent_turns:  Up to 2 most recent completed turns (short history).

    Returns:
        Dict of template variables ready for Jinja2 rendering.
    """
    prior = (prior_profile or UserProfile(constraints=[], preferences=[], attitudes=[], summary="")).model_dump()
    turns_for_prompt = [
        {
            "user": t.user_message,
            "assistant": t.assistant_message or "",
            "step_type": t.step_type or "unknown",
        }
        for t in recent_turns
    ]
    return {
        "user_message": user_message,
        "prior_profile": prior,
        "recent_turns": turns_for_prompt,
    }
