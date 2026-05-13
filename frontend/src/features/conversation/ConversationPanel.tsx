import { useEffect, useRef } from "react";
import { Composer } from "./Composer";
import { MessageBubble } from "./MessageBubble";
import { useFetchTurns } from "./hooks/useFetchTurns";
import { useTurnHandler } from "./hooks/useTurnHandler";
import type { TurnResult } from "@/utils/types";
import styles from "./styles/Conversation.module.css";

interface ConversationPanelProps {
  /** Active session UUID. */
  sessionId: string;
  /** Whether this panel is collapsed into a side rail (post-convergence). */
  collapsed?: boolean;
}

/**
 * Main conversation area: message history and composer.
 *
 * Data comes from useFetchTurns; mutations go through useTurnHandler.
 * No business logic lives here — only composition of sub-components.
 *
 * @param sessionId - UUID of the active session.
 * @param collapsed - Reduces visual weight when the reveal panel takes focus.
 * @returns The full conversation panel.
 */
export function ConversationPanel({ sessionId, collapsed = false }: ConversationPanelProps) {
  const turns = useFetchTurns(sessionId);
  const { submitTurn, isPending } = useTurnHandler();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [turns.length]);

  function handleSubmit(message: string) {
    submitTurn({ sessionId, userMessage: message });
  }

  function handleChoose(choice: string) {
    submitTurn({ sessionId, userMessage: choice });
  }

  return (
    <div className={styles.conversationPanel} aria-label="Conversation">
      <div className={styles.messageList} role="log" aria-live="polite">
        {turns.length === 0 && !collapsed && (
          <div className={styles.emptyState}>
            <p className={styles.emptyStateTitle}>What do you want to watch?</p>
            <p className={styles.emptyStateSubtitle}>
              Describe a mood, a genre, a favourite director — anything. I will
              find the right cluster of films for you.
            </p>
          </div>
        )}

        {turns.map((turn: TurnResult, i: number) => (
          <MessageBubble
            key={turn.turn_id}
            turn={turn}
            isLast={i === turns.length - 1}
            onChoose={handleChoose}
          />
        ))}
        <div ref={bottomRef} />
      </div>

      {!collapsed && (
        <Composer isLoading={isPending} onSubmit={handleSubmit} />
      )}
    </div>
  );
}
