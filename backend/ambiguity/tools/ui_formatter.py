"""Stub for the UI formatter tool used by the Ambiguity Agent.

Future: render the question as button chips, forced-choice cards, or other
UI-specific formats.  Currently returns a plain dict passthrough.
"""

import logging

log = logging.getLogger(__name__)


def format(question_text: str, ui_format: str) -> dict[str, str]:
    """Return a UI-ready payload for *question_text* (passthrough stub).

    Args:
        question_text: The question to surface to the oracle.
        ui_format:     Rendering hint (e.g. ``"binary"``, ``"forced_choice"``).

    Returns:
        Dict with ``text`` and ``ui`` keys.  No transformation yet.
    """
    log.warning("ui_formatter not yet implemented — returning passthrough")
    return {"text": question_text, "ui": ui_format}
