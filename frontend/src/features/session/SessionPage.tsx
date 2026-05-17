import { SessionHeader } from "./SessionHeader";
import { ConversationPanel } from "@/features/conversation/ConversationPanel";
import { FilmDetailDialog } from "@/features/clusters/FilmDetailDialog";
import { StopOverlay } from "./StopOverlay";
import { useFetchSession } from "./hooks/useFetchSession";
import { useSessionHandler } from "./hooks/useSessionHandler";
import { useSessionStore } from "@/store/sessionStore";

/**
 * Root page for an active session.
 *
 * Composes the header and conversation panel. Terminal state (converged/abandoned)
 * is surfaced via the StopOverlay in Phase 3; for now the Composer is gated.
 *
 * @returns The full session page layout.
 */
export function SessionPage() {
  const { sessionId } = useSessionStore();
  const { data: session } = useFetchSession(sessionId);
  const { restartSession } = useSessionHandler();

  const turnCount = session?.turns.length ?? 0;
  const maxTurns = session?.max_turns ?? 20;
  const isTerminal =
    session?.status === "converged" || session?.status === "abandoned";

  if (!sessionId) return null;

  return (
    <div className="flex flex-col min-h-dvh pt-[52px] bg-background">
      <SessionHeader
        turnCount={turnCount}
        maxTurns={maxTurns}
        isTerminal={isTerminal}
        onRestart={restartSession}
      />
      <div className="flex-1 flex flex-col max-w-2xl w-full mx-auto px-4">
        <ConversationPanel sessionId={sessionId} isTerminal={isTerminal} />
      </div>
      <FilmDetailDialog />
      <StopOverlay session={session} onRestart={restartSession} />
    </div>
  );
}
