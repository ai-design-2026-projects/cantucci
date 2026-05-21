import hashlib
import json
from typing import Any


def hash_messages(messages: list[dict[str, Any]]) -> str:
    """Return an 8-character SHA-256 prefix of a serialized messages list.

    Used to identify prompt versions in LLM call logs for deduplication and
    replay. The hash is deterministic for a given message list.

    Args:
        messages: List of ``{"role": ..., "content": ...}`` dicts.

    Returns:
        8-char lowercase hex string.
    """
    serialized = json.dumps(messages, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(serialized.encode()).hexdigest()[:8]
