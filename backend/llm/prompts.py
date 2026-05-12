"""Prompt file loader for the cantucci backend.

All agent prompts live in ``prompts/`` at the repository root, one file per
named prompt, named ``{function}_{version}.txt`` (e.g. ``cluster_agent_v1.txt``).

Usage::

    from backend.prompts import load_prompt

    text, prompt_hash = load_prompt("cluster_agent_v1", vars={"query": user_query})
    # pass text to llm_harness as a message, pass prompt_hash for logging
"""

import hashlib
from pathlib import Path

# Resolved once at import time; stable for the process lifetime.
_PROMPTS_DIR = Path(__file__).parents[1] / "prompts"


def load_prompt(name: str, vars: dict[str, str] | None = None) -> tuple[str, str]:
    """Load and render a prompt file, returning its text and a content hash.

    Args:
        name: Prompt file stem without extension, e.g. ``"cluster_agent_v1"``.
              The file ``prompts/{name}.txt`` must exist.
        vars: Optional mapping for ``str.format_map`` substitution.
              Missing keys raise ``KeyError`` immediately (fail-loudly rule).

    Returns:
        A tuple ``(rendered_text, sha256_8char_prefix)``.  The hash covers the
        *rendered* text so that two calls with different ``vars`` produce
        different hashes.

    Raises:
        FileNotFoundError: If ``prompts/{name}.txt`` does not exist.
        KeyError: If ``vars`` is missing a placeholder used in the template.
    """
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt file not found: {path}")

    raw = path.read_text(encoding="utf-8")
    rendered = raw.format_map(vars) if vars else raw
    digest = hashlib.sha256(rendered.encode()).hexdigest()[:8]
    return rendered, digest
