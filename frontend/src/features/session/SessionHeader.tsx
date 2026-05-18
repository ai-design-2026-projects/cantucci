import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useSessionStore } from "@/store/sessionStore";
import { ThemeToggle } from "@/components/ThemeToggle";
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
 * Top navigation bar showing session progress and oracle type.
 *
 * @param turnCount - Current number of completed turns.
 * @param maxTurns - Session turn budget.
 * @param isTerminal - Whether the session has ended.
 * @param onRestart - Callback for starting a new session.
 * @returns Header bar with title, progress badge, oracle badge, and restart button.
 */
export function SessionHeader({
  turnCount,
  maxTurns,
  isTerminal,
  onRestart,
}: SessionHeaderProps) {
  const { oracleType } = useSessionStore();

  return (
    <header className="fixed top-0 left-0 right-0 z-40 flex items-center gap-3 px-6 h-[52px] bg-background/85 border-b border-border-subtle backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)]">
      <span className="font-display text-lg text-primary tracking-tight shrink-0">
        Cinepal
      </span>

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
        <ThemeToggle />
        <Button variant="ghost" size="sm" onClick={onRestart}>
          New Session
        </Button>
      </div>
    </header>
  );
}
