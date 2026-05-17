import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSession } from "@/features/session/services/sessionService";
import { useSessionStore } from "@/store/sessionStore";
import { useClusterStore } from "@/store/clusterStore";
import { useUiStore } from "@/store/uiStore";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";
import type { SessionState } from "@/utils/types";

/**
 * Handlers for session lifecycle: init, reset.
 *
 * @returns Object with ``initSession`` mutation handler and its loading/error state.
 */
export function useSessionHandler() {
  const queryClient = useQueryClient();
  const { setSessionId, reset: resetSession } = useSessionStore();
  const { reset: resetCluster } = useClusterStore();
  const { reset: resetUi } = useUiStore();
  const { reset: resetClusterSnapshot } = useClusterSnapshotStore();

  const { mutate: initSession, isPending: isCreating, error: createError } = useMutation<
    SessionState,
    Error
  >({
    mutationFn: createSession,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      queryClient.setQueryData(["session", data.session_id], data);
    },
  });

  /**
   * Tear down the current session and bootstrap a new one.
   *
   * Clears all Zustand stores and the query cache, then calls initSession.
   */
  function restartSession() {
    resetSession();
    resetCluster();
    resetUi();
    resetClusterSnapshot();
    queryClient.clear();
    initSession();
  }

  return { initSession, restartSession, isCreating, createError };
}
