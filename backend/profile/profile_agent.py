"""Profile Agent — extracts and updates the oracle preference profile each turn.

Makes a single LLM call (step_type="profile_extract") that reads the oracle's
latest message, the short conversation history, and the prior profile, then
returns a fully validated UserProfile.

The orchestrator calls this AFTER the main pipeline (decision/render/ambiguity)
and persists the result by overwriting sessions.preference_profile.  All other
agents on the SAME turn consume the N-1 profile (loaded from the session at turn
start); agents on the NEXT turn will see the fresh N profile.

No DB writes — the orchestrator owns all persistence.
"""

import logging
from pathlib import Path
from typing import Any
from uuid import UUID

from backend.api.types import TurnDetail
from backend.llm import llm_harness
from backend.llm.prompts import make_prompt_loader
from backend.profile.tools.profile_merger import build_prompt_vars
from backend.profile.types import UserProfile
from backend.settings import get_config_hash, get_settings

log = logging.getLogger(__name__)

load_prompt = make_prompt_loader(Path(__file__).parent / "prompts")


def extract(
    *,
    session_id: UUID,
    run_id: UUID,
    turn_id: UUID,
    turn_number: int,
    user_message: str,
    prior_profile: dict[str, Any] | None,
    recent_turns: list[TurnDetail],
    accumulated_cost_usd: float = 0.0,
    dry_run: bool = False,
) -> UserProfile:
    """Extract and return an updated preference profile for the current turn.

    Args:
        session_id:           UUID of the current session.
        run_id:               UUID of the parent run.
        turn_id:              UUID of the current turn (for log correlation).
        turn_number:          1-based turn index within the session.
        user_message:         Oracle's message for this turn.
        prior_profile:        The profile persisted from the previous turn, or None
                              on the first turn.
        recent_turns:         Up to 2 most recent completed turns (short history).
        accumulated_cost_usd: Running USD cost for the current turn (cost guard).
        dry_run:              If True, the harness returns a fixture instead of a
                              live LLM call.

    Returns:
        A validated ``UserProfile`` reflecting the oracle's updated preferences.

    Raises:
        LLMParseError:     If the model returns malformed JSON or fails schema
                           validation on every retry.
        CostLimitExceeded: If the session budget is exhausted.
    """
    cfg = get_settings()

    prompt_vars = build_prompt_vars(
        user_message=user_message,
        prior_profile=prior_profile,
        recent_turns=recent_turns,
    )

    system_text, prompt_hash = load_prompt("profile_extract_v2", prompt_vars)

    log.debug(
        "profile extract dispatch",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "turn_number": turn_number,
            "prompt_hash": prompt_hash,
            "n_recent_turns": len(recent_turns),
            "has_prior_profile": prior_profile is not None,
        },
    )

    resp = llm_harness.call(
        run_id=run_id,
        session_id=session_id,
        turn_id=turn_id,
        config_hash=get_config_hash(),
        model_and_version=cfg.model.name,
        provider=cfg.model.provider,
        seed=cfg.model.seed,
        max_tokens=cfg.model.max_tokens,
        step_type="profile_extract",
        messages=[{"role": "system", "content": system_text}],
        prompt_hash=prompt_hash,
        cost_limit_usd=cfg.session.cost_limit_usd,
        accumulated_cost_usd=accumulated_cost_usd,
        response_schema=UserProfile,
        dry_run=dry_run,
    )

    profile: UserProfile = resp.parsed  # type: ignore[assignment]

    log.info(
        "profile extracted",
        extra={
            "session_id": str(session_id),
            "turn_id": str(turn_id),
            "n_constraints": len(profile.constraints),
            "n_preferences": len(profile.preferences),
            "n_attitudes": len(profile.attitudes),
            "summary:": profile.summary,
        },
    )

    return profile
