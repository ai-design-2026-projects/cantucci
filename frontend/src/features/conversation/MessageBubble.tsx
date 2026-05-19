import { motion } from "framer-motion";
import { StreamingText } from "@/components/StreamingText";
import { AmbiguityChoice } from "./AmbiguityChoice";
import { WaitingBubbleContent } from "./WaitingBubbleContent";
import { RecommendationMessage } from "./RecommendationMessage";
import { formatTimestamp } from "./utils/messageFormatters";
import type { TurnDto } from "@/utils/types";
import { cn } from "@/lib/utils";

interface MessageBubbleProps {
  /** The turn to render. */
  turn: TurnDto;
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
 * @param turn - TurnDto to render.
 * @param isLast - Whether this is the most recent turn.
 * @param onChoose - Callback for ambiguity choice selection.
 * @returns A div containing oracle and assistant message elements.
 */
export function MessageBubble({ turn, isLast, onChoose }: MessageBubbleProps) {
  const showChoices = isLast && turn.step_type === "ask" && turn.ambiguity_meta !== null;
  const isWaiting = isLast && !turn.assistant_message;
  const hasRecommendation = turn.recommendation !== null;
  const showAssistantBubble = Boolean(turn.assistant_message) || isWaiting;

  return (
    <div className="flex flex-col gap-2">
      <motion.div
        className="self-start max-w-[80%] bg-bg-elevated border border-border-subtle text-foreground rounded-lg rounded-bl-sm px-3.5 py-2.5 text-[0.9375rem] leading-[1.55]"
        initial={{ opacity: 0, x: -16 }}
        animate={{ opacity: 1, x: 0 }}
        transition={{ duration: 0.25 }}
      >
        <p className="whitespace-pre-wrap break-words">{turn.user_message}</p>
        <span className="block text-[0.6875rem] text-muted-foreground mt-1">
          {formatTimestamp(turn.created_at)}
        </span>
      </motion.div>

      {hasRecommendation && !isWaiting && (
        <div className="self-end w-full max-w-[92%]">
          <RecommendationMessage recommendation={turn.recommendation!} />
        </div>
      )}

      {!hasRecommendation && showAssistantBubble && (
        <motion.div
          className={cn(
            "self-end bg-bg-surface border border-border text-foreground rounded-lg rounded-br-sm px-3.5 py-2.5 text-[0.9375rem] leading-[1.55]",
            isWaiting
              ? "w-[min(80%,270px)] min-w-[280px] min-h-[70 px] flex flex-col justify-center"
              : "max-w-[80%] min-w-[280px]"
          )}
          initial={{ opacity: 0, x: 16 }}
          animate={{ opacity: 1, x: 0 }}
          transition={{ duration: 0.25, delay: 0.05 }}
        >
          {isWaiting ? (
            <WaitingBubbleContent />
          ) : (
            <>
              <StreamingText text={turn.assistant_message} className="whitespace-pre-wrap break-words" />
              <span className="block text-[0.6875rem] text-muted-foreground mt-1">
                {formatTimestamp(turn.created_at)}
              </span>
            </>
          )}
        </motion.div>
      )}

      {showChoices && (
        <AmbiguityChoice meta={turn.ambiguity_meta!} onChoose={onChoose} />
      )}
    </div>
  );
}
