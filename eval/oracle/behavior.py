"""Seeded RNG for deterministic per-turn humanoid behavioral nudges.

``BehaviorRng`` wraps Python's ``random.Random`` seeded from a deterministic
hash of ``(persona_hash, gt_id, session_seed)``.  The same triple always
produces the same sequence of per-turn rolls, making conversational behavior
reproducible across reruns even though the LLM's output is stochastic.

The ``acceptance_gate_open`` predicate is deterministic without a random draw:
it computes the minimum turn index at which the persona would be willing to
accept based on ``decisiveness``, preventing over-eager early acceptance for
low-decisiveness personas.
"""

import hashlib
import logging
import random

log = logging.getLogger(__name__)


class BehaviorRng:
    """Deterministic per-turn behavioral RNG for an Oracle session.

    Attributes:
        _rng: Seeded ``random.Random`` instance.
    """

    def __init__(self, persona_hash: str, gt_id: str, session_seed: int) -> None:
        """Initialise the RNG from the session-identifying triple.

        Args:
            persona_hash:  SHA-256 8-char prefix from the persona YAML.
            gt_id:         Ground-truth slug (``GroundTruth.id``).
            session_seed:  Per-session integer seed from the eval run.
        """
        seed_bytes = f"{persona_hash}:{gt_id}:{session_seed}".encode()
        seed_int = int(hashlib.sha256(seed_bytes).hexdigest(), 16) % (2**32)
        self._rng = random.Random(seed_int)
        log.debug(
            "behavior rng seeded persona_hash=%s gt_id=%s session_seed=%d",
            persona_hash, gt_id, session_seed,
        )

    def should_drift(self, drift_probability: float) -> bool:
        """Return ``True`` if a tangent / digression should occur this turn.

        Consumes one random draw from the sequence.  Must be called in the
        same order every turn to preserve reproducibility.

        Args:
            drift_probability: Float in ``[0, 1]`` from ``PersonaDials``.

        Returns:
            ``True`` when the draw is below ``drift_probability``.
        """
        return self._rng.random() < drift_probability

    def should_contradict(self, contradiction_rate: float) -> bool:
        """Return ``True`` if a self-contradiction should occur this turn.

        Consumes one random draw from the sequence.

        Args:
            contradiction_rate: Float in ``[0, 1]`` from ``PersonaDials``.

        Returns:
            ``True`` when the draw is below ``contradiction_rate``.
        """
        return self._rng.random() < contradiction_rate

    @staticmethod
    def acceptance_gate_open(decisiveness: float, turn_n: int) -> bool:
        """Return ``True`` when the decisiveness dial allows acceptance at *turn_n*.

        Deterministic — no random draw.  The minimum turn index scales
        inversely with decisiveness:

        - ``decisiveness = 1.0`` → accepts from turn 1 onward.
        - ``decisiveness = 0.5`` → accepts from turn 5 onward.
        - ``decisiveness = 0.0`` → accepts from turn 10 onward.

        This gate is applied **after** the LLM expresses acceptance so that a
        low-decisiveness persona cannot accept within the first few turns even
        if the LLM judges the recommendation perfect.

        Args:
            decisiveness: Float in ``[0, 1]`` from ``PersonaDials``.
            turn_n:       1-based current turn index.

        Returns:
            ``True`` when the gate is open.
        """
        min_turn = max(1, round((1.0 - decisiveness) * 10))
        return turn_n >= min_turn
