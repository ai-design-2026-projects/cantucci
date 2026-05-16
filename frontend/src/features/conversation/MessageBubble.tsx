import { motion } from "framer-motion";
import { StreamingText } from "@/components/StreamingText";
import { AmbiguityChoice } from "./AmbiguityChoice";
import { WaitingBubbleContent } from "./WaitingBubbleContent";
import { formatTimestamp } from "./utils/messageFormatters";
import type { TurnResult } from "@/utils/types";
import styles from "./styles/Conversation.module.css";

interface MessageBubbleProps {
  /** The turn to render. */
  turn: TurnResult;
  /** Whether this is the last turn in the list (controls tail visibility). */
  isLast: boolean;
  /** Called when the oracle picks an ambiguity choice. */
  onChoose: (choice: string) => void;
}

/**
 * Renders one conversation turn as a pair of bubbles: oracle (left) then assistant (right).
 *
 * Oracle bubble slides in from the left; assistant from the right.
 * If the turn is an ask-type with ambiguity_meta, choice buttons appear below the assistant bubble.
 *
 * @param turn - TurnResult to render.
 * @param isLast - Whether this is the most recent turn.
 * @param onChoose - Callback for ambiguity choice selection.
 * @returns A div containing oracle and assistant message elements.
 */
export function MessageBubble({ turn, isLast, onChoose }: MessageBubbleProps) {
  const showChoices = isLast && turn.step_type === "ask" && turn.ambiguity_meta !== null;
  const isWaiting = isLast && !turn.assistant_message;
  const showAssistantBubble = Boolean(turn.assistant_message) || isWaiting;

  return (
    <div className={styles.turnGroup}>
      {/* Oracle bubble */}
      <motion.div
        className={`${styles.bubble} ${styles.oracle}`}
        initial={{ opacity: 0, x: -16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.25 }}
      >
        <p className={styles.bubbleText}>{turn.user_message}</p>
        <span className={styles.bubbleTime}>{formatTimestamp(turn.created_at)}</span>
      </motion.div>

      {/* Assistant bubble — shows the LLM-wait mask while assistant_message is empty
          on the latest turn, then swaps to the real reply once it arrives. */}
      {showAssistantBubble && (
        <motion.div
          className={`${styles.bubble} ${styles.assistant}`}
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25, delay: 0.05 }}
        >
          {isWaiting ? (
            <WaitingBubbleContent />
          ) : (
            <>
              <StreamingText text={turn.assistant_message} className={styles.bubbleText} />
              <span className={styles.bubbleTime}>{formatTimestamp(turn.created_at)}</span>
            </>
          )}
        </motion.div>
      )}

      {/* Ambiguity choice buttons */}
      {showChoices && (
        <AmbiguityChoice meta={turn.ambiguity_meta!} onChoose={onChoose} />
      )}
    </div>
  );
}
