import { useFetchSession } from "@/features/session/hooks/useFetchSession";
import type { TurnResult } from "@/utils/types";

/**
 * Return the ordered turn list for the active session.
 *
 * Selects over the session query so turn data stays in the same cache entry
 * as the session state — no duplicated server state.
 *
 * @param sessionId - Active session UUID, or null to return an empty list.
 * @returns Array of TurnResult in ascending turn_number order.
 */
export function useFetchTurns(sessionId: string | null): TurnResult[] {
  const { data } = useFetchSession(sessionId);
  return (
    data?.turns.map((turn) => ({
      ...turn,
      recommendation: turn.recommendation ?? null,
    })) ?? []
  );
}
