import { useMutation, useQueryClient } from "@tanstack/react-query";
import { postTurn } from "@/features/conversation/services/turnService";
import { useSessionStore } from "@/store/sessionStore";
import { useUiStore } from "@/store/uiStore";
import type { SessionState, TurnResult } from "@/utils/types";

interface PostTurnParams {
  /** Session id to post the turn to. */
  sessionId: string;
  /** Oracle's message text. */
  userMessage: string;
}

/**
 * Handler for submitting a new oracle turn.
 *
 * Optimistically appends a placeholder user bubble before the request
 * completes, then invalidates the session query on success.  On convergence,
 * triggers the reveal animation.
 *
 * @returns Object with ``submitTurn`` mutate function and loading/error state.
 */
export function useTurnHandler() {
  const queryClient = useQueryClient();
  const { incrementTurn } = useSessionStore();
  const { startReveal } = useUiStore();

  const { mutate: submitTurn, isPending, error } = useMutation<
    TurnResult,
    Error,
    PostTurnParams
  >({
    mutationFn: ({ sessionId, userMessage }) => postTurn(sessionId, userMessage),
    onMutate: async ({ sessionId, userMessage }) => {
      await queryClient.cancelQueries({ queryKey: ["session", sessionId] });

      const previous = queryClient.getQueryData<SessionState>(["session", sessionId]);
      if (previous) {
        const optimistic: TurnResult = {
          turn_id: `optimistic-${Date.now()}`,
          session_id: sessionId,
          turn_number: previous.turns.length + 1,
          user_message: userMessage,
          assistant_message: "",
          step_type: "show",
          converged: false,
          created_at: new Date().toISOString(),
          ambiguity_meta: null,
        };
        queryClient.setQueryData<SessionState>(["session", sessionId], {
          ...previous,
          turns: [...previous.turns, optimistic],
        });
      }
      return { previous };
    },
    onError: (_err, { sessionId }, context) => {
      const ctx = context as { previous?: SessionState } | undefined;
      if (ctx?.previous) {
        queryClient.setQueryData(["session", sessionId], ctx.previous);
      }
    },
    onSuccess: (result, { sessionId }) => {
      incrementTurn();
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      if (result.converged) {
        startReveal();
      }
    },
  });

  return { submitTurn, isPending, error };
}
