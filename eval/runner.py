"""Eval pipeline runner — CLI entry point.

Creates an experiment run, drives the cross-product of
``(ground_truth × persona × seed)`` via the Oracle and CinePal HTTP API,
writes ``session_metrics`` and ``judge_scores`` for each session, and
finalises the run.

Usage::

    python -m eval.runner \\
        --condition baseline \\
        --ground-truths all \\
        --personas all \\
        --seeds 1,2,3 \\
        [--base-url http://localhost:8000] \\
        [--dry-run]

The ``--dry-run`` flag enables ``LLMGateway`` fixture mode so the pipeline can
be exercised end-to-end without live LLM calls.  It does not suppress HTTP
calls to the CinePal API — start the API server first.
"""

import argparse
import asyncio
import logging
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from uuid import UUID

from backend.repository.runs import create_run, finalize_run
from backend.logging_setup import configure_logging
from backend.orchestrator.turn.progress import ClusterSnapshotEvent, ResultEvent, ErrorEvent
from backend.settings import CONFIGS_DIR, PROJECT_ROOT, get_config_hash, get_config_snapshot, get_settings
from eval.judge.judge import Judge
from eval.oracle.oracle import Oracle
from eval.shared.ground_truths import GroundTruth, load_all_ground_truths, load_ground_truth
from eval.shared.http_client import CinePalClient
from eval.shared.llm_gateway import LLMGateway
from eval.shared.personas import PersonaProfile, load_all_personas, load_persona

log = logging.getLogger(__name__)

_ORACLE_PROMPTS_DIR = PROJECT_ROOT / "eval" / "oracle" / "prompts"
_JUDGE_PROMPTS_DIR = PROJECT_ROOT / "eval" / "judge" / "prompts"


async def _run_session(
    *,
    gt: GroundTruth,
    persona: PersonaProfile,
    session_seed: int,
    oracle_llm: LLMGateway,
    judge: Judge,
    client: CinePalClient,
    run_id: UUID,
) -> None:
    """Drive one eval session from creation through scoring.

    Args:
        gt:           Full ground truth (oracle view for the Oracle; GT IDs for metrics).
        persona:      Persona profile (communication style overlay).
        session_seed: Per-session integer seed for ``BehaviorRng``.
        oracle_llm:   LLM gateway for the Oracle (shared budget per run).
        judge:        Judge instance (shared across sessions in a run).
        client:       CinePal HTTP client.
        run_id:       Experiment run UUID.
    """
    oracle = Oracle(
        gt_view=gt.oracle_view(),
        persona=persona,
        llm=oracle_llm,
        prompts_dir=_ORACLE_PROMPTS_DIR,
        session_seed=session_seed,
    )

    session_dto = await client.create_session()
    session_id = session_dto.session_id
    oracle.set_ids(run_id=run_id, session_id=session_id)

    log.info(
        "eval session started session_id=%s gt=%s persona=%s seed=%d",
        session_id, gt.id, persona.id, session_seed,
    )

    opening_message = await oracle.initial_message()
    last_clusters: list = []
    drift_events = 0
    converged = False
    explicit_acceptance = False

    current_message = opening_message
    while True:
        result_turn = None
        async for event in client.stream_turn(session_id, current_message):
            if isinstance(event, ClusterSnapshotEvent):
                last_clusters = event.clusters
            elif isinstance(event, ResultEvent):
                result_turn = event.data
            elif isinstance(event, ErrorEvent):
                log.error(
                    "eval session stream error session_id=%s code=%s message=%s",
                    session_id, event.code, event.message,
                )
                raise RuntimeError(f"CinePal stream error [{event.code}]: {event.message}")

        if result_turn is None:
            raise RuntimeError(f"No ResultEvent received for session {session_id}")

        step_type = (
            result_turn.step_type.value
            if hasattr(result_turn.step_type, "value")
            else str(result_turn.step_type)
        )

        if result_turn.converged or step_type == "stop":
            converged = result_turn.converged
            break

        oracle_reply = await oracle.respond(result_turn, last_clusters)  # type: ignore[arg-type]

        if oracle_reply.intent == "accept":
            explicit_acceptance = True
            current_message = oracle_reply.message
            async for event in client.stream_turn(session_id, current_message):
                if isinstance(event, ResultEvent):
                    result_turn = event.data
                    converged = result_turn.converged
                elif isinstance(event, ErrorEvent):
                    log.error(
                        "eval acceptance turn error session_id=%s code=%s",
                        session_id, event.code,
                    )
            break

        if oracle_reply.intent == "abandon":
            log.info("oracle abandoned session_id=%s", session_id)
            break

        current_message = oracle_reply.message

    turns_to_convergence = result_turn.turn_number if converged and result_turn else None

    final_session = await client.get_session(session_id)
    await judge.score_session(
        final_session,
        gt,
        run_id=run_id,
        converged=converged,
        turns_to_convergence=turns_to_convergence,
        explicit_acceptance=explicit_acceptance,
        drift_events=drift_events,
        # TODO(eval): wire token totals once turns row carries them
        total_input_tokens=0,
        total_output_tokens=0,
        total_cost_usd=Decimal("0"),
    )

    log.info(
        "eval session done session_id=%s converged=%s turns=%s",
        session_id, converged, turns_to_convergence,
    )


