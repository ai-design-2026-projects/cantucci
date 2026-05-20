"""Pure helper: prepare prompt variables from prior profile and recent turns.

No LLM calls, no DB access.
"""

from typing import Any

from backend.repository.sessions import TurnRow


def build_prompt_vars(
    *,
    user_message: str,
    prior_profile: dict[str, Any] | None,
    recent_turns: list[TurnRow],
) -> dict[str, Any]:
    """Build template variables for the profile_extract_v2.j2 prompt.

    Args:
        user_message:  Oracle's message for the current turn.
        prior_profile: Previously persisted profile dict, or None on the first
                       turn (no prior profile exists yet).
        recent_turns:  Up to 2 most recent completed turns (short history).

    Returns:
        Dict of template variables ready for Jinja2 rendering.
    """
    prior: dict[str, Any] = prior_profile or {
        "constraints": [],
        "preferences": [],
        "attitudes": [],
        "summary": "",
    }
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
