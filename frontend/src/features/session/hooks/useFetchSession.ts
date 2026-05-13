import { useQuery } from "@tanstack/react-query";
import { fetchSession } from "@/features/session/services/sessionService";
import type { SessionState } from "@/utils/types";

/**
 * Fetch and subscribe to the current session state.
 *
 * @param sessionId - Active session UUID, or null to skip the query.
 * @returns TanStack Query result containing the SessionState.
 */
export function useFetchSession(sessionId: string | null) {
  return useQuery<SessionState, Error>({
    queryKey: ["session", sessionId],
    queryFn: () => fetchSession(sessionId!),
    enabled: sessionId !== null,
  });
}
