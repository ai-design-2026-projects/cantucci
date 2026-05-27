"""CLI entry point for the evaluation harness.

Usage:
    python -m eval.run simulate --run <run_id> --persona <slug> --ground-truth <slug> --seed <int>
    python -m eval.run evaluate --conversation <conversation_id> [--ground-truth <slug>]
    python -m eval.run create-run [--name <name>] [--condition <cond>] [--notes <text>]
"""
import argparse
import asyncio
import logging
import sys
import uuid

from backend.logging_setup import configure_logging
from backend.settings import get_config_hash, get_config_snapshot


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.run",
        description="CinePal evaluation harness — simulate oracle sessions and score conversations.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    create_run_cmd = sub.add_parser("create-run", help="Register a new eval run and print its UUID.")
    create_run_cmd.add_argument("--name", default=None)
    create_run_cmd.add_argument("--condition", default="conversational", choices=["conversational", "baseline", "human"])
    create_run_cmd.add_argument("--notes", default=None)

    simulate_cmd = sub.add_parser("simulate", help="Drive one simulated oracle session and evaluate it.")
    simulate_cmd.add_argument("--run", required=True, help="Run UUID.")
    simulate_cmd.add_argument("--persona", required=True, help="Persona slug.")
    simulate_cmd.add_argument("--ground-truth", required=True, dest="ground_truth", help="Ground truth slug.")
    simulate_cmd.add_argument("--seed", type=int, required=True, help="RNG seed.")

    evaluate_cmd = sub.add_parser("evaluate", help="Score an existing conversation (idempotent).")
    evaluate_cmd.add_argument("--conversation", required=True, help="Conversation UUID.")
    evaluate_cmd.add_argument("--ground-truth", default=None, dest="ground_truth", help="Ground truth slug (optional).")

    return parser


async def _cmd_create_run(args: argparse.Namespace) -> None:
    from backend.data_access.evaluation.queries import create_run

    run_id = create_run(
        config_hash=get_config_hash(),
        config_snapshot=get_config_snapshot(),
        seed=0,
        name=args.name,
        condition=args.condition,
        notes=args.notes,
    )
    print(str(run_id))


async def _cmd_simulate(args: argparse.Namespace) -> None:
    from eval.runner import run_simulated_session

    run_id = uuid.UUID(args.run)
    conversation_id = await run_simulated_session(
        run_id=run_id,
        persona_slug=args.persona,
        ground_truth_slug=args.ground_truth,
        seed=args.seed,
    )
    print(f"conversation_id={conversation_id}")


async def _cmd_evaluate(args: argparse.Namespace) -> None:
    from eval.runner import evaluate_conversation

    conversation_id = uuid.UUID(args.conversation)
    await evaluate_conversation(
        conversation_id=conversation_id,
        ground_truth_slug=args.ground_truth,
    )
    print(f"evaluated conversation_id={conversation_id}")


async def _main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "create-run":
        await _cmd_create_run(args)
    elif args.command == "simulate":
        await _cmd_simulate(args)
    elif args.command == "evaluate":
        await _cmd_evaluate(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
