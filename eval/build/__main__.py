"""CLI entry point for the bundle builder.

Usage:
    # Random batch (n bundles with randomised themes and dials):
    python -m eval.build --count 5

    # Single explicit bundle:
    python -m eval.build --slug exploration_v1 --verbosity medium --patience 0.7 --hint "psychological thrillers"
    python -m eval.build --slug action_v1 --hint "action films, exclude superhero"
"""
import argparse
import asyncio
import sys

from backend.logging_setup import configure_logging


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m eval.build",
        description="Build persona + ground-truth bundles for the eval harness.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--count",
        type=int,
        metavar="N",
        help="Build N bundles with randomised themes and dials (slugs: rand-001…).",
    )
    mode.add_argument(
        "--slug",
        metavar="SLUG",
        help="Build a single bundle with this slug.",
    )

    parser.add_argument(
        "--verbosity",
        default="medium",
        choices=["terse", "medium", "verbose"],
        help="Oracle verbosity dial (only used with --slug; default: medium).",
    )
    parser.add_argument(
        "--patience",
        type=float,
        default=0.7,
        help="Oracle patience in [0, 1] (only used with --slug; default: 0.7).",
    )
    parser.add_argument(
        "--hint",
        default=None,
        help="Optional theme hint injected into the prompt.",
    )
    return parser


async def _main() -> None:
    configure_logging()
    parser = _build_parser()
    args = parser.parse_args()

    from eval.build.builder import build_bundle, build_random_batch

    if args.count is not None:
        bundles = await build_random_batch(args.count)
        print(f"\n{len(bundles)} bundle(s) written to eval/personas/conf/")
    else:
        bundle = await build_bundle(
            args.slug,
            verbosity=args.verbosity,
            patience=args.patience,
            hint=args.hint,
        )
        from eval.types import PERSONAS_DIR
        path = PERSONAS_DIR / f"{bundle.slug}.yaml"
        print(f"slug={bundle.slug}  ops={len(bundle.operations)}  path={path}")


if __name__ == "__main__":
    asyncio.run(_main())
