import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSessionStore } from "@/store/sessionStore";
import { ClusterSnapshotSheet } from "@/features/clusters/ClusterSnapshotSheet";
import { formatOracleType, formatTurnLabel } from "./utils/sessionFormatters";

interface SessionHeaderProps {
  /** Total turns taken so far. */
  turnCount: number;
  /** Maximum allowed turns for this session. */
  maxTurns: number;
  /** Whether the session is in a terminal state (converged or abandoned). */
  isTerminal: boolean;
  /** Called when the user clicks "New Session". */
  onRestart: () => void;
}

/**
 * Secondary navigation bar showing session-specific progress and controls.
 *
 * Positioned below the AppShell header at top-[52px]. Contains turn progress,
 * oracle type, cluster snapshot sheet, and the new-session button.
 *
 * @param turnCount - Current number of completed turns.
 * @param maxTurns - Session turn budget.
 * @param isTerminal - Whether the session has ended.
 * @param onRestart - Callback for starting a new session.
 * @returns Session toolbar fixed below the app header.
 */
export function SessionHeader({
  turnCount,
  maxTurns,
  isTerminal,
  onRestart,
}: SessionHeaderProps) {
  const { oracleType } = useSessionStore();

  return (
    <header className="fixed top-[52px] left-0 right-0 z-40 flex items-center gap-3 px-6 h-[44px] bg-background/85 border-b border-border-subtle backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]">
      <div className="flex items-center gap-2">
        {isTerminal ? (
          <Badge variant="gold">Ended</Badge>
        ) : (
          <Badge variant="dim">
            {formatTurnLabel(turnCount)} / {maxTurns}
          </Badge>
        )}
        <Badge variant="secondary">{formatOracleType(oracleType)}</Badge>
      </div>

      <div className="ml-auto flex items-center gap-2">
        <ClusterSnapshotSheet />
        <Button variant="ghost" size="sm" onClick={onRestart}>
          New Session
        </Button>
      </div>
    </header>
  );
}
