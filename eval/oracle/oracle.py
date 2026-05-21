"""Oracle agent — humanoid user-simulator for automated eval sessions.

The Oracle embodies a taste target (``OracleGroundTruthView``) and a
communication style (``PersonaProfile``).  On each turn it:

1. Receives CinePal's ``assistant_message`` + optional ``ClusterSnapshotEvent``.
2. Optionally prepends a behavioural stage direction (drift / contradict) via
   ``BehaviorRng``.
3. Calls its ``LLMGateway`` with the full role-tagged conversation history.
4. Parses the structured JSON reply ``{"message": str, "intent": str}``.
5. Applies the acceptance gate (``BehaviorRng.acceptance_gate_open``) to
   prevent over-eager acceptance by low-decisiveness personas.

The Oracle **never** sees ``gt_movie_ids``; only ``OracleGroundTruthView.description``
is available inside this module.
"""

import hashlib
import logging
from dataclasses import dataclass
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel

from backend.llm.utils.prompts import make_prompt_loader
from backend.routers.dto.sessions.dtos import ClusterDto, TurnDto
from eval.oracle.utils.behavior import BehaviorRng
from eval.oracle.utils.memory import OracleMemory
from eval.shared.ground_truths import OracleGroundTruthView
from eval.shared.llm_gateway import LLMGateway
from eval.shared.personas import PersonaProfile

log = logging.getLogger(__name__)

_VERBOSITY_INSTRUCTIONS: dict[str, str] = {
    "terse": "Keep your reply under two sentences.",
    "medium": "Reply in 2–4 sentences.",
    "verbose": "Reply in 4–6 sentences with detail.",
}


class _OracleReplySchema(BaseModel):
    """Expected JSON output from the Oracle LLM per turn.

    Attributes:
        message: The oracle's natural-language reply to send to CinePal.
        intent:  Behavioural signal — ``continue``, ``accept``, or ``abandon``.
    """

    message: str
    intent: str


@dataclass
class OracleReply:
    """Parsed and gate-applied Oracle reply.

    Attributes:
        message: Free-text reply to POST as ``user_message`` to CinePal.
        intent:  ``"continue"`` | ``"accept"`` | ``"abandon"``.
    """

    message: str
    intent: str


