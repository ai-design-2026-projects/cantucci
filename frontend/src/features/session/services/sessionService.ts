import { get, post } from "@/clients/apiClient";
import type { SessionState } from "@/utils/types";

/**
 * Create a new recommendation session on the backend.
 *
 * @returns The newly created SessionState with session_id.
 */
export function createSession(): Promise<SessionState> {
  return post<SessionState>("/sessions", {});
}

/**
 * Fetch full session state including all turns.
 *
 * Normalizes turn fields that the backend may omit when they haven't been
 * deployed yet (e.g. ``recommendation`` defaults to ``null``).
 *
 * @param sessionId - UUID of the session to retrieve.
 * @returns The SessionState with all turns in ascending order.
 */
export async function fetchSession(sessionId: string): Promise<SessionState> {
  const data = await get<SessionState>(`/sessions/${sessionId}`);
  return {
    ...data,
    turns: data.turns.map((turn) => ({
      ...turn,
      recommendation: turn.recommendation ?? null,
    })),
  };
}
