"""Bundle types for the /personas file store."""
from dataclasses import dataclass, field

from eval.types import OpSpec


@dataclass(frozen=True, slots=True)
class PersonaBundle:
    """A self-contained oracle bundle: persona dials + ground truth, stored as one YAML file.

    The bundle is the canonical source of truth. DB rows (personas + ground_truths)
    are derived from the file via ``eval.personas.store.upsert_bundle`` at run time.

    Attributes:
        slug:                Unique identifier used for both the persona and GT slug in the DB.
        verbosity:           Oracle reply-length dial (``"terse"`` | ``"medium"`` | ``"verbose"``).
        patience:            Oracle's willingness to continue after misbehaviour [0.0, 1.0].
        intent_description:  Natural-language goal statement shown to the oracle each turn.
        operations:          Ordered list of operations the oracle aims to elicit.
        prompt_hash:         SHA-256 hex of the builder prompt used (for audit/replay).
    """
    slug: str
    verbosity: str
    patience: float
    intent_description: str
    operations: list[OpSpec]
    prompt_hash: str

    def to_dict(self) -> dict:
        """Serialise to a plain dict suitable for ``yaml.safe_dump``.

        Returns:
            Dict representation with ``operations`` as a list of plain dicts.
        """
        ops = []
        for op in self.operations:
            entry: dict = {"op": op.op, "concept": op.concept}
            if op.kind is not None:
                entry["kind"] = op.kind
            if op.space is not None:
                entry["space"] = op.space
            ops.append(entry)
        return {
            "slug": self.slug,
            "verbosity": self.verbosity,
            "patience": self.patience,
            "intent_description": self.intent_description,
            "operations": ops,
            "prompt_hash": self.prompt_hash,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "PersonaBundle":
        """Deserialise from a plain dict (as returned by ``yaml.safe_load``).

        Args:
            data: Dict with the bundle fields.

        Returns:
            ``PersonaBundle`` instance.

        Raises:
            KeyError: If a required field is missing from ``data``.
        """
        ops = [
            OpSpec(
                op=entry["op"],
                concept=entry["concept"],
                kind=entry.get("kind"),
                space=entry.get("space"),
            )
            for entry in data["operations"]
        ]
        return cls(
            slug=data["slug"],
            verbosity=data["verbosity"],
            patience=float(data["patience"]),
            intent_description=data["intent_description"],
            operations=ops,
            prompt_hash=data["prompt_hash"],
        )
