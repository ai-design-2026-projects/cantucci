import { useMutation, useQueryClient } from "@tanstack/react-query";
import { streamTurn } from "@/features/conversation/services/turnService";
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
 * completes, then invalidates the session query on success. As the backend
 * NDJSON stream emits ``progress`` events, the active pipeline step is
 * mirrored onto ``useUiStore.currentStep`` so the wait-state UI can advance
 * in lockstep with real work instead of a hardcoded timer. On convergence,
 * triggers the reveal animation.
 *
 * @returns Object with ``submitTurn`` mutate function and loading/error state.
 */
export function useTurnHandler() {
  const queryClient = useQueryClient();
  const { incrementTurn } = useSessionStore();
  const { startReveal, setCurrentStep } = useUiStore();

  const { mutate: submitTurn, isPending, error } = useMutation<
    TurnResult,
    Error,
    PostTurnParams
  >({
    mutationFn: ({ sessionId, userMessage }) =>
      streamTurn(sessionId, userMessage, {
        onProgress: (event) => {
          // The end of a step is just a marker; we keep showing the step's
          // label until the next ``start`` arrives, so the UI never flashes
          // an empty state between steps.
          if (event.phase === "start") {
            setCurrentStep(event.step);
          }
        },
      }),
    onMutate: async ({ sessionId, userMessage }) => {
      await queryClient.cancelQueries({ queryKey: ["session", sessionId] });
      setCurrentStep(null);

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
      setCurrentStep(null);
    },
    onSuccess: (result, { sessionId }) => {
      incrementTurn();
      setCurrentStep(null);
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      if (result.converged) {
        startReveal();
      }
    },
  });

  return { submitTurn, isPending, error };
}
