"""File-backed persona bundle store.

Bundle YAML files under ``eval/personas/`` are the canonical source of truth.
Postgres rows (``personas`` + ``ground_truths`` tables) are derived from files
via ``upsert_bundle`` at run time — idempotent and fail-loud on slug conflicts.
"""
import json
import logging
import uuid
from pathlib import Path

import yaml

from backend.data_access.eval.queries import (
    create_ground_truth,
    create_persona,
    get_ground_truth_by_slug,
    get_persona_by_slug,
)
from eval.personas.types import PersonaBundle
from eval.types import PERSONAS_DIR

log = logging.getLogger(__name__)


def _bundle_path(slug: str) -> Path:
    return PERSONAS_DIR / f"{slug}.yaml"


def write_bundle(bundle: PersonaBundle) -> Path:
    """Serialise a bundle to ``eval/personas/<slug>.yaml``.

    Creates the directory if it does not exist. Overwrites any existing file with
    the same slug (use ``load_bundle`` first to check before overwriting).

    Args:
        bundle: The bundle to persist.

    Returns:
        Path of the written file.
    """
    PERSONAS_DIR.mkdir(parents=True, exist_ok=True)
    path = _bundle_path(bundle.slug)
    path.write_text(yaml.safe_dump(bundle.to_dict(), allow_unicode=True, sort_keys=False), encoding="utf-8")
    log.info("bundle_written", extra={"slug": bundle.slug, "path": str(path)})
    return path


def load_bundle(slug: str) -> PersonaBundle:
    """Load a bundle from ``eval/personas/<slug>.yaml``.

    Args:
        slug: Bundle slug to load.

    Returns:
        Deserialised ``PersonaBundle``.

    Raises:
        FileNotFoundError: If no bundle file exists for this slug.
    """
    path = _bundle_path(slug)
    if not path.exists():
        raise FileNotFoundError(f"bundle not found: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return PersonaBundle.from_dict(data)


def list_bundles() -> list[PersonaBundle]:
    """Return all bundles found in the personas directory, sorted by slug.

    Returns:
        List of ``PersonaBundle`` instances. Empty list when the directory does not
        exist or contains no YAML files.
    """
    if not PERSONAS_DIR.exists():
        return []
    bundles = []
    for path in sorted(PERSONAS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        bundles.append(PersonaBundle.from_dict(data))
    return bundles


def upsert_bundle(bundle: PersonaBundle) -> tuple[uuid.UUID, uuid.UUID]:
    """Idempotently ensure the bundle has matching rows in the DB.

    Creates ``personas`` and ``ground_truths`` rows when absent.  Raises when a
    row exists under the same slug but with a different ``prompt_hash`` — this
    indicates a stale DB row that would silently diverge from the file.

    Args:
        bundle: The bundle to sync to the DB.

    Returns:
        Tuple of ``(persona_id, ground_truth_id)``.

    Raises:
        ValueError: If either a persona or a GT row already exists under this slug
                    with a different ``prompt_hash`` than the bundle (conflict detected).
    """
    existing_persona = get_persona_by_slug(bundle.slug)
    if existing_persona is None:
        persona_id = create_persona(
            slug=bundle.slug,
            verbosity=bundle.verbosity,
            patience=bundle.patience,
        )
        log.info("persona_created_from_bundle", extra={"slug": bundle.slug, "persona_id": str(persona_id)})
    else:
        persona_id = existing_persona.id
        log.debug("persona_already_exists", extra={"slug": bundle.slug, "persona_id": str(persona_id)})

    existing_gt = get_ground_truth_by_slug(bundle.slug)
    if existing_gt is None:
        operations = [
            {"op": op.op, "concept": op.concept, **({"kind": op.kind} if op.kind else {}), **({"space": op.space} if op.space else {})}
            for op in bundle.operations
        ]
        ground_truth_id = create_ground_truth(
            slug=bundle.slug,
            intent_description=bundle.intent_description,
            operations=operations,
            prompt_hash=bundle.prompt_hash,
        )
        log.info("ground_truth_created_from_bundle", extra={"slug": bundle.slug, "ground_truth_id": str(ground_truth_id)})
    else:
        if existing_gt.prompt_hash != bundle.prompt_hash:
            raise ValueError(
                f"bundle slug {bundle.slug!r} already exists in the DB with a different prompt_hash "
                f"(db={existing_gt.prompt_hash[:8]!r}, file={bundle.prompt_hash[:8]!r}). "
                "Create a new bundle with a different slug rather than mutating an existing one."
            )
        ground_truth_id = existing_gt.id
        log.debug("ground_truth_already_exists", extra={"slug": bundle.slug, "ground_truth_id": str(ground_truth_id)})

    return persona_id, ground_truth_id
