import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { useAuthStore } from "@/store/authStore";
import { useUiStore } from "@/store/uiStore";
import { ClusterSnapshotSheet } from "@/features/clusters/ClusterSnapshotSheet";
import { formatTurnLabel } from "./utils/sessionFormatters";
import { cn } from "@/lib/utils";

const SIDEBAR_WIDTH = 260;

interface SessionHeaderProps {
  /** Total turns taken so far. */
  turnCount: number;
  /** Maximum allowed turns for this session. */
  maxTurns: number;
  /** Whether the session is in a terminal state (converged or abandoned). */
  isTerminal: boolean;
  /**
   * Called when the user clicks "New Session". When undefined (authenticated
   * URL sessions), the button is hidden — the sidebar handles new session creation.
   */
  onRestart?: () => void;
}

/**
 * Secondary navigation bar showing session-specific progress and controls.
 *
 * Positioned below the AppShell header at top-[52px]. Shifts its left edge to
 * account for the sidebar when it is open and the user is authenticated.
 *
 * @param turnCount - Current number of completed turns.
 * @param maxTurns - Session turn budget.
 * @param isTerminal - Whether the session has ended.
 * @param onRestart - Optional callback for starting a new session (anonymous flow only).
 * @returns Session toolbar fixed below the app header.
 */
export function SessionHeader({
  turnCount,
  maxTurns,
  isTerminal,
  onRestart,
}: SessionHeaderProps) {
  const { status } = useAuthStore();
  const { sidebarOpen } = useUiStore();

  const isAuthenticated = status === "authenticated";
  const leftOffset = isAuthenticated && sidebarOpen ? SIDEBAR_WIDTH : 0;

  return (
    <header
      className={cn(
        "fixed top-[52px] right-0 z-40 flex items-center gap-3 px-6 h-[44px] bg-background/85 border-b border-border-subtle backdrop-blur-[12px] [-webkit-backdrop-filter:blur(12px)] transition-[left] duration-200"
      )}
      style={{ left: leftOffset }}
    >
      <div className="flex items-center gap-2">
        {isTerminal ? (
          <Badge variant="gold">Ended</Badge>
        ) : (
          <Badge variant="dim">
            {formatTurnLabel(turnCount)} / {maxTurns}
          </Badge>
        )}
      </div>

      <div className="ml-auto flex items-center gap-2">
        <ClusterSnapshotSheet />
        {onRestart && (
          <Button variant="ghost" size="sm" onClick={onRestart}>
            New Session
          </Button>
        )}
      </div>
    </header>
  );
}
