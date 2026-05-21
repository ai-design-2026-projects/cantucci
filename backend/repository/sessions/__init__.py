"""Package-level convenience exports for the sessions repository.

This module re-exports the most commonly used functions from the
``reads``, ``sessions_write`` and ``turns_write`` helpers so callers can
import ``backend.repository.sessions`` and access a stable surface like
``backend.repository.sessions.create_session``.

Keep this file small and deterministic — do not run DB logic at import time.
"""

from .reads import (
	list_sessions_by_user,
	get_session_full,
)

from .sessions_write import (
	create_session,
	delete_session,
	mark_abandoned,
	mark_converged,
	update_preference_profile,
)

from .turns_write import (
	append_turn,
	update_turn,
	snapshot_clusters,
	write_feedback,
)

__all__ = [
	"list_sessions_by_user",
	"get_session_full",
	"create_session",
	"delete_session",
	"mark_abandoned",
	"mark_converged",
	"update_preference_profile",
	"append_turn",
	"update_turn",
	"snapshot_clusters",
	"write_feedback",
]
