"""Parallel evaluation batch runner with Rich progress bar.

Runs multiple (persona, seed) pairs concurrently, bounded by ``max_parallel``
from the harness config.  Single-persona debug runs use the same code path with
a list of length 1.
"""
import asyncio
import logging
import uuid

from rich.progress import BarColumn, Progress, SpinnerColumn, TaskProgressColumn, TextColumn, TimeElapsedColumn

from eval.config import load_eval_harness_config
from eval.personas.store import list_bundles, load_bundle, upsert_bundle
from eval.runtime.session import run_simulated_session

log = logging.getLogger(__name__)


async def run_personas(
    run_id: uuid.UUID,
    slugs: list[str],
    seeds: list[int],
    condition: str = "conversational",
) -> list[uuid.UUID]:
    """Run all (slug, seed) combinations in parallel, with a progress bar.

    Upserts each bundle into the DB before running, then dispatches all
    ``(slug, seed)`` pairs concurrently, bounded by ``runner.max_parallel`` from
    ``eval/eval.yaml``.

    Args:
        run_id:    Parent eval run UUID.
        slugs:     Persona bundle slugs to evaluate.
        seeds:     RNG seeds to use for each slug.
        condition: Experimental condition string.

    Returns:
        List of conversation UUIDs created (one per ``(slug, seed)`` pair that succeeded).
        Any exceptions are logged and re-raised after all tasks finish.
    """
    harness_cfg = load_eval_harness_config()
    semaphore = asyncio.Semaphore(harness_cfg.runner.max_parallel)

    pairs: list[tuple[str, int]] = [(slug, seed) for slug in slugs for seed in seeds]
    if not pairs:
        raise ValueError("no (slug, seed) pairs to run")

    for slug in slugs:
        bundle = load_bundle(slug)
        upsert_bundle(bundle)

    conversation_ids: list[uuid.UUID] = []
    errors: list[tuple[str, int, BaseException]] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        TimeElapsedColumn(),
    ) as progress:
        task = progress.add_task("Running sessions…", total=len(pairs))

        async def _one(slug: str, seed: int) -> uuid.UUID | None:
            async with semaphore:
                progress.update(task, description=f"[{slug}  seed={seed}] running…")
                try:
                    conv_id = await run_simulated_session(
                        run_id=run_id,
                        persona_slug=slug,
                        ground_truth_slug=slug,
                        seed=seed,
                        condition=condition,
                    )
                    progress.update(task, description=f"[{slug}  seed={seed}] done ✓")
                    return conv_id
                except Exception as exc:
                    log.error(
                        "session_failed",
                        extra={"slug": slug, "seed": seed, "error": str(exc)},
                        exc_info=True,
                    )
                    errors.append((slug, seed, exc))
                    return None
                finally:
                    progress.advance(task)

        results = await asyncio.gather(*[_one(slug, seed) for slug, seed in pairs])

    for conv_id in results:
        if conv_id is not None:
            conversation_ids.append(conv_id)

    if errors:
        summary = "; ".join(f"{slug}:seed={seed}" for slug, seed, _ in errors)
        raise RuntimeError(
            f"{len(errors)} session(s) failed: {summary}. "
            "Check logs for details."
        )

    log.info(
        "batch_complete",
        extra={"n_pairs": len(pairs), "n_conversations": len(conversation_ids)},
    )
    return conversation_ids


async def run_all_personas(
    run_id: uuid.UUID,
    seeds: list[int],
    condition: str = "conversational",
) -> list[uuid.UUID]:
    """Run all bundles found in the personas directory.

    Equivalent to passing all bundle slugs to ``run_personas``.

    Args:
        run_id:    Parent eval run UUID.
        seeds:     RNG seeds to use for each bundle.
        condition: Experimental condition string.

    Returns:
        List of conversation UUIDs created.

    Raises:
        ValueError: If no bundles are found in the personas directory.
    """
    bundles = list_bundles()
    if not bundles:
        raise ValueError("no bundles found in eval/personas/ — run 'python -m eval.builder' first")
    slugs = [b.slug for b in bundles]
    log.info("running_all_personas", extra={"n_bundles": len(slugs), "seeds": seeds})
    return await run_personas(run_id, slugs, seeds, condition)
