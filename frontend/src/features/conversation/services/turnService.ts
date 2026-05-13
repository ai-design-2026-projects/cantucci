import { post } from "@/clients/apiClient";
import type { TurnResult } from "@/utils/types";

/**
 * Submit one oracle turn and receive the assistant's response.
 *
 * @param sessionId - UUID of the active session.
 * @param userMessage - Oracle's message text.
 * @returns TurnResult with the assistant reply and metadata.
 */
export function postTurn(sessionId: string, userMessage: string): Promise<TurnResult> {
  return post<TurnResult>(`/sessions/${sessionId}/turns`, {
    user_message: userMessage,
  });
}
