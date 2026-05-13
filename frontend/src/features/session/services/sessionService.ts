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
 * @param sessionId - UUID of the session to retrieve.
 * @returns The SessionState with all turns in ascending order.
 */
export function fetchSession(sessionId: string): Promise<SessionState> {
  return get<SessionState>(`/sessions/${sessionId}`);
}
