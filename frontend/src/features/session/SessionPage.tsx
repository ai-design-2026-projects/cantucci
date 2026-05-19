import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { SessionHeader } from "./SessionHeader";
import { ConversationPanel } from "@/features/conversation/ConversationPanel";
import { FilmDetailDialog } from "@/features/clusters/FilmDetailDialog";
import { StopOverlay } from "./StopOverlay";
import { useFetchSession } from "./hooks/useFetchSession";
import { useSessionHandler } from "./hooks/useSessionHandler";
import { useSessionStore } from "@/store/sessionStore";
import { useClusterStore } from "@/store/clusterStore";
import { useClusterSnapshotStore } from "@/store/clusterSnapshotStore";
import { useUiStore } from "@/store/uiStore";
import { hydrateClusterSnapshot } from "@/features/clusters/utils/hydrateSnapshot";

/**
 * Root page for an active session.
 *
 * Reads the session ID from the URL param (:sessionId) when rendered under
 * /sessions/:sessionId, or falls back to the Zustand store for the anonymous
 * landing session at /.
 *
 * @returns The full session page layout.
 */
export function SessionPage() {
  const { sessionId: urlSessionId } = useParams<{ sessionId: string }>();
  const { sessionId: storeSessionId, setSessionId } = useSessionStore();
  const { restartSession, createAndNavigate } = useSessionHandler();
  const { stopOverlayDismissed, reopenStopOverlay } = useUiStore();
  const { reset: resetCluster } = useClusterStore();
  const { reset: resetClusterSnapshot, setSnapshot, setRefining, setOpen: setSheetOpen } = useClusterSnapshotStore();

  const sessionId = urlSessionId ?? storeSessionId;

  useEffect(() => {
    if (urlSessionId && urlSessionId !== storeSessionId) {
      setSessionId(urlSessionId);
    }
  }, [urlSessionId, storeSessionId, setSessionId]);

  const { data: session } = useFetchSession(sessionId ?? null);

  useEffect(() => {
    if (!session) return;
    let cancelled = false;
    resetClusterSnapshot();
    resetCluster();
    setSheetOpen(false);
    hydrateClusterSnapshot(session.cluster_snapshot).then((hydrated) => {
      if (cancelled) return;
      setSnapshot(hydrated);
      setRefining(false);
    });
    return () => {
      cancelled = true;
    };
  }, [session?.session_id]);

  const turnCount = session?.turns.length ?? 0;
  const maxTurns = session?.max_turns ?? 20;
  const isTerminal =
    session?.status === "converged" || session?.status === "abandoned";
  const hasStopTurn = session?.turns.some((t) => t.step_type === "stop") ?? false;

  const isUrlSession = urlSessionId !== undefined;
  const onNewSession = isUrlSession
    ? () => createAndNavigate()
    : restartSession;

  if (!sessionId) return null;

  return (
    <div className="flex flex-col min-h-dvh pt-[96px] bg-background">
      <SessionHeader
        turnCount={turnCount}
        maxTurns={maxTurns}
        isTerminal={isTerminal}
        onRestart={isUrlSession ? undefined : restartSession}
      />
      <div className="flex-1 flex flex-col max-w-2xl w-full mx-auto px-4">
        <ConversationPanel sessionId={sessionId} isTerminal={isTerminal} />
      </div>
      <FilmDetailDialog />
      <StopOverlay session={session} onRestart={onNewSession} />
      {hasStopTurn && stopOverlayDismissed && (
        <div className="fixed bottom-6 right-6 z-40">
          <button
            type="button"
            onClick={reopenStopOverlay}
            className="bg-primary text-primary-foreground rounded-full px-4 py-2 text-sm font-medium shadow-lg hover:bg-primary/90 transition-colors"
          >
            See recommendations
          </button>
        </div>
      )}
    </div>
  );
}