class Oracle:
    """Humanoid Oracle agent driven by a ground truth and a persona profile.

    One ``Oracle`` instance is created per eval session.  It must not be
    reused across sessions — ``OracleMemory`` retains conversation history.

    Attributes:
        _gt_view:   Taste description only (no GT IDs).
        _persona:   Humanoid communication-style overlay.
        _llm:       LLM gateway with independent eval budget.
        _memory:    Per-session conversation history.
        _behavior:  Seeded RNG for per-turn behavioural nudges.
        _turn_n:    1-based turn counter, incremented after each ``respond`` call.
        _session_id: Set by the runner before the first turn; used for logging.
        _run_id:    Set by the runner; used for logging.
    """

    def __init__(
        self,
        gt_view: OracleGroundTruthView,
        persona: PersonaProfile,
        llm: LLMGateway,
        prompts_dir: Path,
        session_seed: int,
    ) -> None:
        """Initialise the Oracle.

        Args:
            gt_view:      Ground-truth view (description only).
            persona:      Persona profile (traits + dials).
            llm:          LLM gateway instance (shared across sessions in a run).
            prompts_dir:  Path to ``eval/oracle/prompts/``.
            session_seed: Per-session seed used by ``BehaviorRng``.
        """
        self._gt_view = gt_view
        self._persona = persona
        self._llm = llm
        self._load_prompt = make_prompt_loader(prompts_dir)
        self._memory = OracleMemory()
        self._behavior = BehaviorRng(
            persona_hash=persona.persona_hash,
            gt_id=gt_view.id,
            session_seed=session_seed,
        )
        self._turn_n = 0
        self._session_id: str | UUID = "unset"
        self._run_id: str | UUID = "unset"

    def set_ids(self, run_id: str | UUID, session_id: str | UUID) -> None:
        """Bind run and session IDs for structured log correlation.

        Args:
            run_id:     Experiment run UUID.
            session_id: CinePal session UUID.
        """
        self._run_id = run_id
        self._session_id = session_id

    async def initial_message(self) -> str:
        """Render the Oracle's opening message and initialise memory.

        Renders the system prompt (persona + taste description + rules) and
        produces the oracle's first free-text message to POST as
        ``user_message`` in the very first ``POST /sessions/{id}/turns`` call.

        Returns:
            The opening free-text message for the first turn.

        Raises:
            FileNotFoundError: If the system or turn prompt template is missing.
        """
        verbosity_hint = _VERBOSITY_INSTRUCTIONS.get(self._persona.dials.verbosity, "")
        decisiveness_hint = _decisiveness_to_text(self._persona.dials.decisiveness)

        system_text, system_hash = self._load_prompt(
            "oracle_system_v1",
            {
                "traits": self._persona.traits,
                "description": self._gt_view.description,
                "verbosity_hint": verbosity_hint,
                "decisiveness_hint": decisiveness_hint,
            },
        )
        self._system_hash = system_hash
        self._memory.set_system(system_text)

        opening_text, _ = self._load_prompt(
            "oracle_turn_v1",
            {
                "assistant_message": "Hello! I'm here to help you find movies you'll love. What kind of films are you in the mood for?",
                "stage_direction": None,
                "step_type": "ask",
                "has_recommendation": False,
                "recommendation_films": [],
            },
        )
        self._memory.append_user(opening_text)

        prompt_hash = hashlib.sha256(opening_text.encode()).hexdigest()[:8]
        reply_text = await self._llm.call(
            messages=self._memory.as_messages(),
            step_type="oracle",
            prompt_hash=prompt_hash,
            run_id=self._run_id,
            session_id=self._session_id,
            turn_id="initial",
            response_schema=_OracleReplySchema,
        )
        parsed = _OracleReplySchema.model_validate_json(reply_text)
        self._memory.append_assistant(reply_text)
        self._turn_n = 1
        log.info(
            "oracle initial message session_id=%s turn=1 intent=%s",
            self._session_id, parsed.intent,
        )
        return parsed.message

    async def respond(
        self,
        turn: TurnDto,
        clusters: list[ClusterDto] | None = None,
    ) -> OracleReply:
        """Generate the oracle's reply for one completed CinePal turn.

        Rolls ``BehaviorRng`` to decide whether a stage direction is injected,
        builds the user-role message, calls the LLM, parses the structured
        reply, and applies the acceptance gate.

        Args:
            turn:     The completed ``TurnDto`` returned by the NDJSON stream.
            clusters: Mid-stream ``ClusterSnapshotEvent.clusters`` if available.

        Returns:
            ``OracleReply`` with ``message`` and gated ``intent``.
        """
        self._turn_n += 1

        stage_direction: str | None = None
        if self._behavior.should_drift(self._persona.dials.drift_probability):
            stage_direction = (
                "[STAGE DIRECTION — internal, do not echo: This turn, introduce a small "
                "tangent or digression in character before returning to the topic. "
                "Stay consistent with your overall taste.]"
            )
        elif self._behavior.should_contradict(self._persona.dials.contradiction_rate):
            stage_direction = (
                "[STAGE DIRECTION — internal, do not echo: This turn, gently contradict "
                "or revise something you said earlier. Stay in character.]"
            )

        film_titles = (
            [f.title for f in turn.recommendation.films]
            if turn.recommendation else []
        )
        turn_text, _ = self._load_prompt(
            "oracle_turn_v1",
            {
                "assistant_message": turn.assistant_message,
                "stage_direction": stage_direction,
                "step_type": turn.step_type.value if hasattr(turn.step_type, "value") else str(turn.step_type),
                "has_recommendation": turn.recommendation is not None,
                "recommendation_films": film_titles,
            },
        )
        self._memory.append_user(turn_text)

        prompt_hash = hashlib.sha256(turn_text.encode()).hexdigest()[:8]
        reply_text = await self._llm.call(
            messages=self._memory.as_messages(),
            step_type="oracle",
            prompt_hash=prompt_hash,
            run_id=self._run_id,
            session_id=self._session_id,
            turn_id=str(turn.turn_id),
            response_schema=_OracleReplySchema,
        )
        parsed = _OracleReplySchema.model_validate_json(reply_text)
        self._memory.append_assistant(reply_text)

        intent = parsed.intent
        if intent == "accept" and not BehaviorRng.acceptance_gate_open(
            self._persona.dials.decisiveness, self._turn_n
        ):
            log.debug(
                "oracle acceptance gate blocked turn_n=%d decisiveness=%.2f session_id=%s",
                self._turn_n, self._persona.dials.decisiveness, self._session_id,
            )
            intent = "continue"

        log.info(
            "oracle respond session_id=%s turn=%d intent=%s",
            self._session_id, self._turn_n, intent,
        )
        return OracleReply(message=parsed.message, intent=intent)


def _decisiveness_to_text(decisiveness: float) -> str:
    """Convert the decisiveness dial to a natural-language prompt hint.

    Args:
        decisiveness: Float in ``[0.0, 1.0]``.

    Returns:
        A one-sentence instruction for the system prompt.
    """
    if decisiveness >= 0.8:
        return "You know what you want quickly — accept after 2–3 turns if the recommendation clearly matches."
    if decisiveness >= 0.5:
        return "You like to explore a bit before committing — accept after 4–6 turns if satisfied."
    return "You need substantial exploration before feeling ready to commit — wait at least 8+ turns before accepting."
