import { useMutation, useQueryClient } from "@tanstack/react-query";
import { streamTurn } from "@/features/conversation/services/turnService";
import { useSessionStore } from "@/store/sessionStore";
import { useUiStore } from "@/store/uiStore";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";
import { useTurnFlightStore } from "@/store/turnFlightStore";
import type { SessionDto, TurnDto } from "@/utils/types";

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
  const { setCurrentStep } = useUiStore();
  const { setSnapshot, setRefining } = useClusterSnapshotStore();
  const { markStarted, markStep, markFinished } = useTurnFlightStore();

  const { mutate: submitTurn, isPending, error } = useMutation<
    TurnDto,
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
            markStep(sessionId, event.step);
          }
        },
        onClusters: (event) => {
          setSnapshot(event.clusters);
        },
      }),
    onMutate: async ({ sessionId, userMessage }) => {
      await queryClient.cancelQueries({ queryKey: ["session", sessionId] });
      setCurrentStep(null);
      markStarted(sessionId);

      const previous = queryClient.getQueryData<SessionDto>(["session", sessionId]);
      if (previous) {
        const optimistic: TurnDto = {
          turn_id: `optimistic-${Date.now()}`,
          session_id: sessionId,
          turn_number: previous.turns.length + 1,
          user_message: userMessage,
          assistant_message: "",
          step_type: "show",
          converged: false,
          created_at: new Date().toISOString(),
          ambiguity_meta: null,
          recommendation: null,
        };
        queryClient.setQueryData<SessionDto>(["session", sessionId], {
          ...previous,
          turns: [...previous.turns, optimistic],
        });
      }
      return { previous };
    },
    onError: (_err, { sessionId }, context) => {
      const ctx = context as { previous?: SessionDto } | undefined;
      if (ctx?.previous) {
        queryClient.setQueryData(["session", sessionId], ctx.previous);
      }
      setCurrentStep(null);
      markFinished(sessionId);
    },
    onSuccess: (_result, { sessionId }) => {
      incrementTurn();
      setCurrentStep(null);
      markFinished(sessionId);
      setRefining(false);
      queryClient.invalidateQueries({ queryKey: ["session", sessionId] });
      queryClient.invalidateQueries({ queryKey: ["sessions", "list"] });
    },
  });

  return { submitTurn, isPending, error };
}