async def run_eval(
    *,
    condition: str,
    ground_truths: list[GroundTruth],
    personas: list[PersonaProfile],
    seeds: list[int],
    base_url: str,
    auth_token: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run the full eval cross-product and write results to the DB.

    Args:
        condition:     Experiment condition name (e.g. ``"baseline"``).
        ground_truths: List of ground-truth specs to evaluate.
        personas:      List of persona profiles to evaluate.
        seeds:         List of integer session seeds (one session per seed per (gt, persona) pair).
        base_url:      CinePal API base URL.
        auth_token:    Optional JWT bearer token for the API.
        dry_run:       Enable LLM fixture mode.
    """
    cfg = get_settings()
    if cfg.eval is None:
        raise RuntimeError("No eval: block in active config. Add it to configs/default.yaml.")

    config_snapshot = get_config_snapshot()
    config_hash = get_config_hash()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    run_name = f"eval-{condition}-{ts}"

    n_sessions = len(ground_truths) * len(personas) * len(seeds)
    personas_summary = [{"id": p.id, "hash": p.persona_hash} for p in personas]
    gts_summary = [{"id": g.id, "hash": g.gt_hash} for g in ground_truths]

    run_id = create_run(
        name=run_name,
        condition=condition,
        config_snapshot={
            **config_snapshot,
            "_eval_ground_truths": gts_summary,
            "_eval_personas": personas_summary,
            "_eval_seeds": seeds,
        },
        config_hash=config_hash,
        seed=seeds[0] if seeds else 0,
        model_version=cfg.models.strong.name,
        notes=f"gts={[g['id'] for g in gts_summary]} personas={[p['id'] for p in personas_summary]}",
    )
    log.info("eval run created run_id=%s name=%s n_sessions=%d", run_id, run_name, n_sessions)

    oracle_llm = LLMGateway(
        model_name=cfg.eval.oracle.model.name,
        provider=cfg.eval.oracle.model.provider,
        seed=cfg.eval.oracle.model.seed,
        max_tokens=cfg.eval.oracle.model.max_tokens,
        cost_limit_usd=cfg.eval.oracle.cost_limit_usd,
        dry_run=dry_run,
        config_hash=config_hash,
    )
    judge_llm = LLMGateway(
        model_name=cfg.eval.judge.model.name,
        provider=cfg.eval.judge.model.provider,
        seed=cfg.eval.judge.model.seed,
        max_tokens=cfg.eval.judge.model.max_tokens,
        cost_limit_usd=cfg.eval.judge.cost_limit_usd,
        dry_run=dry_run,
        config_hash=config_hash,
    )
    judge = Judge(llm=judge_llm, prompts_dir=_JUDGE_PROMPTS_DIR, k=cfg.eval.metrics.k)

    run_status = "completed"
    async with CinePalClient(base_url=base_url, auth_token=auth_token) as client:
        for gt in ground_truths:
            for persona in personas:
                for seed in seeds:
                    try:
                        await _run_session(
                            gt=gt,
                            persona=persona,
                            session_seed=seed,
                            oracle_llm=oracle_llm,
                            judge=judge,
                            client=client,
                            run_id=run_id,
                        )
                    except Exception:
                        log.error(
                            "eval session failed gt=%s persona=%s seed=%d",
                            gt.id, persona.id, seed,
                            exc_info=True,
                        )
                        run_status = "aborted"

    finalize_run(run_id, run_status)  # type: ignore[arg-type]
    log.info(
        "eval run finalised run_id=%s status=%s oracle_cost=%.4f judge_cost=%.4f",
        run_id, run_status,
        oracle_llm.accumulated_cost, judge_llm.accumulated_cost,
    )


def main() -> None:
    """CLI entry point for the eval runner."""
    configure_logging()
    parser = argparse.ArgumentParser(description="Run CinePal automated evaluation.")
    parser.add_argument(
        "--condition", default="baseline",
        help="Experiment condition (baseline, uncertainty, random, boundary, popularity)"
    )
    parser.add_argument(
        "--ground-truths", default="all",
        help="Comma-separated GT IDs or 'all'"
    )
    parser.add_argument(
        "--personas", default="all",
        help="Comma-separated persona IDs or 'all'"
    )
    parser.add_argument(
        "--seeds", default="1",
        help="Comma-separated integer session seeds"
    )
    parser.add_argument(
        "--base-url", default="http://localhost:8000",
        help="CinePal API base URL"
    )
    parser.add_argument(
        "--auth-token", default=None,
        help="Bearer token for the CinePal API"
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Use LLM fixtures; skip live API calls"
    )
    args = parser.parse_args()

    gt_dir = CONFIGS_DIR / "ground_truths"
    persona_dir = CONFIGS_DIR / "personas"

    all_gts = load_all_ground_truths(gt_dir)
    all_personas = load_all_personas(persona_dir)

    if args.ground_truths == "all":
        selected_gts = all_gts
    else:
        requested = set(args.ground_truths.split(","))
        selected_gts = [g for g in all_gts if g.id in requested]
        missing = requested - {g.id for g in selected_gts}
        if missing:
            raise ValueError(f"Ground truths not found: {missing}")

    if args.personas == "all":
        selected_personas = all_personas
    else:
        requested = set(args.personas.split(","))
        selected_personas = [p for p in all_personas if p.id in requested]
        missing = requested - {p.id for p in selected_personas}
        if missing:
            raise ValueError(f"Personas not found: {missing}")

    seeds = [int(s.strip()) for s in args.seeds.split(",")]

    asyncio.run(
        run_eval(
            condition=args.condition,
            ground_truths=selected_gts,
            personas=selected_personas,
            seeds=seeds,
            base_url=args.base_url,
            auth_token=args.auth_token,
            dry_run=args.dry_run,
        )
    )


if __name__ == "__main__":
    main()
