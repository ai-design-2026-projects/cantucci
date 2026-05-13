import { Badge } from "@/components/Badge";
import { Button } from "@/components/Button";
import { useSessionStore } from "@/store/sessionStore";
import { formatOracleType, formatTurnLabel } from "./utils/sessionFormatters";
import styles from "./styles/SessionPage.module.css";

interface SessionHeaderProps {
  /** Total turns taken so far. */
  turnCount: number;
  /** Maximum allowed turns for this session. */
  maxTurns: number;
  /** Whether the session has converged. */
  converged: boolean;
  /** Called when the user clicks "New Session". */
  onRestart: () => void;
}

/**
 * Top navigation bar showing session progress and oracle type.
 *
 * @param turnCount - Current number of completed turns.
 * @param maxTurns - Session turn budget.
 * @param converged - Whether the session has declared convergence.
 * @param onRestart - Callback for starting a new session.
 * @returns Header bar with title, progress badge, oracle badge, and restart button.
 */
export function SessionHeader({
  turnCount,
  maxTurns,
  converged,
  onRestart,
}: SessionHeaderProps) {
  const { oracleType } = useSessionStore();

  return (
    <header className={styles.header}>
      <span className={styles.wordmark}>Cinepal</span>

      <div className={styles.headerMeta}>
        {converged ? (
          <Badge variant="gold">Converged</Badge>
        ) : (
          <Badge variant="dim">
            {formatTurnLabel(turnCount)} / {maxTurns}
          </Badge>
        )}
        <Badge variant="default">{formatOracleType(oracleType)}</Badge>
      </div>

      <Button variant="ghost" onClick={onRestart} style={{ marginLeft: "auto" }}>
        New Session
      </Button>
    </header>
  );
}
