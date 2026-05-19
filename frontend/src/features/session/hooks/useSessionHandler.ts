import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { createSession } from "@/features/session/services/sessionService";
import { useSessionStore } from "@/store/sessionStore";
import { useClusterStore } from "@/store/clusterStore";
import { useUiStore } from "@/store/uiStore";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";
import type { SessionDto } from "@/utils/types";

/**
 * Handlers for session lifecycle: init, reset, and create-and-navigate.
 *
 * @returns Object with ``initSession`` and ``createAndNavigate`` handlers plus their loading/error state.
 */
export function useSessionHandler() {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const { sessionId, setSessionId, reset: resetSession } = useSessionStore();
  const { reset: resetCluster } = useClusterStore();
  const { reset: resetUi } = useUiStore();
  const { reset: resetClusterSnapshot } = useClusterSnapshotStore();

  const { mutate: initSession, isPending: isCreating, error: createError } = useMutation<
    SessionDto,
    Error
  >({
    mutationFn: createSession,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      queryClient.setQueryData(["session", data.session_id], data);
    },
  });

  const { mutate: createAndNavigate, isPending: isCreatingNav } = useMutation<
    SessionDto,
    Error
  >({
    mutationFn: createSession,
    onSuccess: (data) => {
      setSessionId(data.session_id);
      queryClient.setQueryData(["session", data.session_id], data);
      queryClient.invalidateQueries({ queryKey: ["sessions", "list"] });
      navigate(`/sessions/${data.session_id}`);
    },
  });

  /**
   * Tear down the current session state and bootstrap a new anonymous session.
   *
   * Used only for the anonymous (index route) flow. Clears session-specific
   * query data without wiping the sidebar's sessions-list cache.
   */
  function restartSession() {
    const oldId = sessionId;
    resetSession();
    resetCluster();
    resetUi();
    resetClusterSnapshot();
    if (oldId) {
      queryClient.removeQueries({ queryKey: ["session", oldId] });
    }
    initSession();
  }

  return { initSession, createAndNavigate, restartSession, isCreating: isCreating || isCreatingNav, createError };
}
