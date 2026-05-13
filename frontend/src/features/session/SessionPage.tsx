import { motion } from "framer-motion";
import { SessionHeader } from "./SessionHeader";
import { ConversationPanel } from "@/features/conversation/ConversationPanel";
import { RevealPanel } from "@/features/clusters/RevealPanel";
import { useFetchSession } from "./hooks/useFetchSession";
import { useSessionHandler } from "./hooks/useSessionHandler";
import { useSessionStore } from "@/store/sessionStore";
import { useUiStore } from "@/store/uiStore";
import styles from "./styles/SessionPage.module.css";

/**
 * Root page for an active session.
 *
 * Composes the header, conversation panel, and (post-convergence) reveal panel.
 * Contains zero business logic — all data and actions flow through hooks.
 *
 * @returns The full session page layout.
 */
export function SessionPage() {
  const { sessionId } = useSessionStore();
  const { isRevealPlaying } = useUiStore();
  const { data: session } = useFetchSession(sessionId);
  const { restartSession } = useSessionHandler();

  const turnCount = session?.turns.length ?? 0;
  const maxTurns = session?.max_turns ?? 20;
  const converged = session?.status === "converged";

  if (!sessionId) return null;

  return (
    <div className={styles.sessionPage}>
      <SessionHeader
        turnCount={turnCount}
        maxTurns={maxTurns}
        converged={converged}
        onRestart={restartSession}
      />

      {!converged ? (
        <div className={styles.dialogueView}>
          <ConversationPanel sessionId={sessionId} />
        </div>
      ) : (
        <div className={styles.splitView}>
          <motion.div
            className={styles.conversationRail}
            initial={{ opacity: 1 }}
            animate={{ opacity: isRevealPlaying ? 0.4 : 1, scale: isRevealPlaying ? 0.96 : 1 }}
            transition={{ duration: 0.5 }}
          >
            <ConversationPanel sessionId={sessionId} collapsed />
          </motion.div>

          <div className={styles.revealMain}>
            <RevealPanel turnCount={turnCount} />
          </div>
        </div>
      )}
    </div>
  );
}
