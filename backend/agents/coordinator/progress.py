import asyncio

_queues: dict[str, asyncio.Queue] = {}


def register_queue(conversation_id: str) -> asyncio.Queue:
    """Create and register an SSE queue for a conversation.

    Replaces any existing queue for the same conversation so stale
    connections from a previous page load don't accumulate.

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        A fresh asyncio.Queue the SSE stream should drain.
    """
    queue: asyncio.Queue = asyncio.Queue(maxsize=64)
    _queues[conversation_id] = queue
    return queue


def unregister_queue(conversation_id: str) -> None:
    """Remove the SSE queue for a conversation.

    No-op if no queue is registered.

    Args:
        conversation_id: Conversation UUID string.
    """
    _queues.pop(conversation_id, None)


def get_queue(conversation_id: str) -> asyncio.Queue | None:
    """Return the active queue for a conversation, or None if no subscriber.

    Args:
        conversation_id: Conversation UUID string.

    Returns:
        asyncio.Queue if a subscriber is listening, else None.
    """
    return _queues.get(conversation_id)


class ProgressReporter:
    """Publish step events to the conversation's SSE queue.

    Resolves the queue internally on each call; silently does nothing when
    no SSE subscriber is registered for the conversation.

    Args:
        conversation_id: Conversation UUID string.
    """

    def __init__(self, conversation_id: str) -> None:
        self._conversation_id = conversation_id

    def step(self, step_name: str) -> None:
        """Enqueue a step event. No-op when no subscriber is registered.

        Args:
            step_name: Stable step key (e.g. 'intent', 'clustering').
        """
        queue = get_queue(self._conversation_id)
        if queue is None:
            return
        try:
            queue.put_nowait({"type": "step", "step": step_name})
        except asyncio.QueueFull:
            pass

    def done(self) -> None:
        """Enqueue a turn_done terminal event. No-op when no subscriber is registered."""
        queue = get_queue(self._conversation_id)
        if queue is None:
            return
        try:
            queue.put_nowait({"type": "turn_done"})
        except asyncio.QueueFull:
            pass
