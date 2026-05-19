"""Oracle conversation memory — append-only role-tagged message list.

The Oracle LLM call receives the full conversation history on every turn,
structured as a native chat-completion message list from the Oracle's POV:

  - ``system``:    Persona traits + taste description + rules of engagement.
                   Set once at session start; never mutated.
  - ``user``:      What CinePal said to the oracle (the system's assistant_message),
                   possibly prefixed with a behavioural stage-direction.
  - ``assistant``: What the oracle replied in the previous turn.

The list always alternates ``user``/``assistant`` after the initial ``system``
message, matching the chat-completion protocol.  Stage directions are stored
verbatim so replay produces an identical LLM context window.
"""

import logging
from dataclasses import dataclass, field

log = logging.getLogger(__name__)


@dataclass
class OracleMemory:
    """Append-only role-tagged message list for the Oracle LLM.

    Always starts with exactly one ``system`` message followed by alternating
    ``user`` / ``assistant`` pairs.  Calling order must respect the protocol:
    ``set_system`` once, then for each turn ``append_user`` followed by
    ``append_assistant``.

    Attributes:
        _messages: Internal list; access via ``as_messages()``.
    """

    _messages: list[dict[str, str]] = field(default_factory=list)

    def set_system(self, content: str) -> None:
        """Set the system message.  Must be called exactly once before any turns.

        Args:
            content: Rendered system prompt (persona traits + taste description + rules).

        Raises:
            RuntimeError: If a system message has already been set.
        """
        if self._messages:
            raise RuntimeError("OracleMemory.set_system() must be called before any turns")
        self._messages.append({"role": "system", "content": content})
        log.debug("oracle memory: system message set (%d chars)", len(content))

    def append_user(self, content: str) -> None:
        """Append a user-role message (CinePal's reply to the oracle).

        Args:
            content: CinePal's ``assistant_message``, possibly prefixed with a
                     stage direction from ``BehaviorRng``.

        Raises:
            RuntimeError: If called before ``set_system`` or out of protocol order.
        """
        if not self._messages:
            raise RuntimeError("OracleMemory.set_system() must be called first")
        last_role = self._messages[-1]["role"]
        if last_role == "user":
            raise RuntimeError("Protocol violation: two consecutive user messages")
        self._messages.append({"role": "user", "content": content})

    def append_assistant(self, content: str) -> None:
        """Append an assistant-role message (the oracle's reply).

        Args:
            content: Raw oracle reply string returned by the LLM.

        Raises:
            RuntimeError: If not preceded by a user message.
        """
        if not self._messages or self._messages[-1]["role"] != "user":
            raise RuntimeError("Protocol violation: assistant message must follow a user message")
        self._messages.append({"role": "assistant", "content": content})

    def as_messages(self) -> list[dict[str, str]]:
        """Return a snapshot of the full message list.

        Returns:
            New list of ``{"role": ..., "content": ...}`` dicts.
        """
        return list(self._messages)

    @property
    def turn_count(self) -> int:
        """Number of completed oracle turns (each turn = one user + one assistant pair).

        Returns:
            Non-negative integer.
        """
        pairs = sum(1 for m in self._messages if m["role"] == "assistant")
        return pairs
