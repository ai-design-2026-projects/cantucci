"""CLI entry point for the evaluation harness.

Usage:
    python -m eval.run create-persona --slug <slug> [--verbosity terse|medium|verbose] [--patience <float>]
    python -m eval.run create-run [--name <name>] [--condition <cond>] [--notes <text>]
    python -m eval.run simulate (--run <run_id> | --run-name <name>) --persona <slug> --ground-truth <slug> (--seed <int> | --seeds <int> [<int> ...]) [--condition <cond>]
    python -m eval.run evaluate --conversation <conversation_id> [--ground-truth <slug>]
    python -m eval.run build-gt --slug <slug> [--hint <text>]

When --run-name is used, the most-recent run with that name is resolved.  If no
run exists with that name a new one is created automatically.  Pass --seeds with
multiple integers to run several sessions concurrently in a single invocation.
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

    create_persona_cmd = sub.add_parser("create-persona", help="Register an oracle persona and print its UUID.")
    create_persona_cmd.add_argument("--slug", required=True, help="Unique persona identifier.")
    create_persona_cmd.add_argument(
        "--verbosity",
        default="medium",
        choices=["terse", "medium", "verbose"],
        help="Reply-length dial (default: medium).",
    )
    create_persona_cmd.add_argument(
        "--patience",
        type=float,
        default=0.5,
        help="Willingness to continue after misbehaviour, [0, 1] (default: 0.5).",
    )

    create_run_cmd = sub.add_parser("create-run", help="Register a new eval run and print its UUID.")
    create_run_cmd.add_argument("--name", default=None)
    create_run_cmd.add_argument(
        "--condition",
        default="conversational",
        choices=["conversational", "no_agents", "monolithic", "human"],
    )
    create_run_cmd.add_argument("--notes", default=None)

    simulate_cmd = sub.add_parser("simulate", help="Drive one or more simulated oracle sessions and evaluate them.")
    run_group = simulate_cmd.add_mutually_exclusive_group(required=True)
    run_group.add_argument("--run", default=None, help="Run UUID.")
    run_group.add_argument("--run-name", default=None, dest="run_name", help="Run name (creates one if it doesn't exist).")
    simulate_cmd.add_argument("--persona", required=True, help="Persona slug.")
    simulate_cmd.add_argument("--ground-truth", required=True, dest="ground_truth", help="Ground truth slug.")
    seed_group = simulate_cmd.add_mutually_exclusive_group(required=True)
    seed_group.add_argument("--seed", type=int, default=None, help="Single RNG seed.")
    seed_group.add_argument("--seeds", type=int, nargs="+", default=None, help="One or more RNG seeds (runs concurrently).")
    simulate_cmd.add_argument(
        "--condition",
        default="conversational",
        choices=["conversational", "no_agents", "monolithic"],
    )

    evaluate_cmd = sub.add_parser("evaluate", help="Score an existing conversation (idempotent).")
    evaluate_cmd.add_argument("--conversation", required=True, help="Conversation UUID.")
    evaluate_cmd.add_argument(
        "--ground-truth", default=None, dest="ground_truth", help="Ground truth slug (optional)."
    )

    build_gt_cmd = sub.add_parser("build-gt", help="Build and persist a ground truth trajectory.")
    build_gt_cmd.add_argument("--slug", required=True, help="Unique slug for the new ground truth.")
    build_gt_cmd.add_argument("--hint", default=None, help="Optional free-text exploration hint.")

    return parser


async def _cmd_create_persona(args: argparse.Namespace) -> None:
    from backend.data_access.eval.queries import create_persona

    persona_id = create_persona(
        slug=args.slug,
        verbosity=args.verbosity,
        patience=args.patience,
    )
    print(str(persona_id))


async def _cmd_create_run(args: argparse.Namespace) -> None:
    from backend.data_access.eval.queries import create_run

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
    from backend.data_access.eval.queries import (
        count_runs_by_name,
        create_run,
        get_run_by_name,
    )
    from eval.runner import run_simulated_session

    if args.run_name is not None:
        n = count_runs_by_name(args.run_name)
        if n == 0:
            run_id = create_run(
                config_hash=get_config_hash(),
                config_snapshot=get_config_snapshot(),
                seed=0,
                name=args.run_name,
                condition=args.condition,
            )
            print(f"created run name={args.run_name!r} run_id={run_id}")
        else:
            if n > 1:
                logging.getLogger(__name__).warning(
                    "multiple_runs_with_same_name",
                    extra={"name": args.run_name, "count": n},
                )
                print(f"warning: {n} runs named {args.run_name!r} — using most recent")
            row = get_run_by_name(args.run_name)
            run_id = row.run_id
            print(f"resolved run name={args.run_name!r} run_id={run_id}")
    else:
        run_id = uuid.UUID(args.run)

    seeds: list[int] = args.seeds if args.seeds is not None else [args.seed]

    async def _one(seed: int) -> None:
        conversation_id = await run_simulated_session(
            run_id=run_id,
            persona_slug=args.persona,
            ground_truth_slug=args.ground_truth,
            seed=seed,
            condition=args.condition,
        )
        print(f"seed={seed} conversation_id={conversation_id}")

    await asyncio.gather(*[_one(s) for s in seeds])


async def _cmd_evaluate(args: argparse.Namespace) -> None:
    from eval.runner import evaluate_conversation

    conversation_id = uuid.UUID(args.conversation)
    await evaluate_conversation(
        conversation_id=conversation_id,
        ground_truth_slug=args.ground_truth,
    )
    print(f"evaluated conversation_id={conversation_id}")


async def _cmd_build_gt(args: argparse.Namespace) -> None:
    from eval.ground_truths.builder import build_ground_truth

    row = await build_ground_truth(slug=args.slug, hint=args.hint)
    print(f"ground_truth_id={row.id}  slug={row.slug}  ops={len(row.operations)}")


async def _main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "create-persona":
        await _cmd_create_persona(args)
    elif args.command == "create-run":
        await _cmd_create_run(args)
    elif args.command == "simulate":
        await _cmd_simulate(args)
    elif args.command == "evaluate":
        await _cmd_evaluate(args)
    elif args.command == "build-gt":
        await _cmd_build_gt(args)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(_main())
