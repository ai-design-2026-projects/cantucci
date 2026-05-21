import hashlib
from collections.abc import Callable, Mapping
import logging
from pathlib import Path
from typing import Any
import jinja2

log = logging.getLogger(__name__)


def make_prompt_loader(
    prompts_dir: Path,
) -> Callable[[str, Mapping[str, Any] | None], tuple[str, str]]:
    """Return a prompt loader bound to *prompts_dir*.

    The returned callable resolves ``{name}.j2`` inside *prompts_dir*,
    renders the Jinja2 template with *vars*, and returns ``(rendered_text,
    sha256_8char_prefix)`` of the rendered content.

    The Jinja2 Environment is built once and closed over, so each call to
    ``make_prompt_loader`` pays the construction cost once.

    Args:
        prompts_dir: Directory containing ``.j2`` prompt templates.

    Returns:
        A ``load_prompt(name, vars)`` callable bound to *prompts_dir*.
    """
    env = jinja2.Environment(
        loader=jinja2.FileSystemLoader(str(prompts_dir)),
        undefined=jinja2.StrictUndefined,
        autoescape=False,
        keep_trailing_newline=True,
    )

    def load_prompt(
        name: str,
        vars: Mapping[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Load and render a Jinja2 prompt template.

        Args:
            name: Template stem without extension, e.g. ``"orchestrator_system_v1"``.
                  Resolves to ``{prompts_dir}/{name}.j2``.
            vars: Variables for Jinja2 substitution. Missing required variables
                  raise ``jinja2.UndefinedError`` (StrictUndefined).

        Returns:
            ``(rendered_text, sha256_8char_prefix)`` where the hash covers the
            rendered text (so two calls with different vars produce different hashes).

        Raises:
            FileNotFoundError: If ``{name}.j2`` does not exist in *prompts_dir*.
            jinja2.UndefinedError: If a required template variable is missing.
        """
        try:
            template = env.get_template(f"{name}.j2")
        except jinja2.TemplateNotFound:
            raise FileNotFoundError(
                f"Prompt template not found: {prompts_dir / name}.j2"
            )

        rendered = template.render(**(vars or {}))
        digest = hashlib.sha256(rendered.encode()).hexdigest()[:8]
        log.debug("Loaded prompt template", extra={"prompt_name": name, "hash": digest, "content": rendered})
        return rendered, digest

    return load_prompt
