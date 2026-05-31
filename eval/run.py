"""CLI entry point for the evaluation run harness.

Usage:
    # Run all bundles in eval/personas/ (parallel, with progress bar):
    python -m eval.run --all --run-name <name> --seeds <int> [<int> ...]  [--condition <cond>]

    # Run specific persona(s):
    python -m eval.run --persona <slug> --run-name <name> --seeds <int> [<int> ...] [--condition <cond>]
    python -m eval.run --personas <slug> [<slug> ...] --run-name <name> --seeds <int> [<int> ...] [--condition <cond>]

    # Bind to an existing run by UUID instead of name:
    python -m eval.run --persona <slug> --run <uuid> --seeds <int> [<int> ...]

    # Re-score an existing conversation (idempotent):
    python -m eval.run --evaluate-only <conversation_id> [--ground-truth <slug>]
"""
import argparse
import asyncio
import logging
import sys
import uuid

from backend.logging_setup import configure_logging
from backend.settings import get_config_hash, get_config_snapshot

log = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run",
        description="Run simulated oracle sessions and evaluate them.",
    )

    evaluate_only = parser.add_argument_group("re-score only")
    evaluate_only.add_argument(
        "--evaluate-only",
        default=None,
        metavar="CONVERSATION_UUID",
        help="Re-score an existing conversation (idempotent). Skips simulation.",
    )
    evaluate_only.add_argument(
        "--ground-truth",
        default=None,
        dest="ground_truth",
        help="Ground truth slug for --evaluate-only (enables operation_recall).",
    )

    persona_sel = parser.add_mutually_exclusive_group()
    persona_sel.add_argument("--persona", default=None, metavar="SLUG", help="Single persona slug.")
    persona_sel.add_argument("--personas", nargs="+", default=None, metavar="SLUG", help="One or more persona slugs.")
    persona_sel.add_argument("--all", action="store_true", help="Use all bundles in eval/personas/.")

    run_sel = parser.add_mutually_exclusive_group()
    run_sel.add_argument(
        "--run-name",
        default=None,
        dest="run_name",
        help="Run name — auto-creates a run if it does not exist; uses the most recent if multiple exist.",
    )
    run_sel.add_argument("--run", default=None, help="Existing run UUID.")

    parser.add_argument("--seeds", type=int, nargs="+", default=None, help="One or more RNG seeds.")
    parser.add_argument(
        "--condition",
        default="conversational",
        choices=["conversational", "monolithic"],
        help="Experimental condition (default: conversational).",
    )

    return parser


def _resolve_run_id(args: argparse.Namespace) -> uuid.UUID:
    """Resolve or create the run_id from CLI args."""
    from backend.data_access.eval.queries import (
        count_runs_by_name,
        create_run,
        get_run_by_name,
    )
    from eval.config import load_eval_harness_config

    harness_cfg = load_eval_harness_config()

    if args.run is not None:
        return uuid.UUID(args.run)

    name = args.run_name
    n = count_runs_by_name(name)
    if n == 0:
        run_id = create_run(
            config_hash=get_config_hash(),
            config_snapshot=get_config_snapshot(),
            seed=harness_cfg.runner.run_seed,
            name=name,
            condition=args.condition,
        )
        print(f"created run name={name!r} run_id={run_id}")
        return run_id
    if n > 1:
        log.warning("multiple_runs_with_same_name", extra={"name": name, "count": n})
        print(f"warning: {n} runs named {name!r} — using most recent", file=sys.stderr)
    row = get_run_by_name(name)
    print(f"resolved run name={name!r} run_id={row.run_id}")
    return row.run_id


async def _cmd_evaluate_only(args: argparse.Namespace) -> None:
    from eval.runtime.evaluate import evaluate_conversation

    conversation_id = uuid.UUID(args.evaluate_only)
    await evaluate_conversation(
        conversation_id=conversation_id,
        ground_truth_slug=args.ground_truth,
    )
    print(f"evaluated conversation_id={conversation_id}")


async def _cmd_run(args: argparse.Namespace) -> None:
    from eval.runtime.batch import run_all_personas, run_personas

    if args.seeds is None:
        print("error: --seeds is required for simulation runs", file=sys.stderr)
        sys.exit(1)

    run_id = _resolve_run_id(args)

    if args.all:
        conversation_ids = await run_all_personas(
            run_id=run_id,
            seeds=args.seeds,
            condition=args.condition,
        )
    else:
        slugs = [args.persona] if args.persona else (args.personas or [])
        if not slugs:
            print("error: specify --persona, --personas, or --all", file=sys.stderr)
            sys.exit(1)
        conversation_ids = await run_personas(
            run_id=run_id,
            slugs=slugs,
            seeds=args.seeds,
            condition=args.condition,
        )

    for conv_id in conversation_ids:
        print(f"conversation_id={conv_id}")
    print(f"\n{len(conversation_ids)} session(s) completed.")


async def _main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.evaluate_only is not None:
        await _cmd_evaluate_only(args)
    elif args.persona is not None or args.personas is not None or args.all:
        if args.run is None and args.run_name is None:
            print("error: specify --run or --run-name when simulating", file=sys.stderr)
            sys.exit(1)
        await _cmd_run(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(_main())
    finally:
        from backend.data_access.connection import close_pool
        close_pool()
